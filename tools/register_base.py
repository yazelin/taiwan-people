#!/usr/bin/env python3
"""把已經產出並驗收過的底圖登記回 data/counties.json 的 base 欄位。

只登記 img/<id>-base.webp 真的存在的縣市——沒有檔案就不寫，
避免資料宣稱有底圖但實際上沒有。
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
P = ROOT / "data" / "counties.json"
d = json.loads(P.read_text(encoding="utf-8"))

added, missing = [], []
for c in d["counties"]:
    if not c.get("id"):
        continue
    f = ROOT / "img" / f"{c['id']}-base.webp"
    if f.exists():
        if c.get("base") != f"{c['id']}-base":
            c["base"] = f"{c['id']}-base"
            added.append(c["name"])
    elif not c.get("base"):
        missing.append(c["name"])

P.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"新登記 {len(added)} 個：{'、'.join(added) if added else '無'}")
print(f"仍缺底圖 {len(missing)} 個：{'、'.join(missing) if missing else '無'}")
print("\n記得同步 index.html 的 SPLIT 常數：python3 tools/sync_split.py")
