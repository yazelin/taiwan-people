#!/usr/bin/env python3
"""抓移民署每月的新住民統計，存原文、產 data/newcomers.json。

為什麼要有這支：網站上「住一起」那一行的數字不是我寫的，是移民署統計表上的。
每個月都會更新，用手抄遲早抄錯，而且抄了也沒人能驗。
這支跑完會留下兩個東西——原始表格的存檔（data/sources/immigration/）
與網站要用的摘要（data/newcomers.json），兩邊對得起來。

跑法：
    python3 tools/fetch_immigration_stats.py          # 抓最新一期
    python3 tools/fetch_immigration_stats.py 11506    # 指定民國年月

抓完記得跑 tools/sync_split.py，數字才會進 index.html。

口徑（很重要，寫文案前先看）：
  這張表算的是「新住民」＝婚姻移民，不含移工。移工是另一套統計（勞動部與移民署
  的外僑居留表），人更多但居留性質完全不同，不要混在一起講。
  外裔外籍配偶裡有一部分已經歸化取得我國國籍，法律上就是國民，不是外國人。
"""
import json
import pathlib
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIST_URL = "https://www.immigration.gov.tw/5385/7344/7350/8887/?alias=settledown"
ARCHIVE = ROOT / "data" / "sources" / "immigration"
T = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"

# 表上是「臺」，repo 一律用「台」（counties.json 的 name 就是台）。
FIX = {"臺": "台"}
ORIGINS = ["越南", "印尼", "泰國", "菲律賓", "柬埔寨", "日本", "韓國", "其他"]


