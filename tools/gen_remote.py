#!/usr/bin/env python3
"""改打 .11 的 codex-image-service 產一張圖，介面與 tools/gen.sh 相同。

    tools/gen_remote.py <輸出檔> <prompt> [參考圖...]
    GEN=tools/gen_remote.py bash tools/gen_all.sh 高雄市・拉阿魯哇族

為什麼要有這支：本機 gen.sh 走的是完整的 codex agent，出圖後會自己裁圖複驗、
發現形制錯就重修，單張要 30 分鐘以上。.11 那個服務是 FastAPI 直接呼叫一次
image_gen 就回傳，實測單張 4-12 分鐘，但**沒有自我複驗**——快是快，錯了也
不會自己發現。所以這支跑完會另外呼叫服務的 /v1/vision 做一次形制檢查，
把 codex agent 那段複驗補回來，只是變成看得見的一步。

跟 gen.sh 一樣擋兩件事：
  1. 空的或過短的 prompt——多半是產 prompt 的指令失敗了，不該拿去生圖
  2. 拿到重複的舊圖——服務端有內容雜湊去重，這裡再存一份 sha 當第二道

環境變數：
  CODEX_IMAGE_URL   服務位址，預設 https://ching-tech.ddns.net/codex-image
  GEN_NO_VERIFY=1   跳過 /v1/vision 那步（只想比生圖速度時用）
"""
import base64
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = os.environ.get("CODEX_IMAGE_URL", "https://ching-tech.ddns.net/codex-image").rstrip("/")
SEEN = ROOT / "tmp" / "gen_remote_sha.txt"      # 跨次執行記得看過哪些輸出


KEY = os.environ.get("CODEX_IMAGE_KEY", "")


def post(path, payload, timeout):
    if not KEY:
        raise SystemExit("FAIL: 沒有 CODEX_IMAGE_KEY。那把金鑰 export 在 ~/.bashrc，"
                         "而且必須放在「非互動 shell 早退」那段之前，否則腳本讀不到")
    req = urllib.request.Request(
        BASE + path, method="POST",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {KEY}",
                 "User-Agent": "taiwan-people/gen_remote"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def b64(p):
    return base64.b64encode(pathlib.Path(p).read_bytes()).decode()


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    out = pathlib.Path(sys.argv[1])
    prompt = sys.argv[2]
    refs = sys.argv[3:]

    if len(prompt) < 40:
        raise SystemExit(f"FAIL: prompt 太短或是空的（長度 {len(prompt)}）")
    for f in refs:
        if not pathlib.Path(f).is_file():
            raise SystemExit(f"FAIL: 參考圖不存在 {f}")

    payload = {"prompt": prompt, "size": "1536x1024", "quality": "high", "count": 1}
    if refs:
        # 服務端有參考圖時會把 count 夾成 1，本來就只要一張，不衝突
        payload["reference_images_base64"] = [b64(f) for f in refs]

    t0 = time.time()
    print(f"送出 {len(refs)} 張參考圖，prompt {len(prompt)} 字 → {BASE}", file=sys.stderr)
    try:
        res = post("/v1/images/generate", payload, timeout=1800)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:400]
        raise SystemExit(f"FAIL: 服務回 {e.code} {body}")
    took = time.time() - t0

    imgs = res.get("data") or res.get("images") or []
    if not imgs:
        raise SystemExit(f"FAIL: 回應沒有圖 {json.dumps(res, ensure_ascii=False)[:300]}")
    first = imgs[0]
    raw = base64.b64decode(first["b64_json"] if isinstance(first, dict) else first)

    # 第二道去重：服務端已有內容雜湊，這裡再擋一次「拿到上一張」
    sha = hashlib.sha256(raw).hexdigest()
    SEEN.parent.mkdir(parents=True, exist_ok=True)
    if SEEN.exists() and sha in SEEN.read_text().split():
        raise SystemExit(f"FAIL: 拿到的圖與先前某次輸出逐位元組相同（{sha[:12]}），當成失敗處理")
    with SEEN.open("a") as f:
        f.write(sha + "\n")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(raw)
    print(f"✔ {out}（{len(raw)/1024/1024:.1f}MB，{took:.0f} 秒，sha {sha[:12]}）", file=sys.stderr)

    if os.environ.get("GEN_NO_VERIFY"):
        return

    # 補回 codex agent 那段自我複驗。問題從該族的 checklist 產生，不是泛泛問「畫得對嗎」——
    # 開放題會得到客套話，比對題才會得到答案（neko-tensei 那條教訓）。
    county = os.environ.get("GEN_COUNTY")
    if not county:
        return
    try:
        cl = subprocess.run([sys.executable, str(ROOT / "tools" / "build_prompt.py"), county,
                             "--checklist"], capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return
    if not cl.strip():
        return
    # 服飾實物照一起送進去，把「這張畫得對嗎」的開放題變成「跟這張比，哪裡不一樣」的比對題。
    # 開放題會得到客套話，比對題才會得到 NG——這是 neko-tensei 那條教訓，實測也是這樣。
    costume = [f for f in refs if "costume-refs" in f]
    q = ("第一張是插畫，其後是它應該參照的服飾實物照。" if costume else "這是一張插畫。") + \
        "逐條回答下列每一項：符合寫 OK、不符合寫 NG 並說明畫面上實際畫成什麼。" \
        "不要客套、不要總評，只逐條回答。\n\n" + cl
    try:
        v = post("/v1/vision",
                 {"prompt": q,
                  "images_base64": [base64.b64encode(raw).decode()] + [b64(f) for f in costume]},
                 timeout=600)
        print("\n--- 形制複驗 ---\n" + (v.get("text") or json.dumps(v, ensure_ascii=False))[:2000],
              file=sys.stderr)
    except Exception as e:
        print(f"（複驗跳過：{e}）", file=sys.stderr)


if __name__ == "__main__":
    main()
