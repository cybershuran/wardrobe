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

# 转 JPG 并把底色增益到纯白（255/242），multiply 下无缝融合
sips -s format jpeg -s formatOptions 88 "$TMP" --out "images/$NAME.jpg" >/dev/null
node --input-type=module -e "
import sharp from 'sharp';
const f = 'images/$NAME.jpg';
const buf = await sharp(f).linear(255/242, 0).jpeg({quality: 88}).toBuffer();
await sharp(buf).toFile(f);
console.log('saved', f);
" 2>/dev/null || echo "note: sharp unavailable, background not whitened (install sharp or run whiten manually)"
echo "done: images/$NAME.jpg — 记得在 items.js 的 ITEMS 里追加条目"
