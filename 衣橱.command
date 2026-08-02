#!/bin/zsh
# 双击这个文件即可打开衣橱（含 AI 搭配）。关闭窗口即停止。
cd "$(dirname "$0")"

cleanup() { kill $PROXY_PID $ADMIN_PID $HTTP_PID 2>/dev/null; exit 0 }
trap cleanup INT TERM

.venv/bin/python scripts/proxy.py >/tmp/wardrobe-proxy.log 2>&1 &
PROXY_PID=$!
.venv/bin/python scripts/admin_server.py >/tmp/wardrobe-admin.log 2>&1 &
ADMIN_PID=$!
python3 -m http.server 8642 >/tmp/wardrobe-http.log 2>&1 &
HTTP_PID=$!

sleep 2
open "http://localhost:8642"

echo ""
echo "  👗 衣橱已启动 → http://localhost:8642"
echo ""
echo "  管理台（上传照片 / 删除 / 重绘）→ http://127.0.0.1:8644"
echo ""
echo "  AI 搭配可直接使用（API Key 一栏留空即可）。"
echo "  用完关掉这个窗口就行。"
echo ""

wait $HTTP_PID
