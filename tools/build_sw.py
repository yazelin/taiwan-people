#!/usr/bin/env python3
"""依 precache 清單的內容 hash 產生 sw.js 的 SHELL 版號。

手動 bump 版號的遲早會忘，而忘記的症狀最惡劣：**瀏覽器根本不知道有新版**，
使用者永遠停在舊頁，沒有任何徵兆，本機測也測不出來（本機沒有舊 SW）。

所以版號不由人寫，由這支腳本從檔案內容算出來。改完 HTML／JSON／icon 就跑一次：

    python3 tools/build_sw.py

它動 sw.js 裡的 SHELL_V 那一行，以及 ASSET_LIST（離線包清單，由 counties.json 產生
——那份清單手抄的話，新增一個特別版就會靜靜地漏在離線包外），還有 ASSET_V。

ASSET_V 本來是手動的，理由寫著「底圖採換內容就換檔名的慣例，同名檔內容變動很少見」。
那個前提是錯的：2026-08-13 查出來，光那兩天就有 12 個檔沿用原檔名換掉內容
（噶瑪蘭、太魯閣、賽夏、阿美、排灣、泰雅、屏東、宜蘭的底圖，加上首圖兩次），
而 ASSET_V 從建站起一次都沒 bump 過。圖走 cache-first，所以回訪者看到的
全都還是舊圖——包括那些修正過的服飾。這正是本檔開頭說的那種最惡劣的症狀：
沒有徵兆，本機也測不出來。所以 ASSET_V 也改成從內容算。

代價要知道：任何一張圖換內容，整份離線包的快取都會被丟掉重抓（13MB）。
比起讓人看到錯的服飾，這個代價值得。
"""
import hashlib
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SW = ROOT / "sw.js"

src = SW.read_text(encoding="utf-8")
orig = src
m = re.search(r"const PRECACHE = \[(.*?)\];", src, re.S)
if not m:
    sys.exit("在 sw.js 裡找不到 PRECACHE 清單")
files = re.findall(r'"([^"]+)"', m.group(1))

h = hashlib.sha256()
missing = []
for f in files:
    p = ROOT / ("index.html" if f == "./" else f)
    if not p.exists():
        missing.append(f)
        continue
    h.update(f.encode())
    h.update(p.read_bytes())
if missing:
    sys.exit(f"precache 清單裡有檔案不存在：{'、'.join(missing)}\n"
             f"清單錯了就修清單，不要讓它靜靜地裝不起來。")

# 這支腳本算的是**工作區**的內容，但部署出去的是**commit 進去**的內容。
# 只要 precache 清單裡有檔案還沒 commit，算出來的版號就對應不到將來部署的那份，
# 而症狀完全沒有徵兆：本機一切正常，線上使用者卻永遠停在舊版。
# 這個坑實際踩過一次——data/counties.json 當時在清單裡且有未 commit 的改動。
dirty = subprocess.run(["git", "diff", "--name-only", "--"] + [
    ("index.html" if f == "./" else f) for f in files],
    cwd=ROOT, capture_output=True, text=True).stdout.split()
if dirty:
    sys.exit("precache 清單裡有檔案還沒 commit：" + "、".join(dirty) + "\n"
             "先 commit 再產版號，否則算出來的版號對應不到部署出去的內容。\n"
             "（真的要先看版號，可以 git stash 之後再跑，但別把結果 commit 進去。）")

# 離線包清單：所有底圖 + 音檔。這些不進 precache（9.8MB），
# 使用者按「下載離線包」才暖，但清單得跟著 counties.json 走。
counties = json.loads((ROOT / "data" / "counties.json").read_text(encoding="utf-8"))["counties"]
assets = [f"img/{c['base']}.webp" for c in counties if c.get("base")]
assets += [str(a.relative_to(ROOT)) for a in sorted((ROOT / "audio").glob("*.mp3"))]
gone = [a for a in assets if not (ROOT / a).exists()]
if gone:
    sys.exit("counties.json 指到不存在的底圖：" + "、".join(gone))
body = "\n".join(f'  "{a}",' for a in assets)
src, n = re.subn(r"const ASSET_LIST = \[.*?\];",
                 f"const ASSET_LIST = [\n{body}\n];", src, count=1, flags=re.S)
if n != 1:
    sys.exit("在 sw.js 裡找不到 ASSET_LIST")
mb = sum((ROOT / a).stat().st_size for a in assets) / 1e6
print(f"ASSET_LIST → {len(assets)} 個檔、{mb:.1f} MB")

# ASSET_V：拿版控裡所有圖與音檔的內容算。用 git ls-files 而不是 glob，
# 免得草稿版本（img/*-v2.webp 之類，.gitignore 擋掉的）也算進去，害版號亂跳。
tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files", "img", "audio"],
                         capture_output=True, text=True).stdout.split()
media = sorted(f for f in tracked
               if f.lower().endswith((".webp", ".png", ".jpg", ".jpeg", ".svg", ".mp3", ".m4a")))
ha = hashlib.sha256()
for f in media:
    ha.update(f.encode())
    ha.update((ROOT / f).read_bytes())
aver = "asset-" + ha.hexdigest()[:7]
src, n = re.subn(r'const ASSET_V = "[^"]*";', f'const ASSET_V = "{aver}";', src, count=1)
if n != 1:
    sys.exit("在 sw.js 裡找不到 ASSET_V")
print(f"ASSET_V → {aver}（{len(media)} 個圖與音檔）")

ver = "shell-" + h.hexdigest()[:7]
new, n = re.subn(r'const SHELL_V = "[^"]*";', f'const SHELL_V = "{ver}";', src, count=1)
if n != 1:
    sys.exit("在 sw.js 裡找不到 SHELL_V")

if new == src:
    print(f"版號未變：{ver}（precache 的檔案內容都沒動）")
else:
    print(f"SHELL_V → {ver}（{len(files)} 個檔）")
# 比對的是**最原始**的檔案內容。只比 new==src 的話，版號沒變但 ASSET_LIST 變了
# 就整份不寫出去，新增的特別版會靜靜地漏在離線包外。
if new != orig:
    SW.write_text(new, encoding="utf-8")
