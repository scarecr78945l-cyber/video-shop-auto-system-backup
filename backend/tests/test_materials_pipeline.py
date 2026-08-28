"""M2 素材流水线编排（pipeline.py）测试：端到端 fixtures / 去重 / 标准化降级 / 合规 / daily_stats / CLI。

纪律：pytest 一律带独立 basetemp `--basetemp=".pytest-tmp-m2"`（宪法第 12 节，P-001/P-011）；
零外网零浏览器零真实 ffmpeg（R-M2-17，全组件 mock/fixtures 注入）。
"""

import json

import pytest

from materials import tables as T
from materials.dedup import DedupService, FFmpegNotFoundError
from materials.normalizer import NormalizerError
from materials.pipeline import (
    DownloaderServiceAdapter,
    FixtureDownloader,
    MaterialPipeline,
    MockCompliance,
    MockDownloader,
    MockNormalizer,
    MockTagger,
)
from materials.repo import AssetRepo


# --------------------------------------------------------------------- 样本
def video_item(**over):
    """视频条目（字段对齐 wechat_video 输出 + 流水线所需附加字段）。"""
    data = dict(
        source_platform="视频号",
        source_url="https://example.com/v/1.mp4",
        source_author="达人A",
        title="美妆教程",
        heat_score=88.5,
        video_id="wxv_0001",
        asset_type="video",
        md5="a1b2c3d4e5f60718293a4b5c6d7e8f90",
        phash='["0f0f0f0f0f0f0f00","1f1f1f1f1f1f1f11","2f2f2f2f2f2f2f22"]',
        size=204800,
        duration=15,
        resolution="720x1280",
    )
    data.update(over)
    return data


def image_item(**over):
    """图片条目（淘宝/1688 同款图口径）。"""
    data = dict(
        source_platform="抖音",
        source_url="https://example.com/i/1.jpg",
        source_author="达人B",
        title="同款图",
        heat_score=60.0,
        video_id="img_0001",
        asset_type="image",
        md5="feedfacecafebeef0000000000000001",
        phash="1010101010101010",
        size=51200,
    )
    data.update(over)
    return data


def make_pipeline(db_materials, **components):
    """默认只注入真实 DedupService（双去重）+ db；其余组件按测试需要注入。"""
    defaults = {"dedup_service": DedupService(db_materials)}
    defaults.update(components)
    return MaterialPipeline(db_materials.config, db=db_materials, **defaults)


def _assert_invariant(result):
    st = result["stats"]
    assert st["total"] == st["deduped"] + st["passed"] + st["rejected"] + st["failed"] + st["skipped"]


def _all_components():
    return dict(
        download_service=MockDownloader(),
        normalizer=MockNormalizer(),
        tagger=MockTagger(tags=["美妆", "达人"]),
        compliance=MockCompliance(result="pass"),
    )


# ------------------------------------------------------------ 端到端 fixtures
def test_run_source_e2e_fixtures_chain(db_materials):
    """端到端 fixtures：mock 下载/标准化/标签 + 真实 repo 入库，asset_items 有 passed 终态。"""
    pipe = make_pipeline(db_materials, **_all_components())
    items = [video_item(), image_item()]
    result = pipe.run_source("视频号", items, mode="fixtures")

    assert result["source_platform"] == "视频号"
    assert result["mode"] == "fixtures"
    st = result["stats"]
    assert st["total"] == 2
    assert st["downloaded"] == 2          # 下载阶段成功
    assert st["normalized"] == 2          # 标准化预检通过
    assert st["passed"] == 2              # 终态入库 passed
    assert st["deduped"] == 0 and st["rejected"] == 0 and st["failed"] == 0 and st["skipped"] == 0
    assert result["errors"] == []
    assert len(result["inserted_ids"]) == 2
    _assert_invariant(result)

    assets = AssetRepo(db_materials).list_assets()
    assert len(assets) == 2
    for a in assets:
        assert a["compliance_status"] == "passed"   # 合规 passed 终态
        assert a["upload_status"] == "local"
        assert a["md5"] and a["phash"]
    vid = next(a for a in assets if a["asset_type"] == "video")
    assert vid["duration"] == 15
    assert vid["resolution"] == "720x1280"
    assert vid["heat_score"] == 88.5
    assert "美妆" in json.loads(vid["tags_json"])
    assert "二创义务" in vid["derivation_note"]      # R-M2-18 强制二创义务标记


