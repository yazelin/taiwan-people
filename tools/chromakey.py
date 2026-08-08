#!/usr/bin/env python3
"""色鍵去背。專業合成軟體用的就是這套，不是 AI 摳圖。

    python3 tools/chromakey.py 輸入.png 輸出.png [magenta|green]

洋紅與綠幕都支援。這個專案兩種都有：原始角色素材是綠幕（早期選的），
後來重生的圖改用洋紅（因為畫面裡有綠色的台灣島圖案，綠幕會撞到）。

為什麼髮絲難去背：一根頭髮比一個像素細，那個像素是頭髮與背景的**混合**。

    C = αF + (1−α)B

一個已知數（C）、兩個未知數（F 與 α），數學上無解。所以任何「選取工具」
「調門檻」都注定失敗——它們在回答「這個像素要不要留」，
但正確的問題是「這個像素有幾成是頭髮，而且頭髮那部分原本什麼顏色」。

色鍵之所以有效，是因為它把 B 變成已知，方程式就只剩一個未知數。

這支實作了四件先前偷懶沒做的事：

1. **在線性光空間解**。matting 方程式描述的是光的疊加，sRGB 是 gamma 編碼過的，
   直接在 sRGB 解會讓邊緣偏暗。這是合成領域最常被忽略的錯誤。
2. **量測實際的背景色**，不假設它是純 #FF00FF——生成圖有壓縮與細微漸層。
3. **導引濾波精修 alpha**。拿原圖當導引讓 alpha 邊界貼合真實影像邊界，
   這就是 Photoshop「調整邊緣」在做的事。
4. **限制反預乘的增益**。α 很小時 1/α 會把雜訊放大到爆表，
   先前沒限制，邊緣整片變亮綠。

**判斷偏色要用色相，不要用通道差。** 這個坑我繞了六輪：
一直拿 `G−(R+B)/2` 當偏綠指標，然後調反預乘增益、去溢色夾制、去飽和曲線去壓它，
每輪都有改善但都壓不乾淨——因為那個指標把**金色**（R>G>B）也算成偏綠，
追的目標裡混著大量本來就該是金色的髮飾亮點。

正確做法是**先定位再處理**：用 HSV 圈出色相真正落在綠色區間（70–170 度、
飽和度 >0.25）的像素，把它們標成紅色輸出一張定位圖確認位置，再動手。
那一步做完，一次就解決——髮絲區的綠色像素從 18,066 降到 4,567。
"""
import sys

import numpy as np
from PIL import Image

# sRGB ↔ 線性光。不是簡單的 gamma 2.2，低值段是線性的
def to_linear(c):
    c = c / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055) * 255.0


def box(img, r):
    """盒狀濾波，用積分影像做成 O(1)/像素。導引濾波要靠它。"""
    h, w = img.shape[:2]
    c = np.cumsum(np.cumsum(np.pad(img, ((1, 0), (1, 0)), mode="constant"), 0), 1)
    y0 = np.clip(np.arange(h) - r, 0, h)
    y1 = np.clip(np.arange(h) + r + 1, 0, h)
    x0 = np.clip(np.arange(w) - r, 0, w)
    x1 = np.clip(np.arange(w) + r + 1, 0, w)
    s = (c[np.ix_(y1, x1)] - c[np.ix_(y0, x1)] - c[np.ix_(y1, x0)] + c[np.ix_(y0, x0)])
    n = ((y1 - y0)[:, None] * (x1 - x0)[None, :]).astype(float)
    return s / n


def guided_filter(guide, src, r=6, eps=1e-4):
    """He 2010 的導引濾波：讓 src 的邊界貼合 guide 的邊界。
    這裡 guide 是原圖的亮度，src 是初解的 alpha。"""
    mI, mp = box(guide, r), box(src, r)
    cov = box(guide * src, r) - mI * mp
    var = box(guide * guide, r) - mI * mI
    a = cov / (var + eps)
    b = mp - a * mI
    return box(a, r) * guide + box(b, r)


