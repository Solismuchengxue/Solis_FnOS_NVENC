#!/bin/bash
# 仅撤回已识别的单个覆盖文件；拒绝漂移、符号链接及目标冲突。
disable_compat_dropin() {
    local active_file=$1 disabled_file=$2 expected_hash=$3
    case "$active_file:$disabled_file" in /*:/*) ;; *) return 64 ;; esac
    [[ "$expected_hash" =~ ^[a-f0-9]{64}$ ]] || return 64
    test -f "$active_file" && test ! -L "$active_file" || return 65
    test ! -e "$disabled_file" && test ! -L "$disabled_file" || return 66
    test "$(sha256sum "$active_file" | cut -d ' ' -f1)" = "$expected_hash" || return 67
    mv -T -n -- "$active_file" "$disabled_file" || return 68
    test ! -e "$active_file" || return 69
    test "$(sha256sum "$disabled_file" | cut -d ' ' -f1)" = "$expected_hash"
}
