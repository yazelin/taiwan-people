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


LIGHT = {
    "west": "low late-afternoon sun coming from the LEFT, warm and golden, the water catching the light",
    "east": "clear morning light coming from the RIGHT over the ocean, fresh and slightly cool",
    "inland": "low late-afternoon sun raking across the ridges from the LEFT, warm and golden",
}


def build(c):
    """美術指導的六條，每一條都是踩過坑之後才加的：

    1. 一個主地標畫清楚 —— 先前三個地標等權重並列，等於把資料表畫成圖，
       眼睛不知道看哪。
    2. 豐富的配角世界 —— 但全部低對比。只寫「其餘退到霧裡」會讓畫面變空，
       主次要靠明度拉開，不是靠減少東西。
    3. 四個景深層 —— 先前沒有景深指令，畫出來只有人物和背景兩層。
    4. 單一光源 —— 先前沒指定，每張光向都不同，物件像各自貼上去的。
    5. 留白由天空水面構成 —— 寫「stays empty」會得到一片死藍。
    6. **視點** —— 最後才發現的漏洞。少了它，模型會把不同地方的地標拼在同一格：
       台北那張的陽明山、北投、101 三者沒有任何位置能同時看到，
       結果 101 從雲海裡獨自聳立，變成地理拼貼。
    """
    s = c["scene"]
    # A county's other verified landmarks may be geographically remote from the
    # selected viewpoint.  When present, this field lists only supporting details
    # that can genuinely share the hero landmark's frame.
    others = "; ".join(s.get("viewpoint_support_en") or s.get("others_en") or [])
    return (
        "An anime illustration in the same style, colour palette and painterly shading as "
        "image 1. A single continuous scene — not a collage, not a panel of separate items. "
        f"THE CHARACTER, locked by the reference sheets: {CARD['card']} "
        "Keep her face, eyes, hair colour and hair length exactly as in the reference sheets — "
        "but NOT the hairstyle: the sheets show it blown loose by the wind, which is wrong. "
        f"IN HER HAIR: {s['hair']}. "
        f"OUTFIT — do NOT copy the clothes shown in the reference sheets, which lock only her "
        f"face and build. Dress her instead in: {s['outfit']}. Keep the canvas tote bag. "
        f"ON HER: {s.get('accessories', '')}. These small details matter — she should look "
        "lived-in and specific, not stripped down. "
        "If the outfit includes a hat, her hair is fully contained under it, never poking "
        "through the crown. "
        "FRAMING — a character portrait with scenery behind her, NOT a landscape with a person "
        "in it. Her head alone spans about 14 percent of the picture width; her figure about 38 "
        "percent of the width and 76 percent of the height, the top of her hair reaching into "
        "the upper 12 percent. The bottom edge cuts across her legs at mid-thigh. She stands in "
        "the LEFT THIRD and her whole silhouette stays at or left of the horizontal midpoint. "
        # 姿勢是角色的固定動作，22 張都一樣。改寫 build() 加美術指導時
        # 曾經把這條弄丟，結果生出來的圖沒有那隻伸出的手，拿東西的手也左右顛倒。
        "POSE — always the same, this is her signature gesture: her LEFT arm reaches out "
        "toward the viewer at chest height with an open, welcoming palm facing up, fingers "
        "spread, clearly in the foreground. Exactly four fingers and one thumb, natural "
        "knuckles, no extra or fused fingers. "
        f"Meanwhile her RIGHT hand is raised beside her shoulder holding {s['hand']}, "
        "drawn recognisably and appetisingly. "
        # ── 視點：畫面裡只能有從這裡看得到的東西 ──
        f"VIEWPOINT — she is {s['viewpoint']}. {s['viewpoint_sees']}. "
        "EVERYTHING in the picture must be something genuinely visible from this one spot. "
        "Do not assemble landmarks from different parts of the county into one frame. "
        # ── 主角 ──
        f"ONE HERO LANDMARK: {s['hero_landmark_en']}. It sits in the MID-GROUND behind and "
        "beside her, large enough to read clearly, the most sharply lit and highest-contrast "
        "thing after her face — the single thing the eye lands on second. "
        # ── 豐富的配角 ──
        + (f"A RICH SUPPORTING WORLD, all at LOWER contrast than the hero: {others}. "
           if others else "A RICH SUPPORTING WORLD, all at LOWER contrast than the hero. ")
        + "Around and between them, fill the left 60 percent with the real texture of the "
        "place — rooflines layered one behind another, a lantern or a sign shape, two or three "
        "small distant figures, street trees, boats or scooters, whatever belongs at this spot. "
        "Many elements are wanted, but each softer, paler and lower-contrast than the hero. "
        "Depth comes from things getting paler with distance, never from making all equally sharp. "
        # ── 景深 ──
        "FOUR DEPTH PLANES separated by value and focus: (1) foreground corner — "
        f"{s.get('plants_desc') or 'local blossoms'}, DARK and slightly out of focus, framing "
        "the lower left; (2) the character, sharp and highest contrast; (3) mid-ground — the "
        "hero landmark and the life around it, clear but lower contrast than her; (4) far "
        "distance — values compressed toward the sky, dissolving into haze. "
        # ── 光 ──
        f"ONE LIGHT SOURCE: {LIGHT[s.get('light', 'west')]}. Every element casts consistent shadows. "
        # ── 留白 ──
        "NEGATIVE SPACE IS MADE OF SOMETHING. The right 40 percent is quiet and low-detail, "
        "but it is real sky and atmosphere with gradation, NOT an empty flat area. "
        + ("This county is INLAND — there is NO SEA anywhere in the picture. The right 40 "
           "percent contains no buildings, figures, objects, rooftops, nearby trees, vegetation "
           "or dark foreground slopes. It is open sky over only low, pale receding ridges fading "
           "into haze, layer behind layer, staying pale and light from top to bottom. "
           if s.get("right_zone", "sea") == "sky" else
           "The right 40 percent contains no buildings, figures, objects, land, shoreline, rocks "
           "or vegetation. It is calm open water meeting a soft hazy sky. Any sunlight glitter "
           "stays LOW near the horizon; the middle stays smooth and even because text goes over it. ")
        + "The top 22 percent of the right half is open sky with nothing in it — her hair does "
        "reach the top of the frame on the left, which is intended. "
        "NO TEXT ANYWHERE: no headline, captions, panels, photo tiles, icon badges, coloured "
        "bars, border or frame. The T-shirt and tote each carry a printed illustration with "
        "absolutely no words or characters; every print is a complete finished graphic with no "
        "blank patches or unlabelled stickers. Landscape aspect ratio, 4:3. "
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
    s = c["scene"]
    right_zone = (
        "From x=60 percent to the right edge, show only open sky above low, pale receding "
        "ridges dissolving into haze: no buildings, figures, objects, rooftops, nearby trees, "
        "vegetation or dark foreground slopes, and no sea anywhere. "
        if s.get("right_zone", "sea") == "sky" else
        "From x=60 percent to the right edge, show only continuous open sea and sky: no land, "
        "shoreline, rocks, vegetation, buildings, boats, figures or objects. "
    )
    return (
        "Use case: precise-object-edit. Image 1 is the edit target. Change only the spatial "
        "composition. Preserve the exact character identity, face, warm brown eyes, expression, "
        "county-specific hairstyle and flower accessory, gold beaded tassel hairpin, outfit, "
        "jewellery, tote, held item, hand gestures, anime rendering, colour palette and daylight. "
        "Uniformly scale the whole character with both arms, tote and held item to about 92 percent of "
        "its current size and shift it slightly up and left, without cropping the open left hand, "
        "until the top of her hair reaches y=10 percent and every part "
        "of the character including the held item's right edge is at or left of x=50 percent. The head "
        "should span about 14 percent of the canvas width and the lower frame should cut the figure "
        "at mid-thigh. Preserve the hero landmark's exact identity and recognisable architecture: "
        f"{s['hero_landmark_en']}. Reposition it into x=48–58 percent, fully inside the left 60 percent, "
        "behind and beside the character. It must remain large, clear and the second-highest-contrast "
        "subject after her face; DO NOT remove, replace, hide or turn it into a mountain. Compress and "
        "recompose its surrounding city or local setting into x=0–60 percent so the landmark rises "
        "naturally from its real environment. "
        + right_zone +
        "Keep the top 22 percent of the right half completely open sky and keep the whole right "
        "40 percent pale, quiet and low-detail for text. "
        "Do not change, add or remove any other character detail. No text, letters, logos, panels, "
        "borders or watermarks. One continuous 4:3 landscape illustration."
    )


def build_framing_fix(c):
    """右側留白正確後，只修近距離人物尺度與垂直位置。"""
    s = c["scene"]
    right_zone = (
        "Keep the pale open sky and hazy receding ridges from x=60–100 percent exactly unchanged. "
        if s.get("right_zone", "sea") == "sky" else
        "Keep the open sea and sky from x=60–100 percent exactly unchanged. "
    )
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
        "Keep the open left hand fully visible. The complete silhouette including the held item must "
        "remain at or left of x=50 percent. "
        + right_zone +
        "Do not "
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


def build_hand_framing_fix(c):
    """人物尺度正確後，只把伸出的左手完整收進畫面。"""
    right_zone = (
        "pale open sky and hazy receding ridges"
        if c["scene"].get("right_zone", "sea") == "sky" else
        "open sea and sky"
    )
    return (
        "Use case: precise-object-edit. Image 1 is the edit target. Change only the character's "
        "horizontal placement. Move the entire character uniformly a few percent to the RIGHT, "
        "without scaling, rotating or redrawing her, until the leftmost fingertip of her extended "
        "LEFT hand sits at x=3 percent with a small clear margin and the whole hand is fully visible. "
        "Keep the complete character silhouette, including the held item in her RIGHT hand, at or "
        "left of x=50 percent. Preserve exactly her face, warm brown eyes, expression, hair, azalea, "
        "gold beaded tassel hairpin, outfit, badges, earrings, tote, pineapple cake, both hand poses, "
        "body scale, vertical framing, anime rendering, colour palette and lighting. Keep every "
        "background detail, Taipei 101, the city basin, the azalea shrubs, and the " + right_zone +
        " exactly unchanged. No text, letters, logos, panels, borders or watermarks. One continuous "
        "4:3 landscape illustration."
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
    elif "--fix-hand-framing" in sys.argv:
        print(build_hand_framing_fix(county))
    elif "--check" not in sys.argv:
        print(build(county))
