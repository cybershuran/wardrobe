#!/usr/bin/env python3
"""衣橱管理：增删改单品，直接读写 items.js。

用法:
  .venv/bin/python scripts/wardrobe.py list [关键词]
  .venv/bin/python scripts/wardrobe.py remove <id> [--keep-image]
  .venv/bin/python scripts/wardrobe.py redraw <id> [--ref 照片] [--desc "英文描述"]
  .venv/bin/python scripts/wardrobe.py add <id> --img images/x.webp --en NAME --cn 名字 \
      --cat TOPS [--season 四季] [--pal '#aaa,#bbb,#ccc'] [--notes 备注]

redraw 会用新图覆盖原条目的图片，条目本身（名称/分类/备注）保持不变。
不带 --ref 时沿用 .sources.json 里记录的原始照片与描述。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ITEMS_JS = ROOT / "items.js"
SOURCES = ROOT / ".sources.json"          # id -> {ref, desc}，供 redraw 复用
ENTRY_RE = re.compile(r"^\s*\{id:'(?P<id>[^']*)'.*?\},\s*$", re.S | re.M)


# ---------------------------------------------------------------- items.js

def read_items() -> str:
    return ITEMS_JS.read_text(encoding="utf-8")


def entries(text: str | None = None) -> list[tuple[str, str]]:
    """返回 [(id, 该条目的完整文本), ...]，按文件顺序。"""
    text = read_items() if text is None else text
    body = text.split("const ITEMS = [", 1)[1].split("\n];", 1)[0]
    out, cur, cur_id = [], [], None
    for line in body.splitlines():
        m = re.match(r"\s*\{id:'([^']*)'", line)
        if m:
            if cur_id is not None:
                out.append((cur_id, "\n".join(cur)))
            cur, cur_id = [line], m.group(1)
        elif cur_id is not None:
            cur.append(line)
    if cur_id is not None:
        out.append((cur_id, "\n".join(cur)))
    return out


def field(entry: str, name: str) -> str | None:
    m = re.search(rf"{name}:'([^']*)'", entry)
    return m.group(1) if m else None


def write_entries(items: list[tuple[str, str]]) -> None:
    text = read_items()
    head, rest = text.split("const ITEMS = [", 1)
    _, tail = rest.split("\n];", 1)
    body = "\n".join(e for _, e in items)
    ITEMS_JS.write_text(f"{head}const ITEMS = [\n{body}\n];{tail}", encoding="utf-8")


def load_sources() -> dict:
    return json.loads(SOURCES.read_text(encoding="utf-8")) if SOURCES.is_file() else {}


def save_source(item_id: str, ref: str, desc: str) -> None:
    data = load_sources()
    data[item_id] = {"ref": ref, "desc": desc}
    SOURCES.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------- 图片生成

def generate(name: str, ref: str, desc: str) -> Path:
    """跑 generate.sh，返回生成的 webp 路径。"""
    proc = subprocess.run(
        [str(ROOT / "scripts" / "generate.sh"), name, ref, desc],
        cwd=ROOT, text=True, capture_output=True,
    )
    out = ROOT / "images" / f"{name}.webp"
    if proc.returncode != 0 or not out.is_file():
        sys.stderr.write(proc.stdout + proc.stderr)
        raise SystemExit(f"生成失败: {name}")
    return out


# ---------------------------------------------------------------- 命令

def cmd_list(args) -> int:
    kw = (args.keyword or "").lower()
    for item_id, entry in entries():
        line = f"{item_id:<6} {field(entry,'cat'):<8} {field(entry,'cn') or '':<16} {field(entry,'img')}"
        if not kw or kw in line.lower():
            print(line)
    return 0


def cmd_remove(args) -> int:
    items = entries()
    hit = [(i, e) for i, e in items if i == args.id]
    if not hit:
        raise SystemExit(f"没有 id 为 {args.id} 的单品（先用 list 查看）")
    img = ROOT / (field(hit[0][1], "img") or "")
    write_entries([(i, e) for i, e in items if i != args.id])
    if not args.keep_image and img.is_file():
        img.unlink()
        print(f"已删除图片 {img.relative_to(ROOT)}")
    print(f"已从衣橱移除 {args.id}")
    return 0


def cmd_redraw(args) -> int:
    items = entries()
    hit = next((e for i, e in items if i == args.id), None)
    if hit is None:
        raise SystemExit(f"没有 id 为 {args.id} 的单品（先用 list 查看）")

    src = load_sources().get(args.id, {})
    ref = args.ref or src.get("ref")
    desc = args.desc or src.get("desc")
    if not ref or not desc:
        raise SystemExit(
            f"缺少参考照片或描述：{args.id} 没有记录来源，请补上 --ref 和 --desc"
        )
    if not (ROOT / ref).is_file() and not Path(ref).is_file():
        raise SystemExit(f"参考照片不存在: {ref}")

    name = Path(field(hit, "img") or "").stem or args.id
    print(f"重绘 {args.id} ← {ref}\n描述: {desc}")
    generate(name, ref, desc)
    save_source(args.id, ref, desc)
    print(f"完成: images/{name}.webp（条目未变，刷新页面即可看到新图）")
    return 0


def cmd_add(args) -> int:
    items = entries()
    if any(i == args.id for i, _ in items):
        raise SystemExit(f"id {args.id} 已存在")
    pal = [c.strip() for c in (args.pal or "#cccccc,#aaaaaa,#888888").split(",")]
    entry = (
        f"  {{id:'{args.id}', img:'{args.img}', en:'{args.en}', cn:'{args.cn}', "
        f"cat:'{args.cat}', season:'{args.season}',\n"
        f"   pal:[{','.join(repr(c).replace(chr(39), chr(39)) for c in pal)}], "
        f"notes:'{args.notes}'}},"
    )
    write_entries(items + [(args.id, entry)])
    print(f"已加入 {args.id}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("list", help="列出所有单品")
    s.add_argument("keyword", nargs="?", help="按关键词过滤")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("remove", help="删除单品")
    s.add_argument("id")
    s.add_argument("--keep-image", action="store_true", help="只从列表移除，保留图片文件")
    s.set_defaults(func=cmd_remove)

    s = sub.add_parser("redraw", help="重新生成某件衣服的图片")
    s.add_argument("id")
    s.add_argument("--ref", help="参考照片路径（默认沿用上次的）")
    s.add_argument("--desc", help="英文描述（默认沿用上次的）")
    s.set_defaults(func=cmd_redraw)

    s = sub.add_parser("add", help="追加单品条目")
    s.add_argument("id")
    s.add_argument("--img", required=True)
    s.add_argument("--en", required=True)
    s.add_argument("--cn", required=True)
    s.add_argument("--cat", required=True)
    s.add_argument("--season", default="四季")
    s.add_argument("--pal")
    s.add_argument("--notes", default="")
    s.set_defaults(func=cmd_add)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
