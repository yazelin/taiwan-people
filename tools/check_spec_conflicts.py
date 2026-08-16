#!/usr/bin/env python3
"""檢查同一個部位在規格裡有沒有被講兩次、而且講法互斥。

    python3 tools/check_spec_conflicts.py          # 檢查全部特別版
    python3 tools/check_spec_conflicts.py --self   # 自我檢查（拿已知答案的字串校準）

為什麼要有這支：2026-08-16 排灣那張畫成漢式立領盤扣短衫，跟同系列的客家圖幾乎同款。
根因不是模型，是規格自己寫壞——講參考照的段落寫 standing collar、
講衣服本體的段落寫 round neck，同一個部位兩種說法。
**衝突時模型會選比較常見的那個先驗，不會選比較正確的那個。**

這種錯是靜默的：規格讀起來很完整，要跑完一輪生圖（三到四分鐘）才發現。
事前掃一遍便宜得多。

侷限：靠關鍵詞比對，只抓得到列在 GROUPS 裡的部位。它是提醒不是保證，
報出來的每一筆都要自己讀過再判。跑出 0 筆不等於規格沒問題。
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# 同一個部位的互斥講法。同組匹配到兩種以上就要人來看一眼。
# outfit 是英文、checklist 是中文，同一個部位在兩邊各講各的正是要抓的東西，
# 所以每一組都要中英兩套講法。
GROUPS = {
    "領型": [r"standing collar|立領", r"round neck(line)?|圓領", r"cross(ed|-over)? collar|交領",
             r"V-neck", r"collarless"],
    "固定方式": [r"frog button|盤扣", r"\bbutton|釦子(?!是)", r"cloth tie|布綁帶|綁帶",
                 r"\btie[sd]? (it|the|shut)"],
    # below／past the knee 是同一件事的兩種說法，合成一個 pattern，不然自己跟自己衝突
    "衣長": [r"(below|past) the knee|過膝", r"waist-length|及腰", r"above the knee|膝上"],
    "袖": [r"tube sleeve|筒袖", r"sleeveless|no sleeve|無袖", r"cuff turned back|袖口反折"],
    "腰": [r"belt at the waist|腰帶", r"sash|腰繩", r"apron|圍裙", r"NOTHING at the waist|腰間無帶"],
}

# 出現這些就當作是「明講不要畫」，不算一種主張
NEG = ("not ", "no ", "never", "forbidden", "nor ", "without",
       "instead of", "rather than", "avoid", "must not",
       "不是", "沒有", "不可", "不要", "不能", "禁止", "非", "而不", "別")

# 往前找到句首才判否定，不是固定字數。
# 禁止項常寫成「FORBIDDEN: a; b; c; d」，用固定窗口的話排在後面的項目
# 就看不到那個 FORBIDDEN，整串禁止項會被誤報成主張。
# 分號不算句子邊界——它正是列舉禁止項時用的符號
SENT_START = re.compile(r"[.\n。]")


def scan(text):
    """回傳 {部位: {講法, ...}}，只收同組出現兩種以上的。"""
    out = {}
    for group, pats in GROUPS.items():
        found = set()
        for pat in pats:
            for m in re.finditer(pat, text, re.I):
                bounds = [b.end() for b in SENT_START.finditer(text, 0, m.start())]
                before = text[bounds[-1] if bounds else 0:m.start()].lower()
                if not any(k in before for k in NEG):
                    found.add(pat)
        if len(found) > 1:
            out[group] = found
    return out


def self_check():
    """拿已知答案的字串校準。

    第一次跑這支時是拿 git HEAD 當負控制，但那段矛盾文字還沒 commit，
    HEAD 裡根本沒有，於是「改前改後都乾淨」的結果毫無意義。
    校準要餵真的有問題的字串，不是餵一個碰巧沒問題的版本。
    """
    bad = ("Take from the photographs ONLY the CUT: the standing collar, the way the front "
           "edge runs diagonally. LONG GARMENT: a long tunic with a round neck.")
    good = ("Take from the photographs ONLY the CUT: the low ROUND neckline. "
            "FORBIDDEN: a STANDING COLLAR of any height. "
            "the neckline is a plain LOW ROUND opening with NO collar standing up from it.")
    assert "領型" in scan(bad), "校準失敗：抓不到已知的立領／圓領矛盾"
    assert "領型" not in scan(good), "校準失敗：修好的版本被誤報"

    # 短字串過關不代表真實規格也過關——上面那兩個字串曾經通過，
    # 而同一份程式在幾千字的 outfit 上卻什麼都抓不到。
    # 所以再拿真的規格注入一句競爭主張，確認長文字下也抓得到。
    counties = json.loads((ROOT / "data" / "counties.json").read_text(encoding="utf-8"))
    c = next(x for x in counties["counties"] if x["name"] == "屏東縣・排灣族")
    s = c["scene"]
    real = " ".join(x for x in (s.get("outfit"), s.get("accessories"), s.get("hair")) if x)
    anchor = "LONG GARMENT (lungpau)"
    assert anchor in real, "校準用的錨點不在排灣規格裡了，請改這支的 self_check"
    for group, sentence in [("領型", "The tunic has a standing collar."),
                            ("腰", "She wears a belt at the waist."),
                            ("衣長", "It is a waist-length jacket.")]:
        injected = real.replace(anchor, sentence + " " + anchor)
        assert group in scan(injected), f"校準失敗：真實規格注入「{sentence}」後仍抓不到{group}矛盾"

    # 跨檔案、跨語言的那種：outfit 是英文的「圓領」，checklist 是中文的「立領」。
    # 這正是 2026-08-16 實際發生過、而只掃 counties.json 抓不到的那一種。
    assert "領型" in scan(real + " 長衣的骨架對不對：立領、筒袖"), \
        "校準失敗：中文清單裡的「立領」對上英文規格的 round neck，應該要抓得到"
    print("自我檢查通過：矛盾版抓得到、修好版不誤報、"
          "真實規格注入三種競爭主張都抓得到、中英跨檔案矛盾也抓得到")


def main():
    if "--self" in sys.argv:
        return self_check()
    self_check()          # 每次正式跑之前先確認掃描器自己是對的
    counties = json.loads((ROOT / "data" / "counties.json").read_text(encoding="utf-8"))
    costume = json.loads((ROOT / "data" / "costume.json").read_text(encoding="utf-8"))
    peoples = {p["id"]: p for p in costume["peoples"]}
    bad = 0
    for c in counties["counties"]:
        if not c.get("culture"):
            continue
        s = c["scene"]
        # 驗收清單也要一起掃。2026-08-16 排灣的 outfit 改成「低圓領無立領」，
        # 但 costume.json 的 checklist 還留著「立領」，vision 就拿舊清單判了一條假 NG。
        # 規格與清單分在兩個檔案，只掃一邊等於沒掃。
        checks = " ".join(peoples.get(c["culture"], {}).get("checklist") or [])
        text = " ".join(x for x in (s.get("outfit"), s.get("accessories"), s.get("hair"), checks) if x)
        hits = scan(text)
        if hits:
            bad += 1
            print(f"\n■ {c['name']}")
            for g, f in hits.items():
                print(f"   {g}：同時主張 {'、'.join(sorted(f))}")
    n = sum(1 for c in counties["counties"] if c.get("culture"))
    print(f"\n掃過 {n} 個特別版，{bad} 個有疑似矛盾"
          + ("（每一筆都要自己讀過再判，關鍵詞比對會誤報）" if bad else ""))



if __name__ == "__main__":
    main()
