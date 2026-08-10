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
const SHELL_V = "shell-2acfdc5";
const ASSET_V = "asset-v1";

// 前綴要跨專案唯一。CacheStorage 是 per-origin，yazelin.github.io 底下所有專案
// 共用同一份；SW 的 scope 只管 fetch，管不到快取。用兩個字母的前綴很容易撞到別站。
const PREFIX = "taiwan-people-";
const SHELL = PREFIX + SHELL_V;
const ASSET = PREFIX + ASSET_V;
const KEEP = [SHELL, ASSET];

/* 開場一定會用到的排前面。重資產排最後等於最容易掉的就是它們，
   而底圖根本不進 precache——8MB 會讓安裝變得很久，改成看過才留。

   data/counties.json 原本刻意不在這裡（156KB，約佔 shell 的 15%），理由是
   它被 sync_split.py 內嵌進 index.html 的 SPLIT 常數，執行期沒有任何一頁 fetch 它，
   放進來等於每個訪客都白抓一次。**counties.html 上線之後這個前提沒了**——
   那頁直接 fetch 它，不進清單就是離線打不開。所以現在收進來。
   當初另一個顧慮仍然成立：它進 precache 就會製造版號漂移，因為 build_sw.py
   算的是工作區內容而部署的是 commit 的內容。那個由 build_sw.py 的 dirty 檢查擋。 */
const PRECACHE = [
  "./",
  "index.html",
  "costume.html",
  "newcomers.html",
  "counties.html",
  "manifest.json",
  "data/costume.json",
  "data/newcomers.json",
  "data/counties.json",
  "icon-v1-192.png",
  "icon-v1-512.png",
  "icon-v1-maskable-512.png",
  "favicon-32.png",
];

/* 離線包的清單。由 tools/build_sw.py 從 data/counties.json 產生，不要手改。
   這些**不進 precache**——33 張底圖 9.8MB，安裝時全抓會讓第一次開站等很久。
   改成使用者自己按「下載離線包」才暖，而完成度由下面的 offline-status 逐項實查。 */
