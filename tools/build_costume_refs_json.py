#!/usr/bin/env python3
"""把 data/costume-refs/SOURCES.md 的表格轉成 data/costume-refs.json。

    python3 tools/build_costume_refs_json.py

為什麼要有這支：那些實物照要公開展示在網站上，而 CC BY-SA 與 CC BY-NC 的
**姓名標示是法律條件**——每一張都得看得到作者與授權。那些資訊原本只寫在
SOURCES.md 的表格裡（給人看的），網頁讀不到。

不把資料改寫成 JSON 手動維護，是因為那會變成兩份事實來源，遲早不同步。
SOURCES.md 仍然是唯一要編輯的地方，這支只負責轉檔。

表格有「同上」的繼承寫法（同一件藏品的多張裁圖只在第一列寫出處），
轉檔時要展開，否則網頁上會出現「出處：同上」這種對外看不懂的字。
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "costume-refs" / "SOURCES.md"
OUT = ROOT / "data" / "costume-refs.json"

LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def main():
    rows, prev = {}, {}
    for line in SRC.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| `"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        fn = cells[0].strip("`")
        desc, src, holder, lic = cells[1], cells[2], cells[3], cells[4]
        # 「同上」繼承前一列——**而「前一列」是位置相依的**。
        # 2026-08-17 踩過：鄒族的 01 與 02、03 在表格裡不相鄰，中間隔著排灣與客家五列，
        # 於是 02、03 的「同上」繼承到客家那筆，公開頁上把國史館的客家藏品
        # 標成了鄒族參考照的出處。圖本身是對的，錯的是授權標示——而那是法律條件。
        # 所以擋一道：檔名的族群前綴（第一個 - 之前）必須跟被繼承的那列相同。
        group = fn.split("-")[0]
        if "同上" in (src, holder, lic) and prev.get("group") not in (None, group):
            raise SystemExit(
                f"FAIL: `{fn}` 寫「同上」，但上一列是 `{prev.get('fn')}`，"
                f"分屬不同族群（{group} ≠ {prev.get('group')}）。\n"
                "「同上」只繼承緊鄰的上一列，同一件藏品的各張裁圖必須排在一起。\n"
                "把這一列搬到同組後面，或者把出處寫全。")
        src = prev.get("src", src) if src == "同上" else src
        holder = prev.get("holder", holder) if holder == "同上" else holder
        lic = prev.get("lic", lic) if lic == "同上" else lic
        prev = {"src": src, "holder": holder, "lic": lic, "group": group, "fn": fn}

        m = LINK.search(src)
        rows[fn] = {
            "desc": desc,
            "source": m.group(1) if m else re.sub(r"\[|\]|\(.*?\)", "", src),
            "url": m.group(2) if m else "",
            "holder": holder,
            "license": lic,
        }

    # 登記了卻沒有任何一族在用的照片，一定要寫明「為什麼不用」。
    # 2026-08-20 掃出來的：鄒族收了 7 張，只餵 2 張，另外 5 張是達邦社與特富野社的，
    # 形制跟本站採用的那件互斥（V 領＋袖口多層織帶 vs 短外套全素＋另接袖套）。
    # 停用是對的，但當時沒留下任何記號——下次有人覺得「參考照太少」就會整包加回去，
    # 而互斥的照片一起餵進去，模型只能自己混，怎麼重跑都對不了。
    used = set()
    for c in json.loads((ROOT / "data" / "counties.json").read_text(encoding="utf-8"))["counties"]:
        for r in c.get("scene", {}).get("costume_refs", []) or []:
            used.add(pathlib.Path(r).name)
    silent = [fn for fn in rows if fn not in used and "【未使用" not in rows[fn]["desc"]]
    if silent:
        raise SystemExit(
            "FAIL: 這些照片登記在 SOURCES.md，但沒有任何一族在用，也沒寫明為什麼不用：\n  "
            + "\n  ".join(sorted(silent))
            + "\n在描述欄補一句【未使用：理由】，或者把它加進某一族的 scene.costume_refs。")

    have = {p.name for p in (ROOT / "data" / "costume-refs").glob("*.jpg")}
    missing = have - rows.keys()
    orphan = rows.keys() - have
    if missing:
        raise SystemExit("FAIL: 這些檔案在 costume-refs/ 但 SOURCES.md 沒有登記，"
                         "公開展示前一定要補（授權標示是法律條件）：\n  "
                         + "\n  ".join(sorted(missing)))
    if orphan:
        print("警告：SOURCES.md 有登記但檔案不存在：" + "、".join(sorted(orphan)))

    OUT.write_text(json.dumps({
        "_note": "由 tools/build_costume_refs_json.py 從 data/costume-refs/SOURCES.md 產生，"
                 "不要手改。要改出處或授權請改 SOURCES.md 再重跑。",
        "refs": rows,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(rows)} 張實物照的出處與授權已轉出 → {OUT.relative_to(ROOT)}")
    lics = {}
    for v in rows.values():
        lics[v["license"]] = lics.get(v["license"], 0) + 1
    for k, n in sorted(lics.items(), key=lambda x: -x[1]):
        print(f"  {n:>2} 張　{k}")


if __name__ == "__main__":
    main()
