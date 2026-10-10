#!/bin/bash
# 新测试容器内运行：同一合成 packet 输入分别由两份保存库解码。
set -euo pipefail
test "$#" -eq 2 || test "$#" -eq 3
mode=${3:-new}
case "$mode" in new|--append-vlc) ;; *) exit 64 ;; esac
test -f /.dockerenv
root=$(realpath -e -- "$1")
out=$(realpath -e -- "$2")
test -d "$out/preparation/tool"
if test "$mode" = new; then test ! -e "$out/results"; else test -s "$out/results/status.tsv"; fi
test ! -e /test
mkdir /test /test/new /test/historical
if test "$mode" = new; then mkdir "$out/results" "$out/fixtures"; fi
new="$root/artifacts/rebuild-20261009/run1/libavcodec.so.62"
old="$root/artifacts/candidate-lib/libavcodec.so.62"
new_sha=88e48674062ee5ef71864a2619324772bc856fec78c0d4793920fa7d4c15cd57
old_sha=3d7e7e241715fb6a3468a4d47d0fdaef3e6b79cecc3d3bb1f6d3118fac265367
test "$(sha256sum "$new" | cut -d ' ' -f1)" = "$new_sha"
test "$(sha256sum "$old" | cut -d ' ' -f1)" = "$old_sha"
ln -s "$new" /test/new/libavcodec.so.62
ln -s "$old" /test/historical/libavcodec.so.62
tool="$out/preparation/tool/codec_regression"
export LC_ALL=C TZ=UTC
if test "$mode" = new; then
    date -u +%FT%TZ > "$out/started_at.txt"
    printf 'case\tencoder\tdecoder\tchannels\tprofile\tgenerate_exit\tnew_exit\thistorical_exit\n' > "$out/results/status.tsv"
fi
invoke() {
    local library=$1 hash=$2 directory=$3
    shift 3
    EXPECTED_LIB="$library" EXPECTED_SHA="$hash" LD_LIBRARY_PATH="$directory:$out/preparation/tool" "$tool" "$@"
}
while read -r case_name encoder decoder channels profile; do
    test -n "$case_name"
    if test "$mode" = --append-vlc && test "$case_name" != utvideo && test "$case_name" != magicyuv; then continue; fi
    fixture="$out/fixtures/$case_name.scfix"
    gen=0; new_result=125; old_result=125
    invoke "$new" "$new_sha" /test/new generate "$encoder" "$fixture" "$channels" "$profile" > "$out/results/$case_name.generate.json" 2> "$out/results/$case_name.generate.log" || gen=$?
    if test "$gen" -eq 0; then
        new_result=0; old_result=0
        invoke "$new" "$new_sha" /test/new decode "$decoder" "$fixture" "$out/results/$case_name.new.raw" unused > "$out/results/$case_name.new.json" 2> "$out/results/$case_name.new.log" || new_result=$?
        invoke "$old" "$old_sha" /test/historical decode "$decoder" "$fixture" "$out/results/$case_name.historical.raw" unused > "$out/results/$case_name.historical.json" 2> "$out/results/$case_name.historical.log" || old_result=$?
    fi
    printf '%s\t%s\t%s\t%s\t%s\t%d\t%d\t%d\n' "$case_name" "$encoder" "$decoder" "$channels" "$profile" "$gen" "$new_result" "$old_result" >> "$out/results/status.tsv"
done <<'CASES'
h264 libx264 h264 0 -99
hevc libx265 hevc 0 -99
aac_lc_stereo aac aac 2 1
aac_lc_51 aac aac 6 1
aac_he_mono libfdk_aac aac 1 4
aac_he_stereo libfdk_aac aac 2 4
aac_he_fixed libfdk_aac aac_fixed 2 4
aac_hev2 libfdk_aac aac 2 28
aac_hev2_fixed libfdk_aac aac_fixed 2 28
ac3_stereo ac3 ac3 2 -99
ac3_51 ac3 ac3 6 -99
eac3_stereo eac3 eac3 2 -99
eac3_51 eac3 eac3 6 -99
dts_stereo dca dca 2 -99
dts_51 dca dca 6 -99
wmav1 wmav1 wmav1 2 -99
wmav2 wmav2 wmav2 2 -99
ffv1 ffv1 ffv1 0 -99
mp3 libmp3lame mp3float 2 -99
utvideo utvideo utvideo 0 -99
magicyuv magicyuv magicyuv 0 -99
CASES
# 故意声明另一份库：必须在媒体处理前拒绝，不能假借库名通过。
identity_exit=0
invoke "$old" "$old_sha" /test/new decode h264 "$out/fixtures/h264.scfix" "$out/results/invalid_identity.raw" unused > "$out/results/identity_guard.json" 2> "$out/results/identity_guard.log" || identity_exit=$?
test "$identity_exit" -ne 0
test ! -e "$out/results/invalid_identity.raw"
printf 'IDENTITY_MISMATCH_REJECTED=%s\n' "$identity_exit" > "$out/results/identity_guard.txt"
sha256sum "$out/fixtures/"* > "$out/input_sha256.txt"
date -u +%FT%TZ > "$out/completed_at.txt"
cat "$out/results/status.tsv"
