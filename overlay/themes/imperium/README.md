# Imperium

Praetor's default theme. Near-black, crimson, antique gold. See `PALETTE.md`.

Omarchy renders the per-app configs (alacritty, waybar, walker, mako, hyprlock,
btop, ...) from its templates using `colors.toml`. Files shipped here
(`hyprland.conf`, `neovim.lua`, `icons.theme`) take precedence over the
templates. `backgrounds/*.png` is rasterised from the SVG at ISO build time.
