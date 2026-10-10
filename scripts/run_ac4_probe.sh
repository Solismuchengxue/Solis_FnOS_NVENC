#!/bin/bash
# 测试用途已确认的小型 AC4 elementary 输入；仅在当次授权的本地容器内执行。
set -euo pipefail
test "$#" -eq 4 && test -f /.dockerenv
root=$(realpath -e -- "$1")
test_run=$(realpath -e -- "$2")
sample=$(realpath -e -- "$3")
out=$(realpath -e -- "$4")
test -z "$(ls -A -- "$out")"
tool="$test_run/preparation/tool/codec_regression"
mkdir /ac4-new /ac4-historical
ln -s "$root/artifacts/rebuild-20261009/run1/libavcodec.so.62" /ac4-new/libavcodec.so.62
ln -s "$root/artifacts/candidate-lib/libavcodec.so.62" /ac4-historical/libavcodec.so.62
export LD_LIBRARY_PATH="/ac4-new:$test_run/preparation/tool"
export EXPECTED_LIB="$root/artifacts/rebuild-20261009/run1/libavcodec.so.62"
export EXPECTED_SHA=88e48674062ee5ef71864a2619324772bc856fec78c0d4793920fa7d4c15cd57
"$tool" import-ac4 "$sample" "$out/ac4.scfix" 0 0 > "$out/import.json" 2> "$out/import.log"
printf 'role\texit\n' > "$out/status.tsv"
for role in new historical; do
  if test "$role" = historical; then
    export EXPECTED_LIB="$root/artifacts/candidate-lib/libavcodec.so.62"
    export EXPECTED_SHA=3d7e7e241715fb6a3468a4d47d0fdaef3e6b79cecc3d3bb1f6d3118fac265367
  fi
  export LD_LIBRARY_PATH="/ac4-$role:$test_run/preparation/tool"
  set +e
  "$tool" decode ac4 "$out/ac4.scfix" "$out/$role.raw" unused > "$out/$role.json" 2> "$out/$role.log"
  status=$?
  set -e
  printf '%s\t%d\n' "$role" "$status" >> "$out/status.tsv"
done
