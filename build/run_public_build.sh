#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail
export LC_ALL=C TZ=UTC SOURCE_DATE_EPOCH=0
test ! -e /build
mkdir /build
dpkg-query -W -f='${binary:Package}\t${Version}\n' | sort > /export/installed_packages.txt
diff -u <(sort /input/docs/build_packages.txt) /export/installed_packages.txt
bash /input/scripts/build_libavcodec.sh /sources /input/patches /build/output > /export/build.log 2>&1
library=/build/output/candidate-lib/libavcodec.so.62
cp "$library" /export/libavcodec.so.62
cp /build/output/config.mak /build/output/configure.log /build/output/compile.log /build/output/ac4-config.txt /build/output/nvenc-api.txt /export/
readelf -h "$library" > /export/elf_header.txt
readelf -d "$library" > /export/dynamic.txt
readelf --version-info "$library" > /export/symbol_versions.txt
sha256sum /export/libavcodec.so.62 > /export/candidate_sha256.txt
source=/build/output/source/ffmpeg-8.1.1
gcc -Wall -Wextra -Werror -O2 -I"$source" /input/scripts/inspect_libavcodec.c -ldl -o /build/inspect_libavcodec
LD_LIBRARY_PATH="$source/libavutil:$source/libswresample" /build/inspect_libavcodec "$library" | sort > /export/codecs.tsv
mkdir /build/runtime-fixture
bash /input/tests/test_runtime_files.sh /build/runtime-fixture > /export/runtime_file_tests.log
printf 'PUBLIC_CLEAN_BUILD=PASS\n'
