# -*- coding: utf-8 -*-
"""T2 生成器：从 enum-registry.yaml 生成 60 enum 的 Alembic migration（round-51 R50-1 回修）。

- upgrade：按 registry entries 顺序 CREATE TYPE app.<name>
- downgrade：严格逆序 DROP TYPE
- 不生成 enum_error_code（60 保持）
- 确定性单输出：canonical 文件名 = f"{rev}_60_enums.py"（不含时间戳）；Create Date 固定常量；
  连续执行两次产物哈希不变，不产生第二个同 revision 文件。
- --check 模式：不写入，仅校验现有文件与应生成内容一致（缺失/漂移 → 失败）。

用法：
  python scripts/gen_enum_migration.py          # 生成/覆盖 canonical 文件（内容不一致时拒绝覆盖）
  python scripts/gen_enum_migration.py --check  # 只校验，不写入
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / ".." / "docs" / "contracts" / "enum-registry.yaml"
VERSIONS = ROOT / "migrations" / "versions"

REV = "60enum000000"          # 固定可读 revision id（T2）
DOWN = "32f34131a28a"         # baseline
CREATE_DATE = "2026-09-03T12:00:00+00:00"  # 固定常量，保证产物哈希稳定
CANONICAL_NAME = f"{REV}_60_enums.py"


def parse_entries(text):
    entries = []
    blocks = re.split(r"^\s+- name:", text, flags=re.M)[1:]
    for b in blocks:
        m = re.match(r"\s*(\w+)", b)
        if not m:
            continue
        name = m.group(1)
        vm = re.search(r"values: \[([^\]]*)\]", b)
        if not vm:
            continue
        raw = vm.group(1)
        values = []
        for part in raw.split(","):
            part = part.strip().strip('"\'')
            if part:
                values.append(part)
        entries.append((name, values))
    return entries


def build_content(entries):
    lines = []
    lines.append('"""T2: 60 enum migration (generated from enum-registry.yaml, round-51)')
    lines.append("")
    lines.append(f"Revision ID: {REV}")
    lines.append(f"Revises: {DOWN}")
    lines.append(f"Create Date: {CREATE_DATE}")
    lines.append('"""')
    lines.append("from typing import Sequence, Union")
    lines.append("")
    lines.append("from alembic import op")
    lines.append("import sqlalchemy as sa  # noqa: F401")
    lines.append("")
    lines.append("")
    lines.append("revision: str = %r" % REV)
    lines.append("down_revision: Union[str, Sequence[str], None] = %r" % DOWN)
    lines.append("branch_labels: Union[str, Sequence[str], None] = None")
    lines.append("depends_on: Union[str, Sequence[str], None] = None")
    lines.append("")
    lines.append("")
    lines.append("_ENUMS = [")
    for name, values in entries:
        lines.append("    (%r, %r)," % (name, values))
    lines.append("]")
    lines.append("")
    lines.append("")
    lines.append("def upgrade() -> None:")
    lines.append('    """按 registry 顺序创建 60 enum（app schema，search_path 已设）。"""')
    lines.append("    for name, values in _ENUMS:")
    lines.append("        labels = ', '.join(repr(v) for v in values)")
    lines.append("        op.execute(f'CREATE TYPE {name} AS ENUM ({labels})')")
    lines.append("")
    lines.append("")
    lines.append("def downgrade() -> None:")
    lines.append('    """严格逆序删除 60 enum。"""')
    lines.append("    for name, _ in reversed(_ENUMS):")
    lines.append("        op.execute(f'DROP TYPE {name}')")
    lines.append("")
    return "\n".join(lines) + "\n"


def main():
    check_only = "--check" in sys.argv
    text = REGISTRY.read_text(encoding="utf-8")
    entries = parse_entries(text)
    if len(entries) != 60:
        print(f"[FAIL] registry entries={len(entries)} != 60", file=sys.stderr)
        sys.exit(1)
    names = [n for n, _ in entries]
    if len(set(names)) != 60:
        print("[FAIL] duplicate enum names", file=sys.stderr)
        sys.exit(1)

    content = build_content(entries)
    out = VERSIONS / CANONICAL_NAME

    if out.exists():
        existing = out.read_text(encoding="utf-8")
        if existing == content:
            print(f"[OK] {CANONICAL_NAME} 与 registry 一致（无漂移）")
            return
        # 漂移：拒绝覆盖（除非 --check，一律失败）
        print(f"[FAIL] {CANONICAL_NAME} 内容与 registry 漂移；拒绝覆盖。请人工核对。", file=sys.stderr)
        sys.exit(1)

    if check_only:
        print(f"[FAIL] --check：{CANONICAL_NAME} 不存在", file=sys.stderr)
        sys.exit(1)

    out.write_text(content, encoding="utf-8")
    print(f"[OK] generated {out} ({len(entries)} enums)")


if __name__ == "__main__":
    main()
