#!/bin/bash
# 已取得当次授权后，在现有本地 Docker 上运行保存库的 CPU 回归。
set -euo pipefail
test "$#" -eq 3 || { printf 'Usage: %s PROJECT_ROOT NEW_EXPORT_DIR FROZEN_IMAGE_ID\n' "$0" >&2; exit 64; }
root=$(realpath -e -- "$1")
parent=$(realpath -e -- "$(dirname -- "$2")")
out="$parent/$(basename -- "$2")"
image=$3
test "$image" = sha256:168b5407fe9a839977f328d4e18f7c9e79dd596458a93f36a73de6e0e2b0bebc
test ! -e "$out"
test ! -L "$out"
host=unix:///var/run/docker.sock
test "$(docker --host "$host" info --format '{{.KernelVersion}}')" = "$(uname -r)"
test "$(docker --host "$host" image inspect "$image" --format '{{.Id}}')" = "$image"
test "$(docker --host "$host" image inspect "$image" --format '{{index .Config.Labels "solis.project"}}')" = Solis_FnOS_NVENC
mkdir "$out" "$out/preparation"
name="solis-fnos-nvenc-functional-$(cat /proc/sys/kernel/random/uuid)"
run_container() {
    local suffix=$1 output=$2 script=$3
    docker --host "$host" run --rm --pull never --network none --cpus 2 --memory 4g --pids-limit 256 \
      --cap-drop ALL --security-opt no-new-privileges --name "$name-$suffix" \
      --label solis.project=Solis_FnOS_NVENC --label solis.package=functional-20261009 \
      --env LC_ALL=C --env TZ=UTC \
      --mount "type=bind,source=$root,target=/input,readonly" --mount "type=bind,source=$output,target=/export" \
      "$image" /bin/bash "/input/scripts/$script" /input /export
}
run_container prepare "$out/preparation" prepare_codec_probe.sh
run_container test "$out" run_codec_regression.sh
printf '%s\n' "$image" > "$out/environment_image_id.txt"
printf 'PROCESSES_FINISHED; RUN_SUMMARIZER_BEFORE_CLAIMING_PASS\n'
