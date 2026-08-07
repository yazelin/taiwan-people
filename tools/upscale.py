#!/usr/bin/env python3
"""用 Real-ESRGAN 的動畫模型放大。只用 torch，不裝 basicsr。

    python3 tools/upscale.py 輸入.png 輸出.png [倍率]

為什麼不裝官方套件：`realesrgan` 依賴 `basicsr`，而 basicsr 引用了
torchvision 的舊 API，在新版 torch 上會壞。RRDBNet 的架構程式碼很短，
自己寫比處理相依衝突省事。

為什麼用動畫模型而不是通用模型：`RealESRGAN_x4plus_anime_6B` 是用動畫線稿
訓練的，處理平塗色塊與清晰線條比通用模型好；通用模型會把動畫的平面色塊
當成「需要補回細節的照片」，加上不存在的紋理。

**alpha 通道要分開放大。** 模型只吃 RGB。直接把 RGBA 丟進去會丟掉透明度，
而髮絲的價值全在 alpha 裡。這裡的做法是 RGB 走模型、alpha 走 Lanczos，
再合回去——alpha 是單通道的軟遮罩，Lanczos 放大它不會有明顯損失。
"""
import sys

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image

Image.MAX_IMAGE_PIXELS = None


class ResidualDenseBlock(nn.Module):
    def __init__(self, nf=64, gc=32):
        super().__init__()
        self.conv1 = nn.Conv2d(nf, gc, 3, 1, 1)
        self.conv2 = nn.Conv2d(nf + gc, gc, 3, 1, 1)
        self.conv3 = nn.Conv2d(nf + 2 * gc, gc, 3, 1, 1)
        self.conv4 = nn.Conv2d(nf + 3 * gc, gc, 3, 1, 1)
        self.conv5 = nn.Conv2d(nf + 4 * gc, nf, 3, 1, 1)
        self.lrelu = nn.LeakyReLU(0.2, inplace=True)

    def forward(self, x):
        x1 = self.lrelu(self.conv1(x))
        x2 = self.lrelu(self.conv2(torch.cat((x, x1), 1)))
        x3 = self.lrelu(self.conv3(torch.cat((x, x1, x2), 1)))
        x4 = self.lrelu(self.conv4(torch.cat((x, x1, x2, x3), 1)))
        x5 = self.conv5(torch.cat((x, x1, x2, x3, x4), 1))
        return x5 * 0.2 + x


class RRDB(nn.Module):
    def __init__(self, nf, gc=32):
        super().__init__()
        self.rdb1 = ResidualDenseBlock(nf, gc)
        self.rdb2 = ResidualDenseBlock(nf, gc)
        self.rdb3 = ResidualDenseBlock(nf, gc)

    def forward(self, x):
        return self.rdb3(self.rdb2(self.rdb1(x))) * 0.2 + x


class RRDBNet(nn.Module):
    """anime_6B 的參數：nf=64、nb=6、gc=32、scale=4"""

    def __init__(self, nf=64, nb=6, gc=32):
        super().__init__()
        self.conv_first = nn.Conv2d(3, nf, 3, 1, 1)
        self.body = nn.Sequential(*[RRDB(nf, gc) for _ in range(nb)])
        self.conv_body = nn.Conv2d(nf, nf, 3, 1, 1)
        self.conv_up1 = nn.Conv2d(nf, nf, 3, 1, 1)
        self.conv_up2 = nn.Conv2d(nf, nf, 3, 1, 1)
        self.conv_hr = nn.Conv2d(nf, nf, 3, 1, 1)
        self.conv_last = nn.Conv2d(nf, 3, 3, 1, 1)
        self.lrelu = nn.LeakyReLU(0.2, inplace=True)

    def forward(self, x):
        feat = self.conv_first(x)
        feat = feat + self.conv_body(self.body(feat))
        feat = self.lrelu(self.conv_up1(F.interpolate(feat, scale_factor=2, mode="nearest")))
        feat = self.lrelu(self.conv_up2(F.interpolate(feat, scale_factor=2, mode="nearest")))
        return self.conv_last(self.lrelu(self.conv_hr(feat)))


def run(src_path, out_path, scale=4, weights="/tmp/resrgan_anime.pth", tile=384):
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    net = RRDBNet().to(dev).eval()
    sd = torch.load(weights, map_location="cpu", weights_only=True)
    net.load_state_dict(sd.get("params_ema", sd.get("params", sd)), strict=True)

    im = Image.open(src_path)
    has_alpha = im.mode in ("RGBA", "LA")
    rgb = np.asarray(im.convert("RGB"), np.float32) / 255.0
    alpha = np.asarray(im.convert("RGBA"))[..., 3] if has_alpha else None
    h, w = rgb.shape[:2]
    print(f"  輸入 {w}×{h}{'（含 alpha）' if has_alpha else ''} → 模型 4×")

    x = torch.from_numpy(rgb).permute(2, 0, 1).unsqueeze(0).to(dev)
    out = torch.zeros(1, 3, h * 4, w * 4, device=dev)
    pad = 16  # 分塊之間重疊，避免接縫
    with torch.no_grad():
        for y0 in range(0, h, tile):
            for x0 in range(0, w, tile):
                y1, x1 = min(y0 + tile, h), min(x0 + tile, w)
                ya, xa = max(0, y0 - pad), max(0, x0 - pad)
                yb, xb = min(h, y1 + pad), min(w, x1 + pad)
                o = net(x[:, :, ya:yb, xa:xb])
                out[:, :, y0 * 4:y1 * 4, x0 * 4:x1 * 4] = \
                    o[:, :, (y0 - ya) * 4:(y1 - ya) * 4, (x0 - xa) * 4:(x1 - xa) * 4]
    up = (out.clamp(0, 1).squeeze(0).permute(1, 2, 0).cpu().numpy() * 255).astype(np.uint8)
    res = Image.fromarray(up, "RGB")

    if has_alpha:
        # alpha 走 Lanczos：它是單通道軟遮罩，模型只吃 RGB
        a = Image.fromarray(alpha, "L").resize(res.size, Image.LANCZOS)
        res = Image.merge("RGBA", (*res.split(), a))

    if scale != 4:
        tw, th = int(w * scale), int(h * scale)
        res = res.resize((tw, th), Image.LANCZOS)   # 從 4× 縮下來比直接放大乾淨
    res.save(out_path)
    print(f"  輸出 {res.size[0]}×{res.size[1]} → {out_path}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    run(sys.argv[1], sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 4)