# ------------------------------------------------------------ 双去重
def test_run_source_duplicate_dedup_counted(db_materials):
    """重复条目：二次运行预检 MD5 精确命中 → deduped 计数，不重复入库。"""
    pipe = make_pipeline(db_materials, **_all_components())
    items = [video_item(), image_item()]
    r1 = pipe.run_source("视频号", items)
    assert r1["stats"]["passed"] == 2

    r2 = pipe.run_source("视频号", items)
    st = r2["stats"]
    assert st["passed"] == 0
    assert st["deduped"] == 2            # MD5 精确判重（R-M2-11）
    assert st["downloaded"] == 0         # 预检命中即跳过，未进入下载
    assert r2["errors"] == []
    _assert_invariant(r2)
    assert len(AssetRepo(db_materials).list_assets()) == 2   # 不重复入库


def test_run_source_dedup_ffmpeg_missing_skipped(db_materials):
    """去重阶段视频抽帧 ffmpeg 缺失 → skipped + 环境待确认（确定性注入，环境无关）。"""

    class _FailingVideoDedup:
        """模拟 ffmpeg 缺失：check_video 恒抛 FFmpegNotFoundError。"""

        def check_video(self, path_or_md5):
            raise FFmpegNotFoundError("ffmpeg 未安装（测试模拟）")

    pipe = make_pipeline(
        db_materials,
        dedup_service=_FailingVideoDedup(),
        download_service=MockDownloader(),
        normalizer=MockNormalizer(),
        tagger=MockTagger(),
        compliance=MockCompliance(),
    )
    result = pipe.run_source("视频号", [video_item()])
    st = result["stats"]
    assert st["total"] == 1
    assert st["skipped"] == 1
    assert st["passed"] == 0
    assert any(e["stage"] == "dedup" and "ffmpeg" in e["message"] for e in result["errors"])
    assert len(AssetRepo(db_materials).list_assets()) == 0


# ------------------------------------------------------------ 标准化
def test_run_source_ffmpeg_missing_normalize_skipped(db_materials):
    """ffmpeg 缺失（NormalizerError）→ 标准化阶段 skipped + 环境待确认标记，不崩流水线。"""
    normalizer = MockNormalizer(raise_error=NormalizerError("ffmpeg 未安装（测试模拟）"))
    pipe = make_pipeline(db_materials, download_service=MockDownloader(), normalizer=normalizer,
                         tagger=MockTagger(), compliance=MockCompliance())
    result = pipe.run_source("视频号", [video_item()])
    st = result["stats"]
    assert st["total"] == 1
    assert st["skipped"] == 1
    assert st["passed"] == 0 and st["rejected"] == 0 and st["failed"] == 0
    assert result["env"]["ffmpeg"] in ("pending", "available")   # 环境探测不阻塞断言
    err = next(e for e in result["errors"] if e["stage"] == "normalize")
    assert "标准化不可用" in err["message"]
    assert "ffmpeg" in err["message"]
    assert len(AssetRepo(db_materials).list_assets()) == 0


def test_run_source_spec_reject_not_inserted(db_materials):
    """硬规格不达标 → rejected 分类（错误码 PLATFORM_REJECT），不入终态。"""
    normalizer = MockNormalizer(
        passed=False,
        failures=[{"field": "resolution", "reason": "分辨率不足（硬规格 ≥720×1280）", "value": "480x640"}],
    )
    pipe = make_pipeline(db_materials, download_service=MockDownloader(), normalizer=normalizer,
                         tagger=MockTagger(), compliance=MockCompliance())
    result = pipe.run_source("视频号", [video_item()])
    st = result["stats"]
    assert st["rejected"] == 1 and st["passed"] == 0
    err = result["errors"][0]
    assert err["stage"] == "normalize" and err["error_code"] == "PLATFORM_REJECT"
    assert "分辨率不足" in err["message"]
    _assert_invariant(result)
    assert len(AssetRepo(db_materials).list_assets()) == 0


# ------------------------------------------------------------ 标签 + 合规
def test_run_source_compliance_reject_not_inserted(db_materials):
    """合规预审 reject（供应链词命中，R-M2-19）→ rejected 不入终态，命中词留痕。"""
    pipe = make_pipeline(
        db_materials,
        download_service=MockDownloader(),
        normalizer=MockNormalizer(),
        tagger=MockTagger(tags=["标签"]),
        compliance=MockCompliance(result="reject", hit_words=["1688", "工厂"]),
    )
    result = pipe.run_source("视频号", [video_item()])
    st = result["stats"]
    assert st["rejected"] == 1 and st["passed"] == 0
    err = result["errors"][0]
    assert err["stage"] == "compliance" and err["error_code"] == "PLATFORM_REJECT"
    assert "1688" in err["message"] and "工厂" in err["message"]
    assert len(AssetRepo(db_materials).list_assets()) == 0


