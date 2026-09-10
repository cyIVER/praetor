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
