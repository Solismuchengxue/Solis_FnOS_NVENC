#!/bin/bash
# 现有本地 Docker 上启动单个干净构建；冻结镜像必须已取得且属于本项目。
set -euo pipefail
test "$#" -eq 3 || { printf 'Usage: %s PROJECT_ROOT NEW_EXPORT_DIR FROZEN_IMAGE_ID\n' "$0" >&2; exit 64; }
root=$(realpath -e -- "$1")
parent=$(realpath -e -- "$(dirname -- "$2")")
out="$parent/$(basename -- "$2")"
image_id=$3
[[ "$image_id" =~ ^sha256:[a-f0-9]{64}$ ]] || exit 64
test -f "$root/docs/materials.json"
test -f "$root/scripts/run_clean_build.sh"
test ! -e "$out"
test ! -L "$out"
host=unix:///var/run/docker.sock
test "$(docker --host "$host" info --format '{{.KernelVersion}}')" = "$(uname -r)"
test "$(docker --host "$host" image inspect "$image_id" --format '{{.Id}}')" = "$image_id"
test "$(docker --host "$host" image inspect "$image_id" --format '{{index .Config.Labels "solis.project"}}')" = Solis_FnOS_NVENC
test "$(docker --host "$host" image inspect "$image_id" --format '{{index .Config.Labels "solis.environment"}}')" = rebuild-20261009
mkdir -- "$out"
name="solis-fnos-nvenc-build-$(cat /proc/sys/kernel/random/uuid)"
result=0
docker --host "$host" run --rm --pull never --network none --cpus 2 --memory 4g --pids-limit 256 \
 --cap-drop ALL --security-opt no-new-privileges --name "$name" \
 --label solis.project=Solis_FnOS_NVENC --label solis.package=rebuild-20261009 \
 --env LC_ALL=C --env TZ=UTC --env SOURCE_DATE_EPOCH=0 \
 --mount "type=bind,source=$root,target=/input,readonly" --mount "type=bind,source=$out,target=/export" \
 "$image_id" /bin/bash /input/scripts/run_clean_build.sh /input /export || result=$?
printf '%s\n' "$name" > "$out/container_name.txt"
exit "$result"
