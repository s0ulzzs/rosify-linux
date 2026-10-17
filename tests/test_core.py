from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import rosify_core
from rosify_core import _transform_archive, archive_has_rosify_theme, get_themes


class ThemeArchiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.source = self.root / "source.xpui.spa"
        with zipfile.ZipFile(self.source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("index.html", "<!doctype html><html><head><title>Spotify</title></head><body>Hello</body></html>")
            archive.writestr("assets/app.js", "console.log('original');")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_bundled_theme_files_exist(self) -> None:
        themes = get_themes()
        self.assertEqual(len(themes), 3)
        self.assertIn("cotton-candy", {theme.id for theme in themes})


    def test_settings_are_saved_and_loaded(self) -> None:
        settings_file = self.root / "settings.json"
        with mock.patch.object(rosify_core, "SETTINGS_PATH", settings_file):
            saved = rosify_core.save_settings("arctic-glass", False)
            loaded = rosify_core.get_settings()
        self.assertEqual(saved["selected_theme"], "arctic-glass")
        self.assertFalse(loaded["auto_apply_on_startup"])
        self.assertEqual(loaded["selected_theme"], "arctic-glass")

    def test_theme_is_injected_and_can_be_removed(self) -> None:
        patched = self.root / "patched.xpui.spa"
        restored = self.root / "restored.xpui.spa"
        css = "body { background: hotpink !important; }"

        _transform_archive(self.source, patched, css=css)
        self.assertTrue(archive_has_rosify_theme(patched))
        with zipfile.ZipFile(patched) as archive:
            html = archive.read("index.html").decode("utf-8")
            self.assertIn('href="rosify-injected-theme.css"', html)
            self.assertEqual(archive.read("rosify-injected-theme.css").decode("utf-8"), css)
            self.assertEqual(archive.read("assets/app.js"), b"console.log('original');")

        _transform_archive(patched, restored, css=None)
        self.assertFalse(archive_has_rosify_theme(restored))
        with zipfile.ZipFile(restored) as archive:
            self.assertNotIn("rosify-injected-theme.css", archive.namelist())
            self.assertNotIn("ROSIFY_THEME_START", archive.read("index.html").decode("utf-8"))
            self.assertEqual(archive.read("assets/app.js"), b"console.log('original');")

    def test_apply_and_restore_round_trip(self) -> None:
        original_bytes = self.source.read_bytes()
        data_dir = self.root / "rosify-data"
        with (
            mock.patch.object(rosify_core, "spotify_is_running", return_value=False),
            mock.patch.object(rosify_core, "DATA_DIR", data_dir),
            mock.patch.object(rosify_core, "BACKUPS_DIR", data_dir / "backups"),
            mock.patch.object(rosify_core, "STAGING_DIR", data_dir / "staging"),
            mock.patch.object(rosify_core, "MANIFEST_PATH", data_dir / "latest.json"),
        ):
            result = rosify_core.apply_theme("cotton-candy", self.source)
            self.assertTrue(archive_has_rosify_theme(self.source))
            self.assertTrue(Path(result["backup"]).is_file())
            switched = rosify_core.apply_theme("midnight-orchid", self.source)
            self.assertEqual(switched["backup"], result["backup"])
            rosify_core.restore_spotify(self.source)
            self.assertFalse(archive_has_rosify_theme(self.source))
            self.assertEqual(self.source.read_bytes(), original_bytes)

    def test_switching_themes_does_not_duplicate_markers(self) -> None:
        first = self.root / "first.xpui.spa"
        second = self.root / "second.xpui.spa"
        _transform_archive(self.source, first, css="body { color: red; }")
        _transform_archive(first, second, css="body { color: blue; }")
        with zipfile.ZipFile(second) as archive:
            html = archive.read("index.html").decode("utf-8")
            self.assertEqual(html.count("ROSIFY_THEME_START"), 1)
            self.assertEqual(archive.read("rosify-injected-theme.css").decode("utf-8"), "body { color: blue; }")


if __name__ == "__main__":
    unittest.main()
