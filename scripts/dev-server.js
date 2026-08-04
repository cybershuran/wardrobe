#!/usr/bin/env node
/* 极简静态服务器，供 npm run dev 使用（Kimi Work 预览 / 本地调试）。
   用法: npm run dev -- --port 7100 --host 127.0.0.1 */
const http = require('http');
const fs = require('fs');
const path = require('path');

const args = process.argv.slice(2);
function argVal(name, dflt) {
  const i = args.indexOf('--' + name);
  return i >= 0 && args[i + 1] ? args[i + 1] : dflt;
}
const port = parseInt(argVal('port', process.env.PORT || '8642'), 10);
const host = argVal('host', '127.0.0.1');
const root = path.resolve(__dirname, '..');

const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css', '.json': 'application/json', '.png': 'image/png',
  '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp',
  '.gif': 'image/gif', '.svg': 'image/svg+xml', '.heic': 'image/heic',
};

http.createServer((req, res) => {
  let p = decodeURIComponent(req.url.split('?')[0]);
  if (p === '/') p = '/index.html';
  const file = path.join(root, p);
  if (!file.startsWith(root) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
    res.writeHead(404); res.end('not found'); return;
  }
  res.writeHead(200, { 'Content-Type': MIME[path.extname(file).toLowerCase()] || 'application/octet-stream' });
  fs.createReadStream(file).pipe(res);
}).listen(port, host, () => console.log(`衣橱预览 → http://${host}:${port}`));