const ASSET_LIST = [
  "img/keelung-base.webp",
  "img/taipei-base.webp",
  "img/new-taipei-base.webp",
  "img/taoyuan-base.webp",
  "img/hsinchu-city-base.webp",
  "img/hsinchu-county-base.webp",
  "img/yilan-base.webp",
  "img/miaoli-base.webp",
  "img/taichung-base.webp",
  "img/changhua-base.webp",
  "img/nantou-base.webp",
  "img/yunlin-base.webp",
  "img/chiayi-city-base.webp",
  "img/chiayi-county-base.webp",
  "img/tainan-base.webp",
  "img/kaohsiung-base.webp",
  "img/pingtung-base.webp",
  "img/hualien-base.webp",
  "img/taitung-base.webp",
  "img/penghu-base.webp",
  "img/kinmen-base.webp",
  "img/lienchiang-base.webp",
  "img/taitung-pinuyumayan-base.webp",
  "img/hsinchu-county-hakka-base.webp",
  "img/miaoli-hakka-base.webp",
  "img/hualien-truku-base.webp",
  "img/nantou-thao-base.webp",
  "img/kaohsiung-hlaalua-base.webp",
  "img/pingtung-paiwan-base.webp",
  "img/yilan-kavalan-base.webp",
  "img/hsinchu-county-saysiyat-base.webp",
  "img/hsinchu-county-tayal-base.webp",
  "img/chiayi-county-cou-base.webp",
  "audio/theme.mp3",
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

/* 一律只查自己的兩個快取。caches.match 不帶 cacheName 會掃過同 origin 的每一個快取——
   activate 那邊費力保護不刪別站，讀的時候卻可能讀到別站的舊副本，而且無從失效。
   兩個都要查：asset 分支會命中放在 SHELL precache 裡的 icon。 */
async function ownMatch(req) {
  for (const name of [SHELL, ASSET]) {
    const c = await caches.open(name);
    const hit = await c.match(req, MATCH);
    if (hit) return hit;
  }
  return undefined;
}

/* 從快取回應帶 Range 的請求要自己合成 206。回「200 但沒有 Content-Range」
   有些媒體端會直接拒收，症狀是斷網時 MEDIA_ELEMENT_ERROR: Format error。 */
async function rangeResponse(res, range) {
  const buf = await res.arrayBuffer();
  const total = buf.byteLength;
  const m = /bytes=(\d*)-(\d*)/.exec(range || "");
  if (!m) return new Response(buf, { status: 200, headers: res.headers });

  let start, end;
  if (m[1] === "" && m[2] !== "") {
    // bytes=-500 是「最後 500 個位元組」，不是「0 到 500」
    start = Math.max(0, total - parseInt(m[2], 10));
    end = total - 1;
  } else {
    start = m[1] ? parseInt(m[1], 10) : 0;
    // 不夾住的話，播放器要 bytes=3000000-4000000 而檔案只有 3044163 時，
    // 標頭會寫成 bytes 3000000-4000000/3044163（末位元組 ≥ 總長，格式不合法）
    // 而 body 只有 44163 位元組，標頭與內容對不上——那正是這段想防的 Format error。
    end = Math.min(m[2] ? parseInt(m[2], 10) : total - 1, total - 1);
  }
  if (start >= total || start > end) {
    return new Response(null, { status: 416, statusText: "Range Not Satisfiable",
      headers: { "Content-Range": `bytes */${total}` } });
  }

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
        // 一定要檢查再存。Pages 重佈期間根目錄會回 404，無條件存下去等於把
        // precache 的 "./" 蓋成 404，之後離線 fallback 就一直吐那個 404，
        // 直到下次 SHELL_V 換版為止。
        // redirected 也要擋：從沒有尾斜線的網址進來會拿到轉址過的回應，
        // 把它存起來、之後拿它服務導覽會直接失敗（Response ... has redirected flag set）。
        if (res.ok && !res.redirected) await put(SHELL, req, res);
        return res;
      } catch (_) {
        return (await ownMatch(req))
            || (await ownMatch(new Request("index.html")))
            || Response.error();
      }
    })());
    return;
  }

  // 圖與音：cache-first，看過就留著。內容換了就換檔名（底圖本來就是這個慣例）。
  if (isAsset(url)) {
    e.respondWith((async () => {
      const range = req.headers.get("range");
      const hit = await ownMatch(req);
      if (hit) return range ? rangeResponse(hit, range) : hit;

      // <audio> 的第一個請求就帶 Range: bytes=0-，伺服器回 206，
      // 而 Cache.put 對 206 直接丟 TypeError（實測 Chrome:
      // "Failed to execute 'put' on 'Cache': Partial response (status code 206)"）。
      // put() 把錯誤吞掉，所以症狀是「音檔永遠進不了快取」而且完全沒有徵兆，
      // 下面那段 206 合成也就永遠走不到。
      // 解法是另外抓一份不帶 Range 的完整檔存快取，再自己切一段回給播放器。
      if (range) {
        const full = await fetch(new Request(url.href, { credentials: "omit" }));
        if (full && full.ok) {
          await put(ASSET, new Request(url.href), full);
          return rangeResponse(full, range);
        }
        return fetch(req);
      }

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
      return (await ownMatch(req)) || Response.error();
    }
  })());
});

/* 離線完整度不准自我宣告：頁面問「裝好了沒」時，回頭逐項 cache.match 實查，
   不是回報 fetch 成功幾次。fetch 回 200 但 cache.put 因配額或 SW 被回收而失敗時，
   數 fetch 成功次數會謊報——實測撞過 ready=true 但快取只有 151/160 的情況。 */
async function statusOf() {
  const want = PRECACHE.concat(ASSET_LIST);
  const missing = [];
  for (const u of want) {
    if (!(await ownMatch(new Request(u)))) missing.push(u);
  }
  return { type: "offline-status", want: want.length,
           have: want.length - missing.length, missing };
}

const reply = async (e, msg) =>
  (e.source || (await self.clients.matchAll())[0])?.postMessage(msg);

self.addEventListener("message", (e) => {
  const t = e.data && e.data.type;

  if (t === "offline-status") {
    e.waitUntil((async () => reply(e, await statusOf()))());
    return;
  }

  // 暖快取。開場會用到的排前面（PRECACHE 已經在了，這裡只補資產），
  // 一次一個而不是全部並發：並發到三十幾個請求在手機上很容易撞到配額或被中斷，
  // 而中斷的那些不會有任何徵兆。
  if (t === "offline-warm") {
    e.waitUntil((async () => {
      let done = 0;
      for (const u of ASSET_LIST) {
        if (!(await ownMatch(new Request(u)))) {
          try {
            const res = await fetch(new Request(u, { credentials: "omit" }));
            if (res && res.ok) await put(ASSET, new Request(u), res);
          } catch (_) { /* 單一檔失敗不擋住其餘的 */ }
        }
        done++;
        await reply(e, { type: "offline-progress", done, total: ASSET_LIST.length });
      }
      // 暖完不直接說「好了」，回頭實查一次再回報
      await reply(e, await statusOf());
    })());
  }
});