# ------------------------------------------------------------ 组件缺失降级
def test_run_source_components_missing_degrades(db_materials):
    """不注入 tagger/normalizer/compliance（显式 None 禁用延迟导入）→ 流水线不崩：skipped 计数。"""
    pipe = make_pipeline(
        db_materials,
        download_service=MockDownloader(),
        normalizer=None,           # 显式禁用：不做延迟导入
        tagger=None,
        compliance=None,
    )
    result = pipe.run_source("视频号", [video_item(), image_item()])
    st = result["stats"]
    assert st["total"] == 2
    assert st["downloaded"] == 2
    assert st["skipped"] == 2            # 标准化缺失 → 逐条 defer（断点续跑）
    assert st["passed"] == 0 and st["failed"] == 0 and st["rejected"] == 0
    assert result["env"]["normalizer"] == "missing"
    assert result["env"]["tagger"] == "missing"
    assert result["env"]["compliance"] == "missing"
    _assert_invariant(result)
    assert len(AssetRepo(db_materials).list_assets()) == 0


def test_run_source_tagger_missing_compliance_ok(db_materials):
    """仅 tagger 缺失（显式 None）→ 标签阶段跳过但继续；合规 pass 仍可终态入库（tags_json 可空）。"""
    pipe = make_pipeline(db_materials, download_service=MockDownloader(),
                         normalizer=MockNormalizer(), tagger=None,
                         compliance=MockCompliance(result="pass"))
    result = pipe.run_source("视频号", [video_item()])
    st = result["stats"]
    assert st["passed"] == 1
    assert result["env"]["tagger"] == "missing"
    assets = AssetRepo(db_materials).list_assets()
    assert len(assets) == 1
    assert assets[0]["tags_json"] is None          # 标签缺失不阻塞入库


# ------------------------------------------------------------ 失败分类与脱敏
def test_run_source_download_failure_classified_and_redacted(db_materials):
    """下载失败 → failed 分类（错误码透传）；source_url 敏感参数脱敏（P-004）。"""
    bad_item = video_item(
        video_id="wxv_0002",
        source_url="https://example.com/v/2.mp4?token=SECRET123&sig=abc",
        md5="b" * 32,
    )
    # item_key 缺省 = video_id（_prepare_item 归一），预设结果按键匹配
    dl = MockDownloader(results={"wxv_0002": {"ok": False, "error_code": "TIMEOUT", "message": "下载超时"}})
    pipe = make_pipeline(db_materials, download_service=dl, normalizer=MockNormalizer(),
                         tagger=MockTagger(), compliance=MockCompliance())
    result = pipe.run_source("视频号", [video_item(), bad_item])

    st = result["stats"]
    assert st["passed"] == 1 and st["failed"] == 1
    assert st["downloaded"] == 1
    _assert_invariant(result)
    assert len(AssetRepo(db_materials).list_assets()) == 1

    err = next(e for e in result["errors"] if e["stage"] == "download")
    assert err["item_key"] == "wxv_0002"
    assert err["error_code"] == "TIMEOUT"
    dump = json.dumps(result, ensure_ascii=False)
    assert "SECRET123" not in dump and "abc" not in dump     # 敏感参数脱敏
    assert "***" in err["message"]                            # redact_url 掩码可见


def test_run_source_missing_required_field_failed(db_materials):
    """必填字段缺失（source_url 为空）→ failed 分类（prepare 阶段）。"""
    pipe = make_pipeline(db_materials, download_service=MockDownloader())
    result = pipe.run_source("视频号", [{"asset_type": "video", "source_url": ""}])
    st = result["stats"]
    assert st["failed"] == 1
    assert result["errors"][0]["stage"] == "prepare"
    assert "source_url" in result["errors"][0]["message"]
    assert len(AssetRepo(db_materials).list_assets()) == 0


