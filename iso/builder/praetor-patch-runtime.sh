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
other="$rt/install/omarchy-other.packages"
live="$build_cache_dir/packages.x86_64"   # live ISO environment list, seeded from archiso releng
grep -v '^#' "$ov/packages/remove.packages" | grep -v '^$' | tr -d '\r' | while read -r p; do
  sed -i -E "/^[[:space:]]*${p}[[:space:]]*\r?$/d" "$pk" "$other" "$live"
done
{ echo; echo "# --- praetor core ---"; grep -v '^#' "$ov/packages/core.packages" | grep -v '^$' | tr -d '\r'; } >> "$pk"
echo "praetor: verifying removals"
for p in $(grep -v '^#' "$ov/packages/remove.packages" | grep -v '^$' | tr -d '\r'); do
  if grep -qE "^[[:space:]]*${p}[[:space:]]*$" "$pk" "$other" "$live"; then echo "praetor: WARNING $p still listed"; fi
done

echo "praetor: branding"
cp "$ov/branding/logo.txt" "$rt/logo.txt"
cp "$ov/branding/icon.txt" "$rt/icon.txt"

echo "praetor: staging overlay into the live ISO"
staged="$build_cache_dir/airootfs/root/praetor"
cp -r "$ov" "$staged"

echo "praetor: rasterising theme backgrounds (in the writable staged copy)"
pacman -Sy --noconfirm --needed librsvg >/dev/null
for svg in "$staged"/themes/*/backgrounds/*.svg; do
  rsvg-convert -w 2560 -h 1600 "$svg" -o "${svg%.svg}.png"
done
