#!/bin/bash
# 真实执行会撤回覆盖并重启 mediasrv；必须另行取得当次运行授权。
# 需要现场确认的原单元与覆盖 SHA256，不复用旧 PID 或自动推测身份。
set -euo pipefail
if [ "$#" -ne 2 ]; then printf 'Usage: %s CURRENT_UNIT_SHA256 CURRENT_DROPIN_SHA256\n' "$0" >&2; exit 64; fi
unit_hash=$1
dropin_hash=$2
[[ "$unit_hash" =~ ^[a-f0-9]{64}$ ]] && [[ "$dropin_hash" =~ ^[a-f0-9]{64}$ ]]
test "$(id -u)" -eq 0
prefix=/opt/solis-fnos-nvenc/ffmpeg-8.1.1-api12.1
dropin=/run/systemd/system/mediasrv.service.d/90-solis-nvenc-compat.conf
unit=/etc/systemd/system/mediasrv.service
test "$(readlink -f "$prefix")" = "$prefix"
test -f "$unit" && test ! -L "$unit"
test "$(sha256sum "$unit" | cut -d ' ' -f1)" = "$unit_hash"
script_dir=$(cd -- "$(dirname -- "$0")" && pwd -P)
source "$script_dir/runtime_files.sh"
disable_compat_dropin "$dropin" "$prefix/disabled-dropin.conf" "$dropin_hash"
systemctl daemon-reload
systemctl restart mediasrv.service
sleep 2
pid=$(systemctl show mediasrv.service --property=MainPID --value)
test "$pid" -gt 1
systemctl is-active --quiet mediasrv.service
awk '$6 ~ /libavcodec/ {print $6}' "/proc/$pid/maps" | sort -u
grep -F '/usr/trim/lib/mediasrv/lib/libavcodec.so.62' "/proc/$pid/maps" >/dev/null
if grep -F "$prefix/candidate-lib/libavcodec.so.62" "/proc/$pid/maps" >/dev/null; then exit 70; fi
printf 'VENDOR_MAPPING_RESTORED PID=%s\n' "$pid"
