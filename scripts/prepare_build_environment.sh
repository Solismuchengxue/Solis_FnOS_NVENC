#!/bin/bash
# 仅在本轮新建 Debian 构建容器内运行；不用于 WSL/宿主直接安装。
set -euo pipefail
test "$#" -eq 2 || test "$#" -eq 3 || { printf 'Usage: %s PACKAGE_LIST EXPORT_DIR [--record-existing]\n' "$0" >&2; exit 64; }
mode=${3:-prepare}
case "$mode" in prepare|--record-existing) ;; *) exit 64 ;; esac
test -f /.dockerenv
test "$(id -u)" = 0
. /etc/os-release
test "$ID:$VERSION_ID:$(dpkg --print-architecture)" = debian:12:amd64
package_list=$(realpath -e -- "$1")
export_dir=$(realpath -e -- "$2")
test -d "$export_dir"
if test "$mode" = prepare; then test -z "$(ls -A -- "$export_dir")"; else test -s "$export_dir/apt_install.log"; fi
test "$(sha256sum "$package_list" | cut -d ' ' -f1)" = 254308a64ba66d5b0292b62d4eab774ceefdd644c8fae5394dbb77d242593f3b
export LC_ALL=C DEBIAN_FRONTEND=noninteractive
mapfile -t packages < <(cut -f1 "$package_list")
if test "$mode" = prepare; then
sed -i 's/^Components: main$/Components: main non-free/' /etc/apt/sources.list.d/debian.sources
apt-get -o APT::Update::Error-Mode=any -o Acquire::Retries=0 -o Acquire::http::Timeout=30 update > "$export_dir/apt_update.log" 2>&1
test -s /var/lib/apt/lists/deb.debian.org_debian_dists_bookworm_InRelease
apt-cache madison "${packages[@]}" > "$export_dir/available_packages.txt"
test -s "$export_dir/available_packages.txt"
awk -F'|' 'NF==3 {gsub(/^[ \t]+|[ \t]+$/, "", $1); gsub(/^[ \t]+|[ \t]+$/, "", $2); print $1 "\t" $2}' "$export_dir/available_packages.txt" > "$export_dir/available_versions.tsv"
test -s "$export_dir/available_versions.tsv"
awk -F'\t' '{sub(/:amd64$/, "", $1)} NR==FNR {available[$1 FS $2]=1; next} !available[$1 FS $2] {print $0}' "$export_dir/available_versions.tsv" "$package_list" > "$export_dir/missing_versions.tsv"
if test -s "$export_dir/missing_versions.tsv"; then printf 'BLOCKED: exact historical package versions unavailable\n' >&2; exit 69; fi
mapfile -t requests < <(awk -F'\t' '{print $1 "=" $2}' "$package_list")
# Keep APT downloads for the private frozen environment, with authenticated hashes.
rm -f -- /etc/apt/apt.conf.d/docker-clean
apt-get -o Acquire::Retries=0 -o Acquire::http::Timeout=30 install --yes --no-install-recommends --no-remove --allow-downgrades "${requests[@]}" > "$export_dir/apt_install.log" 2>&1
fi
dpkg-query -W -f='${binary:Package}\t${Version}\n' | sort > "$export_dir/installed_packages.txt"
diff -u <(sort -- "$package_list") "$export_dir/installed_packages.txt" > "$export_dir/package_diff.txt"
cp /etc/apt/sources.list.d/debian.sources "$export_dir/debian.sources"
find /var/lib/apt/lists -maxdepth 1 -type f -name '*InRelease' -exec cp -t "$export_dir" {} +
find /var/lib/apt/lists -maxdepth 1 -type f ! -name lock -exec sha256sum {} + > "$export_dir/apt_index_sha256.txt"
find /var/cache/apt/archives -maxdepth 1 -type f -name '*.deb' -exec sha256sum {} + > "$export_dir/downloaded_deb_sha256.txt"
for package in "${packages[@]}"; do apt-cache show "$package"; done > "$export_dir/package_metadata.txt"
find /usr/share/doc -name copyright -type f -exec sha256sum {} + > "$export_dir/copyright_sha256.txt"
gcc --version > "$export_dir/compiler.txt"
ldd --version > "$export_dir/glibc.txt"
test "$(gcc -dumpfullversion)" = 12.2.0
test -s "$export_dir/downloaded_deb_sha256.txt" && test -s "$export_dir/copyright_sha256.txt"
printf 'FROZEN_DEPENDENCIES=PASS; EXACT_INSTALLED_PACKAGES=%s\n' "${#packages[@]}"
