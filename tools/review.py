#!/usr/bin/env python3
"""把所有生圖候選整理成一頁可瀏覽的審查表。

    python3 tools/review.py          # 產生 review/index.html
    開 http://localhost:8901/review/

為什麼需要這個：codex 一次會產生多個不同的嘗試（實測 2–9 張），
而 gen.sh 只取最新的一張。台北那次的最新張 101 最小最淡，第 3 張才是最好的——
等於每次都在丟掉候選，而且沒有理由相信最後一張最好。

這頁把每個縣市的全部候選並列，標上編號與量測值，並註明目前裝上去的是哪一張。
看到更好的就報編號，用 tools/pick.py 換上去。
"""
import glob
import json
import os
import pathlib
import shutil

import numpy as np
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "review"
GEN = pathlib.Path("/tmp/taiwan-people-gen")


def measure(path):
    """跟 verify_base.py 同一套判準，數字要對得起來。

    2026-08-12 對過一次，發現這句註解是假的：verify_base 早就把「右緣」停用
    （它量到的是背景不是人物），也早就把文字區起伏上限放寬到 0.055 並補了右側
    結構下限 0.010；這裡卻還卡在 0.030 上限＋右緣 0.38–0.62，而且完全沒量右側結構。
    後果是真的發生了：太魯閣那張唯一畫對的候選被這裡判 FAIL（右緣 0.64），
    我因此先去看了另外兩張——而那兩張是別的縣市混進來的圖。
    **兩支工具說法不一致時，會有人照著錯的那支做決定。** 現在對齊 verify_base。
    """
    a = np.asarray(Image.open(path).convert("RGB"), float)
    H, W, _ = a.shape
    lum = (.2126 * a[..., 0] + .7152 * a[..., 1] + .0722 * a[..., 2]) / 255
    res = {}
    for lab, x0, x1, y0, y1, floor in [("name", .58, .93, .03, .13, 0.42),
                                       ("text", .58, .93, .18, .49, 0.55)]:
        r = lum[int(y0 * H):int(y1 * H), int(x0 * W):int(x1 * W)]
        b = r[:r.shape[0] // 8 * 8, :r.shape[1] // 8 * 8].reshape(r.shape[0] // 8, 8, -1, 8)
        res[lab] = (round(float(r.mean()), 2), round(float(np.median(b.std(axis=(1, 3)))), 3), floor)
    g = np.abs(np.diff(lum, axis=1))
    col = g.mean(axis=0)
    idx = np.where(col > col.mean() + col.std() * .5)[0]
    # 右緣：跟 verify_base 一樣只留數字供參考，不進判定
    res["right"] = round(float(idx.max() / W) if len(idx) else 0, 2)
    # 右側 40% 的結構下限，verify_base 有、這裡本來沒有
    rz = lum[:, int(.60 * W):]
    rh, rw = rz.shape
    rb = rz[:rh // 16 * 16, :rw // 16 * 16].reshape(rh // 16, 16, -1, 16)
    res["detail"] = round(float(np.median(rb.std(axis=(1, 3)))), 4)
    ok = (all(res[k][0] >= res[k][2] and res[k][1] <= 0.055 for k in ("name", "text"))
          and res["detail"] >= 0.010)
    res["ok"] = bool(ok)   # numpy 的布林不能直接轉 JSON
    return res


def same_image(a, b):
    """判斷候選是否就是目前裝上去的那張（縮圖比對，避開壓縮差異）。"""
    try:
        ia = Image.open(a).convert("RGB").resize((16, 12))
        ib = Image.open(b).convert("RGB").resize((16, 12))
    except Exception:
        return False
    da, db = np.asarray(ia, float), np.asarray(ib, float)
    return bool(np.abs(da - db).mean() < 4)   # numpy 布林不能轉 JSON


def build():
    data = json.loads((ROOT / "data" / "counties.json").read_text(encoding="utf-8"))
    notes = json.loads((OUT / "notes.json").read_text(encoding="utf-8")) \
        if (OUT / "notes.json").exists() else {}
    OUT.mkdir(exist_ok=True)
    (OUT / "img").mkdir(exist_ok=True)

    rows = []
    for c in data["counties"]:
        cid, name = c["id"], c["name"]
        cand = sorted(glob.glob(str(GEN / f"{cid}-base.cand" / "*.png")))
        # 還沒生出底圖的特別版沒有 base 欄，而審查頁正是那種狀態下最需要開的頁
        cur = ROOT / "img" / f"{c.get('base') or c['id'] + '-base'}.webp"
        items = []
        for f in cand:
            no = os.path.basename(f).split(".")[0]
            thumb = OUT / "img" / f"{cid}-{no}.webp"
            if not thumb.exists():
                Image.open(f).convert("RGB").resize((640, 480)).save(thumb, "WEBP", quality=82)
            m = measure(f)
            items.append({"no": no, "src": f"img/{cid}-{no}.webp",
                          "m": m, "cur": same_image(f, cur) if cur.exists() else False,
                          "note": notes.get(f"{cid}-{no}", "")})
        # 沒有候選資料夾的（例如手動換過的）至少列出目前這張
        if not items and cur.exists():
            thumb = OUT / "img" / f"{cid}-cur.webp"
            Image.open(cur).convert("RGB").resize((640, 480)).save(thumb, "WEBP", quality=82)
            items.append({"no": "現用", "src": f"img/{cid}-cur.webp",
                          "m": measure(cur), "cur": True, "note": notes.get(f"{cid}-cur", "")})
        rows.append({"id": cid, "name": name,
                     "hero": c["scene"].get("hero_landmark", ""),
                     "view": c["scene"].get("viewpoint", ""),
                     "items": items})

    html = TEMPLATE.replace("__DATA__", json.dumps(rows, ensure_ascii=False))
    (OUT / "index.html").write_text(html, encoding="utf-8")
    n = sum(len(r["items"]) for r in rows)
    print(f"已產生 review/index.html：{len(rows)} 個縣市、{n} 張候選")
    print("開 http://localhost:8901/review/")


TEMPLATE = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>底圖候選審查</title>
<style>
:root{--bg:#12161c;--card:#1a212a;--line:#26303c;--text:#e6edf5;--dim:#8a99ab;
      --ok:#5edc9a;--bad:#f06060;--pick:#f3c357}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);
  font:14px/1.6 "Noto Sans CJK TC","Noto Sans TC",system-ui,sans-serif;padding:20px}
h1{font-size:1rem;letter-spacing:.14em;color:var(--dim);margin-bottom:4px}
.sum{font-size:.8rem;color:var(--dim);margin-bottom:20px}
.county{margin-bottom:26px;border:1px solid var(--line);border-radius:12px;
  background:var(--card);padding:14px}
.county h2{font-size:1.05rem;margin-bottom:2px}
.county .meta{font-size:.75rem;color:var(--dim);margin-bottom:10px}
.county .meta b{color:var(--pick);font-weight:600}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}
figure{border:2px solid var(--line);border-radius:9px;overflow:hidden;background:#0f151c}
figure.cur{border-color:var(--pick)}
figure img{width:100%;display:block;cursor:zoom-in}
figcaption{padding:7px 9px;font-size:.72rem;line-height:1.5}
.no{font-weight:700;font-size:.9rem}
.tag{display:inline-block;padding:1px 7px;border-radius:99px;font-size:.68rem;
  margin-left:6px;vertical-align:1px}
.tag.cur{background:var(--pick);color:#2a1c04;font-weight:700}
.tag.ok{background:rgba(94,220,154,.18);color:var(--ok)}
.tag.bad{background:rgba(240,96,96,.18);color:var(--bad)}
.nums{color:var(--dim);font-variant-numeric:tabular-nums;margin-top:3px}
.note{margin-top:5px;color:#cfe0ee}
dialog{border:none;background:transparent;max-width:96vw;max-height:96vh;padding:0}
dialog::backdrop{background:rgba(4,10,18,.92)}
dialog img{max-width:96vw;max-height:96vh;display:block}
</style></head><body>
<h1>底圖候選審查</h1>
<div class="sum" id="sum"></div>
<div id="list"></div>
<dialog id="lb"><img id="lbimg" alt=""></dialog>
<script>
const D=__DATA__;
const L=document.getElementById('list');
let tot=0, cur=0;
for(const c of D){
  tot+=c.items.length;
  const d=document.createElement('div'); d.className='county';
  const picked=c.items.find(i=>i.cur);
  if(picked) cur++;
  d.innerHTML=`<h2>${c.name}</h2>
    <div class="meta">主地標 <b>${c.hero||'—'}</b>　${c.view||''}</div>
    <div class="grid">`+c.items.map(i=>{
      const m=i.m;
      return `<figure class="${i.cur?'cur':''}">
        <img src="${i.src}" alt="${c.name} 候選 ${i.no}" loading="lazy">
        <figcaption>
          <span class="no">候選 ${i.no}</span>
          ${i.cur?'<span class="tag cur">目前採用</span>':''}
          <span class="tag ${m.ok?'ok':'bad'}">${m.ok?'量測通過':'量測未過'}</span>
          <div class="nums">縣市名 ${m.name[0]}／${m.name[1]}　文字塊 ${m.text[0]}／${m.text[1]}　右緣 ${Math.round(m.right*100)}%</div>
          ${i.note?`<div class="note">${i.note}</div>`:''}
        </figcaption></figure>`;
    }).join('')+`</div>`;
  L.appendChild(d);
}
document.getElementById('sum').textContent=
  `${D.length} 個縣市、${tot} 張候選，其中 ${cur} 張已標記為目前採用。點圖可放大。`;
const lb=document.getElementById('lb'), lbimg=document.getElementById('lbimg');
L.addEventListener('click',e=>{ if(e.target.tagName==='IMG'){ lbimg.src=e.target.src; lb.showModal(); }});
lb.addEventListener('click',()=>lb.close());
</script></body></html>
"""

if __name__ == "__main__":
    build()
