"""M3 主图/详情图管线 · 视觉策略规划（KimiImagePlanner）。

对齐方案文档 06 第二节与 context/README 外部契约（KIMI_API_KEY）：
- 主图 5 张 1:1 且不能全部相同；详情图 ≥3 张（最低门槛 1 主图 + 1 细节图可放行，标准 3+3）；
- Kimi 规划视觉策略（角度/背景/卖点焦点），无 KIMI_API_KEY 或调用失败/结构不符 →
  规则默认策略（source="rule_fallback"：白底 + 商品主体 + 卖点角标提示）；
- 主图 5 条 prompts 强制差异化（角度/背景/卖点焦点各不相同），从源头保障「5 张不全相同」；
- 所有提示词与策略文本过供应链词校验（optimization.compliance.check_supply_chain），
  1688/工厂/源头/厂家/一件代发/批发 零命中（对齐 10 文档第三节）；
- 类目记忆（CategoryMemory.image_strategy）可覆盖背景策略（拒审率高自动切换）；
- 密钥只读环境变量 KIMI_API_KEY（config.llm.kimi_env），不落库不落日志。
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any, Callable, Optional

from sourcing.compliance import sanitize_title

from ..compliance import check_supply_chain
from ..config import M3Config, load_config
from ..models import CategoryMemory, ImagePlan

KIMI_URL = "https://api.moonshot.cn/v1/chat/completions"
KIMI_MODEL = "moonshot-v1-8k"

PostFn = Callable[[str, dict[str, str], dict[str, Any], float], tuple[int, str]]

# 背景短语（对齐 memory 策略 background 键：white/scenario/gradient/lifestyle）
BACKGROUND_PHRASES: dict[str, str] = {
    "white": "纯白背景",
    "scenario": "家居生活场景背景（虚化）",
    "gradient": "浅灰到米白渐变背景",
    "lifestyle": "真实使用场景背景",
}

# 主图 5 张差异化模板（角度/背景/卖点焦点各不相同）
_MAIN_VARIANTS: list[dict[str, str]] = [
    {"angle": "正面平视视角", "bg_key": "white", "focus": "整体造型与主打卖点（{fact1}）"},
    {"angle": "微俯视 45° 视角", "bg_key": "gradient", "focus": "材质质感细节（{material}）"},
    {"angle": "侧 30° 视角", "bg_key": "white", "focus": "规格与尺寸信息（{size}）"},
    {"angle": "平视略仰视角", "bg_key": "scenario", "focus": "日常使用场景（{usage}）"},
    {"angle": "俯视 60° 视角", "bg_key": "white", "focus": "颜色与包装展示（{color_pack}）"},
]

# 详情图 ≥3 张（侧重细节/尺寸/场景）
_DETAIL_VARIANTS: list[dict[str, str]] = [
    {"focus": "材质细节特写：{material}，表面纹理与做工细节"},
    {"focus": "尺寸规格展示：{size}，比例标注视角"},
    {"focus": "使用场景：{usage}，融入真实生活"},
    {"focus": "包装与配件：{pack}（数量 {count}）"},
]

_USAGE_BY_CATEGORY: dict[str, str] = {
    "家居日用": "居家/办公日常使用",
    "宠物用品": "宠物日常玩耍场景",
}

_STRATEGY_TEXT: dict[str, str] = {
    "main": "白底为主、商品主体居中、卖点角标提示；5 张按 角度/背景/卖点焦点 差异化，避免全相同",
    "detail": "详情图 ≥3 张：侧重 细节特写 / 尺寸规格 / 使用场景",
}

KIMI_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "strategy": {"type": "string", "minLength": 2},
        "prompts": {"type": "array", "items": {"type": "string", "minLength": 5}},
    },
    "required": ["strategy", "prompts"],
}

_BRACKET_RE = re.compile(r"[【\[［][^】\]］]*[】\]］]")
_SPACE_RE = re.compile(r"\s+")
_SUPPLY_FRAGMENTS = ("直发", "直销")  # 「厂家直发」删「厂家」后的残留尾词
_FACT_KEYS = ("fact1", "material", "size", "color", "color_pack", "pack", "count", "usage")


def _default_post(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
) -> tuple[int, str]:
    """默认 HTTP 传输：标准库 urllib（避免第三方依赖）。"""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return int(resp.status), resp.read().decode("utf-8")


class KimiImagePlanner:
    """视觉策略规划：LLM 优先（Kimi），无 Key/失败 → 规则默认策略。"""

    def __init__(
        self,
        config: Optional[M3Config] = None,
        post: Optional[PostFn] = None,
        model: str = KIMI_MODEL,
    ):
        self.config: M3Config = config or load_config()
        self._post: PostFn = post or _default_post
        self.model = model
        self.last_error: str = ""  # 最近一次失败原因（不含密钥），供日志留痕

    @property
    def key_env(self) -> str:
        return self.config.llm.kimi_env

    def has_key(self) -> bool:
        return bool((os.environ.get(self.key_env) or "").strip())

    # ---------- 主入口 ----------

    def plan(
        self,
        product: dict[str, Any],
        image_type: str,
        memory: Optional[CategoryMemory | dict[str, Any]] = None,
    ) -> ImagePlan:
        """规划一个生图批次。image_type: main / detail。"""
        if image_type not in ("main", "detail"):
            raise ValueError(f"image_type 仅支持 main/detail，收到 {image_type!r}")
        if not self.has_key():
            self.last_error = "no_api_key"
            return self._fallback(product, image_type, memory)
        parsed = self._call_kimi(product, image_type)
        if parsed is None:
            return self._fallback(product, image_type, memory)
        plan = self._from_llm(parsed, product, image_type)
        if plan is None:
            return self._fallback(product, image_type, memory)
        return plan

    # ---------- LLM 路径 ----------

    def _call_kimi(self, product: dict[str, Any], image_type: str) -> Optional[dict[str, Any]]:
        """调用 Kimi 结构化输出；失败/结构不符返回 None（重试 max_retries+1 次）。"""
        user = self._user_prompt(product, image_type)
        schema_note = (
            "你必须只输出一个符合以下 JSON Schema 的 JSON 对象，不要输出任何额外文字：\n"
            + json.dumps(KIMI_SCHEMA, ensure_ascii=False)
        )
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": (
                    "你是电商商品主图/详情图视觉策略规划助手。基于用户提供的商品类目、"
                    "清洗后标题与 SKU 真实规格规划生图提示词；严禁出现供应链词"
                    "（1688/工厂/源头/厂家/一件代发/批发）、品牌词与广告禁用词"
                    "（同款/官方/旗舰店/代言/联名）。主图必须恰好 5 条且互不相同"
                    "（角度/背景/卖点焦点差异化）；详情图至少 3 条（侧重细节/尺寸/场景）。"
                ) + "\n" + schema_note},
                {"role": "user", "content": user},
            ],
            "max_tokens": 1200,
            "temperature": 0.7,
            "stream": False,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + (os.environ.get(self.key_env) or "").strip(),
        }
        last_error = ""
        for _ in range(self.config.llm.max_retries + 1):
            try:
                status, body = self._post(
                    KIMI_URL, headers, payload, self.config.llm.timeout_seconds
                )
            except Exception as exc:  # 网络/连接/超时：可恢复
                last_error = f"transport:{type(exc).__name__}"
                continue
            if status == 429 or status >= 500:  # 限流/服务端：可恢复
                last_error = f"http_{status}"
                continue
            if status != 200:
                last_error = f"http_{status}"
                continue
            try:
                data = json.loads(body)
                content = data["choices"][0]["message"]["content"].strip()
                if content.startswith("```"):
                    content = content.split("\n", 1)[-1] if "\n" in content else content[3:]
                    if content.endswith("```"):
                        content = content[:-3]
                parsed = json.loads(content)
            except Exception:
                last_error = "bad_response_json"
                continue
            if self._validate(parsed, image_type):
                self.last_error = ""
                return parsed
            last_error = "schema_mismatch"
        self.last_error = last_error
        return None

    def _validate(self, parsed: Any, image_type: str) -> bool:
        """结构校验 + 供应链词清洗 + 数量/差异化约束（主图 5 张不全相同）。"""
        if not isinstance(parsed, dict):
            return False
        if not isinstance(parsed.get("strategy"), str) or len(parsed["strategy"]) < 2:
            return False
        prompts = parsed.get("prompts")
        if not isinstance(prompts, list) or not prompts:
            return False
        clean = [self._sanitize_prompt(p) for p in prompts]
        if len(clean) != len(prompts) or not all(clean):
            return False
        if image_type == "main":
            if len(clean) != self.config.image.main_image_count:
                return False
            if len(set(clean)) != len(clean):  # 5 张 prompts 不全相同
                return False
        else:
            if len(clean) < self.config.image.detail_image_min:
                return False
        parsed["prompts"] = clean
        return True

    def _from_llm(
        self, parsed: dict[str, Any], product: dict[str, Any], image_type: str
    ) -> Optional[ImagePlan]:
        try:
            return ImagePlan(
                product_id=product["product_id"],
                image_type=image_type,
                strategy=self._sanitize_prompt(parsed["strategy"]),
                prompts=parsed["prompts"],
                source="llm",
            )
        except Exception:
            return None

    def _user_prompt(self, product: dict[str, Any], image_type: str) -> str:
        title = self._clean_title(product.get("taobao_original_title", ""))
        sku = json.dumps(product.get("sku_spec_json") or {}, ensure_ascii=False)
        kind = "主图（恰好 5 条，互不相同）" if image_type == "main" else "详情图（至少 3 条）"
        return (
            f"商品类目：{product.get('category', '')}\n"
            f"清洗后标题：{title}\n"
            f"SKU 规格：{sku}\n"
            f"规划类型：{kind}"
        )

    # ---------- 规则默认策略（source=rule_fallback） ----------

    def _fallback(
        self,
        product: dict[str, Any],
        image_type: str,
        memory: Optional[CategoryMemory | dict[str, Any]] = None,
    ) -> ImagePlan:
        strategy = self._memory_strategy(memory)
        title = self._clean_title(product.get("taobao_original_title", ""))
        facts = self._extract_facts(product)
        if image_type == "main":
            prompts = self._main_prompts(product, title, facts, strategy)
        else:
            prompts = self._detail_prompts(product, title, facts)
        return ImagePlan(
            product_id=product["product_id"],
            image_type=image_type,
            strategy=self._sanitize_prompt(_STRATEGY_TEXT[image_type]),
            prompts=prompts,
            source="rule_fallback",
        )

    def _memory_strategy(self, memory: Any) -> dict[str, Any]:
        if memory is None:
            return {}
        if isinstance(memory, CategoryMemory):
            return dict(memory.image_strategy or {})
        if isinstance(memory, dict):
            if "image_strategy" in memory:
                return dict(memory["image_strategy"] or {})
            return dict(memory)
        return {}

    def _main_prompts(
        self,
        product: dict[str, Any],
        title: str,
        facts: dict[str, str],
        strategy: dict[str, Any],
    ) -> list[str]:
        count = self.config.image.main_image_count
        override_bg = None
        bg = strategy.get("background")
        if bg in BACKGROUND_PHRASES and bg != "white":
            override_bg = bg  # 类目记忆：拒审率高切背景策略
        prompts: list[str] = []
        for i in range(count):
            v = _MAIN_VARIANTS[i % len(_MAIN_VARIANTS)]
            bg_phrase = (
                BACKGROUND_PHRASES[override_bg]
                if override_bg else BACKGROUND_PHRASES[v["bg_key"]]
            )
            focus = self._fill(v["focus"], facts)
            prompt = (
                f"电商商品主图：{product.get('category', '')}「{title}」，"
                f"商品主体居中，{bg_phrase}，{v['angle']}，突出{focus}，"
                f"画面干净高级，商品占比约 70%"
            )
            prompts.append(self._sanitize_prompt(prompt))
        return prompts

    def _detail_prompts(
        self, product: dict[str, Any], title: str, facts: dict[str, str]
    ) -> list[str]:
        count = max(3, self.config.image.detail_image_min)
        prompts: list[str] = []
        for i in range(count):
            v = _DETAIL_VARIANTS[i % len(_DETAIL_VARIANTS)]
            focus = self._fill(v["focus"], facts)
            prompt = (
                f"电商商品详情图：{product.get('category', '')}「{title}」，"
                f"{focus}，高清细节，纯色背景"
            )
            prompts.append(self._sanitize_prompt(prompt))
        return prompts

    # ---------- 文本工具（标题清洗 / SKU 事实 / 供应链词兜底） ----------

    def _clean_title(self, raw: str) -> str:
        t = _BRACKET_RE.sub(" ", raw or "")          # 去【】标签
        t = sanitize_title(t)                        # 复用 sourcing 机械清洗
        t = self._strip_supply(t)                    # 供应链词 + 残留尾词
        return t or "商品"

    def _extract_facts(self, product: dict[str, Any]) -> dict[str, str]:
        sku = product.get("sku_spec_json") or {}
        facts = {k: "" for k in _FACT_KEYS}

        def clean(s: Any) -> str:
            return self._strip_supply(str(s or ""))

        facts["material"] = clean(sku.get("材质", ""))
        facts["size"] = clean(sku.get("尺寸", "") or sku.get("容量", ""))
        color = sku.get("颜色", [])
        if isinstance(color, list):
            color = "、".join(str(c) for c in color)
        facts["color"] = clean(color)
        facts["pack"] = clean(sku.get("包装", ""))
        facts["count"] = clean(sku.get("数量", ""))
        facts["fact1"] = facts["size"] or facts["material"] or "商品卖点"
        facts["color_pack"] = "、".join(
            x for x in (facts["color"], facts["pack"]) if x
        ) or "商品细节"
        facts["usage"] = _USAGE_BY_CATEGORY.get(
            product.get("category", ""), "日常使用场景"
        )
        return facts

    def _fill(self, template: str, facts: dict[str, str]) -> str:
        out = template
        for k in _FACT_KEYS:
            out = out.replace("{" + k + "}", facts.get(k, ""))
        return out.strip(" ：,，。")

    def _strip_supply(self, text: str) -> str:
        """供应链词循环剥离（含 sourcing 词库 + 素材扩展 + 残留尾词），零命中为止。"""
        t = text or ""
        for _ in range(10):
            hits = check_supply_chain(t)
            if not hits:
                break
            for w in hits:
                t = t.replace(w, " ")
            t = _SPACE_RE.sub(" ", t).strip()
        for frag in _SUPPLY_FRAGMENTS:
            t = t.replace(frag, " ")
        return _SPACE_RE.sub(" ", t).strip(" -–—_|·：,，。")

    def _sanitize_prompt(self, text: str) -> str:
        """生图提示词清洗：供应链词兜底剥离；清空则返回空串（调用方判定无效）。"""
        t = self._strip_supply(text or "")
        if not t:
            return ""
        for _ in range(5):
            hits = check_supply_chain(t)
            if not hits:
                break
            for w in hits:
                t = t.replace(w, " ")
            t = _SPACE_RE.sub(" ", t).strip()
        return t.strip(" -–—_|·：,，。")
