#!/usr/bin/env bash
# Build the Praetor ISO on top of a pinned omarchy-iso checkout.
set -euo pipefail

# ---- pins ------------------------------------------------------------------
OMARCHY_ISO_REPO="https://github.com/omacom-io/omarchy-iso.git"
OMARCHY_ISO_REF="main"                                   # v3 builder line
OMARCHY_ISO_SHA="${OMARCHY_ISO_SHA:-}"                   # optional exact commit
OMARCHY_RUNTIME_REPO="omacom/omarchy"                    # cloned by upstream builder
OMARCHY_RUNTIME_REF="master"                             # 3.8.5 line
OMARCHY_RUNTIME_SHA="${OMARCHY_RUNTIME_SHA:-f4378f0d}"   # pinned inside the container
# ----------------------------------------------------------------------------

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$here/.." && pwd)"
work="${PRAETOR_ISO_WORK:-$here/work}"
out="${PRAETOR_ISO_OUT:-$here/out}"
clone="$work/omarchy-iso"
mkdir -p "$work" "$out"

if [[ ! -d "$clone/.git" ]]; then
  git clone --recurse-submodules -b "$OMARCHY_ISO_REF" "$OMARCHY_ISO_REPO" "$clone"
fi
git -C "$clone" fetch -q origin
git -C "$clone" checkout -q --force "${OMARCHY_ISO_SHA:-origin/$OMARCHY_ISO_REF}"
git -C "$clone" submodule update --init -q
git -C "$clone" clean -fdxq -e release   # drops last run's praetor-overlay too

# Praetor files over the clone.
cp -r "$here/configs/." "$clone/configs/"
cp "$here/builder/praetor-patch-runtime.sh" "$clone/builder/"
chmod +x "$clone/builder/praetor-patch-runtime.sh" \
         "$clone/configs/airootfs/root/praetor-cidata-load" \
         "$clone/configs/airootfs/root/praetor-post-install"

# Stage the overlay so the container (which mounts builder/) can reach it.
cp -r "$repo_root/overlay" "$clone/builder/praetor-overlay"
echo "$OMARCHY_RUNTIME_SHA" > "$clone/builder/praetor-runtime-sha"

# Edit the upstream scripts in place.
"$here/patch-builder.sh" "$clone"

flags=()
[[ "${PRAETOR_DEV:-0}" == "1" ]] && flags+=(--dev)
# The upstream wrapper ends with a cosmetic `gum` banner that fails on hosts
# without gum, so judge success by the ISO existing, not by the exit code.
(
  cd "$clone"
  OMARCHY_INSTALLER_REPO="$OMARCHY_RUNTIME_REPO" \
  OMARCHY_INSTALLER_REF="$OMARCHY_RUNTIME_REF" \
  ./bin/omarchy-iso-make "${flags[@]}" || true
)
iso="$(ls -t "$clone"/release/*.iso 2>/dev/null | head -1 || true)"
[[ -n "$iso" ]] || { echo "praetor: build failed, no ISO in $clone/release" >&2; exit 1; }
name="praetor-$(date +%Y.%m.%d)-x86_64.iso"
mv -f "$iso" "$out/$name"
( cd "$out" && sha256sum "$name" > "$name.sha256" )
ls -la "$out"
