#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

python3 scripts/distribution.py stage-apt
for arch in amd64 arm64; do
    directory=".site/dists/stable/main/binary-$arch"
    mkdir -p "$directory"
    (cd .site && apt-ftparchive --arch "$arch" packages pool) > "$directory/Packages"
    gzip -n -9 -c "$directory/Packages" > "$directory/Packages.gz"
    xz -9 -c "$directory/Packages" > "$directory/Packages.xz"
done

(
    cd .site
    apt-ftparchive \
        -o 'APT::FTPArchive::Release::Origin=Numelon OSS (GitHub)' \
        -o 'APT::FTPArchive::Release::Label=Numelon OSS (GitHub) APT' \
        -o 'APT::FTPArchive::Release::Suite=stable' \
        -o 'APT::FTPArchive::Release::Codename=stable' \
        -o 'APT::FTPArchive::Release::Architectures=amd64 arm64' \
        -o 'APT::FTPArchive::Release::Components=main' \
        release dists/stable > dists/stable/Release
)
