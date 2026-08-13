#!/usr/bin/env python3
"""抓原民會每月的原住民人口數，存原文、產 data/indigenous.json。

為什麼要有這支：population.html 上各縣市的原住民人口不是我寫的，是原民會統計表上的。
跟新住民那支同一個道理——手抄遲早抄錯，而且抄了也沒人能驗。

跑法：
    python3 tools/fetch_indigenous_stats.py          # 抓最新一期
    python3 tools/fetch_indigenous_stats.py 11506    # 指定民國年月

口徑（很重要，寫文案前先看）：
  一、這張表算的是「依《原住民身分法》登記者」，是法律身分不是族群認同。
      《平埔原住民族群身分法》民國 114 年 10 月 17 日三讀通過，西拉雅等 9 個平埔
      原住民族群已提出申請、審議中，尚未完成認定，所以**不在這個數字裡**。
      本 repo 的 data/sources/pingpu/ 已經收了西拉雅的資料，寫台南的文案時要一起講。
  二、這是戶籍統計不是現住統計。都市原住民大量設籍在新北、桃園、台中。
  三、一個縣市一個數字說不出是哪一族。花蓮那個數字底下是六族。
      不要拿它當「某族有多少人」用，那要另一張按族別分的表。
  四、**不要跟新住民的數字相加或直接比大小。** 新住民那張是 76 年起的累計申請人數，
      這張是現住登記人口，兩種量根本不同。只能各講各的。

原民會的網站擋掉沒有 token 的直連（回「不好意思! 不可以這樣連網站喔」），
所以下載網址一定要從公告頁的 href 整串帶走，不能自己拼。
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
LIST_URL = ("https://www.cip.gov.tw/zh-tw/news/data-list/"
            "940F9579765AC6A0/index.html?cumid=940F9579765AC6A0")
ARCHIVE = ROOT / "data" / "sources" / "cip"
T = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"

# 表上是「臺」，repo 一律用「台」（counties.json 的 name 就是台）
FIX = {"臺": "台"}
# 要的是縣市層級那張，不是鄉鎮市區、也不是按族別分的那幾張
WANT = "台閩縣市原住民族人口-按性別年齡"


def get(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    return raw if binary else raw.decode("utf-8", "replace")


def find_release(period=None):
    """在公告列表挑一期，回傳（民國年月, 公告頁網址）。"""
    html = get(LIST_URL)
    found = []
    for href, y, m in re.findall(
            r'<a href="([^"]*-info\.html[^"]*)"[^>]*>.{0,400}?'
            r'【(\d{4})年】(\d{1,2})月原住民族人口數統計資料', html, re.S):
        found.append((f"{int(y) - 1911}{int(m):02d}", href))
    if not found:
        raise SystemExit("列表頁找不到任何一期，頁面可能改版了")
    if period:
        hit = next((x for x in found if x[0] == period), None)
        if not hit:
            raise SystemExit(f"列表第一頁沒有 {period} 這一期，有的是："
                             + "、".join(x[0] for x in found[:6]))
    else:
        hit = max(found)
    base = LIST_URL.rsplit("/", 1)[0] + "/"
    return hit[0], urllib.parse.urljoin(base, hit[1])


def find_ods(info_url):
    """公告頁上同一筆附件有 xls 與 ods 兩個連結，檔名只掛在 xls 那個 title 上，
    兩者共用同一個 T-XXXXXXXX 檔號，所以先用檔名認出檔號、再去撈 ods 的完整網址。
    網址後面那串 s / c / fn 是必要的，缺了會被擋。"""
    html = get(info_url)
    ids = [m for u, name, m in
           ((u, name, re.search(r"/(T-\d+)\.xls", u)) for u, name in
            re.findall(r'<a href="([^"]+\.xls[^"]*)"[^>]*title="下載檔案:([^"]+)"', html))
           if WANT in name and m]
    if not ids:
        raise SystemExit(f"公告頁上找不到「{WANT}」這個附件")
    fid = ids[0].group(1)
    ods = re.search(r'href="([^"]*' + fid + r'\.ods[^"]*)"', html)
    if not ods:
        raise SystemExit(f"{fid} 只有 xls 沒有 ods，這支只吃 ods")
    return ods.group(1).replace("&amp;", "&")


def rows_of(ods_bytes):
    """把 ODS 攤成一列一個 list[str]。repeat 要真的展開，否則欄位會錯位。"""
    root = ET.fromstring(zipfile.ZipFile(ods_bytes).read("content.xml"))
    out = []
    for row in root.iter(T + "table-row"):
        cells = []
        for c in row.iter(T + "table-cell"):
            txt = "".join(c.itertext()).strip().replace("　", "")
            rep = int(c.get(T + "number-columns-repeated", "1"))
            cells += [txt] * min(rep, 64)
        while cells and cells[-1] == "":
            cells.pop()
        if cells:
            out.append(cells)
    return out


def num(s):
    s = s.replace(",", "").strip()
    return 0 if s in ("", "－", "-", "…") else int(s)


def norm(name):
    for a, b in FIX.items():
        name = name.replace(a, b)
    return name


def parse(rows):
    """這張表疊了三個區塊：不分平地山地、平地原住民、山地原住民，
    每個區塊都把 22 縣市重跑一遍。要的是第一個區塊，
    抓錯區塊不會報錯、只會少一半人，所以用區塊標題切、不要用列號。"""
    head = next(i for i, r in enumerate(rows) if r and r[0] == "不分平地山地")
    end = next((i for i, r in enumerate(rows)
                if i > head and r and r[0] in ("平地原住民", "山地原住民")), len(rows))
    period = next(c for r in rows for c in r if re.search(r"中華民國\d+年\d+月底", c))

    # 表上除了 22 個縣市，還夾著「臺灣省」「福建省」兩列小計。
    # 不剔掉的話 22 縣市相加會變成 100 萬（多算了省小計那 36 萬與 1,797）
    GROUPS = {"總計", "台灣省", "福建省"}

    out = {}
    for r in rows[head + 1:end]:
        # 0 區域別 1 性別 2 總計。男女各一列，只要「計」
        if len(r) < 3 or r[1] != "計":
            continue
        out[norm(r[0])] = num(r[2])
    if "總計" not in out:
        raise SystemExit("第一個區塊裡沒有總計那一列，表格版型可能改了")
    counties = {k: v for k, v in out.items() if k not in GROUPS}
    assert len(counties) == 22, f"縣市數 {len(counties)} 不是 22：{list(counties)}"
    # 縣市相加要等於總計。對不起來就是切錯區塊或漏列，寧可炸掉也不要寫出錯的數字
    assert sum(counties.values()) == out["總計"], \
        f"縣市相加 {sum(counties.values()):,} != 總計 {out['總計']:,}"
    return re.search(r"中華民國\d+年\d+月底", period).group(), out["總計"], counties


def main():
    want = sys.argv[1] if len(sys.argv) > 1 else None
    period, info_url = find_release(want)
    url = find_ods(info_url)

    import io
    rows = rows_of(io.BytesIO(get(url, binary=True)))
    label, total, counties = parse(rows)

    fname = f"{period}台閩縣市原住民族人口-按性別年齡"
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    tsv = ARCHIVE / f"{fname}.tsv"
    tsv.write_text(
        f"# 來源：原住民族委員會　{label}\n# 公告頁：{info_url}\n"
        f"# 抓取日期：{date.today()}　抓法：直接讀 ODS 轉 TSV，沒有經過任何改寫\n"
        + "\n".join("\t".join(r) for r in rows) + "\n", encoding="utf-8")

    y, m = int(period[:3]) + 1911, int(period[3:])
    (ROOT / "data" / "indigenous.json").write_text(json.dumps({
        "_note": "各縣市原住民人口數。數字全部出自 source 那張表，不要手改；"
                 "要更新就跑 tools/fetch_indigenous_stats.py。"
                 "這是依原住民身分法登記的現住人口，不含審議中的平埔原住民族群，"
                 "也不要跟新住民那份累計申請數相加或比大小。",
        "_caveats": [
            "依《原住民身分法》登記者，是法律身分不是族群認同",
            "《平埔原住民族群身分法》114 年 10 月 17 日三讀，西拉雅等 9 個族群"
            "已提出申請、審議中，尚未完成認定，不在這個數字裡",
            "戶籍統計不是現住統計，都市原住民設籍地與居住地可能不同",
            "一個縣市一個數字說不出是哪一族，花蓮那個數字底下是六族",
        ],
        "as_of": f"{y}-{m:02d}",
        "period": label,
        "source": {"agency": "原住民族委員會",
                   "table": "台閩縣市原住民族人口－按性別年齡（不分平地山地）",
                   "period": label,
                   "url": info_url, "file": url,
                   "archive": f"data/sources/cip/{fname}.tsv",
                   "fetched": str(date.today())},
        "total": total,
        "counties": counties,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"{label}：原住民 {total:,} 人，{len(counties)} 個縣市")
    print(f"存檔 {tsv.relative_to(ROOT)}，摘要 data/indigenous.json")


if __name__ == "__main__":
    import urllib.parse
    main()
