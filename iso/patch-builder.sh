#!/usr/bin/env bash
# Apply Praetor edits to an omarchy-iso clone. Each edit is keyed on a unique
# upstream line and verified; a missing or duplicated key means upstream moved
# and the pin must be reviewed.
set -euo pipefail
clone="$1"

insert() { # insert <file> <desc> <key> <text> before|after
  python3 - "$clone/$1" "$2" "$3" "$4" "$5" <<'PY'
import sys
path, desc, key, ins, where = sys.argv[1:6]
s = open(path).read()
n = s.count(key)
if n != 1:
    sys.exit(f"patch-builder: key for '{desc}' found {n} times in {path}")
s = s.replace(key, ins + key if where == "before" else key + ins)
open(path, "w").write(s)
print(f"  patched: {desc}")
PY
}

replace() { # replace <file> <desc> <key> <text>
  python3 - "$clone/$1" "$2" "$3" "$4" <<'PY2'
import sys
path, desc, key, new = sys.argv[1:5]
s = open(path).read()
n = s.count(key)
if n != 1:
    sys.exit(f"patch-builder: key for '{desc}' found {n} times in {path}")
open(path, "w").write(s.replace(key, new))
print(f"  patched: {desc}")
PY2
}

# 1. build-iso.sh — call the runtime patch after the clone block ends.
python3 - "$clone/builder/build-iso.sh" <<'PY'
import sys
p = sys.argv[1]; s = open(p).read()
i = s.find('airootfs/root/omarchy'); assert i > 0, "runtime clone block not found"
j = s.find('\nfi\n', i);            assert j > 0, "end of clone block not found"
call = ('\nfi\n\n# --- Praetor ---\n'
        '/builder/praetor-patch-runtime.sh "$build_cache_dir" "$(cat /builder/praetor-runtime-sha)"\n'
        '# --- /Praetor ---')
open(p, 'w').write(s[:j] + call + s[j+4:])
print("  patched: runtime patch call")
PY

# 2. .automated_script.sh — cidata before the configurator, post-install before reboot.
replace configs/airootfs/root/.automated_script.sh "cidata load"   '  set_tokyo_night_colors
  ./configurator
'   '  set_tokyo_night_colors
  /root/praetor-cidata-load
  # CIDATA may have supplied the answer files; only prompt if it did not.
  [[ -f user_credentials.json && -f user_configuration.json ]] || ./configurator
'
insert configs/airootfs/root/.automated_script.sh "post-install" \
  '  if [[ -f /mnt/var/tmp/omarchy-install-completed ]]; then' \
  '  /root/praetor-post-install "$OMARCHY_USER"
' before

# 3. profiledef.sh — identity + permissions.
sed -i \
  -e 's/^iso_name="omarchy"/iso_name="praetor"/' \
  -e 's/^iso_label="OMARCHY_/iso_label="PRAETOR_/' \
  -e 's|^iso_publisher=.*|iso_publisher="Praetor <https://github.com/cyIVER/praetor>"|' \
  -e 's/^iso_application=.*/iso_application="Praetor Installer"/' \
  "$clone/configs/profiledef.sh"
grep -q 'iso_name="praetor"' "$clone/configs/profiledef.sh"
insert configs/profiledef.sh "file permissions" \
  '  ["/root/configurator"]="0:0:755"' \
  '
  ["/root/praetor-cidata-load"]="0:0:755"
  ["/root/praetor-post-install"]="0:0:755"' after

echo "patch-builder: done"
