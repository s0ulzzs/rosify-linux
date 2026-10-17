# Contributing

Thanks for looking at Rosify. This is an early Linux-first prototype.

- Test changes with a temporary sample archive first.
- Do not commit Spotify's proprietary files, login data, or a personal backup archive.
- Keep backup/restore behaviour conservative.
- Include a test for archive-manipulation changes.
- If a Spotify update breaks theme loading, report the Spotify client version, package type, and error. Do not share account information.

Run tests with:

```bash
python3 -m unittest discover -s tests -v
```
