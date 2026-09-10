mkdir -p "$HOME/.local/bin"
for f in "$PRAETOR_PATH"/bin/*; do
  ln -sf "$f" "$HOME/.local/bin/$(basename "$f")"
done
