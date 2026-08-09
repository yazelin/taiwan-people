#!/usr/bin/env python3
"""由 data/costume.json 產生 costume.html 的 JSON-LD。

那 50 筆 citation 是資料集裡最有說服力的東西，手抄一定會跟資料脫節——
改了 costume.json 卻忘了改 HTML，結構化資料就會宣稱一份不存在的出處清單。
所以跟 sync_split.py 一樣：資料是唯一事實來源，HTML 由腳本產生。

    python3 tools/build_ld.py

宣告成 Dataset 而不是 Article 是刻意的：這頁的內容是有引用來源的資料集，不是意見文章。
Dataset 才會帶出 creator / distribution / citation。
`disambiguatingDescription` 明寫它不宣稱權威，那不是自貶，是這個專案的立場。
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
k = json.loads((ROOT / "data" / "costume.json").read_text(encoding="utf-8"))
srcs = sorted(k["sources"].values(), key=lambda v: (v["kind"], v["org"]))

ld = {
    "@context": "https://schema.org",
    "@type": "Dataset",
    "name": "台灣族群傳統服飾資料集",
    "alternateName": "服飾依據 ─ 台灣人代表的創作資料庫",
    "description": (
        "台灣二十三個族群傳統服飾的整理資料：官方認定十六族原住民族、四個平埔族群、"
        "客家、閩南漢人與馬祖閩東。逐部位形制、群別差異、色彩、紋樣、階級規範，"
        "每一筆都對得回政府機關、公立博物館或政府委託之學術調查的原始出處。"
        "查證不到的內容不填補，直接記為缺口。"),
    "url": "https://yazelin.github.io/taiwan-people/costume.html",
    "inLanguage": "zh-Hant-TW",
    "keywords": ["台灣原住民族", "傳統服飾", "客家", "平埔族群", "織紋", "文化資產"],
    "creator": {"@type": "Person", "name": "林亞澤", "url": "https://yazelin.github.io/"},
    "isAccessibleForFree": True,
    "distribution": [{
        "@type": "DataDownload", "encodingFormat": "application/json",
        "contentUrl": "https://yazelin.github.io/taiwan-people/data/costume.json"}],
    "citation": [{
        "@type": "CreativeWork", "name": v["t"],
        "publisher": {"@type": "Organization", "name": v["org"]},
        "url": v["url"]} for v in srcs],
    "disambiguatingDescription": (
        "二手整理，整理者非族人，尚未經各族群代表或相關單位審閱。"
        "不宣稱權威或完整，僅提供可查證的起點。"),
}

p = ROOT / "costume.html"
s = p.read_text(encoding="utf-8")
# 出處標題或單位名稱裡只要出現 </script 或 <!--，就會把 script 區塊提早關掉、
# 把頁面弄壞，而且下一次跑這支腳本會連自己的區塊都比對不到。
# JSON 裡的 \u003c 跟 < 等價，跳脫掉不影響語意。
payload = json.dumps(ld, ensure_ascii=False, indent=2).replace("<", "\\u003c")
new, n = re.subn(r'(<script type="application/ld\+json">\n).*?(\n</script>)',
                 lambda m: m.group(1) + payload + m.group(2),
                 s, count=1, flags=re.S)
if n != 1:
    sys.exit("在 costume.html 裡找不到 JSON-LD 區塊")
p.write_text(new, encoding="utf-8")
print(f"JSON-LD 已同步：{len(ld['citation'])} 筆 citation、{len(k['peoples'])} 個族群")
print("改了 costume.html 記得跑 tools/build_sw.py 更新 SHELL 版號")
