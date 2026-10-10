#!/bin/bash
# 已批准的新本地测试容器内执行；参考材料先按当次记录核对，不安装依赖。
set -euo pipefail
test "$#" -eq 4
test -f /.dockerenv
root=$(realpath -e -- "$1")
test_run=$(realpath -e -- "$2")
reference=$(realpath -e -- "$3")
out=$(realpath -e -- "$4")
test -z "$(ls -A -- "$out")"
mkdir "$out/tool" "$out/results"
gcc -Wall -Wextra -Werror -O2 -I"$reference" "$root/scripts/decode_audio_reference.c" "$reference/libdca.so.0" -lfdk-aac -ldl -lm -o "$out/tool/decode_audio_reference" > "$out/compile.log" 2>&1
export LD_LIBRARY_PATH="$reference"
ldd "$out/tool/decode_audio_reference" > "$out/tool/dependencies.txt"
sha256sum "$out/tool/decode_audio_reference" "$reference/libdca.so.0" /usr/lib/x86_64-linux-gnu/libfdk-aac.so.2 > "$out/identities.txt"
printf 'case\treference\texit\n' > "$out/status.tsv"
for case_name in aac_lc_stereo aac_lc_51 aac_he_mono aac_he_stereo aac_he_fixed aac_hev2 aac_hev2_fixed dts_stereo dts_51; do
  if [[ "$case_name" == aac_* ]]; then mode=aac; expected=/usr/lib/x86_64-linux-gnu/libfdk-aac.so.2; else mode=dts; expected="$reference/libdca.so.0"; fi
  set +e
  EXPECTED_REFERENCE_LIB="$expected" "$out/tool/decode_audio_reference" "$mode" "$test_run/fixtures/$case_name.scfix" "$out/results/$case_name.raw" > "$out/results/$case_name.json" 2> "$out/results/$case_name.log"
  status=$?
  set -e
  printf '%s\t%s\t%d\n' "$case_name" "$mode" "$status" >> "$out/status.tsv"
done
set +e
EXPECTED_REFERENCE_LIB="$reference/libdca.so.0" "$out/tool/decode_audio_reference" aac "$test_run/fixtures/aac_hev2.scfix" "$out/guard.raw" > "$out/guard.json" 2> "$out/guard.log"
guard=$?
set -e
test "$guard" -ne 0 && test ! -e "$out/guard.raw"
printf 'REFERENCE_PATH_GUARD=PASS\n'
