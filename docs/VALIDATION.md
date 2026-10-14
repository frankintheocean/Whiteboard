# 🔬 Read the checks and known limits

## ✅ Automated checks

The local suite passes 66 tests on Linux with Qt 6.11.2 and Python 3.12. The source app and a local frozen build both pass startup checks. Windows results are recorded separately by the release workflow.

The test suite checks local save/load, old-file migration, malformed data, duplicate IDs, missing column links, finite timestamps, Unicode, isolated settings, failed writes, delayed deletion, unsafe HTML/URLs, and a 10,000-card save/load case.

Qt tests check project menus with 150 names, very long names, double-click scrolling, scroll retention after refresh, keyboard editing/selection, font-only note formatting, all 15 themes, resizing, card moves, undo/redo, and type changes.

The app works without a network connection. All app state stays in local files. No credentials or network service are required.

## 🧰 New-feature checks

Tests cover UTC/local date round trips, overdue filters, one-time reminders, rescheduling, label cleanup, quoted labels, copied attachments, missing originals, damage detection, blocked paths and executable names, file size limits, portable imports, shared-content exports, global search over 10,000 entries, command filtering, board/list selection, list scroll retention, named views, imported view IDs, manual widths, drag clamping, OLED variants, and metadata-preserving duplication and undo.

## 🪟 Windows release gate

GitHub Actions runs the tests on Windows x64, builds the app and MSI, and verifies the 1.0.0 upgrade with existing tasks and settings, installed-app startup, repair after removing the executable, a second startup, uninstall, and user-data preservation. A release is published only after these checks pass. The workflow saves its test report and MSI logs.

## 🧑‍🦯 Manual limits

An offscreen Qt test does not replace a human check of scrolling feel, high-DPI monitors, Windows 10/11 theme appearance, screen readers, or touch input. Automated installer checks use Windows Server 2022. SmartScreen and code signing need a real signing certificate and separate validation.

SF Pro is not supplied. Qt uses a Windows fallback when it is missing. Embedded note images stay supported; imported external/local file images are blocked for safety. The original data is kept on disk until the user saves an edited note.

## 🧾 Reproduce checks

Run `python -m pytest -q` in a prepared virtual environment. For a full Windows build, follow `docs/BUILD.md` and run `python build/validate_windows.py` on a clean admin test machine. Review the current workflow's results before calling any Windows artifact verified.
