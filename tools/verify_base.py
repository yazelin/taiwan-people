#!/usr/bin/env python3
"""量測底圖是否符合版面規格。縮圖目視不算驗證，這裡量的是會出事的三件事。

    python3 tools/verify_base.py            # 檢查所有已存在的底圖
    python3 tools/verify_base.py 苗栗縣      # 只檢查一個

三個判準的由來：
- 文字區的亮度與局部起伏：文字是深藍色加白光暈，底圖太暗或太雜就讀不到。
  苗栗第三版的右下量到 0.48／0.050，就是模型在那裡放了一片近景暗樹林。
- 人物橫向範圍：規格是佔寬 38%、不越過中線。苗栗第一版只有 26%（太小），
  第四版衝到 59%（越線）。兩種都要擋。
"""
import json
import pathlib
import sys

import numpy as np
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = json.loads((ROOT / "data" / "counties.json").read_text(encoding="utf-8"))

# 文字區：不是猜的，是用 Playwright 量瀏覽器裡 .split-top / .split-side 的實際
# getBoundingClientRect，再換算回原圖座標（卡片是 object-fit:cover，左右各裁掉約 3%）。
# 原本猜成 y 72–90%，但那裡根本沒有文字，害兩張好圖被判不合格。
# 門檻分區：縣市名是粗體大字＋強白光暈，實測 0.54 的藍天上依然清楚，所以放寬；
# 文字塊裡有小標籤（走一趟／吃一輪／XX，代表了），那才是會先看不見的東西。
ZONES = [("縣市名", .58, .93, .03, .13, 0.42),
         ("文字塊", .58, .93, .18, .49, 0.55)]
# 右側細節的上限從 0.030 放寬到 0.055。
# 原本要求右側 40% 幾乎無細節，結果 22 張畫面都變得空洞——
# 「留白」被我做成了「空白」。實測右側最豐富的候選（澎湖 02、新竹市 04）
# 反而最好看，而文字只要加一層很淡的漸層就完全讀得到。
# 可讀性該用合成手段解決，不是靠犧牲畫面。
MAX_VAR = 0.055

# 右側 40% 的結構下限。上面那個 MAX_VAR 是上限（太雜，文字讀不到），
# 一直缺的是下限（太空，畫面空洞）。AGENTS.md 第六條「留白是安靜，不是空」
# 說了很久，但沒有東西在量它，所以四張空的一路留到現在。
#
# 0.010 不是猜的：22 張實測，最低四張是 0.0031/0.0038/0.0043/0.0051，
# 次低的一批從 0.0122 起跳，中間有兩倍以上的斷層，門檻放在斷層裡。
# 目視也同意：那四張右側有大片沒有內容的霧，其餘 18 張都看得出是什麼地方。
#
# 量的是右側 40% 整個高度、16×16 區塊亮度標準差的中位數。用中位數是因為
# 少數幾個高對比物件（一根桅杆、一隻鳥）不該讓整片空白過關。
MIN_DETAIL = 0.010


def measure(path):
    a = np.asarray(Image.open(path).convert("RGB"), float)
    H, W, _ = a.shape
    lum = (.2126 * a[..., 0] + .7152 * a[..., 1] + .0722 * a[..., 2]) / 255
    out = []
    for name, x0, x1, y0, y1, floor in ZONES:
        r = lum[int(y0 * H):int(y1 * H), int(x0 * W):int(x1 * W)]
        b = r[:r.shape[0] // 8 * 8, :r.shape[1] // 8 * 8].reshape(r.shape[0] // 8, 8, -1, 8)
        out.append((name, r.mean(), float(np.median(b.std(axis=(1, 3)))), floor))
    # 人物橫向範圍：縱向邊緣強度沿 x 的分布，取超過門檻的最右緣
    g = np.abs(np.diff(lum, axis=1))
    col = g.mean(axis=0)
    idx = np.where(col > col.mean() + col.std() * .5)[0]
    right = (idx.max() / W) if len(idx) else 0.0
    # 右側 40% 有沒有東西。刻意不只量文字帶——文字帶本來就該安靜，
    # 「缺乏景色」是整片右側的問題，只量文字帶會漏掉「上半真空、下半有山」那種。
    rz = lum[:, int(.60 * W):]
    rh, rw = rz.shape
    rb = rz[:rh // 16 * 16, :rw // 16 * 16].reshape(rh // 16, 16, -1, 16)
    detail = float(np.median(rb.std(axis=(1, 3))))
    return out, right, detail


def main():
    want = sys.argv[1:] or None
    bad = 0
    for c in DATA["counties"]:
        if want and c["name"] not in want:
            continue
        # 高雄的檔名是 kh-base 不是 kaohsiung-base，一律讀資料裡的 base 欄位
        p = ROOT / "img" / f"{c.get('base') or c['id'] + '-base'}.webp"
        if not p.exists():
            continue
        zones, right, detail = measure(p)
        probs = [f"{n.strip()} 亮度{l:.2f}" for n, l, v, f in zones if l < f]
        probs += [f"{n.strip()} 起伏{v:.3f}" for n, l, v, f in zones if v > MAX_VAR]
        if detail < MIN_DETAIL:
            probs.append(f"右側太空 {detail:.4f}<{MIN_DETAIL}")
        # 「右緣」這個指標已停用，只保留數字供參考。
        # 它本來要量「人物延伸到多右」，實際量的是「邊緣密度超過門檻的最右一欄」——
        # 舊的美術方向要求右側留空，那個數字才約等於人物邊界。
        # 改成「右側可以有內容」之後，它量到的是背景：苗栗與台中的好候選都被判 73%。
        # 而它想防的事（人物擋到文字）已經由文字區的亮度與起伏兩個指標涵蓋。
        mark = "✔" if not probs else "✘"
        if probs:
            bad += 1
        cols = "  ".join(f"{n}{l:.2f}/{v:.3f}" for n, l, v, f in zones)
        print(f"{mark} {c['name']:<4}{cols}  右側{detail:.4f}  右緣 {right:.0%}"
              + ("   ← " + "、".join(probs) if probs else ""))
    print(f"\n不合格 {bad} 張" if bad else "\n全部通過")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
