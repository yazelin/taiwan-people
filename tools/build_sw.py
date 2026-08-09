#!/usr/bin/env python3
"""依 precache 清單的內容 hash 產生 sw.js 的 SHELL 版號。

手動 bump 版號的遲早會忘，而忘記的症狀最惡劣：**瀏覽器根本不知道有新版**，
使用者永遠停在舊頁，沒有任何徵兆，本機測也測不出來（本機沒有舊 SW）。

所以版號不由人寫，由這支腳本從檔案內容算出來。改完 HTML／JSON／icon 就跑一次：

    python3 tools/build_sw.py

它只動 sw.js 裡 SHELL_V 那一行。ASSET_V 是手動的，因為底圖採「換內容就換檔名」
的慣例，同名檔內容變動很少見；真的變了再自己 bump。
"""
import hashlib
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SW = ROOT / "sw.js"

src = SW.read_text(encoding="utf-8")
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

ver = "shell-" + h.hexdigest()[:7]
new, n = re.subn(r'const SHELL_V = "[^"]*";', f'const SHELL_V = "{ver}";', src, count=1)
if n != 1:
    sys.exit("在 sw.js 裡找不到 SHELL_V")

if new == src:
    print(f"版號未變：{ver}（precache 的檔案內容都沒動）")
else:
    SW.write_text(new, encoding="utf-8")
    print(f"SHELL_V → {ver}（{len(files)} 個檔）")
