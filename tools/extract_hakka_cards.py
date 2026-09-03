#!/usr/bin/env python3
"""把客委會調查報告第三篇的 200 張文物記錄表抽成結構化資料。

    python3 tools/extract_hakka_cards.py

讀 data/sources/hakka/《台灣客家服飾民間收藏調查研究》…txt（由
archive_sources.py 存的原文），寫 data/sources/hakka/文物記錄表.json。

為什麼要有這一支：這 200 張卡是這個 repo 目前唯一一份**第一手**的
客家服飾實物資料，有丈量、材質、釦數、年代與來源地點，而且每一張在
原 PDF 上都配一張照片。先前 repo 的結論是「北客大襟衫找不到可用的
實物照」，那是因為這份報告存檔存成了 PDF 位元組、從來沒被讀進來。

登錄編號的前綴就是分群：NH＝北部客家，其餘見產出檔的 _note。
"""
import json
import pathlib
import re
import unicodedata

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "data" / "sources" / "hakka"
OUT = SRC_DIR / "文物記錄表.json"

# 一張卡的欄位：欄名 → 抽到下一個欄名為止。欄名在 pdftotext 的輸出裡
# 字間會夾空白（「名    稱」），所以逐字之間允許空白。
FIELDS = ["登錄編號", "性別", "年齡", "名稱", "用途", "年代", "材質", "色彩",
          "來源地點", "提供者", "尺寸", "釦子數量", "特別描述", "備註",
          "文物簡述"]


def loose(name: str) -> str:
    """「名稱」→「名\\s*稱」，容得下 pdftotext 補進欄名裡的空白。"""
    return r"\s*".join(re.escape(c) for c in name)


FIELD_RE = re.compile("|".join(f"(?:{loose(f)})" for f in FIELDS))


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip(" ：:")


def parse_card(blk: str) -> dict:
    """把一張卡切成欄位。用欄名當切點，兩個欄名之間的就是值。"""
    hits = list(FIELD_RE.finditer(blk))
    card = {}
    for i, m in enumerate(hits):
        key = re.sub(r"\s+", "", m.group(0))
        end = hits[i + 1].start() if i + 1 < len(hits) else len(blk)
        val = clean(blk[m.end():end])
        # 原文欄名是「提供者／收藏家」，這裡只用「提供者」當切點，
        # 剩下的「／收藏家」會留在值的開頭，要去掉
        if key == "提供者":
            val = re.sub(r"^[／/]\s*收藏家\s*", "", val)
        # 同一欄名只取第一次出現的（文物簡述內文可能再提到欄名）
        if key not in card and val:
            card[key] = val
    return card


def main() -> None:
    src = next(SRC_DIR.glob("《台灣客家服飾民間收藏調查研究》*.txt"), None)
    if src is None:
        raise SystemExit("找不到報告原文，先跑 tools/archive_sources.py")
    # 原文已由 archive_sources.py 正規化過，這裡再做一次是為了讓這支腳本
    # 拿舊檔或別處的抽出文字也能跑：相容性漢字會讓所有字面比對靜靜失效。
    # 只換 U+F900–U+FAFF，整份 NFKC 會把全形標點換掉，那就不是原文了。
    text = "".join(
        unicodedata.normalize("NFKC", c) if "\uf900" <= c <= "\ufaff" else c
        for c in src.read_text("utf-8")
    )

    # 有三張卡（151-153）漏印「號」字，所以 號 要可有可無
    marks = list(re.finditer(r"(200-\d{3})\s*號?(?=\s*\n)", text))
    cards = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        blk = text[m.end():end]
        # 卡與卡之間夾著頁碼與表頭，切掉才不會混進欄位值
        blk = blk.split("台灣客家服飾民間收藏調查研究表")[0]
        # 卡片末尾黏著該頁的頁碼，那不是欄位內容。只切結尾單獨成行的數字，
        # 不能對每個欄位一律去尾數：登錄編號本身就以數字結尾（NH 016）
        blk = re.sub(r"\n\s*\d{1,3}\s*$", "", blk.rstrip())
        card = {"編號": m.group(1)}
        card.update(parse_card(blk))
        cards.append(card)

    out = {
        "_note": "客委會《台灣客家服飾民間收藏調查研究》（鄭惠美，2007）第三篇"
                 "調查文物記錄表，200 件。由 tools/extract_hakka_cards.py 從"
                 "data/sources/hakka/ 的報告原文抽出，欄位與用字照原文，未經改寫。"
                 "原 PDF 上每一張卡都配一張文物照片，這裡只有文字。",
        "_source": "https://cloud.hakka.gov.tw/Attachment/1/841717122771.pdf",
        "_group_prefix": {
            "NH": "北部客家（桃竹苗）",
            "SH": "六堆（南部）",
        },
        "_caveat": "登錄編號的前綴是依原文照抄，未經驗證；分群請以「來源地點」為準。"
                    "原報告自己有一處編號重複：兩張不同的童帽都印成 200-135，"
                    "所以卡數是 201 而不是 200。這是原文的狀況，沒有改。",
        "count": len(cards),
        "cards": cards,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"寫出 {OUT.relative_to(ROOT)}：{len(cards)} 張")

    miss = [c["編號"] for c in cards if "來源地點" not in c]
    if miss:
        print(f"沒抽到來源地點的（{len(miss)}）：{'、'.join(miss)}")


if __name__ == "__main__":
    main()
