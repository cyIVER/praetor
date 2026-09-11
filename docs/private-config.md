# Private config schema

Praetor reads an optional `praetor-private/` directory from the install media
(second partition of the USB) and, after Omarchy's base install, applies it.
Without the directory, Praetor installs stock and runs a first-run wizard.

```
praetor-private/
  praetor.toml          # required if the directory exists
  secrets/
    tailscale.authkey   # optional; one-line auth key, chmod 600 after copy
  overlay/              # optional; copied verbatim onto / after install
    home/user/...       # e.g. extra dotfiles, ssh config, wallpapers
```

## praetor.toml

All keys optional unless marked. Unknown keys are ignored with a warning.

```toml
[system]
hostname = "praetor"            # required
username = "user"               # required
timezone = "America/New_York"
keymap   = "us"
locale   = "en_US.UTF-8"

[brain]
mode = "local"                  # "local" | "remote"
# remote only:
url  = "http://100.64.0.1:8642" # Hermes API base URL (Tailscale IP or MagicDNS name)
mcp_url = "http://100.64.0.1:8643" # Hermes-as-MCP-server endpoint for other agents

[network]
tailscale = false               # true => join tailnet on first boot using secrets/tailscale.authkey
tailscale_hostname = ""         # defaults to system.hostname

[remote]
wayvnc = false                  # true => wayvnc bound to the Tailscale IP only
wayvnc_bind = "tailscale"       # "tailscale" | an explicit IP
always_on = false               # true => ignore lid switch and mask sleep targets (headless/remote use)
sunshine = false                # true => install Sunshine (AUR) for Moonlight streaming; KMS capture, tailnet-only

[theme]
default = "imperium"            # "imperium" | "obsidian" | any theme dir name

[voice]
enabled     = true
wake_models = ["hey_jarvis"]    # openWakeWord model names or paths
tts         = "piper"           # "piper" (50 MB, robotic) | "kokoro" (500 MB loaded, natural; unloads when idle)
kokoro_voice = "bm_george"      # kokoro voices: af_heart, af_bella, am_michael, bm_george, bm_lewis, ...
kokoro_speed = 1.0
stt_model   = "small"           # faster-whisper size: tiny|base|small
idle_unload_seconds = 300
brain       = "api"             # "api" = local Hermes API server (streaming, persistent session; recommended)
                                #   "local" = hermes chat -q per turn (8-40 s); "remote" = a JARVIS voice relay
api_url     = "http://127.0.0.1:8642"   # api only; key in ~/.config/praetor/hermes-api.key (platforms.api_server.extra.key)
api_session = "praetor-voice"   # api only; one persistent Hermes session keeps conversational context
followup_seconds = 6            # after a reply, listen this long for a follow-up without the wake word
relay_url   = ""                # remote only, e.g. "http://100.64.0.1:8765"; token in ~/.config/praetor/voice-relay.token
piper_voice = "en_US-lessac-medium"
wake_threshold = 0.5            # openWakeWord score 0..1; lower = more sensitive
reasoning   = "none"            # Hermes reasoning effort for voice turns (latency first)
toolsets    = ""                # comma-separated Hermes toolsets for voice, "" = Hermes defaults (terminal, browser, computer_use...)
ack_phrase  = "On it."          # spoken right after transcription; "" to disable
nothing_phrase = "I did not catch that."
# prompt_prefix = "..."          # override the voice-mode instruction prepended to every request

[agents]
scratchpads = ["hermes", "claude", "codex"]   # order = hotkey order
antigravity = false             # install Antigravity from AUR
```

Secrets never go in `praetor.toml`. The installer copies `secrets/` to
`/etc/praetor/secrets/` with mode 0600, owned by root. The copy on the USB stick is left untouched;
wipe the stick yourself when you are done.
