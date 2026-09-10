mkdir -p "$HOME/.config/omarchy/themes" "$HOME/.local/state/praetor"
for t in "$PRAETOR_PATH"/themes/*/; do
  name="$(basename "$t")"
  ln -sfn "${t%/}" "$HOME/.config/omarchy/themes/$name"
done

# Backgrounds ship as SVG; hyprpaper cannot render them. The ISO builder
# rasterises the staged copy, but a plain `git clone` + install/all.sh has to
# work standalone too, so do it here as well when a PNG is missing.
if command -v rsvg-convert >/dev/null; then
  for svg in "$PRAETOR_PATH"/themes/*/backgrounds/*.svg; do
    [[ -f $svg ]] || continue
    png="${svg%.svg}.png"
    [[ -f $png ]] || rsvg-convert -w 2560 -h 1600 "$svg" -o "$png" || true
  done
fi

default="$("$PRAETOR_PATH/bin/praetor-config" theme.default 2>/dev/null || echo imperium)"

# omarchy-theme-set restarts waybar, mako and hyprctl and is not even on PATH in
# the install chroot, so the theme cannot land there. Record what we want and let
# the post-boot hook apply it on the first live session.
echo "$default" >"$HOME/.local/state/praetor/theme.wanted"
if [[ -z ${PRAETOR_CHROOT_INSTALL:-} ]] && command -v omarchy-theme-set >/dev/null; then
  omarchy-theme-set "$default" && touch "$HOME/.local/state/praetor/theme.applied"
fi
