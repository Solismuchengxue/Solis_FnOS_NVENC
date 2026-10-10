#!/bin/bash
# 新测试容器内，仅构建同版本辅助库和探针；不编译 libavcodec。
set -euo pipefail
test "$#" -eq 2
test -f /.dockerenv
root=$(realpath -e -- "$1")
out=$(realpath -e -- "$2")
test -z "$(ls -A -- "$out")"
test ! -e /probe
mkdir /probe
test "$(sha256sum "$root/artifacts/sources/ffmpeg-8.1.1.tar.xz" | cut -d ' ' -f1)" = b6863adde98898f42602017462871b5f6333e65aec803fdd7a6308639c52edf3
tar --no-same-owner -xf "$root/artifacts/sources/ffmpeg-8.1.1.tar.xz" -C /probe
cd /probe/ffmpeg-8.1.1
./configure --disable-everything --disable-programs --disable-avcodec --disable-avformat --disable-avdevice --disable-avfilter --disable-swscale --disable-network --enable-shared --disable-static --disable-doc --disable-debug > "$out/configure.log" 2>&1
make -j2 libavutil/libavutil.so.60 libswresample/libswresample.so.6 > "$out/compile.log" 2>&1
mkdir "$out/tool"
cp libavutil/libavutil.so.60 libswresample/libswresample.so.6 "$out/tool/"
gcc -Wall -Wextra -Werror -O2 -I. "$root/scripts/codec_regression.c" "$root/artifacts/rebuild-20261009/run1/libavcodec.so.62" "$out/tool/libavutil.so.60" -Wl,-rpath-link,"$out/tool" -ldl -lm -o "$out/tool/codec_regression"
test ! -e libavcodec/libavcodec.so.62
cp ffbuild/config.mak "$out/config.mak"
sha256sum "$out/tool/"* > "$out/tool_sha256.txt"
printf 'TEST_DRIVER_PREPARED; LIBAVCODEC_NOT_REBUILT\n'
