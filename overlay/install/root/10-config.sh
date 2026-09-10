mkdir -p /etc/praetor/secrets
chmod 700 /etc/praetor/secrets
if [[ -f "$PRAETOR_PRIVATE/config/praetor.toml" ]]; then
  cp "$PRAETOR_PRIVATE/config/praetor.toml" /etc/praetor/praetor.toml
elif [[ -f "$PRAETOR_PRIVATE/praetor.toml" ]]; then
  cp "$PRAETOR_PRIVATE/praetor.toml" /etc/praetor/praetor.toml
else
  cp "$PRAETOR_PATH/config/praetor.default.toml" /etc/praetor/praetor.toml
fi
chmod 644 /etc/praetor/praetor.toml
if [[ -d "$PRAETOR_PRIVATE/secrets" ]]; then
  cp "$PRAETOR_PRIVATE"/secrets/* /etc/praetor/secrets/ 2>/dev/null || true
  chmod 600 /etc/praetor/secrets/* 2>/dev/null || true
fi
