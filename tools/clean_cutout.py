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

    # 2) 白邊：貼著背景那一圈又白又不飽和的不透明像素，就是沒清掉的白底。
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

    # 4) 碎屑：一定要放在最後。
    # 原本這段排在白邊之前，結果清白邊時把細髮絲切斷，切出來的新碎片沒人清——
    # 「清過」的檔案碎片反而從 76 塊變成 128 塊，貼在深色底上就是一片白點。
    # 只留最大的連通區塊，等於把所有斷掉的碎屑一次收乾淨。
    op = A > 40 / 255
    lab, n = ndimage.label(op)
    if n > 1:
        sz = ndimage.sum(op, lab, range(1, n + 1))
        main = int(np.argmax(sz)) + 1
        frag = (lab > 0) & (lab != main)
        report["碎屑"] = f"{n - 1} 塊／{int(frag.sum()):,} 像素，已清"
        A[frag] = 0
    else:
        report["碎屑"] = "沒有"

    out = np.dstack([rgb, A * 255]).astype(np.uint8)
    return Image.fromarray(out, "RGBA"), report


def tidy_hair(im, radius=4.0, feather=1.5, keep_ratio=0.35):
    """削掉比 radius 還細的突出，用來收掉毛燥的飛散髮絲。

    為什麼不是用上面那段距離淡出：那段處理的是「半透明的斷髮」，
    但 ref-half.png 這類圖的飛髮是**實心畫出來的**，半透明像素幾乎全在
    離實心區 1px 的抗鋸齒邊上，--fade 60 等於完全不作用（實測過）。
    細的突出用形態學開運算才削得到。

    只削細突出、不動主體：開運算保留得住比 radius 粗的任何東西，所以
    髮團本身、髮簪金珠、花、手指都在。實測半徑 4 削掉的像素有 96% 落在
    畫面上方三分之一，就是那圈毛。

    削完要羽化，否則邊緣會變成剪刀剪過的硬邊。
    """
    a = np.asarray(im).astype(float)
    A = a[..., 3]
    solid = A > 128
    r = int(round(radius))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    st = (yy ** 2 + xx ** 2) <= r * r
    keep = ndimage.binary_opening(solid, st)
    # 開運算會把主體邊緣也削掉一圈，補回來：只在「原本就不透明」的範圍內取聯集
    keep = ndimage.binary_dilation(keep, st) & solid
    # 再閉一次填平缺口。少了這步輪廓會有鋸齒感，像被鋸齒剪刀剪過——
    # 因為每根髮絲的根部被削掉後，會在髮團邊緣留下一個小凹口。
    keep = ndimage.binary_closing(keep, st) & solid
    removed = int((solid & ~keep).sum())
    soft = ndimage.gaussian_filter(keep.astype(float), feather)
    # keep_ratio=0 是整根拿掉，頭髮會變成一塊硬邊的實心團，不像頭髮。
    # 留一點才對：細髮絲改成降低不透明度，看得到但不張揚。
    factor = soft + (1.0 - soft) * keep_ratio
    a[..., 3] = A * np.clip(factor, 0, 1)
    return Image.fromarray(a.astype(np.uint8)), removed


def tidy_hair_flatbg(im, radius=4.0, feather=1.5, keep_ratio=0.35, tol=12):
    """face.png 這種「沒有 alpha、平底色」的圖也要能收髮絲。

    它是 RGB、背景是一片很平的灰（實測 211,210,210，標準差 0.7）。
    做法一樣是形態學開運算找出細突出，但不是改 alpha，而是把那些像素
    往背景色混過去——反正最後也是要融回同一個灰，連 un-matte 都省了。
    """
    a = np.asarray(im.convert("RGB")).astype(float)
    h, w, _ = a.shape
    bg = np.median(a[:40, :40].reshape(-1, 3), axis=0)
    fg = np.abs(a - bg).max(axis=2) > tol
    r = int(round(radius))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    st = (yy ** 2 + xx ** 2) <= r * r
    keep = ndimage.binary_opening(fg, st)
    keep = ndimage.binary_dilation(keep, st) & fg
    keep = ndimage.binary_closing(keep, st) & fg
    faded = int((fg & ~keep).sum())
    soft = ndimage.gaussian_filter(keep.astype(float), feather)
    k = np.clip(soft + (1.0 - soft) * keep_ratio, 0, 1)[..., None]
    out = a * k + bg * (1 - k)
    return Image.fromarray(out.astype(np.uint8)), faded, bg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--far", type=float, default=140.0, help="超過這個距離的髮絲清掉")
    ap.add_argument("--fade", type=float, default=60.0, help="這個距離內完全保留")
    ap.add_argument("--tidy-hair", type=float, default=0.0, metavar="R",
                    help="收掉比 R 像素還細的突出（毛燥髮絲）。4 是實測合用的值，0 為不做")
    ap.add_argument("--strand-keep", type=float, default=0.35, metavar="K",
                    help="細髮絲保留多少不透明度。0=整根拿掉（頭髮會變成硬塊，不要用）、"
                         "0.3~0.55 之間是看得到但不毛燥、1=不處理")
    ap.add_argument("--only-hair", action="store_true",
                    help="只做 --tidy-hair，跳過 un-matte／白邊／碎屑／飛髮淡出。"
                         "圖已經手工去背過就用這個——un-matte 重跑一次會把抗鋸齒邊的顏色再推一次")
    args = ap.parse_args()

    if args.only_hair:
        im, rep = Image.open(args.src).convert("RGBA"), {}
    else:
        im, rep = clean(args.src, args.far, args.fade)
    if args.tidy_hair > 0:
        im, n = tidy_hair(im, args.tidy_hair, keep_ratio=args.strand_keep)
        rep[f"淡化的細髮絲（半徑 {args.tidy_hair:g}px、保留 {args.strand_keep:g}）"] = n
    # --only-hair 不重裁：那是拿來修既有資產的，畫布一變就跟原檔對不齊，
    # 沒辦法逐像素驗「臉有沒有被動到」，下游引用它的尺寸也會跟著漂。
    if not args.only_hair:
        bb = im.getbbox()      # 清完可能又空出邊，順手再裁一次
        im = im.crop(bb)
    im.save(args.dst)
    for k, v in rep.items():
        print(f"  {k}：{v}")
    print(f"  輸出 {args.dst} {im.size}")


if __name__ == "__main__":
    main()
