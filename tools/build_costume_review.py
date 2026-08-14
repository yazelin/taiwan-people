#!/usr/bin/env python3
"""產生「實物照 → 出圖」的對照頁，用來驗收特別版。

    python3 tools/build_costume_review.py
    # 產出 review/costume.html，直接用瀏覽器開

為什麼要有這支：特別版的品質取決於「規格寫得對不對」與「模型有沒有照著畫」，
而這兩件事只有把**實物照、出圖、驗收清單擺在同一個畫面**才看得出來。
先前每次驗收都要自己開三個地方對照，容易漏。

輸出的頁面本身不進版控（review/ 在 .gitignore 裡）——它是工具不是產品。
"""
import base64
import html
import json
import mimetypes
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "review" / "costume.html"


def data_uri(p):
    """圖片內嵌成 data URI：這頁常常被複製到別處看，外連相對路徑會壞掉。"""
    p = ROOT / p if not str(p).startswith("/") else pathlib.Path(p)
    if not p.exists():
        return None
    mime = mimetypes.guess_type(p.name)[0] or "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()


def main():
    counties = json.loads((ROOT / "data" / "counties.json").read_text(encoding="utf-8"))
    costume = json.loads((ROOT / "data" / "costume.json").read_text(encoding="utf-8"))
    peoples = {p["id"]: p for p in costume["peoples"]}
    sources = costume.get("sources", {})

    rows = []
    for c in counties["counties"]:
        if not c.get("culture") or not c.get("base"):
            continue
        p = peoples.get(c["culture"], {})
        s = c["scene"]
        refs = [r for r in (s.get("costume_refs") or []) if (ROOT / r).exists()]
        # 男裝條目對阿蕊不適用，跟 build_prompt --checklist 同一條規則
        checks = [x for x in (p.get("checklist") or [])
                  if not x.startswith(("男子", "男性"))]
        rows.append({
            "name": c["name"], "people": p.get("name", c["culture"]),
            "base": data_uri(f"img/{c['base']}.webp"),
            "refs": [(pathlib.Path(r).name, data_uri(r)) for r in refs],
            "checks": checks,
            "pitfalls": p.get("pitfalls") or [],
            "gaps": p.get("gaps") or "",
            "srcs": [sources[i] for i in (p.get("sources") or []) if i in sources],
        })

    e = html.escape
    parts = ["""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>特別版：實物照與出圖對照</title>
<style>
:root{--bg:#12161c;--card:#1a212a;--line:#26303c;--text:#e6edf5;--dim:#8a99ab;--key:#f3c357}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);padding:20px;
  font:14px/1.7 "Noto Sans CJK TC","Noto Sans TC",system-ui,sans-serif}
h1{font-size:1.05rem;letter-spacing:.12em;color:var(--dim)}
.lede{font-size:.82rem;color:var(--dim);margin:6px 0 22px;max-width:60em}
.p{border:1px solid var(--line);border-radius:12px;background:var(--card);
  padding:16px;margin-bottom:22px}
.p>h2{font-size:1.1rem}
.p>h2 small{color:var(--dim);font-weight:400;font-size:.72rem;margin-left:8px;letter-spacing:.1em}
.two{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,1fr);gap:16px;margin-top:12px}
@media(max-width:900px){.two{grid-template-columns:1fr}}
.out img{width:100%;border-radius:9px;display:block;border:1px solid var(--line)}
.refs{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px}
.refs figure{border:1px solid var(--line);border-radius:8px;overflow:hidden;background:#0f151c}
.refs img{width:100%;display:block;aspect-ratio:1;object-fit:cover;cursor:zoom-in}
.refs figcaption{font-size:.66rem;color:var(--dim);padding:4px 6px;word-break:break-all}
.none{color:var(--dim);font-size:.82rem;border:1px dashed var(--line);
  border-radius:8px;padding:14px;text-align:center}
.lab{font-size:.68rem;letter-spacing:.18em;color:var(--key);margin-bottom:7px}
ul{margin:0 0 0 1.1em;font-size:.82rem}
li{margin-bottom:3px}
.pit li{color:#f0a0a0}
.gap{font-size:.76rem;color:var(--dim);margin-top:10px;border-top:1px solid var(--line);padding-top:8px}
.src{font-size:.7rem;color:var(--dim);margin-top:6px}
.src a{color:#7fb3e0}
dialog{border:0;background:#0b0f14;padding:0;max-width:96vw;max-height:96vh}
dialog img{max-width:96vw;max-height:96vh;display:block}
dialog::backdrop{background:rgba(0,0,0,.85)}
</style></head><body>
<h1>特別版：實物照與出圖對照</h1>
<p class="lede">左邊是這一族實際畫出來的底圖，右邊是餵給模型的實物照與該族的驗收清單。
點實物照可放大。男裝條目已濾掉（阿蕊是女子），跟 <code>build_prompt.py --checklist</code> 同一條規則。
這頁由 <code>tools/build_costume_review.py</code> 產生，不進版控。</p>
<dialog id="z"><img></dialog>"""]

    for r in rows:
        parts.append(f'<section class="p"><h2>{e(r["name"])}<small>{e(r["people"])}｜'
                     f'{len(r["refs"]) or "無"} 張實物照</small></h2><div class="two">')
        parts.append('<div class="out">')
        parts.append(f'<img src="{r["base"]}" alt="{e(r["name"])}">' if r["base"]
                     else '<div class="none">沒有底圖</div>')
        parts.append('</div><div>')

        parts.append('<div class="lab">實物照</div>')
        if r["refs"]:
            parts.append('<div class="refs">')
            for name, uri in r["refs"]:
                parts.append(f'<figure><img src="{uri}" alt="{e(name)}">'
                             f'<figcaption>{e(name)}</figcaption></figure>')
            parts.append('</div>')
        else:
            parts.append('<div class="none">沒有實物照——排灣是刻意不用'
                         '（平民不可飾以任何紋飾，正確答案是素面），其餘見 gaps</div>')

        if r["checks"]:
            parts.append('<div class="lab" style="margin-top:14px">驗收清單</div><ul>')
            parts += [f'<li>{e(x)}</li>' for x in r["checks"]]
            parts.append('</ul>')
        if r["pitfalls"]:
            parts.append('<div class="lab" style="margin-top:14px">已知會畫錯</div><ul class="pit">')
            parts += [f'<li>{e(x)}</li>' for x in r["pitfalls"]]
            parts.append('</ul>')
        if r["gaps"]:
            parts.append(f'<div class="gap"><b>查不到什麼：</b>{e(r["gaps"])}</div>')
        if r["srcs"]:
            parts.append('<div class="src">出處：' + '　'.join(
                f'<a href="{e(s["url"])}" target="_blank" rel="noopener">{e(s["org"])}</a>'
                for s in r["srcs"]) + '</div>')
        parts.append('</div></div></section>')

    parts.append("""<script>
const dlg=document.getElementById('z');
document.addEventListener('click',ev=>{
  if(ev.target.matches('.refs img')){dlg.querySelector('img').src=ev.target.src;dlg.showModal();}
  else if(ev.target.closest('dialog'))dlg.close();
});
</script></body></html>""")

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("".join(parts), encoding="utf-8")
    n_ref = sum(1 for r in rows if r["refs"])
    print(f"{len(rows)} 個特別版，{n_ref} 個有實物照")
    print(f"輸出 {OUT.relative_to(ROOT)}（{OUT.stat().st_size / 1024 / 1024:.1f} MB，圖已內嵌）")


if __name__ == "__main__":
    main()
