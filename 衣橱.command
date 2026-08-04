#!/bin/zsh
# 双击这个文件即可打开衣橱（含管理台与 AI 搭配）。关闭窗口即停止。
cd "$(dirname "$0")"

URL="http://127.0.0.1:8642"
PORT=8642

# 健康检查：只认「自己人」—— 响应里带 "service":"wardrobe" 才算衣橱在运行。
# 端口被别的程序（或没退干净的旧进程）占着时，旧逻辑会把死服务当成「已在运行」。
is_wardrobe_running() {
  curl -sf -m 2 "$URL/api/health" 2>/dev/null | grep -q '"service": *"wardrobe"'
}

# 已经在跑就直接打开浏览器 —— 重复双击不会报端口占用
if is_wardrobe_running; then
  open "$URL"
  echo "  👗 衣橱已经在运行 → $URL（管理台 $URL/admin）"
  echo "  这个窗口可以直接关掉；想停止服务，去关掉最早那个启动窗口。"
  exit 0
fi

# 端口被占但不是健康的衣橱：多半是上次没退干净的自家进程，自动清理后重启；
# 是陌生程序则停下来明示，不擅自杀别人的进程。
STALE_PID=$(lsof -nP -ti :$PORT 2>/dev/null | head -1)
if [[ -n "$STALE_PID" ]]; then
  STALE_CMD=$(ps -p "$STALE_PID" -o command= 2>/dev/null)
  if [[ "$STALE_CMD" == *"serve.py"* || "$STALE_CMD" == *"http.server"* ]]; then
    echo "  🧹 清理上次没退干净的衣橱进程（pid $STALE_PID）…"
    kill "$STALE_PID" 2>/dev/null
    sleep 0.5
  else
    echo "  ⚠️  端口 $PORT 被其他程序占用：$STALE_CMD"
    echo "     请先退出它，再双击本文件。"
    exit 1
  fi
fi

cleanup() { kill $SRV_PID 2>/dev/null; exit 0 }
trap cleanup INT TERM

.venv/bin/python scripts/serve.py &
SRV_PID=$!

# 等服务就绪再开浏览器（最多 10 秒）；进程提前退出说明启动失败，把原因留在窗口里
READY=0
for i in {1..50}; do
  if is_wardrobe_running; then READY=1; break; fi
  kill -0 $SRV_PID 2>/dev/null || break
  sleep 0.2
done

if [[ "$READY" != "1" ]]; then
  echo ""
  echo "  ⚠️  衣橱没能启动。上面应该有具体原因；常见的是 .venv 缺失，"
  echo "     可执行  python3 -m venv .venv  后重试。"
  wait $SRV_PID 2>/dev/null
  exit 1
fi

open "$URL"

echo ""
echo "  👗 衣橱已启动 → $URL"
echo "     管理台（上传照片 / 删除 / 重绘）→ $URL/admin"
echo "     AI 搭配可直接使用（API Key 一栏留空即可）。"
echo ""
echo "  用完关掉这个窗口就行。"
echo ""

wait $SRV_PID
