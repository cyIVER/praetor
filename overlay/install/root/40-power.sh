# Remote-access machines must stay reachable: no suspend on lid close or idle.
# Opt-in via [remote] always_on = true (default false for forkers).
cfg="$PRAETOR_PATH/bin/praetor-config"
if [[ "$("$cfg" remote.always_on 2>/dev/null)" == "true" ]]; then
  mkdir -p /etc/systemd/logind.conf.d
  cat > /etc/systemd/logind.conf.d/praetor-always-on.conf <<'CONF'
[Login]
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
IdleAction=ignore
CONF
  systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target >/dev/null 2>&1 || true
  echo "praetor(root): always_on — lid switch ignored, sleep targets masked"
fi
