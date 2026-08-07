#!/usr/bin/env python3
"""從 data/counties.json 產生底圖的生成 prompt。

存在的理由：高雄第一版的紅花畫錯，成因不是模型，是我手打 prompt 時憑印象寫了
「鳳凰木」（台南市樹），沒有對照旁邊那欄已經查證過的市花。
prompt 由資料產生就不會再發生——資料錯要改資料，不能繞過它。

用法：
    python3 tools/build_prompt.py 高雄市
    python3 tools/build_prompt.py 高雄市 --check   # 只檢查資料完整，不輸出 prompt
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = json.loads((ROOT / "data" / "counties.json").read_text(encoding="utf-8"))
CARD = json.loads((ROOT / "data" / "character" / "card.json").read_text(encoding="utf-8"))

REQUIRED = [
    ("scene.landmarks", lambda c: c.get("scene", {}).get("landmarks")),
    ("scene.plants", lambda c: c.get("scene", {}).get("plants")),
    ("scene.hand", lambda c: c.get("scene", {}).get("hand")),
    ("symbols.flower", lambda c: c["symbols"]["flower"]["value"]),
    ("scene.outfit", lambda c: c.get("scene", {}).get("outfit")),
]


def find(name):
    for c in DATA["counties"]:
        if c["name"] == name:
            return c
    sys.exit(f"找不到縣市：{name}")


def check(c):
    missing = [k for k, get in REQUIRED if not get(c)]
    if missing:
        sys.exit(f"{c['name']} 資料不全，缺：{'、'.join(missing)}\n"
                 f"補進 data/counties.json 再產 prompt。")
    # 市花與背景植物不一致時擋下來——這正是高雄那次的錯誤形狀
    flower = c["symbols"]["flower"]["value"]
    plants = c["scene"]["plants"]
    if flower not in plants:
        sys.exit(f"{c['name']}：市花是「{flower}」，但 scene.plants 是 {plants}，"
                 f"兩者不一致。確認哪一個才對再產 prompt。")
    if c["symbols"]["flower"]["source"] != "official":
        print(f"（提醒：{c['name']} 的市花來源是 "
              f"{c['symbols']['flower']['source']}，尚未對官方核實）", file=sys.stderr)


def build(c):
    s = c["scene"]
    return (
        "Repaint the scene from image 1 as one single continuous illustration in exactly the "
        "same anime illustration style, colour palette and lighting. "
        f"THE CHARACTER, locked by the reference sheets: {CARD['card']} "
        "Keep her face, eyes, hair colour and hair length exactly as in the reference sheets — but "
        "NOT the hairstyle: the sheets show it blown loose by the wind, which is wrong. Her hair is "
        "gathered high into a neat compact bun as described above, tidy and close to the head. "
        "Same outstretched left arm and open-hand gesture, same pose. "
        + (f"IN HER HAIR: {s['hair']}. "
           if s.get("hair") else
           f"IN HER HAIR: a single {c['symbols']['flower']['value']} blossom pinned on her left "
           "side together with the gold beaded tassel hairpin — the flower is her signature and "
           "must always be present. ")
        +
        f"OUTFIT — do NOT copy the clothes shown in the reference sheets; the reference "
        f"sheets lock only her face and build. Dress her instead in: {s['outfit']}. "
        "Keep the canvas tote bag. "
        "If the outfit includes a hat, her hair is worn DOWN and loose over her shoulders, "
        "tucked under the hat — never a high ponytail poking through or over the brim. "
        "Without a hat, use the county-specific hairstyle described in IN HER HAIR above; "
        "do not copy the windblown ponytail from the reference sheets. "
        "FRAMING — this is a CHARACTER PORTRAIT with scenery behind her, NOT a landscape with a person standing in it. Match the original posters, measured from them: SHE IS CLOSE TO THE CAMERA. "
        "Her head alone spans about 14 percent of the picture width; her figure spans about "
        "38 percent of the width and about 76 percent of the height, the top of her hair reaching into the upper 12 percent of the frame; the bottom edge of the picture cuts across her legs at "
        "mid-thigh. She dominates the left side. Never draw her whole body with feet visible, "
        "never shrink her into the distance, never place her small against a wide landscape, "
        "and never let her occupy less than a third of the frame. "
        f"Her raised right hand holds {s['hand']}, drawn recognisably and appetisingly. "
        "Behind her, clearly visible across the left third, these three real places — draw each "
        "one recognisably from its description, do not substitute anything else: "
        + "; ".join(s.get("landmarks_en") or s["landmarks"]) + ". "
        f"In the lower left corner, {s.get('plants_desc') or s.get('plants_en') or ('blossoms of ' + '、'.join(s['plants']))}, "
        "attached to their own branches and never floating over water. "
        "COMPOSITION: she stands in the LEFT THIRD of the picture and must not extend past the "
        "horizontal midpoint — the right 40 percent stays empty. "
        "GARMENT PRINTS — no lettering anywhere: the T-shirt and the canvas tote each carry a "
        "printed illustration with absolutely no words, letters or Chinese characters. Any label on "
        "what she is holding carries only a small wordless illustration. Every print must be a complete "
        "finished graphic — do not leave any empty rectangle, blank patch, unlabelled sticker or "
        "vacant label area. Draw the hand holding it with four fingers and a thumb, natural "
        "knuckles, no extra or fused fingers. "
        + (
            "SEA — the right 40 percent is open water only: no buildings, boats, figures or objects, and "
            "also NO shoreline, headland, rocks, cliffs or vegetation may reach into it. "
            "water must look natural and alive: ripples larger in the foreground and finer toward "
            "the horizon, variation in depth colour, and a soft hazy transition where sea meets sky "
            "instead of a hard straight line. Do not repeat one identical wave pattern across the "
            "whole surface. Any sunlight glitter on the water stays LOW near the horizon and in "
            "the far distance — the middle of the right 40 percent is smooth even water with no "
            "sparkle, no bright speckles and no busy highlights, because text is placed over it. "
            if s.get("right_zone", "sea") == "sea" else
            "THE RIGHT 40 PERCENT — this county is inland; there is NO SEA anywhere in the picture. "
            "That area is open sky over receding ridges of hills fading into pale blue haze, layer behind "
            "layer, with no buildings, roads, figures or objects in it. It must stay PALE AND LIGHT "
            "from top to bottom — no near dark forested slope, no foreground trees or vegetation "
            "anywhere on the right side, including the bottom right corner, because text is placed "
            "over it. "
        )
        + "The top 22 percent OF THE RIGHT HALF is open sky with nothing in it — but her head and hair do reach the top of the frame on the left, which is correct and intended. Remove everything else from image 1: no headline, no captions, "
        "no information panels, no photo tiles, no icon badges, no coloured category bars, no "
        "decorative border, no frame. Landscape aspect ratio, 4:3. "
        "MUST NOT APPEAR: " + "; ".join(CARD["must_not"]) + "."
    )


def refs(c):
    """生圖要附的參考圖，順序固定：立繪 → 臉部四視圖 → 該縣市舊海報。"""
    out = [ROOT / "data" / "character" / "ref-half.png",
           ROOT / "data" / "character" / "face.png"]
    if c.get("poster"):
        out.append(ROOT / "img" / f"{c['poster']}.webp")
    return [str(p) for p in out if p.exists()]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    county = find(sys.argv[1])
    check(county)
    if "--refs" in sys.argv:
        print("\n".join(refs(county)))
    elif "--check" not in sys.argv:
        print(build(county))
