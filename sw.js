/* 台灣人代表 service worker
 *
 * 快取分兩層，因為兩種東西的壽命完全不同：
 *   SHELL —— HTML、JSON、icon、manifest。每次部署都會變，版號跟著 bump。約 1MB。
 *   ASSET —— 底圖與音檔。只有同名檔換內容才需要換版。26 張底圖就 7.9MB，
 *            綁在同一個版號的話每次改一行文案都要讓所有人重抓 8MB。
 *
 * SHELL_V 由 tools/build_sw.py 依 precache 清單的內容 hash 產生，不要手改。
 * 手動 bump 的遲早會忘記，而忘記的症狀是「使用者永遠看不到新版」，沒有任何徵兆。
 */
const SHELL_V = "shell-bc03371";
const ASSET_V = "asset-v1";

// 前綴要跨專案唯一。CacheStorage 是 per-origin，yazelin.github.io 底下所有專案
// 共用同一份；SW 的 scope 只管 fetch，管不到快取。用兩個字母的前綴很容易撞到別站。
const PREFIX = "taiwan-people-";
const SHELL = PREFIX + SHELL_V;
const ASSET = PREFIX + ASSET_V;
const KEEP = [SHELL, ASSET];

/* 開場一定會用到的排前面。重資產排最後等於最容易掉的就是它們，
   而底圖根本不進 precache——8MB 會讓安裝變得很久，改成看過才留。 */
const PRECACHE = [
  "./",
  "index.html",
  "costume.html",
  "manifest.json",
  "data/costume.json",
  "data/counties.json",
  "icon-v1-192.png",
  "icon-v1-512.png",
  "icon-v1-maskable-512.png",
  "favicon-32.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil((async () => {
    const c = await caches.open(SHELL);
    // addAll 是全有全無：一個檔 404 就整批不裝，之後每次更新都卡在同一個地方。
    await Promise.allSettled(PRECACHE.map((u) => c.add(new Request(u, { cache: "reload" }))));
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    // 只刪自己前綴的。無差別 caches.delete 會把同 origin 其他專案的離線包整包清空，
    // 而且對方毫無徵兆——這是跨專案最容易誤傷的一件事。
    await Promise.all(
      keys.filter((k) => k.startsWith(PREFIX) && !KEEP.includes(k))
          .map((k) => caches.delete(k))
    );
    await self.clients.claim();
  })());
});

const isAsset = (url) =>
  /\.(webp|png|jpg|jpeg|svg|mp3|m4a|woff2?)$/i.test(url.pathname);

/* GitHub Pages 對每個檔都回 Vary: Accept-Encoding。
   ignoreVary 照加（無害、成本零），但別把它當保證——實測把它拿掉之後預設比對照樣命中，
   真正治好媒體播不出來的可能是下面的 206 合成。會不會播只有真的 decode 過才知道。
   ignoreSearch 是必要的：preview.html?x=1 這種帶 query 的路由離線時會 miss。 */
const MATCH = { ignoreSearch: true, ignoreVary: true };

/* 從快取回應帶 Range 的請求要自己合成 206。回「200 但沒有 Content-Range」
   有些媒體端會直接拒收，症狀是斷網時 MEDIA_ELEMENT_ERROR: Format error。 */
async function rangeResponse(res, range) {
  const buf = await res.arrayBuffer();
  const m = /bytes=(\d*)-(\d*)/.exec(range || "");
  if (!m) return new Response(buf, { status: 200, headers: res.headers });
  const total = buf.byteLength;
  const start = m[1] ? parseInt(m[1], 10) : 0;
  const end = m[2] ? parseInt(m[2], 10) : total - 1;
  const slice = buf.slice(start, end + 1);
  const h = new Headers(res.headers);
  h.set("Content-Range", `bytes ${start}-${end}/${total}`);
  h.set("Content-Length", String(slice.byteLength));
  h.set("Accept-Ranges", "bytes");
  return new Response(slice, { status: 206, statusText: "Partial Content", headers: h });
}

async function put(cacheName, req, res) {
  // fetch 成功不等於存進快取：配額不足或 SW 被回收時 cache.put 會失敗而 fetch 照回 200。
  // 拿 fetch 成功次數當離線完成度會謊報，所以這裡吞掉錯誤、由呼叫端另外實查。
  try {
    const c = await caches.open(cacheName);
    await c.put(req, res.clone());
  } catch (_) { /* 配額或狀態問題，略過 */ }
}

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;

  // 導覽：network-first，線上永遠拿到最新的頁；離線才吃快取。
  // fallback 要 ignoreSearch，否則帶 query 的網址離線時會掉到首頁、開錯頁。
  if (req.mode === "navigate") {
    e.respondWith((async () => {
      try {
        const res = await fetch(req);
        await put(SHELL, req, res);
        return res;
      } catch (_) {
        return (await caches.match(req, MATCH))
            || (await caches.match("index.html", MATCH))
            || Response.error();
      }
    })());
    return;
  }

  // 圖與音：cache-first，看過就留著。內容換了就換檔名（底圖本來就是這個慣例）。
  if (isAsset(url)) {
    e.respondWith((async () => {
      const hit = await caches.match(req, MATCH);
      const range = req.headers.get("range");
      if (hit) return range ? rangeResponse(hit, range) : hit;
      const res = await fetch(req);
      if (res && res.ok) await put(ASSET, req, res);
      return res;
    })());
    return;
  }

  // 其餘（JSON、CSS、JS）：network-first，離線退回 SHELL。
  e.respondWith((async () => {
    try {
      const res = await fetch(req);
      if (res && res.ok) await put(SHELL, req, res);
      return res;
    } catch (_) {
      return (await caches.match(req, MATCH)) || Response.error();
    }
  })());
});

/* 離線完整度不准自我宣告：頁面問「裝好了沒」時，回頭逐項 cache.match 實查，
   不是回報 fetch 成功幾次。實測撞過 ready=true 但快取只有 151/160 的情況。 */
self.addEventListener("message", (e) => {
  if (!e.data || e.data.type !== "offline-status") return;
  e.waitUntil((async () => {
    const want = PRECACHE.concat(e.data.extra || []);
    const have = [];
    for (const u of want) {
      if (await caches.match(new Request(u), MATCH)) have.push(u);
    }
    (e.source || (await self.clients.matchAll())[0])?.postMessage({
      type: "offline-status", have: have.length, want: want.length,
      missing: want.filter((u) => !have.includes(u)),
    });
  })());
});
