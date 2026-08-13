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
# 新住民人數。這一欄不是文案是統計，由 tools/fetch_immigration_stats.py 抓來，
# 網頁上「住一起」那一行直接顯示原始數字，不做四捨五入也不改寫。
nc = json.loads((ROOT / "data" / "newcomers.json").read_text(encoding="utf-8"))


def newcomers(name):
    c = nc["counties"].get(name)
    if not c:
        return None
    # 「其他」是統計上的殘差桶，不是一個地方，列進來會讀成「有 2,540 人來自其他」
    top = sorted(((k, v) for k, v in c["by_origin"].items() if k != "其他"),
                 key=lambda kv: -kv[1])
    return {"t": c["total"], "n": c["naturalized"],
            "top": [[k, v] for k, v in top[:3] if v]}


split = {
    c["name"]: {"b": c["base"], "places": c["places"], "foods": c["foods"],
                "traits": c["traits"], "quote": c["quote"],
                "nc": newcomers(c["name"])}
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

s2, j = re.subn(r"const NC_SRC=\{.*?\};\n",
                "const NC_SRC=" + json.dumps(
                    # 表名寫全稱會在版面上佔掉兩行小字，這裡只給單位與期別，
                    # 全稱與完整期間留在 data/newcomers.json 與存檔的 TSV 裡。
                    # 期別一定要帶起始年與「累計」兩個字：那張表是 76 年起的累計申請人數，
                    # 原本寫「截至 115 年 6 月」會被讀成現住人口，差了將近四十年的存量。
                    {"table": nc["source"]["agency"] + "統計",
                     "period": "%s 年至 %s 年 %d 月累計" % (
                         nc["period"].split("年")[0],
                         int(nc["as_of"][:4]) - 1911, int(nc["as_of"][5:])),
                     "url": nc["source"]["url"]},
                    ensure_ascii=False) + ";\n",
                s2, count=1, flags=re.S)
assert j == 1, "在 index.html 找不到 NC_SRC 常數"

s2, k = re.subn(r"const VARIANTS=\{.*?\};\n",
                "const VARIANTS=" + json.dumps(variants, ensure_ascii=False) + ";\n",
                s2, count=1, flags=re.S)
assert k == 1, "在 index.html 找不到 VARIANTS 常數"

p.write_text(s2, encoding="utf-8")
print(f"已同步 {len(split)} 個縣市與 {len(flowers)} 筆髮花：{'、'.join(split)}")
print(f"新住民數字 {nc['period']}，共 {nc['total']['total']:,} 人")
print(f"特別版 {sum(len(v) for v in variants.values())} 筆："
      + "；".join(f"{k}→" + "、".join(x["label"] for x in v) for k, v in variants.items()))
