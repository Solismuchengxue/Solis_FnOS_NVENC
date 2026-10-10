#!/bin/bash
# New local experiment only. Never replaces the single-library deployment artifact.
set -euo pipefail
test "$#" -eq 3 || { echo 'Usage: build_ac4_experiment.sh ROOT NEW_EXPORT before|after' >&2; exit 64; }
test -f /.dockerenv
root=$(realpath -e -- "$1")
out=$(realpath -e -- "$2")
mode=$3
test "$mode" = before || test "$mode" = after
test -z "$(ls -A -- "$out")"
test ! -e /build
export LC_ALL=C TZ=UTC SOURCE_DATE_EPOCH=0
mkdir /build
sha256sum "$root/artifacts/sources/ffmpeg-8.1.1.tar.xz" "$root/patches/ac4_decoder.patch" "$root/patches/ac4_parser_type.patch" > "$out/inputs.sha256"
check_hash() { test "$(sha256sum "$1" | cut -d ' ' -f1)" = "$2"; }
check_hash "$root/artifacts/sources/ffmpeg-8.1.1.tar.xz" b6863adde98898f42602017462871b5f6333e65aec803fdd7a6308639c52edf3
check_hash "$root/patches/ac4_decoder.patch" 1a51adb35c14a50811487146d4215f4efab641ec4ca10ec75cc39b33310e92bd
check_hash "$root/patches/ac4_parser_type.patch" 7e68fc5ace33cec0ca3a120e0e8d003c49232bdd52bb61c99310ffeec97771fe
sha256sum "$root/scripts/build_ac4_experiment.sh" "$root/scripts/ac4_packet_probe.c" >> "$out/inputs.sha256"
tar --no-same-owner -xf "$root/artifacts/sources/ffmpeg-8.1.1.tar.xz" -C /build
cd /build/ffmpeg-8.1.1
git apply --check "$root/patches/ac4_decoder.patch"
git apply "$root/patches/ac4_decoder.patch"
git apply --check "$root/patches/ac4_parser_type.patch"
git apply "$root/patches/ac4_parser_type.patch"
cp libavformat/ac4dec.c "$out/upstream_ac4dec.c"
if test "$mode" = after; then
    sha256sum "$root/patches/ac4_demux.patch" >> "$out/inputs.sha256"
    git apply --check "$root/patches/ac4_demux.patch"
    git apply "$root/patches/ac4_demux.patch"
fi
cp libavformat/ac4dec.c "$out/built_ac4dec.c"
./configure --prefix=/build/install --disable-everything --disable-autodetect --enable-shared --disable-static \
    --disable-doc --disable-debug --disable-network --disable-avdevice --enable-gpl --enable-version3 \
    --enable-ffmpeg --enable-ffprobe --enable-decoder=ac4 --enable-parser=ac4 --enable-demuxer=ac4 \
    --enable-protocol=file --enable-encoder=pcm_s16le --enable-muxer=wav --enable-filter=aresample,anull \
    > "$out/configure.log" 2>&1
cp ffbuild/config.mak "$out/config.mak"
make -j2 > "$out/compile.log" 2>&1
make install > "$out/install.log" 2>&1
mkdir "$out/bin" "$out/lib"
cp /build/install/bin/ffmpeg /build/install/bin/ffprobe "$out/bin/"
cp -L /build/install/lib/*.so.* "$out/lib/"
export LD_LIBRARY_PATH="$out/lib"
gcc -std=c11 -Wall -Wextra -Werror -I/build/install/include "$root/scripts/ac4_packet_probe.c" -L"$out/lib" -l:libavformat.so.62 -l:libavcodec.so.62 -l:libavutil.so.60 -o "$out/bin/ac4_packet_probe"
"$out/bin/ffmpeg" -version > "$out/version.txt"
find "$out/bin" "$out/lib" -type f -exec sha256sum {} + > "$out/artifacts.sha256"
printf 'EXPERIMENT_%s_BUILT; TESTS_NOT_RUN (use existing local Linux Python)\n' "$mode"