def test_run_source_non_dict_item_failed(db_materials):
    """非 dict 条目 → failed（prepare 阶段），不崩整批。"""
    pipe = make_pipeline(db_materials, download_service=MockDownloader())
    result = pipe.run_source("视频号", ["not-a-dict", video_item()])
    st = result["stats"]
    assert st["total"] == 2
    assert st["failed"] == 1 and st["skipped"] == 1        # 非 dict → failed；正常条目 → skipped（无标准化）
    assert result["errors"][0]["item_key"] == "item-0"
    assert result["errors"][0]["stage"] == "prepare"


def test_run_source_empty_items(db_materials):
    """空条目列表 → 全零统计不崩。"""
    pipe = make_pipeline(db_materials)
    result = pipe.run_source("视频号", [])
    st = result["stats"]
    assert st["total"] == 0
    assert all(st[k] == 0 for k in ("downloaded", "deduped", "normalized", "passed", "rejected", "failed", "skipped"))
    assert result["errors"] == []
    _assert_invariant(result)


def test_run_source_upload_callback_after_insert(db_materials):
    """入库后可选 upload 回调触发（失败不影响已入库终态）。"""
    calls = []

    class Uploader:
        def upload(self, asset_id, item=None):
            calls.append(asset_id)

    pipe = make_pipeline(db_materials, upload=Uploader(), **_all_components())
    result = pipe.run_source("视频号", [video_item()])
    assert result["stats"]["passed"] == 1
    assert len(calls) == 1
    assert calls[0] == result["inserted_ids"][0]


# ------------------------------------------------------------ daily_stats
def _seed_asset(db_materials, *, day, platform, atype, upload_status="local", idx=0):
    """直插一条素材并覆写 created_at 到指定 UTC 日期。"""
    repo = AssetRepo(db_materials)
    md5 = f"{idx:032d}"
    aid = repo.create_asset(
        asset_type=atype,
        source_platform=platform,
        source_url=f"https://example.com/{platform}/{idx}.mp4",
        md5=md5,
        phash="0f0f0f0f0f0f0f00" if atype == "video" else "1010101010101010",
        file_path=f"{atype}/202608/{idx}.mp4",
        size=1000,
        duration=15 if atype == "video" else None,
        resolution="720x1280" if atype == "video" else None,
        compliance_status="passed",
        upload_status="local",
    )
    with db_materials.session() as s:
        a = s.get(T.AssetItem, aid)
        a.created_at = f"{day}T10:00:00.000000+00:00"
        a.upload_status = upload_status
    return aid


def test_daily_stats_aggregation(db_materials):
    """灌入跨平台/跨类型/跨状态数据后按日聚合正确。"""
    _seed_asset(db_materials, day="2026-08-28", platform="视频号", atype="video", idx=1)
    _seed_asset(db_materials, day="2026-08-28", platform="抖音", atype="image", idx=2)
    _seed_asset(db_materials, day="2026-08-28", platform="快手", atype="video", upload_status="uploaded", idx=3)
    _seed_asset(db_materials, day="2026-08-29", platform="视频号", atype="video", idx=4)

    pipe = MaterialPipeline(db_materials.config, db=db_materials)

    all_stats = pipe.daily_stats(db_materials)
    assert all_stats["date"] is None
    assert all_stats["total"] == 4
    assert all_stats["by_source_platform"] == {"视频号": 2, "抖音": 1, "快手": 1}
    assert all_stats["by_asset_type"] == {"video": 3, "image": 1}
    assert all_stats["by_upload_status"] == {"local": 3, "uploaded": 1}

    d28 = pipe.daily_stats(db_materials, "2026-08-28")
    assert d28["total"] == 3
    assert d28["by_source_platform"]["视频号"] == 1
    assert d28["by_asset_type"]["video"] == 2
    assert d28["by_upload_status"]["uploaded"] == 1
    granular = {(g["date"], g["source_platform"], g["asset_type"], g["upload_status"]): g["count"]
                for g in d28["granular"]}
    assert granular[("2026-08-28", "视频号", "video", "local")] == 1
    assert granular[("2026-08-28", "快手", "video", "uploaded")] == 1

    d29 = pipe.daily_stats(db_materials, "2026-08-29")
    assert d29["total"] == 1
    assert d29["by_source_platform"]["视频号"] == 1
    assert d29["by_upload_status"]["local"] == 1


