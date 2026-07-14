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

## Windows MSI / Authenticode (G-C11-05)

MelosViz does **not** ship a Windows MSI or Add/Remove Programs entry backed by
Authenticode yet. That path is blocked on org certificate work (**W-224** /
**WBS-P4.4**); see [`docs/SIGNING.md`](SIGNING.md) and
[`docs/PACKAGING.md`](PACKAGING.md).

Until then, Windows cleanup is manual and surface-dependent:

| Install shape | How you installed | Uninstall today | Residual data |
|---------------|-------------------|-----------------|---------------|
| Portable zip | Extracted a folder | Delete the install folder | AppData paths below if the app ran |
| Electrobun / dev build | Copied binaries locally | Delete the install folder | Start Menu shortcut + AppData |
| Future MSI (post-Authenticode) | *not available* | *blocked on W-224* | N/A |

**G-C11-05** is documented honestly here: there is no MSI uninstaller to invoke
until Authenticode packaging lands. Do not expect **Settings → Apps** to list
MelosViz unless an installer registered it.

### Windows manual cleanup checklist

1. Remove the install directory (zip/portable or local Electrobun output).
2. If Electrobun registered a Start Menu shortcut, delete it from
   `%APPDATA%\Microsoft\Windows\Start Menu\Programs\`.
3. Remove user data if you want a full wipe:
   - `%LOCALAPPDATA%\MelosViz`
   - `%APPDATA%\MelosViz`
   - Bridge audit JSONL (if run outside the app):
     `%MELOSVIZ_DATA_DIR%\audit\` or `%LOCALAPPDATA%\MelosViz\audit\`
4. On Unix-like shells, bridge audit logs also live under
   `$MELOSVIZ_DATA_DIR/audit/` — delete that directory to wipe request JSONL.
