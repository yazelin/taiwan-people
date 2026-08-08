#!/usr/bin/env python3
"""從 data/counties.json 產生底圖的生成 prompt。

存在的理由：高雄第一版的紅花畫錯，成因不是模型，是我手打 prompt 時憑印象寫了
「鳳凰木」（台南市樹），沒有對照旁邊那欄已經查證過的市花。
prompt 由資料產生就不會再發生——資料錯要改資料，不能繞過它。

用法：
    python3 tools/build_prompt.py 高雄市
    python3 tools/build_prompt.py 高雄市 --check       # 只檢查資料完整，不輸出 prompt
    python3 tools/build_prompt.py 台東縣・卑南族        # 指名族群的造型
    python3 tools/build_prompt.py 台東縣・卑南族 --checklist   # 出圖後的驗收清單

指名族群的造型（有 culture 欄的那些筆）只寫要覆寫的欄位，地標、市花、視點、光向
全部繼承所屬縣市。服裝的形制、色彩、紋樣、階級限制直接從 data/costume.json 讀進 prompt，
不必也不准手打。
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = json.loads((ROOT / "data" / "counties.json").read_text(encoding="utf-8"))
CARD = json.loads((ROOT / "data" / "character" / "card.json").read_text(encoding="utf-8"))
COSTUME = json.loads((ROOT / "data" / "costume.json").read_text(encoding="utf-8"))
PEOPLES = {p["id"]: p for p in COSTUME["peoples"]}

REQUIRED = [
    ("scene.landmarks", lambda c: c.get("scene", {}).get("landmarks")),
    ("scene.plants", lambda c: c.get("scene", {}).get("plants")),
    ("scene.hand", lambda c: c.get("scene", {}).get("hand")),
    ("symbols.flower", lambda c: c["symbols"]["flower"]["value"]),
    ("scene.outfit", lambda c: c.get("scene", {}).get("outfit")),
]

# 出現這些字眼就代表衣服在宣稱某個族群的傳統服飾。宣稱就要有依據，
# 所以 scene.costume_basis 必須有東西。這條擋的是花蓮那次的錯誤形狀：
# 「保留織紋但不指名族群」＝畫出一件不屬於任何族的族服。
CLAIM_WORDS = [
    "woven geometric", "geometric band", "tribal", "indigenous",
    "hakka", "da-jin-shan", "lan-shan",
    "織紋", "族服", "藍衫", "大襟衫", "圖騰",
]


def find(name):
    """通用版與指名族群的造型放在同一個陣列，靠 name 區分。

    這樣 gen_all.sh、verify_base.py、register_base.py、review.py、pick.py
    都不必知道有兩種紀錄——它們本來就只認 name 與 id。
    """
    for c in DATA["counties"]:
        if c["name"] == name:
            return resolve(c)
    sys.exit(f"找不到：{name}\n"
             f"可用的有：{'、'.join(x['name'] for x in DATA['counties'])}")


def resolve(c):
    """指名族群的那些筆只寫要覆寫的欄位，其餘全部繼承所屬縣市。

    沒有繼承的話，每加一筆造型就要把地標、市花、視點、光向整份抄一次，
    抄錯了就是又一個「憑印象覆蓋既有資料」的案例。
    """
    if not c.get("culture"):
        return c
    parent = next((x for x in DATA["counties"] if x["name"] == c["county"]), None)
    if parent is None:
        sys.exit(f"{c['name']}：county 欄寫的「{c['county']}」在資料裡找不到。")
    merged = {**parent, **{k: v for k, v in c.items() if k != "scene"}}
    merged["scene"] = {**parent.get("scene", {}), **c.get("scene", {})}
    return merged


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
    check_costume(c)


def check_costume(c):
    s = c["scene"]
    blob = " ".join([s.get("outfit", ""), s.get("accessories", ""),
                     s.get("outfit_zh", ""), s.get("hair", ""), s.get("hair_zh", "")]).lower()
    claims = [w for w in CLAIM_WORDS if w.lower() in blob]

    if c.get("culture"):
        p = PEOPLES.get(c["culture"])
        if p is None:
            sys.exit(f"{c['name']}：culture「{c['culture']}」在 data/costume.json 裡沒有這一族。")
        county = c.get("county") or c["name"]
        if not any(a.replace("臺", "台") == county.replace("臺", "台") for a in p["areas"]):
            sys.exit(f"{c['name']}：{p['name']} 的分布縣市是 {p['areas']}，不含 {county}。"
                     f"確認是不是掛錯縣市。")
        if not p["female"] and not p["male"]:
            sys.exit(f"{c['name']}：data/costume.json 的 {p['name']} 沒有逐部位資料"
                     f"（gaps：{p['gaps']}）。\n"
                     f"依據不足就不要畫，這是資料集寫明的。")
        if not s.get("costume_basis"):
            sys.exit(f"{c['name']}：指名了族群就必須填 scene.costume_basis，"
                     f"寫明每一項對回 costume.json 的哪一欄。")
    elif claims and not s.get("costume_basis"):
        sys.exit(f"{c['name']}：服裝欄出現「{'、'.join(claims)}」，那是在宣稱某個族群的傳統服飾，"
                 f"但 scene.costume_basis 是空的。\n"
                 f"要嘛補上對回 data/costume.json 的依據，要嘛改成不宣稱族群的當代穿著。\n"
                 f"「保留織紋但不指名族群」不是折衷，那等於畫出一件不屬於任何族的族服。")


def costume_block(c):
    """指名族群時，把 costume.json 的色彩、紋樣與階級限制直接寫進 prompt。

    分工是刻意的：**穿哪幾件由人挑**（寫在 scene.outfit，並用 scene.costume_basis
    交代每一件對回 costume.json 的哪一欄），**色彩紋樣與不准越界的部分由資料灌**。
    逐部位的完整清單不進 prompt——那份清單含日常／勞動／年長等替代選項
    （例如卑南族年長女性改穿長褲），整份倒給模型只會讓它把不同情境的東西畫在一起。
    要看完整清單跑 --checklist。
    """
    p = PEOPLES.get(c.get("culture") or "")
    if p is None:
        return ""
    parts = [f"THIS IS {p['name']}（{p['en']}）DRESS, and it must be recognisable as such. "
             f"Every garment above comes from a cited record; do not substitute, simplify or "
             f"invent ornament. "]
    if p["palette"]:
        parts.append("COLOUR: " + "; ".join(p["palette"]) + ". ")
    if p["motifs"]:
        parts.append("MOTIFS, and only these: " + "; ".join(p["motifs"]) + ". ")
    if p["rank"]:
        parts.append("RANK AND ELIGIBILITY — this decides what she is allowed to wear: "
                     + p["rank"] + " ")
    parts.append("Do not add ornament from any other Taiwanese people: no other people's "
                 "weave patterns, head-dress, feathers or bead work. ")
    return "".join(parts)


LIGHT = {
    "west": "low late-afternoon sun coming from the LEFT, warm and golden, the water catching the light",
    "east": "clear morning light coming from the RIGHT over the ocean, fresh and slightly cool",
    "inland": "low late-afternoon sun raking across the ridges from the LEFT, warm and golden",
    "urban_west": "low late-afternoon sun coming from the LEFT, warm and golden across the old brick, roof tiles and plaster",
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
        f"face and build. Dress her instead in: {s['outfit']}. "
        + costume_block(c)
        + "Keep the canvas tote bag. "
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
        + (s.get("foreground_layout", "") + ". " if s.get("foreground_layout") else "")
        # ── 主角 ──
        + f"ONE HERO LANDMARK: {s['hero_landmark_en']}. It sits in the MID-GROUND behind and "
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
        # 留白＝安靜，不是空。要求右側「幾乎無細節」會讓畫面空洞——
        # 文字的可讀性由網頁那層很淡的漸層負責，不必犧牲畫面。
        "THE RIGHT SIDE IS QUIET, NOT EMPTY. The scene continues naturally into the right 40 "
        "percent — water, sky, a distant shoreline, a far ridge, whatever genuinely belongs at "
        "this viewpoint. Keep it lower in contrast and slightly lower in saturation than the "
        "left, with no figures, vehicles, signs or busy detail competing for attention, and no "
        "hard dark shapes. It should read as calm depth, not as a blank area. "
        # right_zone 只有幾種通則，但有些地方全都不對——
        # 花蓮的視點在太魯閣峽谷內，留白既不是海也不是「天空與遠山」，
        # 是峽谷自身層層退去的岩壁與霧。逐縣市覆寫優先。
        + (s["right_zone_desc"] + " " if s.get("right_zone_desc") else
           "The right 40 percent is a plausible quiet opening within this same old-street viewpoint: "
           "soft pale sky above a low, sunlit old plaster courtyard wall, both low-detail and gently "
           "graded for text. No sea, water, salt pans, mountains, distant landmarks, figures, vehicles, "
           "signs, lanterns, trees or roof silhouettes appear in this zone. "
           if s.get("right_zone") == "city_sky" else
           "This county is INLAND — there is NO SEA anywhere in the picture. The right 40 "
           "percent contains no buildings, figures, objects, rooftops, nearby trees, vegetation "
           "or dark foreground slopes. It is open sky over only low, pale receding ridges fading "
           "into haze, layer behind layer, staying pale and light from top to bottom. "
           if s.get("right_zone", "sea") == "sky" else
           "The right 40 percent contains no buildings, figures, objects, land, shoreline, rocks "
           "or vegetation. It is calm open river water meeting a soft hazy sky. Any sunlight "
           "glitter stays LOW near the horizon; the middle stays smooth and even because text "
           "goes over it. "
           if s.get("right_zone") == "river" else
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
    zone = s.get("right_zone", "sea")
    right_zone = (
        "From x=60 percent to the right edge, show only pale open sky above a low, sunlit old "
        "plaster courtyard wall belonging to this same viewpoint: no sea, water, salt pans, mountains, "
        "distant landmarks, figures, vehicles, signs, lanterns, trees or roof silhouettes. "
        if zone == "city_sky" else
        "From x=60 percent to the right edge, show only open sky above low, pale receding "
        "ridges dissolving into haze: no buildings, figures, objects, rooftops, nearby trees, "
        "vegetation or dark foreground slopes, and no sea anywhere. "
        if zone == "sky" else
        "From x=60 percent to the right edge, show only continuous open river water and sky: "
        "no land, shoreline, rocks, vegetation, buildings, boats, figures or objects. "
        if zone == "river" else
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
    zone = s.get("right_zone", "sea")
    right_zone = (
        "Keep the pale open sky and low sunlit old plaster courtyard wall from x=60–100 percent exactly unchanged. "
        if zone == "city_sky" else
        "Keep the pale open sky and hazy receding ridges from x=60–100 percent exactly unchanged. "
        if zone == "sky" else
        "Keep the open river water and sky from x=60–100 percent exactly unchanged. "
        if zone == "river" else
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


def build_hair_flower_fix(c):
    """既有底圖只修髮花的物種形態，不動前景植物或角色造型。"""
    s = c["scene"]
    flower = s.get("hair_flower_desc") or s["hair"]
    return (
        "Use case: precise-object-edit. Image 1 is the edit target. Change only the single "
        "flower worn in the character's hair. Redraw it as: " + flower + ". Keep its current "
        "position, scale and red-orange colour family. Preserve exactly the character's face, "
        "warm brown eyes, expression, compact high bun, dark brown-black hair, gold beaded tassel "
        "hairpin, earrings, clothing, badge, bracelet, tote, burger, hands, pose, body scale and "
        "placement. Preserve every foreground kapok branch and flower, every background detail, "
        "the lighthouse, harbour, open right-side sea and sky, lighting, palette, painterly anime "
        "rendering and 4:3 framing. Do not change, add or remove anything else. No text, letters, "
        "logos, panels, borders or watermarks anywhere."
    )


def build_tote_print_fix(c):
    """既有底圖只修提袋印花，內容必須能對回該縣市資料。"""
    s = c["scene"]
    motif = s.get("tote_print") or ("a complete wordless illustration of " + s["hero_landmark_en"])
    return (
        "Use case: precise-object-edit. Image 1 is the edit target. Change only the printed "
        "illustration on the canvas tote, replacing its current motif with: " + motif + ". The "
        "new print must be a seamless finished illustration integrated into the fabric, with no "
        "text, letters, pseudo-letters, characters, logo, label, sticker or blank rectangular patch. "
        "Preserve exactly the tote's shape, seams, folds, strap, position and colour. Preserve every "
        "other detail exactly: the character's face, warm brown eyes, expression, county-specific "
        "hairstyle and flower accessory, gold beaded tassel hairpin, earrings, clothing, jewellery, "
        "held item, hands, pose, body scale and placement; every foreground plant and background "
        "detail, the hero landmark, open right-side sky and water, lighting, palette, painterly anime "
        "rendering and 4:3 framing. Do not "
        "change, add or remove anything else. No text, letters, logos, panels, borders or watermarks anywhere."
    )


def build_right_zone_cleanup(c):
    """既有底圖只清空右側文字區的離散物件，保留原本水天漸層。"""
    return (
        "Use case: precise-object-edit. Image 1 is the edit target. Remove only the few tiny dark "
        "cargo-ship silhouettes sitting directly on the far horizon at x=64–100 percent. Inpaint each "
        "tiny removed silhouette locally with the immediately surrounding pale hazy horizon colour. "
        "Do not repaint or change the open sea, sky, horizon height, sunlight glitter, clouds or colour "
        "gradation around them. Everything at x=0–64 percent is outside the edit and must remain exactly "
        "unchanged, especially Cijin Lighthouse and its wooded headland near x=54 percent, the harbour "
        "breakwater, ferries, character, both hands, burger, five-petalled kapok hair flower, tote and "
        "its lighthouse print, foreground flowers and seawall. Preserve every pixel except the tiny "
        "far-horizon ship silhouettes at x=64–100 percent. Do not change composition, scale, palette, "
        "lighting, painterly anime style or 4:3 framing. No text, letters, logos, panels, borders or watermarks."
    )


def build_landmark_boundary_fix(c):
    """既有底圖只把主地標收進左 60%，不重畫角色或右側文字區。"""
    s = c["scene"]
    return (
        "Use case: precise-object-edit. Image 1 is the edit target. Change only the complete hero "
        "landmark group — " + s["hero_landmark_en"] + " — by translating that existing group "
        "uniformly about four percent of the canvas width to the LEFT without changing its scale, "
        "shape, architecture, lighting, focus or contrast. Its lighthouse should sit near x=52–54 "
        "percent and the rightmost edge of its wooded headland and shoreline must end at or before "
        "x=59 percent. Locally fill only the narrow vacated strip with the immediately adjacent calm "
        "sea and hazy sky. Preserve the complete character, face, five-petalled kapok hair flower, "
        "hairpin, clothing, both hands, burger, badge, bracelet, tote and its lighthouse print, every "
        "foreground kapok flower, harbour building, ferry, breakwater and seawall exactly unchanged. "
        "Keep the entire rightmost 40 percent as uninterrupted open sea and sky with no ships, land "
        "or objects. Do not change composition, palette, lighting, painterly anime style or 4:3 framing. "
        "No text, letters, logos, panels, borders or watermarks."
    )


def build_bottom_right_cleanup(c):
    """既有底圖只清除右下文字區的近景障礙物。"""
    return (
        "Use case: precise-object-edit. Image 1 is the edit target. Image 2 is the same image with a "
        "translucent magenta rectangle marking the only editable region; magenta is markup only and "
        "must not appear in the result. Change only the marked bottom-right rectangle x=60–100 percent "
        "and y=50–100 percent. Remove the concrete seawall, breakwater, "
        "tetrapods and rocks that intrude into that rectangle, and locally continue the immediately "
        "adjacent calm open sea through the removed area with matching perspective, small wave texture, "
        "warm reflection and colour. Do not alter anything above y=50 percent. Keep everything at "
        "x=0–60 percent exactly unchanged, including the complete character and clothing, both hands, "
        "burger, five-petalled kapok hair flower, tote with lighthouse print, foreground flowers, "
        "harbour buildings, ferries, Cijin Lighthouse and its wooded headland. Preserve the current "
        "open sky, horizon height, lighting, palette, painterly anime style and 4:3 framing. The entire "
        "rightmost 40 percent must finish as uninterrupted open sea and sky with no land, shoreline, "
        "rocks, structures, boats, figures or objects. No text, letters, logos, panels, borders or watermarks."
    )


def build_print_fix(c):
    """既有底圖只清掉衣物與提袋印花裡的偽字。"""
    s = c["scene"]
    return (
        "Use case: precise-object-edit. Image 1 is the edit target. Change only the printed "
        "graphics on the white T-shirt and canvas tote. Remove every text-like mark, pseudo-letter, "
        "character, logo and tiny typographic stroke from both prints. Rebuild each affected area "
        f"as a complete, seamless, finished wordless illustration of {s['hero_landmark_en']}, "
        f"consistent with this verified view: {s['viewpoint_sees']}. Do not introduce a generic "
        "landscape or any remote county landmark. Leave no blank patch, rectangle, sticker or label "
        "shape. Preserve exactly the character's face, warm brown eyes, "
        "expression, hair, moth orchid, gold beaded tassel hairpin, outfit construction and colours, "
        "jewellery, bracelet, pouch, coffee cup, hands, pose, body scale and placement. Preserve every "
        "background detail, the Xiluo Bridge, river, open right-side sky and water, composition, anime "
        "rendering, colour palette and lighting. Do not change, add or remove anything else. No text, "
        "letters, logos, panels, borders or watermarks anywhere. One continuous 4:3 landscape illustration."
    )


def build_hand_framing_fix(c):
    """人物尺度正確後，只把伸出的左手完整收進畫面。"""
    zone = c["scene"].get("right_zone", "sea")
    right_zone = (
        "pale open sky and a low sunlit old plaster courtyard wall"
        if zone == "city_sky" else
        "pale open sky and hazy receding ridges"
        if zone == "sky" else
        "open river water and sky"
        if zone == "river" else
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
    if "--checklist" in sys.argv:
        p = PEOPLES.get(county.get("culture") or "")
        if p is None:
            sys.exit(f"{county['name']} 是通用版，沒有指名族群，沒有族服驗收清單。")
        print(f"{p['name']} 出圖驗收（出自 data/costume.json）")
        for x in p["checklist"]:
            print(f"  □ {x}")
        if p["pitfalls"]:
            print("\n已知會畫錯的地方")
            for x in p["pitfalls"]:
                print(f"  ! {x}")
        print("\n出處")
        for sid in p["sources"]:
            src = COSTUME["sources"].get(sid)
            if src:
                print(f"  - {src['org']}｜{src['t']}\n    {src['url']}")
    elif "--refs" in sys.argv:
        print("\n".join(refs(county)))
    elif "--fix-composition" in sys.argv:
        print(build_composition_fix(county))
    elif "--fix-framing" in sys.argv:
        print(build_framing_fix(county))
    elif "--fix-plant" in sys.argv:
        print(build_plant_fix(county))
    elif "--fix-hair-flower" in sys.argv:
        print(build_hair_flower_fix(county))
    elif "--fix-tote-print" in sys.argv:
        print(build_tote_print_fix(county))
    elif "--cleanup-right-zone" in sys.argv:
        print(build_right_zone_cleanup(county))
    elif "--fix-landmark-boundary" in sys.argv:
        print(build_landmark_boundary_fix(county))
    elif "--cleanup-bottom-right" in sys.argv:
        print(build_bottom_right_cleanup(county))
    elif "--fix-print" in sys.argv:
        print(build_print_fix(county))
    elif "--fix-hand-framing" in sys.argv:
        print(build_hand_framing_fix(county))
    elif "--check" not in sys.argv:
        print(build(county))
