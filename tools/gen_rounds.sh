#!/bin/bash
# 同一份規格連跑幾輪，每輪存成不同檔名，跑完自己挑，不要直接蓋掉 img/。
#
#     bash tools/gen_rounds.sh 屏東縣・排灣族 3
#     # 產出 tmp/rounds/<id>-r1.webp … -r3.webp，img/ 不動
#     cp tmp/rounds/<id>-r2.webp img/<id>-base.webp   # 挑好再自己複製
#
# 為什麼要有這支：同一份規格每次抽樣本來就有好有壞，單次結果不能拿來判斷
# 規格改對沒有。2026-08-16 排灣第二輪形制全對只差顏色，第三輪改完規格重跑
# 反而倒退（上衣縮回臀部、開叉不見了），這時才發現第二輪那張已經被覆蓋掉，
# /tmp 的 PNG 也是同一個檔名一起沒了，git 裡留的是第一輪的錯版，等於白跑。
#
# 直接落地到 img/ 的版本在 tools/gen_all.sh，那支適合已經穩定的縣市。
set -u
cd "$(dirname "$0")/.."

# 金鑰要自己撈：~/.bashrc 第 15 行左右有「非互動 shell 直接 return」，
# 排在那之後的 export 對腳本無效，所以不能只靠 source。
export CODEX_IMAGE_KEY="${CODEX_IMAGE_KEY:-$(grep -oP '^export CODEX_IMAGE_KEY=\K.*' ~/.bashrc | tr -d '"')}"
[ -n "$CODEX_IMAGE_KEY" ] || {
  echo "FAIL: 讀不到 CODEX_IMAGE_KEY，先確認 ~/.bashrc 裡有 export CODEX_IMAGE_KEY=..." >&2
  exit 1
}

n="${1:?用法：bash tools/gen_rounds.sh 縣市名 [輪數]}"
rounds="${2:-3}"
keep=tmp/rounds
mkdir -p "$keep"

id=$(python3 -c "
import json
d = json.load(open('data/counties.json'))
print(next(c['id'] for c in d['counties'] if c['name'] == '$n'))") || exit 1

# prompt 只取一次：中途改資料會讓各輪不可比，那就失去連跑的意義了
prompt=$(python3 tools/build_prompt.py "$n") || exit 1
refs=$(python3 tools/build_prompt.py "$n" --refs)

for r in $(seq 1 "$rounds"); do
  echo "═══════ $n 第 $r 輪 ═══════"
  dst="$keep/$id-r$r.png"
  for i in 1 2 3; do
    rm -f "$dst"
    if GEN_COUNTY="$n" python3 tools/gen_remote.py "$dst" "$prompt" $refs; then
      python3 - "$dst" "$keep/$id-r$r.webp" <<'PY'
import sys
from PIL import Image
Image.open(sys.argv[1]).convert("RGB").save(sys.argv[2], "WEBP", quality=88, method=5)
PY
      echo "  ✔ $keep/$id-r$r.webp"
      break
    fi
    echo "  （第 $i 次失敗，重試）"
  done
done

echo "═══════ 跑完 $rounds 輪，自己挑一張複製進 img/ ═══════"
ls -la "$keep"/$id-r*.webp 2>/dev/null
