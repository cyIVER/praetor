#!/usr/bin/env bash
# Praetor root-level install stages. PRAETOR_USER must be set.
set -euo pipefail
: "${PRAETOR_USER:?PRAETOR_USER is required}"
export PRAETOR_PATH="/home/$PRAETOR_USER/.local/share/praetor"
export PRAETOR_PRIVATE="/home/$PRAETOR_USER/.local/share/praetor-private"
for stage in "$PRAETOR_PATH"/install/root/*.sh; do
  echo "praetor(root): $(basename "$stage")"
  # shellcheck source=/dev/null
  source "$stage"
done
