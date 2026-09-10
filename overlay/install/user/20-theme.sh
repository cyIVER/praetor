mkdir -p "$HOME/.config/omarchy/themes"
for t in "$PRAETOR_PATH"/themes/*/; do
  name="$(basename "$t")"
  ln -sfn "${t%/}" "$HOME/.config/omarchy/themes/$name"
done
default="$(praetor-config theme.default 2>/dev/null || echo imperium)"
# In the chroot there is no compositor to restart; ignore those failures.
omarchy-theme-set "$default" >/dev/null 2>&1 || true
