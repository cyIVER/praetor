mkdir -p "$HOME/.local/bin"
for f in "$PRAETOR_PATH"/bin/*; do
  [[ -f $f ]] || continue
  case "$(basename "$f")" in .gitkeep | *.md) continue ;; esac
  # The exec bit has to survive git, `cp -r` off the ISO and this symlink. Set it
  # here as well: a stripped mode silently disables every praetor command.
  chmod +x "$f"
  ln -sf "$f" "$HOME/.local/bin/$(basename "$f")"
done
