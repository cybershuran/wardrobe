#!/usr/bin/env python3
"""把产品图抠成透明底 WebP。

用法:
  .venv/bin/python scripts/cutout.py images/xxx.jpg [more.jpg ...]
  .venv/bin/python scripts/cutout.py --all   # 处理 items.js 里引用的所有 .jpg

输出与源文件同目录同名，扩展名 .webp（透明底）。
首次运行会下载 u2net 模型（~170MB）到 ~/.u2net。
"""
import io
import re
import sys
from pathlib import Path

from PIL import Image
from rembg import new_session, remove

ROOT = Path(__file__).resolve().parent.parent


def targets_from_items() -> list[Path]:
    text = (ROOT / "items.js").read_text(encoding="utf-8")
    return [ROOT / m for m in re.findall(r"img:'(images/[^']+\.jpg)'", text)]


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1
    paths = targets_from_items() if args == ["--all"] else [Path(p) for p in args]

    session = new_session("u2net")
    for src in paths:
        if not src.is_file():
            print(f"skip (missing): {src}")
            continue
        out = src.with_suffix(".webp")
        img = Image.open(src).convert("RGB")
        cut = remove(img, session=session, post_process_mask=True)
        cut.save(out, "WEBP", quality=90)
        print(f"cut: {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
