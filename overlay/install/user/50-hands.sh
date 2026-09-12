# Waybar badge for computer-use sessions. Omarchy's user waybar config is a plain copy, so
# add the module once, next to the screen-recording indicator, plus its CSS.
cfgj="$HOME/.config/waybar/config.jsonc"; css="$HOME/.config/waybar/style.css"
mkdir -p "$HOME/.config/waybar"
cp "$PRAETOR_PATH/config/waybar/praetor-driving.sh" "$HOME/.config/waybar/praetor-driving.sh"; chmod +x "$HOME/.config/waybar/praetor-driving.sh"
if [[ -f "$cfgj" ]] && ! grep -q "custom/praetor-driving" "$cfgj"; then
  sed -i 's|"custom/screenrecording-indicator",|"custom/praetor-driving", "custom/screenrecording-indicator",|' "$cfgj"
  python3 - "$cfgj" <<'PY'
import sys
p = sys.argv[1]; s = open(p).read()
block = '''  "custom/praetor-driving": {
    "exec": "~/.config/waybar/praetor-driving.sh",
    "on-click": "praetor-hands panic",
    "signal": 11,
    "return-type": "json"
  },
'''
i = s.find('  "custom/screenrecording-indicator": {')
if i > 0 and 'custom/praetor-driving": {' not in s:
    open(p, "w").write(s[:i] + block + s[i:])
PY
fi
if [[ -f "$css" ]] && ! grep -q "praetor-driving" "$css"; then
  printf '\n#custom-praetor-driving.active {\n  color: #B3122E;\n  font-weight: bold;\n  margin-left: 8px;\n  margin-right: 8px;\n}\n' >> "$css"
fi
pkill -SIGUSR2 waybar 2>/dev/null || true
