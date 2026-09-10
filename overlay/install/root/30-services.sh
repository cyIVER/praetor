# Offline: only install and enable units here; joining networks happens at first boot.
systemctl enable tailscaled.service >/dev/null 2>&1 || true

# praetor-config is needed by the root first-boot unit, which runs before any
# user session and must not depend on a home directory.
install -Dm755 "$PRAETOR_PATH/bin/praetor-config" /usr/local/lib/praetor/praetor-config
install -Dm755 "$PRAETOR_PATH/bin/praetor-first-boot-root" /usr/local/lib/praetor/praetor-first-boot-root

cat >/etc/systemd/system/praetor-first-boot-root.service <<'UNIT'
[Unit]
Description=Praetor first-boot setup (root half)
After=network-online.target
Wants=network-online.target
ConditionPathExists=!/var/lib/praetor/first-boot-root.done

[Service]
Type=oneshot
ExecStart=/usr/local/lib/praetor/praetor-first-boot-root
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
UNIT
systemctl enable praetor-first-boot-root.service >/dev/null 2>&1 || true
