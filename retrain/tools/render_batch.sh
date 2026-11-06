#!/usr/bin/env bash
# 分批渲染：每批重開一次 Blender（避免長時間 GPU 錯誤累積），失敗就用 --skip-existing 重試。
# 用法：bash retrain/tools/render_batch.sh <render|empty> <seed> <起始編號> <結束編號(不含)> [每批張數]
set -u
cmd=$1; seed=$2; from=$3; to=$4; chunk=${5:-200}
here=$(dirname "$0")
for ((s=from; s<to; s+=chunk)); do
  n=$(( to - s < chunk ? to - s : chunk ))
  for try in 1 2 3; do
    echo "[batch] $cmd seed=$seed start=$s count=$n try=$try"
    python "$here/run_blender.py" "$cmd" --seed "$seed" --start "$s" --count "$n" --skip-existing && break
  done
done
