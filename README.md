# Wardrobe · 衣橱

个人电子衣橱：极简画廊风格的静态网页 + AI 服装重绘管线。

日常照片放进 `selfie/`（已 gitignore，不入库），由 AI 识别照片里的衣服并重绘成
统一的白底产品图，进入可筛选的画廊。

## 使用

- 直接打开 `index.html`，或起任意静态服务器（如 `python3 -m http.server`）
- 分类浏览 / 单品详情（色板、笔记）/ 勾选单品保存 OUTFIT
- 可选 AI 搭配：OUTFITS 页底部填入 OpenAI 兼容接口的 Key

## 结构

```
index.html   页面与交互（不含数据）
items.js     衣橱数据 —— 每件单品一条记录，新增衣服改这里
images/      产品图（白底 JPG；页面用 mix-blend-mode:multiply 融进格子）
selfie/      日常照片输入（gitignore，不入库）
scripts/     AI 重绘管线
  kimi_ai.py    Kimi agent-gw 桥接（图像生成；vision 检测接口目前不可用）
  generate.sh   生成一件衣服的产品图：generate.sh <名字> <参考照片> "<英文描述>"
.env          KIMI_API_KEY（gitignore；模板见 .env.example）
.venv/        python venv，含 agent_gw SDK（gitignore）
```

## 添加新衣服的流程

1. 把日常照片放进 `selfie/`
2. 识别照片中的衣服（Kimi vision 接口当前超时不可用，由 Claude 直接看图代替）
3. 逐件生成产品图：
   ```sh
   scripts/generate.sh s18_red-coat selfie/IMG_1234.jpg \
     "red wool double-breasted coat worn by the person (coat only)"
   ```
4. 在 `items.js` 的 `ITEMS` 数组末尾追加条目（id/img/en/cn/cat/season/pal/notes）
5. `git add -A && git commit && git push`

## 设计要点

- 产品图统一为**透明底 WebP**（`scripts/cutout.py`，本地 rembg/U²-Net 抠图）：
  没有底图就没有"框中框"；页面用 CSS `drop-shadow` 沿衣服轮廓打柔影，
  白色衣服也能从浅灰格子中清晰分离。抠图顺带去掉了 Kimi 的"AI生成"水印。
- 生成管线：`generate.sh` 出图后自动抠图输出 `images/<名字>.webp`。
- 配饰（帽/鞋/腰带）暂无分类，未入库。

## 历史

- 本项目由两个原型合并而来：静态画廊（本体）+ Electronic Wardrobe 的
  Kimi 管线（`scripts/kimi_ai.py`）。后者的 Vite 服务器与上传审核 UI 已不再需要。
- 灵感来源：[tandpfun/wardrobe](https://github.com/tandpfun/wardrobe) 与
  [wardrobe-vibe](https://wingchunsiu.github.io/wardrobe-vibe/)
