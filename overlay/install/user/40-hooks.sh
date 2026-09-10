mkdir -p "$HOME/.config/omarchy/hooks/post-boot.d"
cp "$PRAETOR_PATH/config/omarchy/hooks/post-boot.d/praetor-first-boot" \
   "$HOME/.config/omarchy/hooks/post-boot.d/praetor-first-boot"
chmod +x "$HOME/.config/omarchy/hooks/post-boot.d/praetor-first-boot"
