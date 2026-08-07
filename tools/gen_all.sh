#!/bin/bash
# 逐一產生各縣市的無字底圖。
#
#   bash tools/gen_all.sh                 # 生所有還沒有底圖的縣市
#   bash tools/gen_all.sh 澎湖縣 金門縣    # 只生指定的
#
# 每張約 1–2 分鐘。已經有 img/<id>-base.webp 的會跳過，可以中斷後續跑。
set -u
cd "$(dirname "$0")/.."
# gen.sh 改放 repo 內：原本在 /tmp，重開機被清掉整條產線就斷了
GEN="${GEN:-tools/gen.sh}"   # 上面已經 cd 到 repo 根目錄，所以用相對路徑
OUT=/tmp/taiwan-people-gen
mkdir -p "$OUT"

if [ $# -gt 0 ]; then
  NAMES=("$@")
else
  mapfile -t NAMES < <(python3 -c "
import json
d=json.load(open('data/counties.json',encoding='utf-8'))
for c in d['counties']:
    if not c.get('base'): print(c['name'])
")
fi

ok=0; fail=0
for n in "${NAMES[@]}"; do
  id=$(python3 -c "
import json,sys
d=json.load(open('data/counties.json',encoding='utf-8'))
print(next(c['id'] for c in d['counties'] if c['name']=='$n'))
")
  dst="$OUT/$id-base.png"
  if [ -f "$dst" ]; then echo "跳過 $n（已存在）"; continue; fi

  prompt=$(python3 tools/build_prompt.py "$n" 2>/dev/null) || { echo "✘ $n 資料不全"; fail=$((fail+1)); continue; }
  refs=$(python3 tools/build_prompt.py "$n" --refs 2>/dev/null)

  echo "生成 $n …"
  # gen.sh 有時回報成功卻沒把檔案搬出來（AGENTS.md 有記）。留一個時間戳當救援依據。
  stamp=$(mktemp); touch "$stamp"
  "$GEN" "$dst" "$prompt" $refs >/dev/null 2>&1
  if [ ! -f "$dst" ]; then
    rescue=$(find ~/.codex/generated_images -name '*.png' -newer "$stamp" 2>/dev/null \
             | xargs -r ls -1t 2>/dev/null | head -1)
    [ -n "$rescue" ] && { cp "$rescue" "$dst"; echo "  （從 codex 目錄救回）"; }
  fi
  rm -f "$stamp"
  if [ -f "$dst" ]; then
    python3 - "$dst" "img/$id-base.webp" <<'PY'
import sys
from PIL import Image
Image.open(sys.argv[1]).convert("RGB").save(sys.argv[2], "WEBP", quality=88, method=5)
PY
    echo "  ✔ img/$id-base.webp"
    ok=$((ok+1))
  else
    echo "  ✘ $n 生成失敗"
    fail=$((fail+1))
  fi
done
echo "完成 $ok 張，失敗 $fail 張。原始 PNG 留在 $OUT。"
echo "驗收過之後跑 tools/register_base.py 把 base 欄位寫回 data/counties.json。"
