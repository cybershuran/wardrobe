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
images/      产品图（透明底 WebP；页面用 drop-shadow 沿轮廓打影）
selfie/      日常照片输入（gitignore，不入库）
scripts/     AI 重绘管线
  kimi_ai.py    Kimi 桥接：generate 走 agent-gw（图像生成）；
                detect 走 Kimi Code 接口（视觉识别，OpenAI 兼容）
  generate.sh   生成一件衣服的产品图：generate.sh <名字> <参考照片> "<英文描述>"
  cutout.py     抠透明底：cutout.py <图片...> 或 --all
  proxy.py      本机 Kimi 代理（本地版 AI 搭配用，见下）
衣橱.command    双击即可本地启动（自动开代理 + 站点并打开浏览器）
.env          密钥（gitignore；模板见 .env.example）：
                KIMI_API_KEY / KIMI_BASE_URL —— agent-gw 图像生成
                KIMI_CODE_API_KEY / KIMI_CODE_BASE_URL —— Kimi Code 会员 Key，
                视觉识别与文本
.venv/        python venv，含 agent_gw SDK（gitignore）
```

## 添加新衣服的流程

1. 把日常照片放进 `selfie/`
2. 自动识别照片中的衣服：
   ```sh
   .venv/bin/python scripts/kimi_ai.py detect --image selfie/IMG_1234.jpg
   ```
3. 逐件生成产品图：
   ```sh
   scripts/generate.sh s18_red-coat selfie/IMG_1234.jpg \
     "red wool double-breasted coat worn by the person (coat only)"
   ```
4. 在 `items.js` 的 `ITEMS` 数组末尾追加条目（id/img/en/cn/cat/season/pal/notes）
5. `git add -A && git commit && git push`

## AI 搭配怎么用

两种都行，按你打开网站的方式自动切换默认值：

**线上版**（https://cybershuran.github.io/wardrobe/ ，手机电脑都行）
需要一个 [Kimi 开放平台](https://platform.moonshot.cn) 的 API Key（与会员的
Kimi Code Key 不是同一个，按量计费）。在 OUTFITS 页底部把 Key 填进第一栏，
填一次就记住了，只存在这台设备的浏览器里。地址与模型保持默认
（`https://api.moonshot.cn/v1` / `moonshot-v1-8k`）。
该接口自带 CORS 头，浏览器可直连，不需要任何代理。

**本地版**（用现有的 Kimi Code Key，不用另外申请）
双击项目里的 `衣橱.command`，浏览器会自动打开 http://localhost:8642 ，
AI 搭配直接可用、**API Key 一栏留空**（由 `scripts/proxy.py` 从 .env 注入，
浏览器不接触密钥）。用完关掉那个黑窗口即可。

> 为什么本地版要代理：Kimi Code 接口不返回 CORS 头，且其反滥用防护会拒绝
> 云端代理的请求（403 质询页），但本机直连正常。曾试过 Cloudflare Worker，
> 因此不可行，已弃用。

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
