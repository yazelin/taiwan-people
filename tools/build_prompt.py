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
        # rank 是整族的階級規範，同時寫著各階級各能穿什麼。當這一筆畫的是特定階級時，
        # 那段裡「別的階級不可以穿什麼」會直接跟 outfit 打架——2026-08-17 排灣改畫貴族後
        # 連跑兩輪紋飾一項都沒出來，就是因為 rank 裡的「平民不可飾以任何紋飾」還在，
        # 而且它前面冠著「this decides what she is allowed to wear」，語氣比 outfit 更強。
        # rank 本身是正確的族群知識不能刪，所以由 scene.rank_note 指明這一筆屬於哪一階級。
        parts.append("RANK AND ELIGIBILITY — this is the people's rank system as a whole: "
                     + p["rank"] + " ")
        note = c.get("scene", {}).get("rank_note")
        if note:
            parts.append("WHICH RANK THIS PICTURE SHOWS — read the paragraph above through this: "
                         + note + " ")
    parts.append("Do not add ornament from any other Taiwanese people: no other people's "
                 "weave patterns, head-dress, feathers or bead work. ")
    # 實測兩張特別版都退回模型熟悉的「民族風／戲服」樣板：卑南族被畫成及地長袍長裙
    # （短身上衣變長袍、護腿布片被裙子蓋住看不見），客家大襟衫被畫成立領盤扣對襟
    # ——盤扣正是 costume_basis 裡標記為錯誤的那一項。
    # 光把正確的形制寫出來不夠，要把錯誤的版本明確否定掉。
    parts.append(
        "CONSTRUCTION IS NOT DECORATION — draw the garment shapes exactly as described "
        "above, not a generic 'ethnic costume' or stage-opera silhouette. "
        "If a garment is described as short-bodied, it must NOT become a full-length robe. "
        "If a skirt length is given, it must NOT become floor-length. "
        "If the front opening is described as asymmetric and fastening to one side, it must "
        "NOT be drawn as a symmetrical centre-front opening. "
        "If the fastenings are described as straight cloth-strip buttons, they must NOT be "
        "drawn as knotted frog closures. "
        "Every layer named above must remain visible in the finished picture — do not let an "
        "outer garment cover and hide a layer that was listed, especially leg-cloths and "
        "chest-cloths. ")
    # 有實物照時才加這段。
    # 第一版寫成「不得複製任何織紋」——那是錯的，而且自相矛盾：族服的識別特徵常常
    # 就是紋樣本身（賽夏沒有雷女紋只剩標籤、太魯閣沒有菱紋就變泛族風），
    # 禁掉紋樣等於禁掉這張圖存在的理由。要禁的從來不是「紋樣」，是
    # 「登記在案的特定作品」與「可辨識到單一部落的專屬紋章」。
    if c.get("scene", {}).get("costume_refs"):
        # cut_only：照片跟這一筆的階級或場合對不上，只能拿來看剪裁。
        # 排灣就是這種情形——找得到的女裝照片都是貴族盛裝，而這一筆畫平民，
        # 平民不可飾以任何紋飾。這段通用文字原本一律要求「照著照片把紋飾畫出來」，
        # 跟族別規格的「裝飾一律不取」在同一份 prompt 裡正面打架，
        # 而排灣連跑三輪都畫錯。最後那句「文字與照片不符時以文字為準」
        # 擋不住它——那是元規則，位置又在整段最後，份量遠不如前面那句「draw it」。
        cut_only = c["scene"].get("costume_refs_cut_only")
        # 每張實物照各自報上自己拍的是什麼。原本這段只寫「THE LAST REFERENCE IMAGE」單數，
        # 但實際附的是 2 到 4 張，而且常常是不同件衣服的不同部位；「follow it for how the
        # colours are distributed」這種話在多張並存時沒有明確對象，模型只能自己混。
        # 2026-08-20 掃出來的實例：卑南附 4 張，其中 3 張是長袖 makiteng，
        # 而 checklist 第 3 條明寫「當代穿法是無袖、胸兜直接上身，不要把長袖畫進去」——
        # 照片與文字各拉一邊，畫對純屬運氣。所以清單末尾那句
        # 「照片裡有、但上面文字沒列的衣物，不要畫」是這段的重點，不是補充。
        parts.append(_ref_manifest(c))
        parts.append(
            "THE LAST REFERENCE IMAGE is a photograph of this actual garment as it is worn today. "
            + ("Take from it ONLY the CUT AND THE PROPORTIONS: how the pieces are constructed and "
               "layered, the garment lengths, where the openings and slits fall, how the wrap "
               "pieces sit under the outer one. Take NONE of its ornament, and none of its "
               "colours: that photograph shows a garment of a DIFFERENT RANK OR OCCASION from the "
               "one described in words above, and its decoration would be a false claim on this "
               "character. The written description alone decides what pattern and what colour "
               "this garment carries — and it says PLAIN. "
               if cut_only else
               "Follow it for how the pieces are constructed and layered, the proportions (garment "
               "lengths, how deep the trim bands are, how wide the panels are), how the colours are "
               "distributed, AND the ornament actually visible on it — the bead work, the metal discs "
               "and the way they are laid out along the bands. That patterning is the point of the "
               "garment, not an optional extra: draw it. ")
            + "Two things you must NOT take from it: do not reproduce it as a ceremonial or wedding "
            "dress, and do not add any single crest or emblem that would mark one specific village "
            "rather than the people as a whole. "
            "Do NOT copy the person, face, pose, hairstyle, background or framing from it — "
            "those come from the character sheets and the scene description. "
            "THE COSTUME PHOTOGRAPHS ARE GARMENT-ONLY CROPS AND CONTAIN NO FACE. The character's "
            "face, eyes, eye shape, face shape, skin and hair come from the character sheets and "
            "from nowhere else: keep the round face and large round brown eyes exactly as drawn "
            "there. Do not lengthen the face, narrow the eyes, raise the cheekbones or make her "
            "look older — if the finished face would not be recognised as the same person as the "
            "character sheets, the picture is wrong. "
            + ("" if cut_only else
               "Match the DENSITY of the ornament in the photographs, not just its motifs: where the "
               "photograph shows a few separate ornaments on empty cloth, draw a few separate "
               "ornaments on empty cloth. Filling the band with continuous bead lines or dense inlay "
               "is a mistake even when every individual motif is correct. ")
            + "Where the photograph and the written description disagree, the written description wins. ")
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
        # 畫布規則放第一行，不是放結尾。prompt 有一萬多字，結尾那句
        # 「Landscape aspect ratio, 4:3」讀不到——.11 的服務會回 1536x1024（1.50），
        # 那個比例放進網頁 1.25 的框會被裁掉。2026-08-14 賽夏與泰雅各試五次全敗，
        # 而邵族把同一句話搬到前面之後就過了。長 prompt 裡指令的位置比措辭重要。
        "CANVAS: landscape FOUR-TO-THREE (4:3) — noticeably taller than a widescreen 3:2 frame. "
        "Compose for 4:3, not for a wide banner. This governs the whole picture. "
        "An anime illustration in the same style, colour palette and painterly shading as "
        "image 1. A single continuous scene — not a collage, not a panel of separate items. "
        f"THE CHARACTER, locked by the reference sheets: {CARD['card']} "
        "Keep her face, eyes, hair colour and hair length exactly as in the reference sheets — "
        "but NOT the hairstyle: the sheets show it blown loose by the wind, which is wrong. "
        f"IN HER HAIR: {s['hair']}. "
        f"OUTFIT — do NOT copy the clothes shown in the reference sheets, which lock only her "
        f"face and build. Dress her instead in: {s['outfit']}. "
        + costume_block(c)
        # 帆布提袋是系列的固定道具，但有些特別版該背的是族群自己的攜物袋
        # （噶瑪蘭的檳榔袋就是整組服飾的一件），兩個都掛在身上會變成雜物。
        # tote=False 有兩種情況：族群自己有攜物袋（噶瑪蘭的檳榔袋、阿美的攜物袋），
        # 或這一族的女子服飾根本沒有袋子（拉阿魯哇）。後者若照抄「只背傳統的那個」，
        # 等於在暗示畫面上該有一個袋子，模型就會自己發明一個。所以看 outfit 有沒有提到袋。
        + ("Keep the canvas tote bag. " if c["scene"].get("tote", True) else
           "She carries NO canvas tote bag in this picture"
           + (" — the only bag is the traditional one described in the outfit above. "
              if any(w in c["scene"].get("outfit", "").lower()
                     for w in ("bag", "pouch", "satchel"))
              else ", and no bag or satchel of any kind: her hands and shoulders are free. "))
        # tote_print 原本只有 --fix-tote-print 讀得到，build() 沒用它——
        # 等於正式生成時提袋印花一律由模型自由發揮。新竹市那次就發明出一張
        # 像剪貼素材的 IC 晶片示意圖，而且對不回任何一筆 landmarks。
        + (f"THE TOTE'S PRINT: {s['tote_print']}. " if s.get("tote_print") else "")
        # 角色卡固定寫著「small hoop earrings」，但特別版的 accessories 常常另有指定
        # （拉阿魯哇是獸骨貝類耳飾、噶瑪蘭是多股白珠頸鍊）。兩句都進 prompt，模型會自己挑一個——
        # 拉阿魯哇那張最後畫成金色小圈，明明資料裡有依據的飾品沒被畫出來。
        # 所以特別版要明講以 accessories 為準，覆寫角色卡。
        + ("ON HER, and these REPLACE the small hoop earrings named in the character sheet — "
           "draw what is listed here instead: " if c.get("culture") else "ON HER: ")
        + f"{s.get('accessories', '')}. These small details matter — she should look "
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
        # 野柳那次：女王頭是單一小物件，剛好落在她舉起的右手旁邊，
        # 看起來像她手上舉著一塊蜂窩岩。地標大範圍（老街、城市）時不會有這個問題，
        # 單一物件時一定要把它跟手推開。
        "The landmark must be clearly SEPARATED from her raised right hand and from whatever "
        "she is holding — leave open background between them so it never reads as an object "
        "she is carrying, balancing or holding up. It belongs to the scenery, not to her. "
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
           # 這三段原本寫成一連串的「不准有」，模型照做的結果就是一片死白霧。
           # 台北、台東、新北、新竹縣都栽在這裡。現在改成先要求實質內容再列禁令——
           # 禁令留著（那是防地理錯誤用的），但不再是全部。
           "This county is INLAND — there is NO SEA anywhere in the picture. The right 40 "
           "percent is open sky over low receding ridges, and it must NOT be a flat empty wash. "
           "Give it real substance at LOW contrast: three or four ridgelines layered one behind "
           "another, each paler than the one in front, mist pooling in the valleys between them, "
           "and banded cloud with soft edges in the sky above. No buildings, figures, objects, "
           "rooftops, nearby trees, vegetation, dark foreground slopes or hard dark shapes. "
           "It should read as calm depth with things to look at, not as blank paper. "
           if s.get("right_zone", "sea") == "sky" else
           "The right 40 percent is calm open river water meeting sky, and it must NOT be a flat "
           "empty wash. Give it real substance at LOW contrast: banded cloud with soft edges high "
           "up, a paler haze band along the far bank, gentle current texture on the water and long "
           "soft reflected light bands. No buildings, figures, boats, objects, land, shoreline, "
           "rocks, vegetation or hard dark shapes. Any sunlight glitter stays LOW near the horizon "
           "so the middle stays even for text. "
           if s.get("right_zone") == "river" else
           "The right 40 percent is calm open water meeting sky, and it must NOT be a flat empty "
           "wash. Give it real substance at LOW contrast: banded cloud layers with soft edges high "
           "up, a paler haze band at the horizon, gentle swell texture and long soft reflected "
           "light bands on the water, and — only if it is genuinely visible from this viewpoint — "
           "one far, pale headland or islet low on the horizon. No figures, boats, vehicles, signs, "
           "buildings, rocks, vegetation or hard dark shapes. Any sunlight glitter stays LOW near "
           "the horizon so the middle stays even for text. It should read as calm depth with "
           "things to look at, not as blank paper. ")
        + "The top 22 percent of the right half is open sky with nothing in it — her hair does "
        "reach the top of the frame on the left, which is intended. "
        "NO TEXT ANYWHERE: no headline, captions, panels, photo tiles, icon badges, coloured "
        "bars, border or frame. The T-shirt and tote each carry a printed illustration with "
        "absolutely no words or characters; every print is a complete finished graphic with no "
        "blank patches or unlabelled stickers. Landscape aspect ratio, 4:3. "
        "MUST NOT APPEAR: " + "; ".join(CARD["must_not"]) + "."
    )


