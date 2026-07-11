# Uninstall / cleanup matrix

| Surface | Uninstall | Leftovers to remove |
|---------|-----------|---------------------|
| macOS DMG app | Drag MelosViz.app to Trash | `~/Library/Application Support/MelosViz` if created |
| Windows desktop (Apps & features) | Settings → Apps → MelosViz → Uninstall | `%LOCALAPPDATA%\MelosViz`, `%APPDATA%\MelosViz` |
| Windows desktop (portable zip) | Delete the extracted folder | same AppData paths if the app wrote config |
| Windows CLI zip | Delete extracted folder | none |
| Linux CLI tarball | Delete extracted folder | `~/.local/share/melosviz` if used |
| pip editable | `pip uninstall melosviz` | local `.venv` |
| GHCR bridge image | `docker rmi ghcr.io/kooshapari/melosviz-bridge:<tag>` | stopped containers (`docker ps -a`) |
| Air-gap extract | Delete `melosviz-airgap-*` directory | loaded docker images from `docker load` |
| Devcontainer | Delete codespace / container | docker volumes |

### Windows notes

1. If Electrobun registered a Start Menu shortcut, remove it from
   `%APPDATA%\Microsoft\Windows\Start Menu\Programs\`.
2. Bridge audit JSONL (if run outside the app) lives under
   `%MELOSVIZ_DATA_DIR%\audit\` or `%LOCALAPPDATA%\MelosViz\audit\`.
3. No MSI/Authenticode uninstaller yet (W-224) — delete the install directory
   when Apps & features does not list MelosViz.

Bridge audit logs live under `$MELOSVIZ_DATA_DIR/audit/` — delete that directory to wipe request JSONL.
