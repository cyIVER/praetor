# Praetor

An AI-first, hardware-efficient Arch Linux distribution built on
[Omarchy](https://github.com/basecamp/omarchy) and Hyprland.

**Status: pre-alpha, under construction. Nothing here boots yet.**

## What it is

- **Omarchy underneath.** Hyprland, Waybar, Walker, Neovim, Limine + btrfs +
  Snapper, zram, the Omarchy theme system and Super-key workflow. Praetor is an
  overlay, so upstream Omarchy updates keep flowing.
- **Hermes Agent built in.** [Hermes Agent](https://github.com/NousResearch/hermes-agent)
  is the OS's agent runtime, with memory, skills, and computer use. Signs in
  with a Codex or Claude subscription; no metered API key required. Point it
  at a remote Hermes instead with one config line.
- **Local voice.** Wake word, streaming speech-to-text, and text-to-speech all
  run on the laptop CPU. Nothing leaves the machine except the text the agent
  needs.
- **Shared memory.** Hermes's memory graph is served over MCP so Claude Code,
  Codex, and any other agent on the machine read and write the same knowledge.
- **Supervised computer use.** A Wayland harness lets the agent drive the
  desktop with a visible "driving" indicator and a global panic key.
- **Lean.** Targets ~900 MB idle on 8 GB. Tested on an Intel Tiger Lake / Iris
  Xe laptop.
- **Imperium theme.** Near-black, crimson, antique gold. A second glass-style
  theme ships alongside.

## Layout

```
iso/        ISO builder (fork of omarchy-iso) — produces praetor-*.iso
overlay/    Everything applied on top of a stock Omarchy install
  install/  Post-install stages, run in order
  packages/ Package lists (core, extras)
  config/   Dotfile fragments for Hyprland, Waybar, etc.
  themes/   Praetor themes in Omarchy's theme format
  bin/      praetor-* helper scripts and the Praetor menu
  voice/    Wake word, STT, TTS pipeline
  hands/    Computer-use harness for Wayland
docs/       User and developer documentation
```

## Private config

Praetor separates the public distro from anything personal. Put a
`praetor-private/` folder on the second partition of the install USB and the
installer applies it after the base install. The schema is documented in
`docs/private-config.md`. Without it you get a stock Praetor and a first-run
wizard.

## License

MIT. See `LICENSE` and `NOTICE` for upstream attributions.
