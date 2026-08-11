#!/usr/bin/env python3
"""從候選裡挑一張裝上去。

    python3 tools/pick.py 桃園市 03
    python3 tools/pick.py 桃園市 03 --note "壩體最清楚，遠山層次也最好"

配合 review/index.html 使用：在那頁看到更好的候選，記下編號用這支換上。
換完會自動跑量測與同步，並重建審查頁。
"""
import json
import pathlib
import shutil
import subprocess
import sys

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
GEN = pathlib.Path("/tmp/taiwan-people-gen")


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    name, no = sys.argv[1], sys.argv[2].zfill(2)
    note = None
    if "--note" in sys.argv:
        note = sys.argv[sys.argv.index("--note") + 1]

    data = json.loads((ROOT / "data" / "counties.json").read_text(encoding="utf-8"))
    c = next((x for x in data["counties"] if x["name"] == name), None)
    if not c:
        sys.exit(f"找不到縣市：{name}")

    src = GEN / f"{c['id']}-base.cand" / f"{no}.png"
    if not src.exists():
        avail = sorted(p.stem for p in (GEN / f"{c['id']}-base.cand").glob("*.png"))
        sys.exit(f"找不到候選 {no}。{name} 現有的候選：{'、'.join(avail) or '無'}")

    # 用 get 不用索引：還沒生出底圖的特別版本來就沒有 base 欄（那是「排進生成佇列」的表示法），
    # 而第一次挑候選正好就是那種狀態，寫成 c["base"] 會 KeyError。
    dst = ROOT / "img" / f"{c.get('base') or c['id'] + '-base'}.webp"
    # 換掉之前先備份現用的那張，挑錯了還能換回來
    bak = ROOT / "review" / "replaced"
    bak.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        shutil.copy(dst, bak / f"{c['id']}-{dst.stat().st_mtime_ns}.webp")
    Image.open(src).convert("RGB").save(dst, "WEBP", quality=88, method=5)
    print(f"{name} 已換成候選 {no}")

    if note:
        np_ = ROOT / "review" / "notes.json"
        notes = json.loads(np_.read_text(encoding="utf-8")) if np_.exists() else {}
        notes[f"{c['id']}-{no}"] = note
        np_.write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")

    for cmd in (["python3", "tools/verify_base.py", name],
                ["python3", "tools/sync_split.py"],
                ["python3", "tools/review.py"]):
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        out = (r.stdout or r.stderr).strip().splitlines()
        if out:
            print("  " + out[0])


if __name__ == "__main__":
    main()
