#!/bin/zsh
# 生成单件衣服的白底产品图并放入 images/。
#
# 用法:
#   scripts/generate.sh <输出名(不带扩展名)> <参考照片路径> "<英文衣服描述>"
# 例:
#   scripts/generate.sh s18_red-coat selfie/IMG_1234.jpg "red wool double-breasted coat worn by the person (coat only)"
#
# 生成后底色会被推成纯白（网站靠 mix-blend-mode:multiply 融合格子底色）。
set -e
ROOT="${0:A:h:h}"
NAME="$1"; REF="$2"; DESC="$3"
[ -z "$DESC" ] && { echo "usage: generate.sh <name> <reference> <description>"; exit 1; }

cd "$ROOT"
set -a; source .env; set +a

PROMPT="E-commerce product photography of ONLY the $DESC. Recreate the exact same garment from the reference photo faithfully, matching its color, fabric texture and details. Display the garment alone, floating ghost-mannequin style, front view, neatly presented, centered, on a clean pure white studio background. Soft even lighting, minimal aesthetic. No person, no mannequin, no other clothing items, no text or watermarks."

TMP="$(mktemp -d)/out.png"
for attempt in 1 2 3; do
  if .venv/bin/python scripts/kimi_ai.py generate \
      --prompt "$PROMPT" --reference "$REF" \
      --ratio 2:3 --resolution 1K --background opaque \
      --output "$TMP"; then
    break
  fi
  echo "attempt $attempt failed, retrying..."; sleep 20
done
[ -f "$TMP" ] || { echo "generation failed"; exit 1; }

# 抠成透明底 WebP（网站用 drop-shadow 沿轮廓打影，无需底图）
cp "$TMP" "images/$NAME.png"
.venv/bin/python scripts/cutout.py "images/$NAME.png"
rm -f "images/$NAME.png"
echo "done: images/$NAME.webp — 记得在 items.js 的 ITEMS 里追加条目"
