# Praetor ISO pipeline

Praetor does not vendor the Omarchy ISO builder. `build.sh` clones
`omacom-io/omarchy-iso` at a pinned commit, applies Praetor's edits to the
clone (keyed on unique upstream lines, verified after each edit), drops
Praetor's files into `configs/`, and runs the upstream `bin/omarchy-iso-make`
inside Docker.

```
iso/
  build.sh                 entry point (needs Docker + git)
  patch-builder.sh         edits applied to the omarchy-iso clone
  builder/
    praetor-patch-runtime.sh   runs INSIDE the build container after the
                               omarchy runtime is cloned: pin SHA, package
                               list edits, branding, theme rasterising,
                               overlay staging
  configs/                 copied over the clone's configs/ (archiso airootfs)
    airootfs/root/praetor-cidata-load    loads praetor-private from a CIDATA partition
    airootfs/root/praetor-post-install   runs after omarchy's install, before reboot
```

Install-time flow on the live ISO (`.automated_script.sh`):

```
praetor-cidata-load → configurator (interactive unless CIDATA supplied JSON)
→ archinstall → omarchy install.sh (chroot) → praetor-post-install → reboot
```

The install is offline (Omarchy ships an offline pacman mirror). Praetor's
chroot stages therefore do only offline work; anything needing the network
(Hermes, Codex, AUR packages, Tailscale join) runs once on first boot via
`praetor-first-boot`, hooked into Omarchy's `post-boot` hook.

## Build

```bash
./iso/build.sh                 # → iso/out/praetor-<date>.iso
PRAETOR_DEV=1 ./iso/build.sh   # --dev (edge mirror) for faster iteration
```

Pins live at the top of `build.sh`. Bump them deliberately.

## Build host notes (learned 2026-09-10)

- The upstream wrapper `bin/omarchy-iso-make` calls `sudo` on the host and ends with a
  `gum` banner. On WSL2 run the build **as root** (`wsl -d Ubuntu -u root`) so sudo does not
  prompt; the missing `gum` is harmless because `build.sh` judges success by the ISO existing.
- Root needs `git config --global --add safe.directory "*"` when the work dir belongs to
  another user.
- Keep the work dir on the WSL ext4 filesystem (`PRAETOR_ISO_WORK=/home/<you>/praetor-iso-work`);
  building on `/mnt/c` is very slow. The output ISO still lands in `iso/out/` on Windows.
- `/builder` is mounted read-only in the container; anything the runtime patch generates
  (rasterised wallpapers) must be written into the staged copy under `airootfs/root/praetor`.
- Package names in `overlay/packages/*.packages` must exist in the Arch or Omarchy repos;
  AUR-only packages belong in first-boot (`overlay/bin/praetor-first-boot`).
- The first build takes roughly 20 minutes (offline mirror download). Later builds reuse the
  Docker image and pacman cache.
- Removing packages from Omarchy's base list is only safe for apps its install scripts never
  touch. Removing `chromium` halts `install/config/theme-system.sh` (it writes Chromium's
  `initial_preferences`) and breaks webapps. See the comments in `overlay/packages/remove.packages`.

## First-install findings (Flex 5, 2026-09-10)

The first installed ISO staged the overlay correctly but nothing Praetor-specific
was visible on login. Four bugs, all fixed in this commit:

- **No exec bit in the repo.** Every file was `100644`, so `overlay/bin/*` landed
  non-executable, and the post-boot hook's `exec ~/.local/bin/praetor-first-boot`
  died with 126. The ISO pipeline hid this because it runs everything as
  `bash <file>` and `profiledef.sh` forces `0755` on the two `/root/praetor-*`
  scripts. Scripts are `100755` in git now; `install/user/10-bin.sh` chmods
  defensively, and `praetor-patch-runtime.sh` restores the bits and *fails the
  build* if they are missing — a DrvFs/NTFS checkout on the build host loses them.
- **Stage ordering.** `praetor-post-install` ran `all.sh` before `root.sh`, so the
  user stages read `/etc/praetor/praetor.toml` before `root/10-config.sh` wrote it.
  Root stages run first now.
- **Theme could never apply in the chroot.** `omarchy-theme-set` is not on `PATH`
  there and restarts waybar/mako/hyprctl, and `|| true` hid the failure.
  `20-theme.sh` now records the wanted theme in
  `~/.local/state/praetor/theme.wanted`; the post-boot hook applies it on the
  first live session and marks `theme.applied` so a later operator choice sticks.
- **`praetor-first-boot` needed a tty.** `sudo` and `yay` prompt for a password
  (no NOPASSWD drop-in on an Omarchy install) and the hook has no terminal. Split:
  `praetor-first-boot-root` runs unattended as a systemd oneshot
  (`praetor-first-boot-root.service`) for Tailscale join and the Hermes install —
  the machine must reach the tailnet with nobody at the keyboard — and the user
  half now opens in a terminal window so prompts are answerable.

Also: theme backgrounds are SVG in the repo and were rasterised only by the ISO
builder, so `git clone && install/all.sh` left hyprpaper with an SVG it cannot
render. `20-theme.sh` rasterises missing PNGs itself (`librsvg` is in
`core.packages`); the generated PNGs are gitignored.

The theme `hyprland.conf` files used pre-0.5x `layerrule = blur, <ns>` syntax,
which Hyprland 0.56 rejects. Now `layerrule = blur on, match:namespace <ns>`.
