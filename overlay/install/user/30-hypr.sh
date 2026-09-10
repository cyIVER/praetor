mkdir -p "$HOME/.config/hypr"
cp "$PRAETOR_PATH/config/hypr/praetor.conf" "$HOME/.config/hypr/praetor.conf"
grep -q 'hypr/praetor.conf' "$HOME/.config/hypr/hyprland.conf" 2>/dev/null || \
  printf '\n# Praetor\nsource = ~/.config/hypr/praetor.conf\n' >> "$HOME/.config/hypr/hyprland.conf"
# Lock immediately after autologin (unencrypted-disk design).
grep -q 'exec-once = hyprlock' "$HOME/.config/hypr/autostart.conf" 2>/dev/null || \
  printf 'exec-once = hyprlock\n' >> "$HOME/.config/hypr/autostart.conf"
