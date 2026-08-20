#!/usr/bin/env python3
"""把 data/*.json 裡「自己寫的說明文字」抽出來跑 speak-tw。

    python3 tools/check_prose.py

為什麼不直接 `speak-tw --public data/*.json`：那樣會連驗收清單一起掃，而
清單裡的「A 是不是 X，不是 Y」正是資訊本身：Y 是這個系列真的畫錯過的形制
（鄒族的袖子被畫成整條藍袖、賽夏的雷女紋被畫成紅底白紋、客家的直布釦被
畫成盤扣）。那個對比句刪掉，清單就退化成沒有鑑別力的形容詞。
speak-tw 的放行記號要寫在該行，而 JSON 字串裡寫什麼都會顯示在網頁上，
所以只能用範圍來區分，區分的規則就寫在這裡。

掃的（自己寫的敘述，看得到也讀得懂的那種）：
  counties.json  _fields 的說明、各縣市的 notes／todo／scene.costume_basis
  costume.json   _note、_disclaimer、_fields 的說明、_redlines 的標題與內文

不掃的：
  checklist                     驗收題目，理由如上
  motifs／palette／rank／variants／system／material
                                引用來源的轉錄，改寫等於誤引
  outfit／accessories／hair 等   給模型看的英文
"""
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEAK = pathlib.Path.home() / "speak-tw" / "bin" / "speak-tw"


def collect():
    out = []
    c = json.loads((ROOT / "data" / "counties.json").read_text(encoding="utf-8"))
    out += [f"counties._fields.{k}｜{v}" for k, v in (c.get("_fields") or {}).items()
            if isinstance(v, str)]
    for x in c["counties"]:
        for k in ("notes", "todo"):
            out += [f"counties.{x['id']}.{k}｜{s}" for s in (x.get(k) or [])]
        for holder in (x, x.get("scene") or {}):
            b = holder.get("costume_basis")
            if isinstance(b, str) and b.strip():
                out.append(f"counties.{x['id']}.costume_basis｜{b}")

    p = json.loads((ROOT / "data" / "costume.json").read_text(encoding="utf-8"))
    for k in ("_note", "_disclaimer"):
        if isinstance(p.get(k), str):
            out.append(f"costume.{k}｜{p[k]}")
    out += [f"costume._fields.{k}｜{v}" for k, v in (p.get("_fields") or {}).items()
            if isinstance(v, str)]
    for i, r in enumerate(p.get("_redlines") or [], 1):
        out.append(f"costume._redlines[{i}].title｜{r.get('title', '')}")
        out.append(f"costume._redlines[{i}].body｜{r.get('body', '')}")
    # 一筆一行：speak-tw 回報行號，行號要對得回一筆資料才找得到要改哪裡
    return [s.replace("\n", " ") for s in out]


def main():
    if not SPEAK.exists():
        sys.exit(f"找不到 {SPEAK}，先 git clone speak-tw 並跑 install.sh")
    lines = collect()
    with tempfile.TemporaryDirectory() as d:
        f = pathlib.Path(d) / "prose.txt"
        f.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"抽出 {len(lines)} 段自己寫的說明文字")
        sys.exit(subprocess.run([str(SPEAK), "--public", str(f)]).returncode)


if __name__ == "__main__":
    main()
