#!/bin/bash
# 仅在调用者提供的空临时目录内测试文件函数，不调用 systemctl 或 SSH。
set -euo pipefail
test "$#" -eq 1
fixture=$(realpath -e -- "$1")
test -d "$fixture" && test -z "$(ls -A -- "$fixture")"
task_dir=$(cd -- "$(dirname -- "$0")/.." && pwd -P)
source "$task_dir/scripts/runtime_files.sh"
printf '[Service]\nEnvironment=LOCAL_TEST_ONLY\n' > "$fixture/ours.conf"
cp "$fixture/ours.conf" "$fixture/unrelated.conf"
expected=$(sha256sum "$fixture/ours.conf" | cut -d ' ' -f1)
disable_compat_dropin "$fixture/ours.conf" "$fixture/disabled.conf" "$expected"
test ! -e "$fixture/ours.conf"
test "$(sha256sum "$fixture/unrelated.conf" | cut -d ' ' -f1)" = "$expected"
printf 'PASS moves_only_ours_preserves_unrelated\n'
cp "$fixture/disabled.conf" "$fixture/drift.conf"
printf '\nchanged\n' >> "$fixture/drift.conf"
if disable_compat_dropin "$fixture/drift.conf" "$fixture/drift-disabled.conf" "$expected"; then exit 1; fi
test -f "$fixture/drift.conf" && test ! -e "$fixture/drift-disabled.conf"
printf 'PASS refuses_changed_dropin\n'
cp "$fixture/disabled.conf" "$fixture/collision.conf"
if disable_compat_dropin "$fixture/collision.conf" "$fixture/disabled.conf" "$expected"; then exit 1; fi
test -f "$fixture/collision.conf"
printf 'PASS refuses_existing_destination\n'
ln -s "$fixture/disabled.conf" "$fixture/link.conf"
if [ ! -L "$fixture/link.conf" ]; then
    printf 'SKIP refuses_symlink: genuine symlink unavailable in this local environment\n'
else
    if disable_compat_dropin "$fixture/link.conf" "$fixture/link-disabled.conf" "$expected"; then exit 1; fi
    test -L "$fixture/link.conf" && test ! -e "$fixture/link-disabled.conf"
    printf 'PASS refuses_symlink\n'
fi
