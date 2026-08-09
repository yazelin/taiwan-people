#!/usr/bin/env python3
"""把 data/counties.json 同步進 index.html 的 SPLIT 常數。

index.html 是單檔靜態站，資料得內嵌。改完 counties.json 一定要跑這支，
否則網頁上的內容會停在舊資料。
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
d = json.loads((ROOT / "data" / "counties.json").read_text(encoding="utf-8"))
# 只同步通用版（沒有 culture 欄的那些）。指名族群的造型是同一個縣市底下的另一張圖，
# 地圖上仍然只有 22 個可點區域，直接倒進 SPLIT 會讓地圖與資料對不起來。
split = {
    c["name"]: {"b": c["base"], "places": c["places"], "foods": c["foods"],
                "traits": c["traits"], "quote": c["quote"]}
    for c in d["counties"] if c.get("base") and not c.get("culture")
}
# 特別版：有 culture 欄的那些造型，掛在所屬縣市底下。
# 這裡刻意帶出 culture 的 id 與族名——網頁上必須標明是哪一族並連到依據，
# 不標族名等於用一族代表整個縣市（AGENTS.md 硬規則一之一）。
costume = json.loads((ROOT / "data" / "costume.json").read_text(encoding="utf-8"))
peoples = {x["id"]: x for x in costume["peoples"]}
variants = {}
for c in d["counties"]:
    if not c.get("culture") or not c.get("base"):
        continue
    p_ = peoples.get(c["culture"])
    variants.setdefault(c["county"], []).append(
        {"b": c["base"], "label": (p_ or {}).get("name", c["culture"]), "culture": c["culture"]})

p = ROOT / "index.html"
s = p.read_text(encoding="utf-8")
s2, n = re.subn(r"const SPLIT=\{.*?\};\n",
                "const SPLIT=" + json.dumps(split, ensure_ascii=False) + ";\n",
                s, count=1, flags=re.S)
assert n == 1, "在 index.html 找不到 SPLIT 常數"

# 那排花名清單也由資料產生。原本硬寫在 index.html 裡，
# 結果跟畫面對不起來——它寫台南是蝴蝶蘭，實際畫在頭上的是鳳凰花。
flowers = [[c["name"], c["scene"]["flower_shown"]]
           for c in d["counties"] if not c.get("culture")]
s2, m = re.subn(r"const HAIR_FLOWERS=\[.*?\];",
                "const HAIR_FLOWERS=" + json.dumps(flowers, ensure_ascii=False) + ";",
                s2, count=1, flags=re.S)
assert m == 1, "在 index.html 找不到 HAIR_FLOWERS 常數"

s2, k = re.subn(r"const VARIANTS=\{.*?\};\n",
                "const VARIANTS=" + json.dumps(variants, ensure_ascii=False) + ";\n",
                s2, count=1, flags=re.S)
assert k == 1, "在 index.html 找不到 VARIANTS 常數"

p.write_text(s2, encoding="utf-8")
print(f"已同步 {len(split)} 個縣市與 {len(flowers)} 筆髮花：{'、'.join(split)}")
print(f"特別版 {sum(len(v) for v in variants.values())} 筆："
      + "；".join(f"{k}→" + "、".join(x["label"] for x in v) for k, v in variants.items()))
