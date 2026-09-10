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
