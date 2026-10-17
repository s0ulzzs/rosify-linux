#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.local/lib/rosify"
BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"
AUTOSTART_DIR="$HOME/.config/autostart"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/rosify"

if ! python3 -c 'import tkinter, zipfile' >/dev/null 2>&1; then
    echo "Python Tkinter is missing. On Arch, run: sudo pacman -S --needed python tk"
    exit 1
fi

mkdir -p "$INSTALL_DIR" "$BIN_DIR" "$APP_DIR" "$AUTOSTART_DIR" "$STATE_DIR"
SOURCE_REAL="$(realpath "$SCRIPT_DIR")"
INSTALL_REAL="$(realpath -m "$INSTALL_DIR")"
if [[ "$SOURCE_REAL" != "$INSTALL_REAL" ]]; then
    cp -a "$SCRIPT_DIR/." "$INSTALL_DIR/"
fi

cat > "$BIN_DIR/rosify" <<EOF2
#!/usr/bin/env bash
exec /usr/bin/python3 "$INSTALL_DIR/rosify.py" "\$@"
EOF2

cat > "$BIN_DIR/rosify-monitor" <<EOF2
#!/usr/bin/env bash
STATE_DIR="\${XDG_STATE_HOME:-\$HOME/.local/state}/rosify"
mkdir -p "\$STATE_DIR"
exec /usr/bin/python3 "$INSTALL_DIR/rosify.py" monitor >> "\$STATE_DIR/autostart.log" 2>&1
EOF2
chmod +x "$BIN_DIR/rosify" "$BIN_DIR/rosify-monitor"

escape_exec_path() {
    local value="$1"
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    printf '%s' "$value"
}
APP_EXEC="$(escape_exec_path "$BIN_DIR/rosify")"
MONITOR_EXEC="$(escape_exec_path "$BIN_DIR/rosify-monitor")"

cat > "$APP_DIR/rosify.desktop" <<EOF2
[Desktop Entry]
Type=Application
Name=Rosify
Comment=Change Spotify themes on Linux
Exec="$APP_EXEC"
Terminal=false
Categories=AudioVideo;Utility;
EOF2

cat > "$AUTOSTART_DIR/rosify-monitor.desktop" <<EOF2
[Desktop Entry]
Type=Application
Name=Rosify background monitor
Comment=Keep the selected Spotify theme applied
Exec="$MONITOR_EXEC"
Terminal=false
NoDisplay=true
X-GNOME-Autostart-enabled=true
EOF2

chmod 644 "$APP_DIR/rosify.desktop" "$AUTOSTART_DIR/rosify-monitor.desktop"
if pgrep -u "$(id -u)" -f '[r]osify.py monitor' >/dev/null 2>&1; then
    echo "Rosify background monitor is already running."
else
    nohup "$BIN_DIR/rosify-monitor" </dev/null >/dev/null 2>&1 &
    echo "Rosify background monitor started."
fi
echo "Rosify is installed and will also start after you log in."
echo "Open Rosify from your application menu to choose a theme. Apply it once to enable automatic maintenance."
echo "Background log: $STATE_DIR/autostart.log"
echo "User data and backups are stored in: ${XDG_DATA_HOME:-$HOME/.local/share}/rosify"
