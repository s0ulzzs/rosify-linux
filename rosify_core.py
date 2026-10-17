from __future__ import annotations

import json
import os
import posixpath
import shutil
import stat
import subprocess
import tempfile
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

APP_NAME = "Rosify"
APP_ROOT = Path(__file__).resolve().parent
THEMES_DIR = APP_ROOT / "themes"
START_MARKER = "<!-- ROSIFY_THEME_START -->"
END_MARKER = "<!-- ROSIFY_THEME_END -->"
CSS_ASSET_NAME = "rosify-injected-theme.css"


def _user_data_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME")
    return (Path(base).expanduser() if base else Path.home() / ".local" / "share") / "rosify"


def _user_config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    return (Path(base).expanduser() if base else Path.home() / ".config") / "rosify"


def _user_state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME")
    return (Path(base).expanduser() if base else Path.home() / ".local" / "state") / "rosify"


DATA_DIR = _user_data_dir()
BACKUPS_DIR = DATA_DIR / "backups"
STAGING_DIR = DATA_DIR / "staging"
MANIFEST_PATH = DATA_DIR / "latest.json"
SETTINGS_PATH = _user_config_dir() / "settings.json"


@dataclass(frozen=True)
class Theme:
    id: str
    name: str
    description: str
    accent: str
    background: str
    filename: str

    def public_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "accent": self.accent,
            "background": self.background,
        }


def get_themes() -> list[Theme]:
    """Load the bundled theme catalogue, keeping paths inside the project."""
    catalogue = THEMES_DIR / "themes.json"
    try:
        items = json.loads(catalogue.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read the theme catalogue: {exc}") from exc

    themes: list[Theme] = []
    for item in items:
        theme = Theme(
            id=str(item["id"]),
            name=str(item["name"]),
            description=str(item["description"]),
            accent=str(item["accent"]),
            background=str(item["background"]),
            filename=str(item["filename"]),
        )
        candidate = (THEMES_DIR / theme.filename).resolve()
        if candidate.parent != THEMES_DIR.resolve() or not candidate.is_file():
            raise RuntimeError(f"Theme file is missing or invalid: {theme.filename}")
        themes.append(theme)
    return themes


def get_theme(theme_id: str) -> Theme:
    for theme in get_themes():
        if theme.id == theme_id:
            return theme
    valid = ", ".join(theme.id for theme in get_themes())
    raise ValueError(f"Unknown theme '{theme_id}'. Available themes: {valid}")


def read_theme_css(theme: Theme | str) -> str:
    selected = get_theme(theme) if isinstance(theme, str) else theme
    path = (THEMES_DIR / selected.filename).resolve()
    if path.parent != THEMES_DIR.resolve():
        raise ValueError("Theme file must remain inside the themes directory.")
    css = path.read_text(encoding="utf-8")
    if not css.strip():
        raise ValueError(f"Theme '{selected.name}' has an empty CSS file.")
    return css


def discover_spotify_archive(explicit_path: str | Path | None = None) -> Path | None:
    """Find a native Linux Spotify XPUI archive without scanning the whole disk."""
    candidates: list[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path).expanduser())
    env_path = os.environ.get("ROSIFY_SPOTIFY_ARCHIVE")
    if env_path:
        candidates.append(Path(env_path).expanduser())
    candidates.extend(
        [
            Path("/opt/spotify/Apps/xpui.spa"),
            Path("/usr/share/spotify/Apps/xpui.spa"),
            Path("/usr/lib/spotify/Apps/xpui.spa"),
            Path("/usr/lib64/spotify/Apps/xpui.spa"),
            Path.home() / ".local/share/spotify/Apps/xpui.spa",
        ]
    )
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.resolve(strict=False))
        if key in seen:
            continue
        seen.add(key)
        if candidate.is_file() and zipfile.is_zipfile(candidate):
            return candidate.resolve()
    return None


