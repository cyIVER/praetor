#!/usr/bin/env bash
# Install the Praetor voice stack into a user venv and fetch models. Idempotent. Needs network.
set -euo pipefail
base="$HOME/.local/share/praetor/voice"; venv="$base/.venv"; models="$base/models"
src="${PRAETOR_PATH:-$HOME/.local/share/praetor}/voice"
mkdir -p "$models"
# openWakeWord pulls tflite-runtime, which ships wheels only up to CPython 3.11 (2026-09),
# so the venv is pinned to 3.11 via uv. Rebuild it if it exists with another version.
py_want="3.11"
if [[ -x "$venv/bin/python" ]] && ! "$venv/bin/python" -c "import sys; sys.exit(0 if sys.version_info[:2]==(3,11) else 1)"; then
  uv venv --clear --python "$py_want" "$venv" >/dev/null
fi
[[ -x "$venv/bin/python" ]] || uv venv --python "$py_want" "$venv" >/dev/null
uv pip install --python "$venv/bin/python" -q -r "$src/requirements.txt"
cp "$src/praetor_voice.py" "$base/praetor_voice.py"
# Wake-word models ship with openWakeWord but are fetched on first use; do it now.
"$venv/bin/python" - <<'PY'
import openwakeword
openwakeword.utils.download_models()
print("openwakeword models ready")
PY
# Piper voice (about 60 MB) from the official voices repo on Hugging Face.
voice="${PIPER_VOICE:-en_US-lessac-medium}"
if [[ ! -f "$models/$voice.onnx" ]]; then
  # Voice names are <locale>-<name>-<quality>, stored as <lang>/<locale>/<name>/<quality>/.
  IFS=- read -r loc vname qual <<< "$voice"; lang="${loc%%_*}"
  base_url="https://huggingface.co/rhasspy/piper-voices/resolve/main/$lang/$loc/$vname/$qual"
  curl -fsSL -o "$models/$voice.onnx" "$base_url/$voice.onnx"
  curl -fsSL -o "$models/$voice.onnx.json" "$base_url/$voice.onnx.json"
fi
# Short chimes so you know it is listening / done.
"$venv/bin/python" - "$models" <<'PY'
import sys, wave, math, struct
from pathlib import Path
out = Path(sys.argv[1])
def tone(name, freqs, secs=0.12, rate=22050):
    with wave.open(str(out / f"chime-{name}.wav"), "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        n = int(rate * secs)
        for f in freqs:
            w.writeframes(b"".join(struct.pack("<h", int(12000 * math.sin(2 * math.pi * f * i / rate) * (1 - i / n))) for i in range(n)))
tone("listen", [660, 880]); tone("done", [880, 660])
print("chimes ready")
PY
# User service.
mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/praetor-voice.service" <<UNIT
[Unit]
Description=Praetor voice (wake word, local STT/TTS, Hermes)
After=graphical-session.target pipewire.service
PartOf=graphical-session.target
[Service]
ExecStart=$venv/bin/python $base/praetor_voice.py
Restart=on-failure
RestartSec=5s
MemoryMax=2500M
[Install]
WantedBy=graphical-session.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now praetor-voice.service || true
echo VOICE_INSTALL_OK
