// Kimi API 的 CORS 代理（Cloudflare Worker）。
//
// ⚠️ 现状：对 api.kimi.com/coding（Kimi Code 会员 Key）**不可用**。
// 该接口有反滥用防护，会拒绝来自云端代理的请求并返回 Cloudflare 质询页
// （403）；同一个 Key 从本机直连则正常。所以线上版 AI 搭配请改用
// scripts/proxy.py（本机代理）。这份 Worker 保留备用：若将来换成
// Kimi 开放平台的 Key，把 UPSTREAM 改成对应地址重新部署即可。
//
// Worker 本身不存任何密钥——浏览器把 Key 放在 Authorization 头里带过来，
// 这里原样转发。只允许下面列出的来源跨域调用。

const UPSTREAM = 'https://api.kimi.com/coding/v1';
const ALLOWED_ORIGINS = new Set([
  'https://cybershuran.github.io',
  'http://localhost:8642',
  'http://127.0.0.1:8642',
]);

export default {
  async fetch(req) {
    const origin = req.headers.get('Origin') || '';
    const allowed = ALLOWED_ORIGINS.has(origin);
    const cors = {
      'Access-Control-Allow-Origin': allowed ? origin : 'null',
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Authorization, Content-Type',
      'Access-Control-Max-Age': '86400',
      'Vary': 'Origin',
    };

    if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
    if (!allowed) return new Response('origin not allowed', { status: 403, headers: cors });
    if (req.method !== 'POST') return new Response('POST only', { status: 405, headers: cors });

    const url = new URL(req.url);
    const upstream = await fetch(UPSTREAM + url.pathname, {
      method: 'POST',
      headers: {
        'Authorization': req.headers.get('Authorization') || '',
        'Content-Type': 'application/json',
        'User-Agent': 'wardrobe-gallery/1.0',
        'Accept': 'application/json',
      },
      body: req.body,
    });

    const resp = new Response(upstream.body, upstream);
    for (const [k, v] of Object.entries(cors)) resp.headers.set(k, v);
    return resp;
  },
};