def get(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    return raw if binary else raw.decode("utf-8", "replace")


def latest_period():
    """從列表頁挑最新一期的民國年月，例如 11506。"""
    found = re.findall(r"配偶人數按證件分(\d{5})\.ods", get(LIST_URL))
    if not found:
        raise SystemExit("列表頁找不到 ODS 連結，頁面可能改版了")
    return max(found)


def rows_of(ods_bytes):
    """把 ODS 攤成一列一個 list[str]。repeat 要真的展開，否則欄位會錯位。"""
    with zipfile.ZipFile(ods_bytes) as z:
        root = ET.fromstring(z.read("content.xml"))
    out = []
    for row in root.iter(T + "table-row"):
        cells = []
        for c in row.iter(T + "table-cell"):
            txt = "".join(c.itertext()).strip().replace("　", "")
            rep = int(c.get(T + "number-columns-repeated", "1"))
            cells += [txt] * min(rep, 64)   # 尾端的空白 repeat 動輒上千，截掉
        while cells and cells[-1] == "":
            cells.pop()
        if cells:
            out.append(cells)
    return out


def num(s):
    """統計表用「－」表示無資料。"""
    s = s.replace(",", "").strip()
    return 0 if s in ("", "－", "-", "…") else int(s)


def norm(name):
    for a, b in FIX.items():
        name = name.replace(a, b)
    return name


def parse(rows):
    """兩張表：前半按證件分（歸化／居留），後半按國籍分。"""
    # 標題與期別不一定落在第一欄（表頭前面有空白欄），所以整列找
    head2 = next(i for i, r in enumerate(rows)
                 if any(c.startswith("各縣市外裔、外籍配偶人數按國籍分") for c in r))
    period = next(c for r in rows for c in r if c.endswith("底") and "年" in c)

    def body(chunk):
        return [r for r in chunk
                if r and re.fullmatch(r"總計|未詳|.{2,3}[市縣]", r[0]) and len(r) > 20]

    by_doc, by_origin = {}, {}
    for r in body(rows[:head2]):
        # 0 區域別 1 總計 2-4 外籍配偶計男女 5-7 歸化 8-10 外僑居留 11 65歲以上 12-14 陸港澳
        by_doc[norm(r[0])] = {
            "total": num(r[1]), "foreign_spouse": num(r[2]),
            "naturalized": num(r[5]), "residence_permit": num(r[8]),
            "prc_hk_macau": num(r[12]),
        }
    for r in body(rows[head2:]):
        # 國籍分後面還跟著一張「按國籍與性別分」，欄位不同但同樣過得了篩選，
        # 所以只認每個縣市第一次出現的那一列（＝按國籍分那張）。
        if norm(r[0]) in by_origin:
            continue
        # 人數與百分比交錯：1 總計 2 外籍合計 4 越南 6 印尼 …… 18 其他 22 大陸 24 港澳
        by_origin[norm(r[0])] = {
            **{k: num(r[4 + 2 * i]) for i, k in enumerate(ORIGINS)},
            "大陸": num(r[22]), "港澳": num(r[24]),
        }

    out = {}
    for k, doc in by_doc.items():
        o = by_origin[k]
        # 兩張表對不起來就是欄位錯位了，寧可炸掉也不要寫出錯的數字
        assert doc["naturalized"] + doc["residence_permit"] == doc["foreign_spouse"], k
        assert doc["foreign_spouse"] + doc["prc_hk_macau"] == doc["total"], k
        assert sum(o[x] for x in ORIGINS) == doc["foreign_spouse"], k
        assert o["大陸"] + o["港澳"] == doc["prc_hk_macau"], k
        out[k] = {**doc, "by_origin": o}
    assert sum(v["total"] for k, v in out.items() if k != "總計") == out["總計"]["total"]
    return period, out


def main():
    period = sys.argv[1] if len(sys.argv) > 1 else latest_period()
    fname = f"外籍配偶人數按證件分與國籍分{period}"
    url = next((m for m in re.findall(r'href="(/media/\d+/[^"]+\.ods)"', get(LIST_URL))
                if period in m), None)
    if not url:
        raise SystemExit(f"列表頁找不到 {period} 這一期")
    url = "https://www.immigration.gov.tw" + urllib.parse.quote(url)

    import io
    rows = rows_of(io.BytesIO(get(url, binary=True)))
    label, data = parse(rows)

    ARCHIVE.mkdir(parents=True, exist_ok=True)
    tsv = ARCHIVE / f"{fname}.tsv"
    tsv.write_text(
        f"# 來源：內政部移民署　{label}\n# 網址：{url}\n"
        f"# 抓取日期：{date.today()}　抓法：直接讀 ODS 轉 TSV，沒有經過任何改寫\n"
        + "\n".join("\t".join(r) for r in rows) + "\n", encoding="utf-8")

    y, m = int(period[:3]) + 1911, int(period[3:])
    (ROOT / "data" / "newcomers.json").write_text(json.dumps({
        "_note": "各縣市新住民（婚姻移民）人數。數字全部出自 source 那張表，"
                 "不要手改；要更新就跑 tools/fetch_immigration_stats.py。"
                 "本檔不含移工——移工不是婚姻移民，居留性質不同，混在一起講會失準。",
        "_fields": {
            "total": "新住民合計",
            "foreign_spouse": "外裔、外籍配偶（不含大陸港澳）",
            "naturalized": "其中已歸化取得我國國籍者，法律上為中華民國國民",
            "residence_permit": "其中仍持外僑居留證或永久居留證者",
            "prc_hk_macau": "大陸、港澳地區配偶",
            "by_origin": "外裔外籍配偶按原屬國籍分，加上大陸與港澳",
        },
        "as_of": f"{y}-{m:02d}",
        "period": label,
        "source": {"agency": "內政部移民署",
                   "table": "外籍配偶人數與大陸（含港澳）配偶人數統計",
                   "period": label,
                   # 給人點的是統計專頁，不是直接丟一個 ODS 下載
                   "url": LIST_URL, "file": url,
                   "archive": f"data/sources/immigration/{fname}.tsv",
                   "fetched": str(date.today())},
        "total": data["總計"],
        "counties": {k: v for k, v in data.items() if k not in ("總計", "未詳")},
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    t = data["總計"]
    print(f"{label}：新住民 {t['total']:,} 人"
          f"（外裔外籍 {t['foreign_spouse']:,}，其中已歸化 {t['naturalized']:,}；"
          f"大陸港澳 {t['prc_hk_macau']:,}）")
    print(f"存檔 {tsv.relative_to(ROOT)}，摘要 data/newcomers.json")
    print("接著跑 tools/sync_split.py，數字才會進 index.html")


if __name__ == "__main__":
    import urllib.parse
    main()