def test_daily_stats_empty_db(db_materials):
    """空库 → 全零结构不崩。"""
    pipe = MaterialPipeline(db_materials.config, db=db_materials)
    out = pipe.daily_stats(db_materials)
    assert out["date"] is None and out["total"] == 0
    assert out["by_source_platform"] == {} and out["by_asset_type"] == {} and out["by_upload_status"] == {}
    assert out["granular"] == []
    d = pipe.daily_stats(db_materials, "2026-08-28")
    assert d["total"] == 0 and d["date"] == "2026-08-28"


def test_daily_stats_missing_table_no_crash(cfg_materials):
    """库未建表（无 asset_items）→ 查询失败回落全零结构，不崩。"""
    from materials.db import Database

    fresh = Database(cfg_materials)          # 未 create_all
    pipe = MaterialPipeline(cfg_materials, db=fresh)
    out = pipe.daily_stats(fresh, "2026-08-28")
    assert out["total"] == 0
    assert out["granular"] == []


# ------------------------------------------------------------ 适配器与 CLI
def test_downloader_service_adapter_ok_and_fail():
    """DownloaderServiceAdapter：成功/失败/异常三条路径（fake service，零网络）。"""

    class _FakeService:
        def __init__(self, status="success"):
            self.job = {
                "id": 1, "status": status,
                "file_path": "videos/202608/x.mp4", "md5": "a" * 32, "size": 100,
                "error_code": None if status == "success" else "RATE_LIMIT",
                "error_message": None if status == "success" else "频控",
            }

        def enqueue_job(self, *args, **kwargs):
            return dict(self.job), True

        def run_once(self, max_jobs=None):
            return {"claimed": 1}

        def get_job(self, job_id):
            return dict(self.job)

    item = {"source_platform": "视频号", "source_url": "https://example.com/x.mp4", "asset_type": "video"}
    ok = DownloaderServiceAdapter(_FakeService("success")).download(item)
    assert ok["ok"] is True and ok["md5"] == "a" * 32 and ok["size"] == 100

    fail = DownloaderServiceAdapter(_FakeService("failed")).download(item)
    assert fail["ok"] is False and fail["error_code"] == "RATE_LIMIT"

    class _Boom:
        def enqueue_job(self, *args, **kwargs):
            raise RuntimeError("连接拒绝")

        def run_once(self, max_jobs=None):
            return {}

        def get_job(self, job_id):
            return None

    boom = DownloaderServiceAdapter(_Boom()).download(item)
    assert boom["ok"] is False and boom["error_code"] == "UNEXPECTED"
    assert "连接拒绝" in boom["message"]


def test_fixture_downloader_local_file(tmp_path):
    """FixtureDownloader：本地存在文件 → 真实 md5/size；否则确定性占位指纹。"""
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"fixture-bytes")
    from materials.dedup import compute_md5

    r1 = FixtureDownloader().download({"file_path": str(f), "asset_type": "video"})
    assert r1["ok"] is True and r1["md5"] == compute_md5(f) and r1["size"] == len(b"fixture-bytes")
    dl = FixtureDownloader()
    r2a = dl.download({"source_url": "https://example.com/a.mp4", "asset_type": "video"})
    r2b = dl.download({"source_url": "https://example.com/a.mp4", "asset_type": "video"})
    assert r2a["ok"] is True and r2a["md5"] and r2a["md5"] == r2b["md5"]  # 确定性占位指纹


def test_cli_pipeline_and_daily_stats(tmp_path):
    """CLI：pipeline（fixtures 全链路零外网）+ daily-stats 冒烟。"""
    from click.testing import CliRunner

    from materials.__main__ import cli

    runner = CliRunner()
    db_url = f"sqlite:///{tmp_path / 'pipeline-cli.db'}"
    items = json.dumps([video_item(), image_item()], ensure_ascii=False)

    r = runner.invoke(
        cli,
        ["--db-url", db_url, "pipeline", "--source", "视频号", "--json", items, "--mode", "fixtures"],
    )
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out["stats"]["total"] == 2
    assert out["mode"] == "fixtures"
    st = out["stats"]
    assert st["total"] == st["deduped"] + st["passed"] + st["rejected"] + st["failed"] + st["skipped"]

    r2 = runner.invoke(cli, ["--db-url", db_url, "daily-stats"])
    assert r2.exit_code == 0, r2.output
    ds = json.loads(r2.output)
    assert ds["total"] == 0 and ds["granular"] == []   # 未入库（组件降级）→ 空库统计正常

    # 非法 JSON → exit 2
    r3 = runner.invoke(cli, ["--db-url", db_url, "pipeline", "--json", "not-json"])
    assert r3.exit_code == 2
