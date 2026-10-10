#!/bin/bash
# Local experimental consumer; strict demux precheck prevents partial-success exit codes.
set -euo pipefail
test "$#" -eq 3 || { echo 'Usage: decode_ac4_checked.sh BUILT_BIN INPUT NEW_WAV' >&2; exit 64; }
bin=$(realpath -e -- "$1")
export LD_LIBRARY_PATH
LD_LIBRARY_PATH=$(realpath -e -- "$bin/../lib")
input=$(realpath -e -- "$2")
target=$(realpath -m -- "$3")
test ! -e "$target" && test ! -L "$target"
test ! -e "$target.partial" && test ! -L "$target.partial"
test -d "$(dirname -- "$target")"
"$bin/ac4_packet_probe" "$input" >/dev/null
"$bin/ffmpeg" -nostdin -hide_banner -v error -xerror -i "$input" -c:a pcm_s16le -f wav "$target.partial"
mv --no-clobber -- "$target.partial" "$target"
test ! -e "$target.partial"
printf 'AC4_CHECKED_DECODE=PASS\n'
