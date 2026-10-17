#!/usr/bin/env bash
set -euo pipefail

rm -f "$HOME/.local/bin/rosify" \
      "$HOME/.local/bin/rosify-monitor" \
      "$HOME/.local/share/applications/rosify.desktop" \
      "$HOME/.config/autostart/rosify-monitor.desktop"
rm -rf "$HOME/.local/lib/rosify"
echo "Rosify was removed. Your settings, Spotify backups, and logs were kept."
echo "To remove them too, delete ~/.config/rosify, ~/.local/share/rosify, and ~/.local/state/rosify yourself."
