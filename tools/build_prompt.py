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
    hairstyle_lock = (
        "Use the county-specific hairstyle in IN HER HAIR below; it overrides the default bun. "
        if s.get("hair") else
        "Her hair is gathered high into a neat compact bun as described above, tidy and close "
        "to the head. "
    )
    return (
        "Repaint the scene from image 1 as one single continuous illustration in exactly the "
        "same anime illustration style, colour palette and lighting. "
        f"THE CHARACTER, locked by the reference sheets: {CARD['card']} "
        "Keep her face, eyes, hair colour and hair length exactly as in the reference sheets — but "
        "NOT the hairstyle: the sheets show it blown loose by the wind, which is wrong. "
        + hairstyle_lock +
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
        "COMPOSITION: she stands in the LEFT THIRD of the picture. Her entire silhouette — "
        "including both hands, hair, clothing, tote and the cup — must fit at or left of the "
        "horizontal midpoint; hold the cup inward near her chest so its right edge does not cross "
        "that midpoint. Confine all land, shoreline, cliffs, rocks and vegetation to the left 60 "
        "percent. From x=60% to the right edge, the right 40 percent stays empty. "
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
    """生圖要附的參考圖：image 1 是舊海報，其後才是角色設定圖。"""
    out = []
    if c.get("poster"):
        out.append(ROOT / "img" / f"{c['poster']}.webp")
    out.extend([ROOT / "data" / "character" / "ref-half.png",
                ROOT / "data" / "character" / "face.png"])
    return [str(p) for p in out if p.exists()]


def build_composition_fix(c):
    """既有底圖只重排人物與右側留白，不重畫角色設計。"""
    return (
        "Use case: precise-object-edit. Image 1 is the edit target. Change only the spatial "
        "composition. Preserve the exact character identity, face, warm brown eyes, expression, "
        "county-specific hairstyle and flower accessory, gold beaded tassel hairpin, outfit, "
        "jewellery, tote, held item, hand gestures, anime rendering, colour palette and daylight. "
        "Uniformly scale the whole character with both arms, tote and cup to about 85 percent of "
        "its current size and shift it left, without cropping the open left hand, until every part "
        "of the character including the cup's right edge is at or left of x=50 percent. The head "
        "should span about 14 percent of the canvas width and the lower frame should cut the figure "
        "at mid-thigh. Recompose only the scenery needed to fill the revealed space naturally. "
        "Confine every piece of land, shoreline, cliff, rock and vegetation to x=0–60 percent. "
        "From x=60 percent to the right edge, show only continuous open sea and sky: no land, "
        "shoreline, rocks, vegetation, buildings, boats, figures or objects. Keep the top 22 percent "
        "of the right half completely open sky and keep the middle-right water smooth for text. "
        "Do not change, add or remove any other subject detail. No text, letters, logos, panels, "
        "borders or watermarks. One continuous 4:3 landscape illustration."
    )


def build_framing_fix(c):
    """右側留白正確後，只修近距離人物尺度與垂直位置。"""
    return (
        "Use case: precise-object-edit. Image 1 is the edit target. Change only the character's "
        "scale and vertical framing; keep the current left/right scene boundary and every background "
        "detail exactly unchanged. Preserve the exact face, warm brown eyes, expression, "
        "county-specific hairstyle and flower accessory, gold beaded tassel hairpin, clothing, "
        "jewellery, tote, held item, both hand gestures, anime style, palette and lighting. Enlarge "
        "the entire "
        "character uniformly to 115 percent of its current size and move it upward so the top of the "
        "flower crown reaches y=10 percent of the canvas. Continue the lower body naturally beyond "
        "the canvas so the bottom edge crops her at mid-thigh; do not leave scenery beneath her. "
        "Keep the open left hand fully visible. The complete silhouette including the cup must remain "
        "at or left of x=50 percent. Do not alter the open sea and sky from x=60–100 percent. Do not "
        "change, add or remove any other subject detail. No text, letters, logos, panels, borders or "
        "watermarks. One continuous 4:3 landscape illustration."
    )


def build_plant_fix(c):
    """既有底圖只修左下角的縣花植物形態。"""
    plant = c["scene"].get("plants_desc") or c["scene"].get("plants_en")
    return (
        "Use case: precise-object-edit. Image 1 is the edit target. Change only the botanical "
        "cluster in the lower-left corner so it clearly and accurately contains: " + plant + ". "
        "Every flower, seed pod, stalk and leaf must be physically connected as one natural plant. "
        "Preserve the exact character, face, brown eyes, hair, flower accessory, hairpin, outfit, "
        "jewellery, tote, held item, hands, pose, scenery, left/right composition, open sea and sky, "
        "anime style, palette and lighting. Do not change, add or remove anything else. No text, "
        "letters, logos, panels, borders or watermarks. One continuous 4:3 landscape illustration."
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    county = find(sys.argv[1])
    check(county)
    if "--refs" in sys.argv:
        print("\n".join(refs(county)))
    elif "--fix-composition" in sys.argv:
        print(build_composition_fix(county))
    elif "--fix-framing" in sys.argv:
        print(build_framing_fix(county))
    elif "--fix-plant" in sys.argv:
        print(build_plant_fix(county))
    elif "--check" not in sys.argv:
        print(build(county))
