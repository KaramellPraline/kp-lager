# Releases mit Versionsnummer

Versionen folgen `Major.Minor.Patch` (z. B. `0.3.0`). Einzige Quelle: `app/__init__.py` (`__version__`),
`pyproject.toml` wird mitgezogen. Sie erscheint in Mehr › Status, `/health`, der API (`/overview`) und in den
Dateinamen der Windows-Installer. Das Docker-Image bekommt das Tag `0.3.0` (und `latest`).

## Release veröffentlichen
```bash
git checkout main && git pull
uv run python tools/release.py bump 0.3.0     # setzt die Version, legt einen Kopf in CHANGELOG.md an
$EDITOR CHANGELOG.md                          # Änderungen unter „## [0.3.0]“ eintragen (wird zum Release-Text)
git commit -am "Release 0.3.0"
git push                                      # Pull Request/Merge nach main wie gewohnt
git tag v0.3.0 && git push origin v0.3.0      # löst den Workflow „Release“ aus
```
Der Workflow (`.github/workflows/release.yml`)
1. prüft, dass Tag, `app/__init__.py` und `pyproject.toml` übereinstimmen und der Changelog-Text vorhanden ist,
2. führt Lint, Typprüfung und Tests aus,
3. baut beide Windows-Installer (`KP-Lager-Client-Setup-0.3.0.exe`, `KP-Lager-Server-Setup-0.3.0.exe`) und die Android-App (`KP-Lager-0.3.0.apk`),
4. baut das Docker-Image (amd64 + arm64) und legt es unter `ghcr.io/karamellpraline/kp-lager:0.3.0` ab,
5. erstellt das GitHub-Release `v0.3.0` mit Changelog-Text, beiden Installern und der APK (das Docker-Image läuft daneben und hält das Release nicht auf).

Schlägt ein Schritt fehl, entsteht kein Release; nach der Korrektur den Tag löschen und neu setzen
(`git tag -d v0.3.0 && git push origin :refs/tags/v0.3.0`). Zum Testen ohne Release: Actions › „Windows-Installer“.

## Versionswahl
- **Patch** (0.2.1): Fehlerkorrekturen, keine neuen Funktionen.
- **Minor** (0.3.0): neue Funktionen, Migrationen möglich (immer abwärts-kompatibel zum Update, nicht zurück).
- **Major** (1.0.0): wenn sich Bedienung oder Datenformat grundlegend ändern.

## Installation und Update
Siehe `docs/INSTALL.md`.
