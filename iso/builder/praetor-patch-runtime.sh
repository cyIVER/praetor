#!/usr/bin/env bash
# Runs INSIDE the build container after omarchy-iso cloned the Omarchy runtime
# into $build_cache_dir/airootfs/root/omarchy.
set -euo pipefail
build_cache_dir="$1"; runtime_sha="$2"
rt="$build_cache_dir/airootfs/root/omarchy"
ov="/builder/praetor-overlay"

echo "praetor: pinning runtime to $runtime_sha"
git -C "$rt" checkout -q "$runtime_sha"

echo "praetor: editing package list"
pk="$rt/install/omarchy-base.packages"
grep -v '^#' "$ov/packages/remove.packages" | grep -v '^$' | while read -r p; do
  sed -i "/^${p}\$/d" "$pk"
done
{ echo; echo "# --- praetor core ---"; grep -v '^#' "$ov/packages/core.packages" | grep -v '^$'; } >> "$pk"

echo "praetor: branding"
cp "$ov/branding/logo.txt" "$rt/logo.txt"
cp "$ov/branding/icon.txt" "$rt/icon.txt"

echo "praetor: rasterising theme backgrounds"
pacman -Sy --noconfirm --needed librsvg >/dev/null
for svg in "$ov"/themes/*/backgrounds/*.svg; do
  rsvg-convert -w 2560 -h 1600 "$svg" -o "${svg%.svg}.png"
done

echo "praetor: staging overlay into the live ISO"
cp -r "$ov" "$build_cache_dir/airootfs/root/praetor"
