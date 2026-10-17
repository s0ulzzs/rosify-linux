# Rosify

A small Spotify theme tool for Linux. I made it to try out custom looks without having to edit the Spotify files by hand.

Themes included:
- Cotton Candy: pastel pink, lilac and peach clouds, glossy bubble cards, strawberry glow
- Midnight Orchid: neon orchid on deep violet with a drifting aurora and glass panels
- Arctic Glass: icy northern-lights gradients, frosted glass, electric cyan highlights

## Install on Arch

```bash
sudo pacman -S --needed python tk polkit
bash install.sh
```

Rosify will show up in your app menu. The installer starts a background monitor now and after each login, so you don't have to type the Python command every time.

Open Rosify, choose a theme, and apply it once. After that, the monitor keeps your chosen theme applied and checks again after Spotify updates. It waits for Spotify to close before changing its files. If the install needs admin access, Linux will ask for permission.

To remove the app, run `bash uninstall.sh` from this folder. Your backups and settings stay on your computer.

## Files

- `rosify.py`: the app window and commands
- `rosify_core.py`: Spotify detection, theme changes, backups, and auto-apply
- `themes/`: the CSS themes
- `tests/`: basic tests

Run tests with:

```bash
python3 -m unittest discover -s tests -v
```

Spotify updates might change how themes work. Rosify isn't affiliated with Spotify.
