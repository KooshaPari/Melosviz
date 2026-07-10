# Uninstall / cleanup matrix

| Surface | Uninstall | Leftovers to remove |
|---------|-----------|---------------------|
| macOS DMG app | Drag MelosViz.app to Trash | `~/Library/Application Support` MelosViz data if created |
| Windows desktop | Uninstall via Apps & features / delete install dir | `%APPDATA%` MelosViz if present |
| Windows/Linux CLI zip | Delete extracted folder | none |
| pip editable | `pip uninstall melosviz` | local `.venv` |
| GHCR bridge image | `docker rmi ghcr.io/<owner>/melosviz-bridge:<tag>` | stopped containers |
| Devcontainer | Delete codespace / container | docker volumes |

Bridge audit logs live under `$MELOSVIZ_DATA_DIR/audit/` — delete that directory to wipe request JSONL.
