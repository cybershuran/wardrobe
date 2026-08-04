#!/usr/bin/env python3
"""衣橱产品测试套件。

    .venv/bin/python -m unittest discover -s tests -v

覆盖三层：
  1. 数据层（wardrobe.py）：items.js 解析 / 字段 / 写入往返
  2. 服务器（serve.py）：真实起实例验证全部路由、健康检查、路径穿越防护
  3. 前端：index.html 与管理台内联脚本语法（node --check）、关键入口存在性
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import serve  # noqa: E402
import wardrobe as wb  # noqa: E402

TEST_PORT = 8649
BASE = f"http://127.0.0.1:{TEST_PORT}"


def http(method: str, path: str, body: dict | None = None) -> tuple[int, bytes]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


# ---------------------------------------------------------------- 数据层

class TestDataLayer(unittest.TestCase):
    """写操作会备份并还原 items.js，不影响真实数据。"""

    def setUp(self):
        self.backup = wb.ITEMS_JS.read_text(encoding="utf-8")

    def tearDown(self):
        wb.ITEMS_JS.write_text(self.backup, encoding="utf-8")

    def test_entries_parse(self):
        items = wb.entries()
        self.assertGreater(len(items), 0, "items.js 里没有解析出任何单品")
        ids = [i for i, _ in items]
        self.assertEqual(len(ids), len(set(ids)), "存在重复的单品 id")

    def test_field_reads(self):
        item_id, entry = wb.entries()[0]
        self.assertEqual(wb.field(entry, "id"), item_id)
        self.assertTrue(wb.field(entry, "img"), "首条单品缺 img")
        self.assertTrue(wb.field(entry, "cat"), "首条单品缺 cat")

    def test_every_entry_complete(self):
        """每件单品的必填字段都齐全，且引用的图片文件存在。"""
        missing = []
        for item_id, entry in wb.entries():
            for f in ("en", "cn", "cat", "season", "img"):
                if not wb.field(entry, f):
                    missing.append(f"{item_id} 缺 {f}")
            img = ROOT / (wb.field(entry, "img") or "")
            if not img.is_file():
                missing.append(f"{item_id} 图片不存在: {img.name}")
        self.assertEqual(missing, [])

    def test_write_roundtrip(self):
        items = wb.entries()
        wb.write_entries(items)
        self.assertEqual([i for i, _ in wb.entries()], [i for i, _ in items])
        # 内容逐条一致（写入不丢失条目文本）
        for (i1, e1), (i2, e2) in zip(items, wb.entries()):
            self.assertEqual(i1, i2)
            self.assertEqual(e1.strip(), e2.strip())

    def test_remove_last_entry(self):
        items = wb.entries()
        last_id = items[-1][0]
        wb.write_entries(items[:-1])
        self.assertNotIn(last_id, [i for i, _ in wb.entries()])


# ---------------------------------------------------------------- 服务器

class TestServer(unittest.TestCase):
    """在测试端口起真实 serve.py 实例，验证每条路由。"""

    proc: subprocess.Popen | None = None

    @classmethod
    def setUpClass(cls):
        env = dict(os.environ, WARDROBE_PORT=str(TEST_PORT))
        cls.proc = subprocess.Popen(
            [sys.executable, "scripts/serve.py"],
            cwd=ROOT, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(50):                       # 最多等 10 秒
            try:
                code, _ = http("GET", "/api/health")
                if code == 200:
                    return
            except Exception:
                time.sleep(0.2)
        cls.proc.kill()
        raise RuntimeError("测试服务器 10 秒内未就绪")

    @classmethod
    def tearDownClass(cls):
        if cls.proc:
            cls.proc.terminate()
            cls.proc.wait(timeout=5)

    def test_health(self):
        code, body = http("GET", "/api/health")
        data = json.loads(body)
        self.assertEqual(code, 200)
        self.assertTrue(data["ok"])
        self.assertGreater(data["items"], 0)

    def test_health_identifies_service(self):
        """健康检查必须带服务身份 —— 启动器据此辨认端口上是不是「自己人」。"""
        req = urllib.request.Request(BASE + "/api/health")
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
            cors = r.headers.get("Access-Control-Allow-Origin")
        self.assertEqual(data.get("service"), "wardrobe")
        self.assertIn("version", data)
        self.assertIn("pid", data)
        self.assertEqual(cors, "*", "健康检查需放行 CORS，file:// 页面才能探测本地服务")

    def test_second_instance_fails_gracefully(self):
        """端口被占时再起一个实例：人话报错并以非零码退出，而不是一屏 traceback。"""
        env = dict(os.environ, WARDROBE_PORT=str(TEST_PORT))  # 与测试服务器同端口
        proc = subprocess.run([sys.executable, "scripts/serve.py"],
                              cwd=ROOT, env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("端口", proc.stdout)
        self.assertNotIn("Traceback", proc.stdout + proc.stderr)

    def test_home_page(self):
        code, body = http("GET", "/")
        self.assertEqual(code, 200)
        self.assertIn("WARDROBE", body.decode())

    def test_admin_page(self):
        code, body = http("GET", "/admin")
        text = body.decode()
        self.assertEqual(code, 200)
        self.assertIn("管理台", text)
        self.assertIn("返回衣橱", text, "管理台缺返回主页的链接")

    def test_home_has_admin_entry(self):
        """本地打开时导航必须渲染管理台入口（入口由 JS 按环境动态生成）。"""
        _, body = http("GET", "/")
        html = body.decode()
        self.assertIn("isLocal() ? '/admin'", html, "主页缺本地管理台入口逻辑")
        self.assertIn("管理台 →", html)

    def test_items_api(self):
        code, body = http("GET", "/api/items")
        data = json.loads(body)
        self.assertEqual(code, 200)
        self.assertGreater(len(data["items"]), 0)
        for key in ("id", "img", "en", "cn", "cat", "season", "hasSource"):
            self.assertIn(key, data["items"][0])

    def test_static_items_js(self):
        code, body = http("GET", "/items.js")
        self.assertEqual(code, 200)
        self.assertIn("const ITEMS", body.decode())

    def test_static_image(self):
        _, body = http("GET", "/api/items")
        img = json.loads(body)["items"][0]["img"]
        code, rbody = http("GET", "/" + img)
        self.assertEqual(code, 200)
        self.assertGreater(len(rbody), 1000, "图片响应太小，可能不是真图")

    def test_path_traversal_blocked(self):
        code, _ = http("GET", "/..%2F..%2Fetc%2Fpasswd")
        self.assertEqual(code, 404)

    def test_not_found(self):
        code, _ = http("GET", "/no-such-page")
        self.assertEqual(code, 404)

    def test_remove_unknown_id(self):
        code, body = http("POST", "/api/remove", {"id": "test-nonexistent-999"})
        self.assertEqual(code, 404)
        self.assertIn("error", json.loads(body))

    def test_unknown_endpoint(self):
        code, _ = http("POST", "/api/nope", {})
        self.assertEqual(code, 404)

    def test_classify(self):
        """识别结果分类：外套纠偏到 JACKETS，其余按部位映射，连衣裙不误判。"""
        c = serve.classify
        self.assertEqual(c({"part": "upperbody", "name": "houndstooth blazer",
                            "cn": "格纹西装外套", "tags": ["blazer"]}), "JACKETS")
        self.assertEqual(c({"part": "upperbody", "name": "cream turtleneck sweater",
                            "cn": "米白色高领针织衫", "tags": ["knit"]}), "TOPS")
        self.assertEqual(c({"part": "upperbody", "name": "驼色羊毛大衣",
                            "cn": "驼色羊毛大衣", "tags": []}), "JACKETS")
        self.assertEqual(c({"part": "wholebody_up", "name": "black jumpsuit",
                            "cn": "黑色连体裤", "tags": []}), "DRESSES")
        self.assertEqual(c({"part": "lowerbody", "name": "jeans"}), "BOTTOMS")
        self.assertEqual(c({"part": "shoes", "name": "loafers"}), "SHOES")
        self.assertEqual(c({"part": "accessories_up", "name": "silk scarf"}),
                         "ACCESSORIES")


# ---------------------------------------------------------------- 前端

def extract_scripts(html: str) -> list[str]:
    return re.findall(r"<script>(.*?)</script>", html, re.S)


class TestFrontend(unittest.TestCase):

    def _node_check(self, code: str, label: str):
        node = shutil.which("node")
        if not node:
            self.skipTest("没有 node，跳过 JS 语法检查")
        proc = subprocess.run([node, "--check", "/dev/stdin"],
                              input=code.encode(), capture_output=True)
        self.assertEqual(proc.returncode, 0,
                         f"{label} 语法错误: {proc.stderr.decode()[:400]}")

    def test_index_scripts(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        scripts = extract_scripts(html)
        self.assertTrue(scripts, "index.html 里没有内联脚本")
        for i, s in enumerate(scripts):
            self._node_check(s, f"index.html 脚本 #{i+1}")

    def test_admin_scripts(self):
        for i, s in enumerate(extract_scripts(serve.ADMIN_PAGE)):
            self._node_check(s, f"管理台脚本 #{i+1}")

    def test_local_ai_default_is_same_origin(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("location.origin + '/api/ai'", html,
                      "本地 AI 默认地址应指向同源 /api/ai")
        self.assertNotIn("127.0.0.1:8643", html, "仍存在旧代理地址")
        self.assertNotIn("127.0.0.1:8644", html, "仍存在旧管理台地址")

    def test_file_protocol_probes_local_server(self):
        """file:// 直开 index.html 时，页面应探测本地服务并据此显示管理台入口。"""
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("probeLocal", html)
        self.assertIn("location.protocol !== 'file:'", html)
        self.assertIn("d.service === 'wardrobe'", html,
                      "探测必须校验服务身份，不能把端口上的陌生服务当成衣橱")
        self.assertIn("localServer + '/admin'", html,
                      "探测到本地服务后应给出管理台入口")

    def test_launcher_script(self):
        """启动器：只认带 wardrobe 身份的健康检查；能清理自家残留；失败要明示。"""
        script = (ROOT / "衣橱.command").read_text(encoding="utf-8")
        self.assertIn('"service": *"wardrobe"', script,
                      "启动器必须校验服务身份，否则会把端口上的死服务当成「已在运行」")
        self.assertIn("serve.py", script)
        self.assertIn("lsof", script, "启动器应能发现并清理端口上的自家残留进程")
        self.assertIn("衣橱没能启动", script, "启动失败必须在窗口里留下人话提示")


if __name__ == "__main__":
    unittest.main()