def _ref_manifest(c):
    """把附上的實物照逐張報出「這張拍的是什麼」，並劃清它管到哪裡。

    描述文字取自 data/costume-refs.json（由 SOURCES.md 轉出），不另外手寫一份，
    免得同一件事有兩個版本。
    """
    import json as _json
    meta = _json.loads((ROOT / "data" / "costume-refs.json").read_text(encoding="utf-8"))["refs"]
    lines = []
    for i, p in enumerate(c["scene"]["costume_refs"], 1):
        d = meta.get(pathlib.Path(p).name, {}).get("desc", "")
        if d:
            lines.append(f"({i}) {d}")
    if not lines:
        return ""
    return (
        "THE COSTUME PHOTOGRAPHS attached after the two character sheets, in the order attached, "
        "each show this: " + "; ".join(lines) + ". "
        "Each photograph governs only the garment and the part of the body its own line names. "
        "Do not carry one photograph's colour, density or ornament across onto a garment that a "
        "different photograph — or the written description above — is responsible for. "
        "If a photograph shows a garment that the written description above does not list for this "
        "picture, DO NOT DRAW THAT GARMENT: the photograph was collected for its construction and "
        "its patterning, not as an instruction to dress her in it. "
    )


def refs(c):
    """生圖要附的參考圖：image 1 是舊海報，其後是角色設定圖，最後才是服飾實物照。

    服飾實物照放在最後，是因為 build() 裡那段說明用「最後一張參考圖」來指涉它。
    只有 scene.costume_refs 有寫的那幾筆才會附——照片要授權允許才收，見
    data/costume-refs/SOURCES.md。
    """
    out = []
    if c.get("poster"):
        out.append(ROOT / "img" / f"{c['poster']}.webp")
    out.extend([ROOT / "data" / "character" / "ref-half.png",
                ROOT / "data" / "character" / "face.png"])
    out.extend(ROOT / p for p in c.get("scene", {}).get("costume_refs", []))
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


