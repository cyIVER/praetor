#!/usr/bin/env bash
# Praetor user-level install stages. Runs as the target user, inside the
# install chroot (offline) and is safe to re-run from a live system.
set -euo pipefail
export PRAETOR_PATH="${PRAETOR_PATH:-$HOME/.local/share/praetor}"
export PATH="$HOME/.local/bin:$PATH"
for stage in "$PRAETOR_PATH"/install/user/*.sh; do
  echo "praetor: $(basename "$stage")"
  # shellcheck source=/dev/null
  source "$stage"
done
