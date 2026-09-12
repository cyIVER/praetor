#!/usr/bin/env bash
# Install Praetor hands: wtype + ydotool (repos), the MCP server venv, ydotool user service,
# and register the server with the local Hermes. Idempotent.
set -euo pipefail
base="$HOME/.local/share/praetor/hands"; venv="$base/.venv"
src="${PRAETOR_PATH:-$HOME/.local/share/praetor}/hands"
mkdir -p "$base"
if ! pacman -Q wtype ydotool >/dev/null 2>&1; then
  sudo pacman -S --noconfirm --needed wtype ydotool
fi
systemctl --user enable --now ydotool.service >/dev/null 2>&1 || true
[[ -x "$venv/bin/python" ]] || uv venv --python 3.12 "$venv" >/dev/null
uv pip install --python "$venv/bin/python" -q "mcp>=1.2,<2" pillow
cp "$src/praetor_hands_mcp.py" "$base/praetor_hands_mcp.py"
# Register with Hermes (stdio) via its config block; the interactive `hermes mcp add` needs a tty.
cfg="$HOME/.hermes/config.yaml"
if [[ -f "$cfg" ]] && ! grep -q "praetor-hands" "$cfg"; then
  if grep -q "^mcp_servers:" "$cfg"; then
    printf '  praetor-hands:\n    command: %s\n    args: ["%s"]\n' "$venv/bin/python" "$base/praetor_hands_mcp.py" > /tmp/praetor-hands.mcp
    python3 - "$cfg" /tmp/praetor-hands.mcp <<'PY'
import sys
p, blk = sys.argv[1], open(sys.argv[2]).read()
s = open(p).read(); i = s.find("mcp_servers:\n") + len("mcp_servers:\n")
open(p, "w").write(s[:i] + blk + s[i:])
PY
  else
    printf '\nmcp_servers:\n  praetor-hands:\n    command: %s\n    args: ["%s"]\n' "$venv/bin/python" "$base/praetor_hands_mcp.py" >> "$cfg"
  fi
fi
echo HANDS_INSTALL_OK