def get_settings() -> dict[str, Any]:
    """Load saved user options, falling back to sensible defaults."""
    defaults: dict[str, Any] = {
        "selected_theme": "cotton-candy",
        "auto_apply_on_startup": True,
    }
    try:
        saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaults
    if not isinstance(saved, dict):
        return defaults
    try:
        theme_id = str(saved.get("selected_theme", defaults["selected_theme"]))
        get_theme(theme_id)
    except (ValueError, RuntimeError):
        theme_id = str(defaults["selected_theme"])
    return {
        "selected_theme": theme_id,
        "auto_apply_on_startup": bool(saved.get("auto_apply_on_startup", defaults["auto_apply_on_startup"])),
    }


def save_settings(selected_theme: str, auto_apply_on_startup: bool) -> dict[str, Any]:
    """Save the selected theme and background auto-apply preference."""
    get_theme(selected_theme)
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "selected_theme": selected_theme,
        "auto_apply_on_startup": bool(auto_apply_on_startup),
    }
    temporary = SETTINGS_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(temporary, SETTINGS_PATH)
    return data


def spotify_is_running() -> bool:
    """Return True when a process named spotify is present on Linux."""
    proc = Path("/proc")
    if not proc.is_dir():
        return False
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            name = (entry / "comm").read_text(encoding="utf-8").strip().lower()
        except (OSError, UnicodeDecodeError):
            continue
        if name in {"spotify", "spotify-launcher"}:
            return True
    return False


def _index_html_name(archive: zipfile.ZipFile) -> str:
    names = [info.filename for info in archive.infolist() if not info.is_dir()]
    if "index.html" in names:
        return "index.html"
    candidates = [name for name in names if name.endswith("/index.html")]
    if candidates:
        return min(candidates, key=lambda value: (value.count("/"), len(value)))
    raise RuntimeError("The Spotify archive does not contain an index.html file. It might use an unsupported client layout.")


def _strip_injected_link(html: str) -> str:
    start = html.find(START_MARKER)
    end = html.find(END_MARKER)
    if start == -1 and end == -1:
        return html
    if start == -1 or end == -1 or end < start:
        raise RuntimeError("Rosify's theme markers in Spotify's archive are incomplete. Restore the backup before trying again.")
    end += len(END_MARKER)
    return html[:start] + html[end:]


def _inject_link(html: str, link: str) -> str:
    lower_html = html.lower()
    head_end = lower_html.find("</head>")
    if head_end == -1:
        raise RuntimeError("Could not find </head> in Spotify's index.html. This client layout is not supported yet.")
    block = f"\n{START_MARKER}\n{link}\n{END_MARKER}\n"
    return html[:head_end] + block + html[head_end:]


def archive_has_rosify_theme(archive_path: str | Path) -> bool:
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            index_name = _index_html_name(archive)
            html = archive.read(index_name).decode("utf-8")
            return START_MARKER in html and END_MARKER in html
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, RuntimeError):
        return False


def _transform_archive(source: str | Path, destination: str | Path, css: str | None) -> None:
    """Create a new XPUI archive with Rosify's theme link added or removed."""
    source_path = Path(source)
    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(source_path, "r") as original:
        index_name = _index_html_name(original)
        css_name = posixpath.join(posixpath.dirname(index_name), CSS_ASSET_NAME)
        with zipfile.ZipFile(destination_path, "w", allowZip64=True) as patched:
            patched.comment = original.comment
            for info in original.infolist():
                if info.filename == css_name:
                    # Remove the file Rosify added during an earlier application.
                    continue
                content = original.read(info.filename)
                if info.filename == index_name:
                    try:
                        html = content.decode("utf-8")
                    except UnicodeDecodeError as exc:
                        raise RuntimeError("Spotify's index.html is not UTF-8, so Rosify cannot safely patch it.") from exc
                    html = _strip_injected_link(html)
                    if css is not None:
                        href = posixpath.basename(css_name)
                        tag = f'<link id="rosify-theme" rel="stylesheet" href="{href}">'
                        html = _inject_link(html, tag)
                    content = html.encode("utf-8")
                patched.writestr(info, content)
            if css is not None:
                css_info = zipfile.ZipInfo(css_name)
                css_info.compress_type = zipfile.ZIP_DEFLATED
                css_info.external_attr = (stat.S_IFREG | 0o644) << 16
                patched.writestr(css_info, css.encode("utf-8"))


