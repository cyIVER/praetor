# Omarchy strips SDDM autologin on unencrypted installs; Praetor restores it and
# relies on hyprlock at session start instead.
mkdir -p /etc/sddm.conf.d
printf '[Autologin]\nUser=%s\nSession=omarchy\n' "$PRAETOR_USER" > /etc/sddm.conf.d/autologin.conf
