# 📝 WhiteBoard

WhiteBoard is a task board for Windows 10/11 x64. Create a project, add task cards, and move them through status columns. Keep notes, set priorities, and see what needs work next.

Your projects stay on your computer. The app saves changes as you work and runs offline. No account or server is needed.

## 🗂️ Use your board

- Create projects with Classic, Simple, Bug Tracker, Kanban, Sprint, or Blank templates.
- Add, rename, delete, and reorder columns. Drag columns or use their arrow buttons.
- Add, edit, duplicate, delete, and drag cards. Double-click a card to edit it.
- Use Add, Change, Remove, Fix, or Idea types. Create, rename, or delete your own types.
- Set four priority levels, or leave priority blank. Type and priority badges have quick menus.
- Filter columns by type. Sort by type or priority without changing saved card order.
- Select cards with checkboxes or Ctrl/Shift-click. Move, duplicate, delete, or change them together.
- Undo and redo card and column changes. Save, open, import, and export projects.
- Add rich-text notes with fonts, sizes, bold, italic, and underline.
- Pick from 15 themes, including three OLED Black options. Adjust text, zoom, focus marks, click targets, and motion.

See [the user guide](docs/USER_GUIDE.md) for details and keyboard shortcuts.

## ✨ New in 1.1.0

- 🔎 Search cards across all projects with Ctrl+F.
- ⏰ Set due dates and reminders in the card editor.
- 🏷️ Give each card several labels.
- 📎 Keep file attachments with cards and include them in exported projects.
- 🧭 Use Ctrl+K to find commands, projects, and cards.
- 📋 Switch between a board and a sortable task list.
- 🎚️ Save named views with filters, sorting, and column widths.
- ↔️ Drag a column's right edge or enter an exact width in its menu.
- 🌑 Choose OLED Black with blue, mint, or purple accents.

See [the new-feature guide](docs/FEATURES.md) for controls and limits.

## 🚀 Install

Download `WhiteBoard-1.1.0-x64.msi` from [Releases](https://github.com/frankintheocean/Whiteboard/releases). Open it and follow the steps. Windows asks for admin permission because the app installs in Program Files.

Run the same MSI again to **Repair** or **Remove** the app. You can also remove it in Windows Settings → Apps. Repair restores missing app files. Uninstall keeps your projects and settings.

The release ZIP has one root folder, `WhiteBoard-1.1.0/`. It contains all source, resources, build tools, docs, licenses, the built app, and the MSI when the Windows build passes. You can run `application/WhiteBoard/WhiteBoard.exe` without installing it.

The app and MSI are unsigned. Windows may show a SmartScreen warning. Check the SHA-256 values in the release before using the files.

## 🔤 Fonts and reading

SF Pro Text is the first-choice app font. Select another installed font in Settings → General → App font. Windows uses a system fallback when SF Pro is missing. Apple fonts are not included or installed by this project.

Change Description text size to make card notes easier to read. Formatting already stored in rich-text notes stays intact. Accessibility settings also offer larger text and 80–150% zoom.

## 💾 Your data

Projects save automatically. The footer says when changes are saved or when a write fails. Keep the app open if a save fails and check disk space and permissions.

- Windows: `%APPDATA%\WhiteBoard\`
- macOS/Linux source runs: `~/.whiteboard/`
- Optional: set `WHITEBOARD_DATA_DIR` to use a different writable folder.

Each project has its own JSON file in `projects/`. `index.json` stores settings and the active project. Old `whiteboard_data.json` files are imported on first launch and kept as `.migrated` files. Unreadable files are kept as numbered `.bak` copies. The app tells you when a recovery copy was made.

Only one app instance can use a data folder at a time. Use Save As for a separate project backup. Keep the app closed when copying its whole data folder.

## 🐍 Run from source

Use Python 3.12 x64 for the tested build. The source also supports Python 3.10 or later.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install --require-hashes -r app\requirements.txt
.venv\Scripts\python app\main.py
```

On macOS/Linux, use `.venv/bin/python` in place of `.venv\Scripts\python`.

## 🧪 Test and build

```powershell
.venv\Scripts\python -m pip install --require-hashes -r requirements-dev.lock
.venv\Scripts\python -m pytest -q
.venv\Scripts\python build\build.py --installer
```

The MSI build also needs WiX 5.0.2 and its matching UI extension. See [build instructions](docs/BUILD.md). Windows installers must be built on Windows x64. Linux builds are useful for checks but are not Windows releases.

## 🧭 Files and folders

| Path | Purpose |
| --- | --- |
| `app/` | 🧠 App logic, widgets, themes, settings, and local storage. |
| `build/` | 🏗️ App builder, MSI definition, package tool, and installer checks. |
| `build/assets/` | 🎨 Flat app icon in PNG and multi-size ICO formats. |
| `tests/` | 🔬 Data, text, UI, scroll, and workflow tests. |
| `docs/` | 📚 User, build, validation, and release notes. |
| `.github/` | 🪟 Windows tests, installer checks, release workflow, and issue forms. |
| `app/requirements.txt` | 🧩 Pinned app packages with SHA-256 hashes. |
| `requirements-dev.lock` | 🧰 Pinned test and build packages with hashes. |
| `LICENSE` | ⚖️ The repository's GPL-3.0 license, kept unchanged. |

## 🛡️ Safety and limits

Imported titles stay plain text. Rich descriptions keep normal formatting and embedded images, while blocking scripts, unsafe links, and local file images. Saving a file uses a complete temporary write before replacement.

The app is local and works offline. Its tasks, settings, templates, and file workflows remain in place.

See [the source file guide](docs/FILES.md), [validation notes](docs/VALIDATION.md), [changes](CHANGELOG.md), and [possible next features](docs/NEXT_FEATURES.md).
