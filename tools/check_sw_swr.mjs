// 驗 sw.js 的底圖 stale-while-revalidate：同名底圖換過內容之後，回訪者拿不拿得到新的。
//
//     NODE_PATH=/home/ct/mycelium/node_modules node tools/check_sw_swr.mjs . --port=8144
//
// 為什麼要有這支：2026-08-19 使用者回報線上的高雄拉阿魯哇還是舊的海邊那張，
// 而伺服器上早就換成山谷了。無痕視窗看是新的、md5 也對，只有裝過 service worker
// 的那個瀏覽器停在舊版——底圖走 cache-first，而這個站的底圖是「同名覆蓋」的，
// 兩者天生相剋。這種壞法沒有任何徵兆，所以要有一支會回傳退出碼的東西盯著。
//
// 負控制：把 sw.js 裡 isVolatileImage 那個分支停掉（改成 if (false && ...)）再跑，
// 這支必須紅。不會紅就代表它什麼都沒驗到。
import http from 'http';
import { readFileSync, existsSync, mkdtempSync, cpSync, writeFileSync } from 'fs';
import { join, extname } from 'path';
import { tmpdir } from 'os';

const SITE = process.argv[2];
const PORT = Number((process.argv.find(a => a.startsWith('--port=')) || '--port=8144').split('=')[1]);
const pw = await import(join(process.env.NODE_PATH, 'playwright/index.js'));
const chromium = (pw.chromium || pw.default.chromium);

// 複製一份站台，才敢在測試中途改檔
const dir = mkdtempSync(join(tmpdir(), 'swr-'));
cpSync(SITE, dir, { recursive: true, filter: (s) => !s.includes('/.git/') });

const TARGET = 'img/hsinchu-county-saysiyat-base.webp';
if (!existsSync(join(dir, TARGET))) throw new Error('測試用的底圖不在：' + TARGET);

const MIME = { '.html': 'text/html', '.js': 'application/javascript', '.json': 'application/json',
  '.webp': 'image/webp', '.png': 'image/png', '.svg': 'image/svg+xml', '.css': 'text/css',
  '.mp3': 'audio/mpeg', '.webmanifest': 'application/manifest+json' };

const srv = http.createServer((req, res) => {
  const p = decodeURIComponent(req.url.split('?')[0]);
  const f = join(dir, p === '/' ? 'index.html' : p);
  if (!existsSync(f)) { res.writeHead(404); return res.end(); }
  const body = readFileSync(f);
  // 仿 GitHub Pages
  res.writeHead(200, { 'content-type': MIME[extname(f)] || 'application/octet-stream',
    'vary': 'Accept-Encoding', 'cache-control': 'max-age=600' });
  res.end(body);
});
await new Promise(r => srv.listen(PORT, '127.0.0.1', r));
const BASE = `http://127.0.0.1:${PORT}/`;

const browser = await chromium.launch();
const ctx = await browser.newContext();
const page = await ctx.newPage();

const sizeOf = () => page.evaluate(async (u) => {
  const r = await fetch(u, { cache: 'no-store' });
  return (await r.arrayBuffer()).byteLength;
}, BASE + TARGET);

await page.goto(BASE, { waitUntil: 'load' });
await page.evaluate(() => navigator.serviceWorker.ready);
const before = await sizeOf();               // 第一次：進快取

// 伺服器端換內容，檔名不變——這正是這個站在做的事
const fake = Buffer.concat([readFileSync(join(dir, TARGET)), Buffer.alloc(50_000, 7)]);
writeFileSync(join(dir, TARGET), fake);

await page.goto(BASE, { waitUntil: 'load' });
const first = await sizeOf();                // 回訪第一次：拿到舊的（stale，正常）
await page.waitForTimeout(1500);             // 等背景 revalidate 寫回快取
await page.goto(BASE, { waitUntil: 'load' });
const second = await sizeOf();               // 回訪第二次：應該是新的

await browser.close();
srv.close();

console.log(`原始 ${before} → 換過內容 ${fake.length}`);
console.log(`回訪第 1 次 ${first}（stale 是預期的）`);
console.log(`回訪第 2 次 ${second}`);
if (second === fake.length) { console.log('PASS：底圖換內容後，回訪者第二次就拿到新的'); }
else { console.log('FAIL：回訪者一直拿到舊圖，SWR 沒有生效'); process.exit(1); }