def build_landmark_shape_fix(c):
    """既有底圖只重畫主地標本身，其餘一律保留。

    用在「畫面是好的、但那個地標畫錯了」的情況——宜蘭那張把離岸的龜山島畫成接在
    陸地上的岬角，整張圖其他部分（國蘭髮花、構圖、右側留白）都比重生的候選好，
    重生等於用好的換壞的。內容取自 scene.hero_landmark_en，所以其他縣市也能用。
    """
    s = c["scene"]
    return (
        "Use case: precise-object-edit. Image 1 is the edit target. "
        "Change ONLY the main landmark in the middle distance and the water immediately around it. "
        "Whatever landform currently occupies that part of the picture is wrong and must be removed "
        "completely, together with any buildings, roads, breakwaters or shoreline that currently sit on "
        "it or connect it to the land. In its place, continue the open sea, and on the far horizon draw: "
        + s["hero_landmark_en"] + " "
        "Draw it at the size and haze of things that far away — small, pale and low-contrast, clearly "
        "behind everything in the foreground. "
        "Preserve everything else exactly unchanged: the complete character, her face, eyes, hair, the "
        "flower and leaves in her hair, the hairpin, earrings, all clothing, both hands and whatever she "
        "is holding, every foreground plant, and all the town, road, railway, bridge, near shoreline and "
        "rocks on the left side. Keep the sky, horizon height, lighting, palette, painterly anime style "
        "and 4:3 framing. Do not move or rescale the character. "
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


def build_ornament_cleanup(c):
    """既有底圖只清掉衣物上多畫的裝飾，其餘保留。

    噶瑪蘭那張的上衣黑帶上殘留兩三顆大銀圓盤——那些盤只屬於攜物袋的斜背帶與袋身。
    整張重生要冒新的風險（前一輪就是為了修島而把國蘭髮花畫壞），這種只錯一處的
    情況用定點編輯比較划算。要清掉什麼寫在 scene.ornament_cleanup。
    """
    what = c["scene"].get("ornament_cleanup") or ""
    return (
        "Use case: precise-object-edit. Image 1 is the edit target. "
        "Change only this: " + what + " "
        "Rebuild each cleared spot as the plain cloth that surrounds it, matching its colour, "
        "weave, shading and the fall of the fabric, so that nothing looks erased or patched. "
        "Preserve exactly everything else: the character's face, warm brown eyes, expression, hair, "
        "head-dress, hairpin, earrings, every other part of the clothing and its ornament, the bag "
        "and its strap with all of their discs and tassels, both hands and whatever she holds, the "
        "necklace, the foreground plants, the whole background including the offshore island, the "
        "composition, lighting, palette, painterly anime style and 4:3 framing. "
        "Do not change, add or remove anything else. No text, letters, logos, panels, borders or "
        "watermarks."
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
        # 阿蕊是女子，畫面上永遠不會有男裝。男子條目留在 costume.json 是資料完整性，
        # 但拿去當驗收清單會每次都產生假 NG（拉阿魯哇那輪十項裡有兩項是這樣來的），
        # 而假 NG 會讓人開始略過整份清單。要看全部跑 --checklist --all。
        skipped = 0
        print(f"{p['name']} 出圖驗收（出自 data/costume.json）")
        for x in p["checklist"]:
            if x.startswith(("男子", "男性")) and "--all" not in sys.argv:
                skipped += 1
                continue
            print(f"  □ {x}")
        if skipped:
            print(f"  （另有 {skipped} 條男裝條目，阿蕊是女子用不到，要看加 --all）")
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
    elif "--fix-landmark-shape" in sys.argv:
        print(build_landmark_shape_fix(county))
    elif "--fix-landmark-boundary" in sys.argv:
        print(build_landmark_boundary_fix(county))
    elif "--cleanup-bottom-right" in sys.argv:
        print(build_bottom_right_cleanup(county))
    elif "--cleanup-ornament" in sys.argv:
        print(build_ornament_cleanup(county))
    elif "--fix-print" in sys.argv:
        print(build_print_fix(county))
    elif "--fix-hand-framing" in sys.argv:
        print(build_hand_framing_fix(county))
    elif "--check" not in sys.argv:
        print(build(county))