def _read_manifest() -> dict[str, Any] | None:
    try:
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _write_manifest(data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = MANIFEST_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(temporary, MANIFEST_PATH)


def _timestamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")


def _make_backup(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _install_privileged(source: Path, target: Path, mode: int) -> None:
    pkexec = shutil.which("pkexec")
    if not pkexec:
        raise PermissionError(
            f"Rosify cannot write to {target.parent}. Install polkit/pkexec for a permission prompt, "
            "or use a user-owned Spotify installation. Rosify never runs the whole app as root."
        )
    install_bin = "/usr/bin/install" if Path("/usr/bin/install").exists() else shutil.which("install")
    if not install_bin:
        raise RuntimeError("The system 'install' utility was not found.")
    result = subprocess.run(
        [pkexec, install_bin, "-m", format(mode, "04o"), str(source), str(target)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "The permission request was cancelled.").strip()
        raise PermissionError(f"Privileged copy failed or was cancelled. {detail}")


def _replace_file(source: Path, target: Path) -> None:
    """Replace an archive atomically where possible, else request targeted admin permission."""
    target = target.resolve()
    if not target.exists():
        raise FileNotFoundError(f"Spotify archive no longer exists: {target}")
    target_mode = stat.S_IMODE(target.stat().st_mode)
    sibling: Path | None = None
    try:
        fd, sibling_name = tempfile.mkstemp(prefix=".rosify-", suffix=".tmp", dir=target.parent)
        os.close(fd)
        sibling = Path(sibling_name)
        shutil.copyfile(source, sibling)
        os.chmod(sibling, target_mode)
        os.replace(sibling, target)
        sibling = None
        return
    except PermissionError:
        # The Spotify package directory is commonly owned by root on Linux.
        pass
    finally:
        if sibling is not None:
            try:
                sibling.unlink(missing_ok=True)
            except OSError:
                pass

    _install_privileged(source, target, target_mode or 0o644)


def get_status(archive_path: str | Path | None = None) -> dict[str, Any]:
    path = discover_spotify_archive(archive_path)
    running = spotify_is_running()
    if path is None:
        return {
            "found": False,
            "path": "",
            "running": running,
            "patched": False,
            "message": "Spotify XPUI archive not found. Install the native Linux client or browse to xpui.spa.",
        }
    patched = archive_has_rosify_theme(path)
    return {
        "found": True,
        "path": str(path),
        "running": running,
        "patched": patched,
        "message": "Rosify theme is applied." if patched else "Spotify was found. No Rosify theme is applied.",
    }


def apply_theme(theme_id: str, archive_path: str | Path | None = None) -> dict[str, str]:
    target = discover_spotify_archive(archive_path)
    if target is None:
        raise FileNotFoundError("Spotify's xpui.spa was not found. Use the Browse button or set ROSIFY_SPOTIFY_ARCHIVE.")
    if spotify_is_running():
        raise RuntimeError("Close Spotify completely before applying a theme, then try again.")
    if not zipfile.is_zipfile(target):
        raise RuntimeError(f"The selected file is not a valid ZIP-based Spotify archive: {target}")

    theme = get_theme(theme_id)
    css = read_theme_css(theme)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    previous = _read_manifest()
    current_has_theme = archive_has_rosify_theme(target)
    backup_path: Path
    if current_has_theme and previous:
        previous_target = str(Path(str(previous.get("target", ""))).resolve())
        previous_backup = Path(str(previous.get("backup", "")))
        if previous_target == str(target.resolve()) and previous_backup.is_file():
            # Reuse the original clean backup when switching Rosify themes.
            backup_path = previous_backup
        else:
            stamp = _timestamp()
            backup_dir = BACKUPS_DIR / stamp
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / "xpui.spa"
            _transform_archive(target, backup_path, css=None)
    else:
        stamp = _timestamp()
        backup_dir = BACKUPS_DIR / stamp
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / "xpui.spa"
        _make_backup(target, backup_path)

    staged = STAGING_DIR / f"xpui-{os.getpid()}-{time.time_ns()}.spa"
    try:
        base = backup_path if current_has_theme else target
        _transform_archive(base, staged, css=css)
        manifest = {
            "app": APP_NAME,
            "target": str(target.resolve()),
            "backup": str(backup_path.resolve()),
            "theme_id": theme.id,
            "theme_name": theme.name,
            "applied_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        # Save the recovery location before replacing the system file.
        _write_manifest(manifest)
        _replace_file(staged, target)
    finally:
        staged.unlink(missing_ok=True)

    return {"path": str(target), "theme": theme.name, "backup": str(backup_path)}


def restore_spotify(archive_path: str | Path | None = None) -> dict[str, str]:
    if spotify_is_running():
        raise RuntimeError("Close Spotify completely before restoring its original archive, then try again.")
    manifest = _read_manifest()
    if not manifest:
        raise FileNotFoundError("No Rosify backup record was found. Apply a theme first.")
    recorded_target = Path(str(manifest.get("target", ""))).expanduser()
    target = Path(archive_path).expanduser().resolve() if archive_path else recorded_target.resolve()
    backup = Path(str(manifest.get("backup", ""))).expanduser()
    if str(target) != str(recorded_target.resolve()):
        raise RuntimeError(
            "The selected Spotify path differs from the backup path. Select the original installation at "
            f"{recorded_target} to restore its backup."
        )
    if not backup.is_file():
        raise FileNotFoundError(f"The Rosify backup is missing: {backup}")
    if not target.is_file():
        raise FileNotFoundError(f"Spotify archive no longer exists: {target}")
    if not archive_has_rosify_theme(target):
        raise RuntimeError("No Rosify theme marker was found in the current archive, so there is nothing for Rosify to restore.")

    _replace_file(backup, target)
    return {"path": str(target), "backup": str(backup)}


def monitor_auto_apply(poll_seconds: int = 15) -> None:
    """Keep the selected theme applied, waiting for Spotify to close before patching."""
    attempted: set[tuple[str, str, int, int]] = set()
    last_wait_message = 0.0
    print("Rosify background monitor started.", flush=True)
    while True:
        try:
            settings = get_settings()
            if not settings["auto_apply_on_startup"]:
                time.sleep(poll_seconds)
                continue

            if not _read_manifest():
                now = time.monotonic()
                if now - last_wait_message >= 300:
                    print("Choose a theme and apply it once in Rosify to enable automatic maintenance.", flush=True)
                    last_wait_message = now
                time.sleep(poll_seconds)
                continue

            target = discover_spotify_archive()
            if target is None:
                now = time.monotonic()
                if now - last_wait_message >= 300:
                    print("Spotify archive not found yet. Will check again.", flush=True)
                    last_wait_message = now
                time.sleep(poll_seconds)
                continue

            if spotify_is_running():
                time.sleep(poll_seconds)
                continue

            try:
                info = target.stat()
            except OSError:
                time.sleep(poll_seconds)
                continue
            key = (str(target.resolve()), settings["selected_theme"], info.st_mtime_ns, info.st_size)

            manifest = _read_manifest()
            if (
                archive_has_rosify_theme(target)
                and manifest
                and str(Path(str(manifest.get("target", ""))).resolve()) == str(target.resolve())
                and manifest.get("theme_id") == settings["selected_theme"]
            ):
                time.sleep(poll_seconds)
                continue

            if key not in attempted:
                attempted.add(key)
                try:
                    result = apply_theme(settings["selected_theme"], target)
                    print(f"Applied {result['theme']} to {result['path']}.", flush=True)
                except Exception as exc:
                    print(f"Could not apply theme automatically: {exc}", flush=True)
                    print("Rosify will retry if Spotify's files or the selected theme change, or after the next login.", flush=True)
        except Exception as exc:
            print(f"Rosify monitor error: {exc}", flush=True)
        time.sleep(poll_seconds)

