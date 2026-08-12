#!/usr/bin/env python3
"""清理角色去背後殘留的白邊、碎屑與飛散髮絲。

    python3 tools/clean_cutout.py <輸入.png> <輸出.png> [--far 140] [--fade 60]

為什麼需要這支：角色是從白底上去背的，留下三種東西——

  1. 半透明像素還混著白背景（un-matte 沒做），貼到藍天上髮絲會鑲一圈白邊
  2. 76 塊完全脫離人物的碎屑，在天空裡就是一點一點的白斑
  3. 飛得特別遠的斷髮，讓髮型外圍看起來毛燥

三件事都能用幾何判斷處理，不必重新生圖——重生圖會換掉臉，那是這個專案踩過的坑。

做法：
  白邊  對 0<alpha<1 的像素做 un-matte：影像是 C = α·C_真 + (1-α)·白，
        反推 C_真 = (C - (1-α)·255) / α。這是去白底的標準解，不是調色。
  碎屑  連通區塊只留最大的那塊（人物本體），其餘全部清掉。
  飛髮  從「實心區」做距離變換，距離 <fade 的完全保留，fade→far 之間線性淡出，
        超過 far 清掉。實心區用 alpha>200 認定，所以手、衣服都算實心，不會被削到。
"""
import argparse
import pathlib

import numpy as np
from PIL import Image
from scipy import ndimage


def clean(src, far=140.0, fade=60.0):
    im = Image.open(src).convert("RGBA")
    a = np.asarray(im).astype(float)
    rgb, A = a[..., :3], a[..., 3] / 255.0
    report = {}

    # 1) un-matte：把混在半透明像素裡的白背景扣掉
    semi = (A > 0.02) & (A < 0.98)
    report["半透明像素"] = int(semi.sum())
    al = A[semi][:, None]
    rgb[semi] = np.clip((rgb[semi] - (1 - al) * 255.0) / al, 0, 255)

    # 2) 碎屑：只留最大的連通區塊
    op = A > 40 / 255
    lab, n = ndimage.label(op)
    if n > 1:
        sz = ndimage.sum(op, lab, range(1, n + 1))
        main = int(np.argmax(sz)) + 1
        frag = (lab > 0) & (lab != main)
        report["碎屑塊數"] = n - 1
        report["碎屑像素"] = int(frag.sum())
        A[frag] = 0
    else:
        report["碎屑塊數"] = report["碎屑像素"] = 0

    # 2.5) 白邊：貼著背景那一圈又白又不飽和的不透明像素，就是沒清掉的白底。
    # 只清「邊界上」的，所以白T、帆布袋的內部一格都不會動到。
    op = A > 40 / 255
    edge = op & ~ndimage.binary_erosion(op, np.ones((3, 3)))
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    halo = edge & (mn > 195) & ((mx - mn) < 30)
    report["白邊像素"] = int(halo.sum())
    A[halo] = 0

    # 3) 飛髮：這張的 alpha 幾乎是二值的（半透明只有一千多點），髮絲本身就是實心，
    # 拿 alpha 高低分不出「頭」跟「一根飛出去的髮」。改用形狀：開運算把細的東西吃掉，
    # 剩下的是頭、手、衣服這些粗的部位；再從那裡量距離。
    op = A > 40 / 255
    r = 5
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    disk = (xx ** 2 + yy ** 2) <= r * r
    mass = ndimage.binary_opening(op, disk)
    dist = ndimage.distance_transform_edt(~mass)
    # 只動「細」的：粗的部位一格都不碰，臉、手、衣服不可能被削到。
    # 再加一條「暗」：髮絲是深褐到黑，金穗子與亮色配件不會落進來。
    thin = op & ~mass
    dark = rgb.max(axis=2) < 130
    target = thin & dark & (dist > fade)
    k = np.ones_like(A)
    k[target] = np.clip((far - dist[target]) / (far - fade), 0, 1)
    before = A.sum()
    A = A * k
    report["飛髮"] = (f"細的 {int(thin.sum()):,} 像素，其中暗且離頭 >{fade:.0f}px 的 "
                     f"{int(target.sum()):,} 淡出（總不透明量 -{(1 - A.sum() / before) * 100:.1f}%）")

    out = np.dstack([rgb, A * 255]).astype(np.uint8)
    return Image.fromarray(out, "RGBA"), report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--far", type=float, default=140.0, help="超過這個距離的髮絲清掉")
    ap.add_argument("--fade", type=float, default=60.0, help="這個距離內完全保留")
    args = ap.parse_args()

    im, rep = clean(args.src, args.far, args.fade)
    bb = im.getbbox()          # 清完可能又空出邊，順手再裁一次
    im = im.crop(bb)
    im.save(args.dst)
    for k, v in rep.items():
        print(f"  {k}：{v}")
    print(f"  輸出 {args.dst} {im.size}")


if __name__ == "__main__":
    main()
