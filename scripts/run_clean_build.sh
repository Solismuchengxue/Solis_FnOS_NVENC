#!/bin/bash
# 新容器内的单次构建与只读 ELF/注册信息检查；不运行媒体或 GPU。
set -euo pipefail
test "$#" -eq 2 || { printf 'Usage: %s INPUT_ROOT EXPORT_DIR\n' "$0" >&2; exit 64; }
test -f /.dockerenv
root=$(realpath -e -- "$1")
export_dir=$(realpath -e -- "$2")
test -d "$export_dir" && test -z "$(ls -A -- "$export_dir")"
test ! -e /build
export LC_ALL=C TZ=UTC SOURCE_DATE_EPOCH=0
mkdir /build
hostname > "$export_dir/container_hostname.txt"
dpkg-query -W -f='${binary:Package}\t${Version}\n' | sort > "$export_dir/installed_packages.txt"
diff -u <(sort -- "$root/docs/build_packages.txt") "$export_dir/installed_packages.txt"
gcc --version > "$export_dir/compiler.txt"
uname -srmo > "$export_dir/kernel.txt"
sha256sum "$root/scripts/build_libavcodec.sh" "$root/scripts/run_clean_build.sh" "$root/scripts/inspect_libavcodec.c" > "$export_dir/script_inputs_sha256.txt"
date -u +%FT%TZ > "$export_dir/started_at.txt"
bash "$root/scripts/build_libavcodec.sh" "$root/artifacts/sources" "$root/patches" /build/output > "$export_dir/build.log" 2>&1
source_tree=/build/output/source/ffmpeg-8.1.1
library=/build/output/candidate-lib/libavcodec.so.62
cp "$library" "$export_dir/libavcodec.so.62"
cp /build/output/config.mak /build/output/configure.log /build/output/compile.log /build/output/ac4-config.txt /build/output/nvenc-api.txt "$export_dir/"
sha256sum "$export_dir/libavcodec.so.62" > "$export_dir/candidate_sha256.txt"
gcc -Wall -Wextra -Werror -O2 -I"$source_tree" "$root/scripts/inspect_libavcodec.c" -ldl -o /build/inspect_libavcodec
export LD_LIBRARY_PATH="$source_tree/libavutil:$source_tree/libswresample"
for label in rebuilt historical; do
    if test "$label" = rebuilt; then target=$library; else target="$root/artifacts/candidate-lib/libavcodec.so.62"; fi
    readelf -h "$target" > "$export_dir/$label.elf_header.txt"
    readelf -d "$target" > "$export_dir/$label.dynamic.txt"
    readelf --version-info "$target" > "$export_dir/$label.symbol_versions.txt"
    nm -D --defined-only "$target" | awk '{print $3}' | sort > "$export_dir/$label.exports.txt"
    /build/inspect_libavcodec "$target" | sort > "$export_dir/$label.codecs.tsv"
done
mkdir /build/runtime-fixture
bash "$root/tests/test_runtime_files.sh" /build/runtime-fixture > "$export_dir/runtime_file_tests.log" 2>&1
date -u +%FT%TZ > "$export_dir/completed_at.txt"
printf 'CLEAN_BUILD_AND_LOCAL_INSPECTION=PASS\n'
