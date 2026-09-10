# Offline: only enable units here; joining networks happens at first boot.
systemctl enable tailscaled.service >/dev/null 2>&1 || true
