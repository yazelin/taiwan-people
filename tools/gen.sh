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

# stdin 一定要導 /dev/null。codex exec 會把 stdin 當成「還有補充輸入要讀」並等 EOF：
#   $ codex exec -- "回覆 OK"        # 前景，stdin 已關 → 幾秒回
#   $ (背景執行同一行)                # stdin 是不會關的管線 → 印一行
#                                     # 「Reading additional input from stdin...」然後永遠等下去
# 2026-08-11 實測：背景跑兩輪各卡了 1 小時 55 分與 1 小時 27 分，連 session 檔都沒建，
# 因為它根本還沒開工。導 /dev/null 之後同一條指令 10 秒完成。
# 輸出也不要再整包丟掉，卡住時那一行提示是唯一的線索。
codex exec -C "$(pwd)" -s workspace-write --skip-git-repo-check \
  "${args[@]}" -- "\$imagegen $prompt" </dev/null >"${out%.*}.codex.log" 2>&1

after=$(mktemp)
find ~/.codex/generated_images -name '*.png' 2>/dev/null | sort > "$after"
# codex 一次會產生「多個不同的嘗試」，不是「一張逐步改進」——
# 實測台北那次出了 5 張，最新的那張 101 最小最淡，第 3 張才是最好的。
# 所以全部留下由人審，取最新的等於每次丟掉 4 個候選而且沒理由相信最後一張最好。
mapfile -t news < <(comm -13 "$before" "$after" | xargs -r ls -1t 2>/dev/null)
rm -f "$before" "$after"

if [ ${#news[@]} -eq 0 ]; then
  # 原本這裡寫死「prompt 被拒或額度用盡」，那是猜的，而且猜錯過：實際遇到的是
  # server_overloaded（Selected model is at capacity），額度其實只用了 9%。
  # 猜測性的錯誤訊息比沒有訊息更糟，會把人帶去查錯方向。真正的原因在 codex 自己的
  # session 檔裡，抓出來印。
  sess=$(ls -t ~/.codex/sessions/*/*/*/*.jsonl 2>/dev/null | head -1)
  reason=$(python3 - "$sess" <<'PY' 2>/dev/null
import json, sys
try:
    for line in open(sys.argv[1], encoding='utf-8', errors='ignore'):
        try: p = json.loads(line).get('payload', {})
        except Exception: continue
        e = p.get('error')
        if e:
            print(e.get('message', ''), '／', e.get('codex_error_info', ''))
except Exception:
    pass
PY
)
  echo "FAIL: codex 沒有產生新的 PNG${reason:+　原因：$reason}" >&2
  echo "      完整輸出：${out%.*}.codex.log" >&2
  exit 1
fi

# 候選全部複製到 <輸出檔>.cand/ 供審查，預設仍先放最新的一張到 <輸出檔>
cand="${out%.*}.cand"
rm -rf "$cand"; mkdir -p "$cand"
i=1
for f in "${news[@]}"; do
  cp "$f" "$cand/$(printf '%02d' $i).png"
  i=$((i+1))
done
cp "${news[0]}" "$out"
echo "OK $out  <-  $(basename "${news[0]}")  （共 ${#news[@]} 個候選在 $cand/）"
