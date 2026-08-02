#!/usr/bin/env python3
"""上传自拍 → 识别衣服 → 生成产品图 → 入库，全流程本地网页。

跑起来：
    .venv/bin/python scripts/import_server.py      # http://127.0.0.1:8644

浏览器打开后拖入照片即可。识别用 Kimi 视觉接口，生成用 agent-gw，
都在本机跑，密钥只在服务端读取，不进浏览器。
生成完会自动写入 items.js 并记录来源（供 wardrobe.py redraw 复用）。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import unicodedata
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wardrobe as wb  # noqa: E402

ROOT = wb.ROOT
PORT = 8644
PART_TO_CAT = {
    "upperbody": "TOPS",
    "wholebody_up": "DRESSES",
    "lowerbody": "BOTTOMS",
    "accessories_up": "TOPS",
    "shoes": "BOTTOMS",
}


def load_env() -> None:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        import os
        os.environ.setdefault(k.strip(), v.strip())


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "item"


def next_id() -> str:
    used = {i for i, _ in wb.entries()}
    n = 1
    while f"u{n:02d}" in used:
        n += 1
    return f"u{n:02d}"


def parse_upload(body: bytes, content_type: str) -> tuple[str, bytes]:
    """从 multipart/form-data 里取出单个文件字段（文件名, 内容）。"""
    m = re.search(r"boundary=(.+)$", content_type or "")
    if not m:
        raise RuntimeError("请求不是 multipart/form-data")
    sep = b"--" + m.group(1).strip('"').encode()
    for part in body.split(sep):
        head, _, data = part.partition(b"\r\n\r\n")
        if b'name="photo"' not in head:
            continue
        fn = re.search(rb'filename="([^"]*)"', head)
        return (fn.group(1).decode() or "upload.jpg" if fn else "upload.jpg",
                data.rsplit(b"\r\n", 1)[0])
    raise RuntimeError("没有收到照片")


def detect(photo: Path) -> list[dict]:
    proc = subprocess.run(
        [str(ROOT / ".venv/bin/python"), "scripts/kimi_ai.py", "detect", "--image", str(photo)],
        cwd=ROOT, text=True, capture_output=True, timeout=300,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "识别失败")
    raw = proc.stdout.strip()
    start = raw.find("{")
    if start < 0:
        raise RuntimeError(f"识别返回无法解析: {raw[:300]}")
    depth, end = 0, None
    for i, ch in enumerate(raw[start:], start):          # 大括号配平，避免贪婪匹配吃到尾部杂讯
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise RuntimeError(f"识别返回被截断: {raw[-300:]}")
    try:
        return json.loads(raw[start:end]).get("items", [])
    except ValueError as exc:
        raise RuntimeError(f"{exc}｜原文片段: {raw[start:end][:300]}") from exc


PAGE = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>上传自拍 · 衣橱</title><style>
:root{--ink:#111;--muted:#8b8b8b;--line:#e5e5e5;--cell:#efefef}
*{box-sizing:border-box}
body{margin:0;background:#fff;color:var(--ink);font:14px/1.6 "Helvetica Neue",Helvetica,Arial,
  -apple-system,"PingFang SC",sans-serif;padding:0 0 80px}
header{position:sticky;top:0;background:rgba(255,255,255,.95);backdrop-filter:blur(8px);
  border-bottom:1px solid var(--line);padding:20px 28px;z-index:5}
h1{margin:0;font-size:15px;letter-spacing:.22em;font-weight:700}
h1 span{font-weight:400;letter-spacing:.1em;color:#555;margin-left:8px}
main{max-width:920px;margin:0 auto;padding:28px}
#drop{border:1.5px dashed #ccc;padding:56px 20px;text-align:center;color:var(--muted);
  cursor:pointer;transition:.2s;letter-spacing:.04em}
#drop.hot{border-color:#111;color:#111;background:#fafafa}
#drop input{display:none}
.preview{display:flex;gap:20px;margin-top:24px;align-items:flex-start}
.preview img{width:200px;border:1px solid var(--line)}
button{padding:12px 22px;font-size:12.5px;letter-spacing:.16em;font-weight:700;text-transform:uppercase;
  cursor:pointer;border:1px solid #111;background:#111;color:#fff;font-family:inherit}
button.alt{background:#fff;color:#111}
button:disabled{opacity:.4;cursor:default}
.card{border:1px solid var(--line);padding:16px 18px;margin-top:14px;display:grid;
  grid-template-columns:26px 1fr;gap:14px;align-items:start}
.card.off{opacity:.45}
.card .row{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px}
.card label{font-size:11px;letter-spacing:.16em;color:#777;text-transform:uppercase;display:block}
.card input,.card select{padding:8px 10px;border:1px solid var(--line);font:inherit;font-size:13px;background:#fafafa}
.card input.wide{min-width:260px;flex:1}
.sw{display:inline-block;width:18px;height:18px;border-radius:50%;border:1px solid rgba(0,0,0,.1);
  vertical-align:-4px;margin-right:5px}
.status{margin-top:24px;font-size:13px;color:var(--muted);white-space:pre-line}
.done{border-left:3px solid #111;padding-left:14px;margin-top:10px;font-size:13px}
</style></head><body>
<header><h1>WARDROBE <span>上传自拍</span></h1></header>
<main>
  <div id="drop">拖入或点击选择一张照片<input type="file" id="file" accept="image/*"></div>
  <div id="stage"></div>
  <div class="status" id="status"></div>
</main>
<script>
const $ = s => document.querySelector(s);
const drop = $('#drop'), file = $('#file');
let photoPath = null, detected = [];

drop.onclick = () => file.click();
drop.ondragover = e => { e.preventDefault(); drop.classList.add('hot'); };
drop.ondragleave = () => drop.classList.remove('hot');
drop.ondrop = e => { e.preventDefault(); drop.classList.remove('hot');
  if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]); };
file.onchange = () => file.files[0] && upload(file.files[0]);

async function upload(f){
  $('#status').textContent = '上传并识别中…（约 20 秒）';
  $('#stage').innerHTML = '';
  const fd = new FormData(); fd.append('photo', f);
  const r = await fetch('/api/detect', {method:'POST', body:fd});
  const d = await r.json();
  if (!r.ok) { $('#status').textContent = '识别失败：' + d.error; return; }
  photoPath = d.photo; detected = d.items;
  $('#status').textContent = '';
  render(d.preview);
}

function render(preview){
  const cats = ['TOPS','JACKETS','BOTTOMS','DRESSES'];
  const seasons = ['四季','春夏','春秋','夏','秋冬','冬'];
  $('#stage').innerHTML = `
    <div class="preview"><img src="${preview}">
      <div><b>识别到 ${detected.length} 件</b><br>
      <span style="color:#8b8b8b">取消勾选可跳过；中文名和分类可以改。</span></div></div>
    ${detected.map((it,i)=>`
      <div class="card${it.pick?'':' off'}" id="c${i}">
        <input type="checkbox" ${it.pick?'checked':''} onchange="document.getElementById('c${i}').classList.toggle('off',!this.checked)">
        <div>
          <div><span class="sw" style="background:${it.color}"></span><b>${it.name}</b>
            <span style="color:#8b8b8b">· ${(it.tags||[]).join(' / ')}</span></div>
          <div class="row">
            <div><label>中文名</label><input id="cn${i}" value="${it.cn||''}" placeholder="例：米色宽松T恤"></div>
            <div><label>分类</label><select id="cat${i}">${cats.map(c=>
              `<option ${c===it.cat?'selected':''}>${c}</option>`).join('')}</select></div>
            <div><label>季节</label><select id="se${i}">${seasons.map(s=>
              `<option>${s}</option>`).join('')}</select></div>
          </div>
          <div class="row"><div style="flex:1"><label>备注</label>
            <input class="wide" id="nt${i}" value="${it.notes||''}"></div></div>
        </div>
      </div>`).join('')}
    <div style="margin-top:22px"><button onclick="run()" id="go">生成并入库</button></div>`;
}

async function run(){
  const go = $('#go'); go.disabled = true;
  const picks = detected.map((it,i)=>({i,it})).filter(({i})=>
    document.querySelector(`#c${i} input[type=checkbox]`).checked);
  if (!picks.length) { $('#status').textContent = '没有勾选任何单品。'; go.disabled=false; return; }
  let n = 0;
  for (const {i,it} of picks){
    n++;
    $('#status').textContent = `生成中 ${n}/${picks.length}：${it.name}…（每件约 1 分钟）`;
    const body = {photo: photoPath, item: it,
      cn: $('#cn'+i).value, cat: $('#cat'+i).value,
      season: $('#se'+i).value, notes: $('#nt'+i).value};
    const r = await fetch('/api/generate', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(body)});
    const d = await r.json();
    $('#status').insertAdjacentHTML('afterend', r.ok
      ? `<div class="done">✓ ${it.name} → ${d.id}　<code>${d.img}</code></div>`
      : `<div class="done">✕ ${it.name} 失败：${d.error}</div>`);
  }
  $('#status').textContent = `完成。刷新衣橱页面即可看到新单品；确认无误后 git push 就能上线。`;
  go.disabled = false;
}
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: dict) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def log_message(self, *a):  # 安静一点
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            return
        target = (ROOT / self.path.lstrip("/")).resolve()
        if target.is_file() and str(target).startswith(str(ROOT)):
            ctype = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                     "webp": "image/webp", "heic": "image/heic"}.get(target.suffix.lstrip(".").lower(),
                                                                     "application/octet-stream")
            self._send(200, target.read_bytes(), ctype)
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        try:
            if self.path == "/api/detect":
                self.handle_detect()
            elif self.path == "/api/generate":
                self.handle_generate()
            else:
                self._json(404, {"error": "unknown endpoint"})
        except Exception as exc:  # 任何失败都回给前端，别把服务打挂
            self._json(500, {"error": str(exc)})

    # ------------------------------------------------------------ endpoints

    def handle_detect(self):
        filename, content = parse_upload(
            self.rfile.read(int(self.headers["Content-Length"])),
            self.headers["Content-Type"],
        )
        selfie_dir = ROOT / "selfie"
        selfie_dir.mkdir(exist_ok=True)
        name = Path(filename).name
        dest = selfie_dir / name
        i = 1
        while dest.exists():
            dest = selfie_dir / f"{Path(name).stem}_{i}{Path(name).suffix}"
            i += 1
        dest.write_bytes(content)

        # HEIC 等格式转成 jpg 再送识别与生成
        ref = dest
        if dest.suffix.lower() in (".heic", ".heif"):
            ref = dest.with_suffix(".jpg")
            subprocess.run(["sips", "-s", "format", "jpeg", str(dest), "--out", str(ref)],
                           capture_output=True, check=True)

        items = detect(ref)
        for it in items:
            part = it.get("part", "")
            it["cat"] = PART_TO_CAT.get(part, "TOPS")
            it["cn"] = ""
            it["notes"] = " · ".join(it.get("tags") or [])
            # 配饰和鞋没有对应分类，默认不勾选（想要的话手动勾上）
            it["pick"] = part not in ("accessories_up", "shoes")
        self._json(200, {"photo": str(ref.relative_to(ROOT)),
                         "preview": "/" + str(ref.relative_to(ROOT)),
                         "items": items})

    def handle_generate(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        it = payload["item"]
        photo = payload["photo"]
        item_id = next_id()
        stem = f"{item_id}_{date.today().isoformat()}_{slugify(it['name'])}"

        tags = ", ".join(it.get("tags") or [])
        desc = f"{it['name']} worn by the person (this garment only)"
        if tags:
            desc += f", {tags}"
        wb.generate(stem, photo, desc)

        pal = [c for c in (it.get("color"), it.get("secondaryColor"), "#8b8b8b") if c][:3]
        entry = (
            f"  {{id:'{item_id}', img:'images/{stem}.webp', en:'{it['name'].upper()}', "
            f"cn:'{payload.get('cn') or it['name']}', cat:'{payload.get('cat', 'TOPS')}', "
            f"season:'{payload.get('season', '四季')}',\n"
            f"   pal:[{','.join(chr(39) + c + chr(39) for c in pal)}], "
            f"notes:'{payload.get('notes', '')}'}},"
        )
        wb.write_entries(wb.entries() + [(item_id, entry)])
        wb.save_source(item_id, photo, desc)
        self._json(200, {"id": item_id, "img": f"images/{stem}.webp"})


def main() -> int:
    load_env()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"上传入口已启动 → http://127.0.0.1:{PORT}\nCtrl-C 退出")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
