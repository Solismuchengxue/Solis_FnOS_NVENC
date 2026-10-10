#!/bin/bash
# Docker 容器内的构建核心步骤；环境启动与依赖准备由公开构建编排器负责。
# 用法：build_libavcodec.sh <源码包目录> <补丁目录> <不存在的输出目录>
# 不下载、不安装依赖、不接入服务；只交付候选 libavcodec。
set -euo pipefail
if [ "$#" -ne 3 ]; then printf 'Usage: %s SOURCE_DIR PATCH_DIR NEW_OUTPUT_DIR\n' "$0" >&2; exit 64; fi
sources=$(realpath -e -- "$1")
patches=$(realpath -e -- "$2")
output=$(realpath -m -- "$3")
test -d "$sources" && test -d "$patches"
test ! -e "$output" && test ! -L "$output"
test -d "$(dirname -- "$output")"
for tool in gcc make nasm pkg-config git tar gpg sha256sum; do command -v "$tool" >/dev/null; done
check_hash() { test "$(sha256sum "$1" | cut -d ' ' -f1)" = "$2"; }
check_hash "$sources/ffmpeg-8.1.1.tar.xz" b6863adde98898f42602017462871b5f6333e65aec803fdd7a6308639c52edf3
check_hash "$sources/nv-codec-headers.tar.gz" e30d4791fd386de8b5c9f88dec781e546ec148b8808440dd421da5f26c2700ae
check_hash "$patches/ac4_decoder.patch" 1a51adb35c14a50811487146d4215f4efab641ec4ca10ec75cc39b33310e92bd
check_hash "$patches/ac4_parser_type.patch" 7e68fc5ace33cec0ca3a120e0e8d003c49232bdd52bb61c99310ffeec97771fe
mkdir -- "$output"
mkdir -- "$output/source" "$output/prefix" "$output/candidate-lib" "$output/gnupg"
chmod 700 "$output/gnupg"
export GNUPGHOME="$output/gnupg"
gpg --batch --no-auto-key-retrieve --import "$sources/ffmpeg-devel.asc"
test "$(gpg --batch --with-colons --fingerprint | awk -F: '$1=="fpr" {print $10; exit}')" = FCF986EA15E6E293A5644F10B4322F04D67658D8
gpg --batch --no-auto-key-retrieve --verify "$sources/ffmpeg-8.1.1.tar.xz.asc" "$sources/ffmpeg-8.1.1.tar.xz"
tar --no-same-owner -xf "$sources/nv-codec-headers.tar.gz" -C "$output/source"
headers="$output/source/nv-codec-headers-1889e62e2d35ff7aa9baca2bceb14f053785e6f1"
test -d "$headers"
make -C "$headers" PREFIX="$output/prefix" install
export PKG_CONFIG_PATH="$output/prefix/lib/pkgconfig"
test "$(pkg-config --modversion ffnvcodec)" = 12.1.14.0
grep -E '^#define NVENCAPI_(MAJOR|MINOR)_VERSION' "$output/prefix/include/ffnvcodec/nvEncodeAPI.h" > "$output/nvenc-api.txt"
grep -Eq '^#define NVENCAPI_MAJOR_VERSION +12$' "$output/nvenc-api.txt"
grep -Eq '^#define NVENCAPI_MINOR_VERSION +1$' "$output/nvenc-api.txt"
tar --no-same-owner -xf "$sources/ffmpeg-8.1.1.tar.xz" -C "$output/source"
cd -- "$output/source/ffmpeg-8.1.1"
test "$(cat RELEASE)" = 8.1.1
git apply --check -p1 "$patches/ac4_decoder.patch"
git apply -p1 "$patches/ac4_decoder.patch"
git apply --check -p1 "$patches/ac4_parser_type.patch"
git apply -p1 "$patches/ac4_parser_type.patch"
./configure --fatal-warnings --prefix="$output/prefix" --enable-shared --disable-static --disable-doc --disable-debug \
    --disable-programs --disable-avdevice --disable-avfilter --disable-avformat \
    --disable-swscale --disable-network --disable-cuda-llvm --disable-cuda-nvcc \
    --enable-gpl --enable-version3 --enable-nonfree --enable-cuda --enable-cuvid --enable-nvdec --enable-nvenc \
    --enable-decoder=ac4 --enable-parser=ac4 \
    --enable-libx264 --enable-libx265 --enable-libvpx --enable-libwebp --enable-libopus \
    --enable-libmp3lame --enable-libvorbis --enable-libtheora --enable-libzvbi \
    --enable-libdav1d --enable-libsvtav1 --enable-libfdk-aac --enable-libdrm --enable-vaapi --enable-libvpl \
    > "$output/configure.log" 2>&1
cp ffbuild/config.mak "$output/config.mak"
grep -E '^CONFIG_AC4_(DECODER|PARSER)=yes$' "$output/config.mak" > "$output/ac4-config.txt"
test "$(wc -l < "$output/ac4-config.txt")" -eq 2
make -j2 libavcodec/libavcodec.so.62 > "$output/compile.log" 2>&1
install -m 0644 libavcodec/libavcodec.so.62 "$output/candidate-lib/libavcodec.so.62"
sha256sum "$output/candidate-lib/libavcodec.so.62" > "$output/candidate-sha256.txt"
printf 'BUILD_CORE_COMPLETE; PRIVATE_BINARY_ONLY; RUNTIME_NOT_VERIFIED\n'
