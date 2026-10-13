#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail
test "$#" -eq 1
snapshot=$1
[[ "$snapshot" =~ ^[0-9]{8}T[0-9]{6}Z$ ]]
test "$(id -u)" = 0
. /etc/os-release
test "$ID:$VERSION_ID:$(dpkg --print-architecture)" = debian:12:amd64
test "$(sha256sum /input/build/build_packages.txt | cut -d ' ' -f1)" = 254308a64ba66d5b0292b62d4eab774ceefdd644c8fae5394dbb77d242593f3b
# Only fixed archived Release expiry is relaxed; signatures and package hashes remain mandatory.
cat > /etc/apt/sources.list.d/debian.sources <<EOF
Types: deb
URIs: https://snapshot.debian.org/archive/debian/$snapshot/
Suites: bookworm bookworm-updates
Components: main non-free
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
Check-Valid-Until: no

Types: deb
URIs: https://snapshot.debian.org/archive/debian-security/$snapshot/
Suites: bookworm-security
Components: main non-free
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
Check-Valid-Until: no
EOF
export LC_ALL=C DEBIAN_FRONTEND=noninteractive
# The pinned base has no CA certificates; signed HTTP indexes authenticate every fixed package.
sed -i 's|https://snapshot.debian.org|http://snapshot.debian.org|g' /etc/apt/sources.list.d/debian.sources
apt-get -o APT::Update::Error-Mode=any -o Acquire::Retries=0 update > /export/apt_update.log 2>&1
mapfile -t requests < <(awk -F '\t' '{print $1 "=" $2}' /input/build/build_packages.txt)
apt-get -o Acquire::Retries=0 install --yes --no-install-recommends --no-remove --allow-downgrades "${requests[@]}" > /export/apt_install.log 2>&1
dpkg-query -W -f='${binary:Package}\t${Version}\n' | sort > /export/installed_packages.txt
diff -u <(sort /input/build/build_packages.txt) /export/installed_packages.txt > /export/package_diff.txt
cp /etc/apt/sources.list.d/debian.sources /export/debian.sources
find /var/lib/apt/lists -maxdepth 1 -type f -name '*InRelease' -exec cp -t /export {} +
find /var/lib/apt/lists -maxdepth 1 -type f ! -name lock -exec sha256sum {} + > /export/index_sha256.txt
printf 'FIXED_PUBLIC_ENVIRONMENT=PASS\n'
