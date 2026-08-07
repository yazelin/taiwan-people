#!/bin/bash
# 呼叫 codex 產生一張圖。
#
#   tools/gen.sh <輸出檔> <prompt> [參考圖...]
#
# 原本這支放在 /tmp，重開機被清掉整條產線就斷了，所以搬進 repo。
#
# 擋兩件事：
#   1. 空的或過短的 prompt——多半是產 prompt 的指令失敗了，不該拿去生圖
#   2. 「沒有真的產生新圖卻複製到舊檔」——只認執行後才出現的 PNG
set -u
out="$1"; shift
prompt="$1"; shift

if [ ${#prompt} -lt 40 ]; then
  echo "FAIL: prompt 太短或是空的（長度 ${#prompt}）" >&2
  exit 1
fi

args=()
for f in "$@"; do
  [ -f "$f" ] || { echo "FAIL: 參考圖不存在 $f" >&2; exit 1; }
  args+=(--image "$f")
done

before=$(mktemp)
find ~/.codex/generated_images -name '*.png' 2>/dev/null | sort > "$before"

codex exec -C "$(pwd)" -s workspace-write --skip-git-repo-check \
  "${args[@]}" -- "\$imagegen $prompt" >/dev/null 2>&1

after=$(mktemp)
find ~/.codex/generated_images -name '*.png' 2>/dev/null | sort > "$after"
newest=$(comm -13 "$before" "$after" | xargs -r ls -1t 2>/dev/null | head -1)
rm -f "$before" "$after"

[ -z "$newest" ] && { echo "FAIL: codex 沒有產生新的 PNG（prompt 被拒或額度用盡）" >&2; exit 1; }
cp "$newest" "$out" && echo "OK $out  <-  $(basename "$newest")"
