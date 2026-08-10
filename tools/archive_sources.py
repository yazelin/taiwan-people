#!/usr/bin/env python3
"""把 costume.json 裡還沒存檔的來源抓一份原文進 data/sources/。

會這樣做是因為連結會爛，而且不是假設：這個 repo 引用過的
台灣原住民族資訊資源網（tipp.org.tw）與臺南市的兩個原民頁面，
在 2026 年 8 月實測時都已經回 410 Gone。只留網址，等於幾年後
沒有人能驗證我們寫的是不是真的。

    python3 tools/archive_sources.py            # 只補還沒存的
    python3 tools/archive_sources.py --force    # 全部重抓

抓法是直接讀網頁 HTML 再去標籤，沒有經過任何模型改寫，所以文字與
當時的原始頁面一致。**抓不到就明講**：純前端渲染的頁面用這種抓法
只會拿到一個空殼，那種情況下這支腳本會拒絕寫檔並列出來，由人另外
處理（例如用瀏覽器存渲染後的內容），而不是靜靜地存一份空的下來
假裝存過了。
"""
import argparse
import json
import pathlib
import re
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sources"

# source id 的前綴 → 存檔子目錄。由上往下比對，第一個對上的算數，所以順序有意義
# （`hakka` 要排在 `kcg-hakka` 之前會誤判，故長前綴先寫）。對不上的丟 misc/。
DIRS = [("nmns-", "nmns"), ("shungye-", "shungye"), ("om-", "openmuseum"),
        ("cip-", "cip"), ("aborgpedia-", "aborgpedia"),
        ("nmp-", "nmp"), ("kcg-hakka", "hakka"), ("hakka", "hakka"),
        ("th-", "han"), ("nmth-han", "han"),
        ("titic", "titic"), ("law-titic", "titic"),
        ("raptor-", "hawkeagle"), ("einfo-", "hawkeagle"),
        ("moc-matsu", "matsu"), ("matsu-", "matsu"), ("taitung-", "taitung"),
        # 平埔族群的資料散在各機關，但用途是同一件事，收在一起才找得到
        ("pingpu", "pingpu"), ("sinica-fanshe", "pingpu"), ("ianthro-siraya", "pingpu"),
        ("tainan-siraya", "pingpu"), ("tcmb-taivoan", "pingpu"), ("ntu-taivoan", "pingpu")]

# 低於這個字數就當作沒抓到內容。純前端渲染的頁面通常只回一個幾 KB 的空殼，
# 而空殼存下來比沒存更糟：看起來有存檔，實際上驗證不了任何東西。
MIN_CHARS = 400


def detag(html: str) -> str:
    html = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
    html = re.sub(r"<br\s*/?>|</(p|div|li|tr|h[1-6])>", "\n", html, flags=re.I)
    text = re.sub(r"<[^>]+>", "", html)
    for a, b in [("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                 ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")]:
        text = text.replace(a, b)
    lines = [l.strip() for l in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(l for l in lines if l))


def slug(s: str) -> str:
    return re.sub(r"[\s/\\:*?\"<>|]+", "_", s).strip("_")[:80]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="已存在的也重抓")
    args = ap.parse_args()

    sources = json.loads((ROOT / "data" / "costume.json").read_text("utf-8"))["sources"]
    added, skipped, thin, failed = [], [], [], []

    for sid, s in sources.items():
        sub = next((d for pre, d in DIRS if sid.startswith(pre)), "misc")
        path = OUT / sub / f"{slug(s['t'])}.txt"
        if path.exists() and not args.force:
            skipped.append(sid)
            continue
        try:
            req = urllib.request.Request(s["url"], headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=45) as r:
                raw = r.read().decode(r.headers.get_content_charset() or "utf-8", "replace")
        except Exception as e:  # noqa: BLE001 — 抓不到就記下來，不要中斷整批
            failed.append(f"{sid}：{e}")
            continue

        body = detag(raw)
        if len(body) < MIN_CHARS:
            thin.append(f"{sid}（{len(body)} 字）　{s['url']}")
            continue

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"來源：{s['org']} {s['t']}\nURL：{s['url']}\n\n{body}\n", "utf-8")
        added.append(f"{sub}/{path.name}")
        time.sleep(0.8)   # 別把對方的站打疼了

    print(f"新增 {len(added)}、已存在 {len(skipped)}")
    for a in added:
        print("  +", a)
    if thin:
        print(f"\n抓到的內容太少，沒有寫檔（{len(thin)} 筆）。原因通常是三種之一："
              f"純前端渲染（要用瀏覽器存渲染後的內容）、"
              f"網址已死但會轉址到首頁所以還回 200、"
              f"或者那根本是查詢介面而不是文件（那就不該當 source）：")
        for t in thin:
            print("  -", t)
    if failed:
        print(f"\n抓取失敗（{len(failed)} 筆）：")
        for f in failed:
            print("  -", f)
        sys.exit(1)


if __name__ == "__main__":
    main()
