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
split = {
    c["name"]: {"b": c["base"], "places": c["places"], "foods": c["foods"],
                "traits": c["traits"], "quote": c["quote"]}
    for c in d["counties"] if c.get("base")
}
p = ROOT / "index.html"
s = p.read_text(encoding="utf-8")
s2, n = re.subn(r"const SPLIT=\{.*?\};\n",
                "const SPLIT=" + json.dumps(split, ensure_ascii=False) + ";\n",
                s, count=1, flags=re.S)
assert n == 1, "在 index.html 找不到 SPLIT 常數"
p.write_text(s2, encoding="utf-8")
print(f"已同步 {len(split)} 個縣市：{'、'.join(split)}")
