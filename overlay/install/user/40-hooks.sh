mkdir -p "$HOME/.config/omarchy/hooks/post-boot.d" "$HOME/.local/state/praetor"
cp "$PRAETOR_PATH/config/omarchy/hooks/post-boot.d/praetor-first-boot" \
   "$HOME/.config/omarchy/hooks/post-boot.d/praetor-first-boot"
chmod +x "$HOME/.config/omarchy/hooks/post-boot.d/praetor-first-boot"
# The hook runs from the Hyprland session, where PRAETOR_PATH is not exported.
# Record where this install came from so it does not guess.
echo "$PRAETOR_PATH" >"$HOME/.local/state/praetor/path"