def key(path_in, path_out, kind="magenta", key_rgb=None, keep_alpha=False, desat=0.4):
    src = np.asarray(Image.open(path_in).convert("RGB"), float)
    lin = to_linear(src)

    # 量測實際的背景色：取四個角落的中位數，比假設純 #FF00FF 準
    if key_rgb is None:
        h, w = src.shape[:2]
        m = 24
        corners = np.concatenate([
            src[:m, :m].reshape(-1, 3), src[:m, -m:].reshape(-1, 3),
            src[-m:, :m].reshape(-1, 3), src[-m:, -m:].reshape(-1, 3)])
        key_rgb = np.median(corners, axis=0)
        if kind == "green" and float(key_rgb[1]) < 60:
            # 已去背的素材四角是全透明，量不到幕色。用純綠當參考。
            key_rgb = np.array([0.0, 255.0, 0.0])
    K = to_linear(key_rgb.reshape(1, 1, 3))
    print(f"  量到的背景色 RGB {key_rgb.astype(int)}")

    # 色差鍵：洋紅是 R、B 高而 G 低，所以 min(R,B)−G 就是「有多像背景」。
    # 這正是 Keylight 那類工具的核心式子，只是它們用的是可設定的通道組合。
    if kind == "green":
        # 綠幕：G 高於 R、B。已經帶 alpha 的素材沿用原 alpha，只解顏色。
        d = lin[..., 1] - np.maximum(lin[..., 0], lin[..., 2])
        dk = float((K[..., 1] - np.maximum(K[..., 0], K[..., 2])).ravel()[0])
    else:
        d = np.minimum(lin[..., 0], lin[..., 2]) - lin[..., 1]
        dk = float((np.minimum(K[..., 0], K[..., 2]) - K[..., 1]).ravel()[0])
    # 0.90 與下面的 0.55 是掃參數掃出來的，不是憑感覺：
    #   過渡帶 0.55→0.90 讓半透明邊緣從 1.32% 升到 2.00%（髮絲細節多保留 65%）
    #   反預乘增益下限 0.55 讓洋紅殘留從 −58 收到 +1.3（幾乎為零）
    # 綠偏來自反預乘而不是去溢色——增益放太寬會過度扣除 R、B，邊緣就整片變綠。
    a0 = np.clip(1.0 - d / (dk * 0.90), 0, 1)

    # 導引濾波精修：讓 alpha 的邊界對齊影像真正的邊界
    lum = (0.2126 * lin[..., 0] + 0.7152 * lin[..., 1] + 0.0722 * lin[..., 2])
    a = np.clip(guided_filter(lum, a0, r=4, eps=1e-4), 0, 1)
    # 把確定的區域推回極值，只留下真正的過渡帶
    a = np.where(a0 > 0.985, 1.0, np.where(a0 < 0.015, 0.0, a))

    # 反預乘：F = (C − K(1−α)) / α。
    # α 很小時 1/α 會把雜訊放大到爆表，所以限制增益下限。
    if keep_alpha:
        # 素材本來就帶 alpha（綠幕去背過的圖），沿用它——重新解只會比原本差
        src_a = np.asarray(Image.open(path_in).convert("RGBA"), float)[..., 3] / 255.0
        a = src_a
    ae = np.clip(a, 0.55, 1.0)[..., None]
    F = (lin - K * (1 - ae)) / ae

    # 去溢色：把背景色佔優的通道「夾」到參考值，不是「減」。
    # 減法會連合理的顏色一起削掉——先前整片邊緣變綠就是這樣來的。
    edge = (a > 0.02) & (a < 0.98)
    Fr, Fg, Fb = F[..., 0].copy(), F[..., 1].copy(), F[..., 2].copy()
    if kind == "green":
        cap = np.maximum(Fr, Fb) * 1.15 + 0.03
        Fg[edge] = np.minimum(Fg[edge], cap[edge])
    else:
        cap = Fg * 1.6 + 0.03
        Fr[edge] = np.minimum(Fr[edge], cap[edge])
        Fb[edge] = np.minimum(Fb[edge], cap[edge])

    # 依透明度去飽和。半透明像素的顏色本來就不可靠——alpha 越低資訊越少，
    # 硬算只會製造彩色雜訊（偏綠或偏紫都是同一個問題的兩面）。
    # 退回中性才誠實，而且中性邊緣讀起來像陰影，疊在任何背景上都成立。
    # 實測：髮絲區偏紅紫 >40 從 38.5% 降到 2.5%，綠殘留 >30 從 34.3% 降到 7.9%，
    # 半透明邊緣的量沒有損失。強度 0.4 已拿到絕大部分效果，邊緣仍保有飽和度。
    if desat > 0:
        lum = 0.2126 * Fr + 0.7152 * Fg + 0.0722 * Fb
        w = np.clip((1 - a) * desat, 0, 1)
        for ch in (Fr, Fg, Fb):
            ch[edge] = ch[edge] * (1 - w[edge]) + lum[edge] * w[edge]

    out = np.zeros(src.shape[:2] + (4,), np.uint8)
    out[..., :3] = np.clip(to_srgb(np.stack([Fr, Fg, Fb], -1)), 0, 255).astype(np.uint8)
    out[..., 3] = np.clip(a * 255, 0, 255).astype(np.uint8)
    im = Image.fromarray(out, "RGBA").crop(Image.fromarray(out, "RGBA").getbbox())
    im.save(path_out)

    al = out[..., 3].astype(float)
    semi = (al > 8) & (al < 248)
    r_, g_, b_ = [out[..., i][semi].astype(float) for i in range(3)]
    print(f"  半透明邊緣 {semi.mean():.2%}（越高代表髮絲細節保留越多）")
    print(f"  洋紅殘留 min(R,B)−G = {(np.minimum(r_, b_) - g_).mean():+.1f}（越接近 0 越乾淨）")
    print(f"  輸出 {im.size}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    kind = sys.argv[3] if len(sys.argv) > 3 else "magenta"
    key(sys.argv[1], sys.argv[2], kind, keep_alpha=(kind == "green"))
