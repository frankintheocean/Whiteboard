# 🛠️ Build and package the Windows app

Use a Windows 10/11 x64 machine, Python 3.12 x64, and the .NET 8 SDK. GitHub Actions uses Windows Server 2022 for automated build checks.

## 📐 Install tools

From the project root:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install --require-hashes -r requirements-dev.lock
dotnet tool install --global wix --version 5.0.2
wix extension add --global WixToolset.UI.wixext/5.0.2
```

Open a new terminal if `wix` is not found. The .NET global tool folder must be on PATH. Package hashes and TLS checks stay enabled.

## 🧫 Run checks

```powershell
.venv\Scripts\python -m pytest -q
.venv\Scripts\python app\main.py
```

Use a fresh `WHITEBOARD_DATA_DIR` for manual checks. Try many projects, long names, card editing, drag/drop, filtering, keyboard focus, themes, and window resizing. Try a long column near its bottom and double-click several cards.

## 🏭 Build Windows files

```powershell
.venv\Scripts\python build\build.py --installer
```

Outputs:

- `dist/WhiteBoard/WhiteBoard.exe` and its required files.
- `dist_installer/WhiteBoard-1.0.0-x64.msi`.

The MSI installs to Program Files, adds a Start Menu shortcut, and supports standard Windows Installer repair and removal. User data lives outside the install folder.

## 🧯 Check the real installer

Use a clean Windows test machine with admin permission:

```powershell
.venv\Scripts\python build\validate_windows.py
```

This installs the MSI, runs the installed app with an isolated data folder, deletes the executable, repairs and checks every app file, runs the app again, and uninstalls it. It checks that user data survives. Logs are saved in `build/output/`.

Do not run this script on a machine with an existing WhiteBoard installation. For normal use, choose Repair or Remove in the MSI.

## 🗜️ Make the single-root ZIP

```powershell
.venv\Scripts\python build\collect_licenses.py
.venv\Scripts\python build\package.py --installer
```

`artifacts/WhiteBoard-1.0.0-complete.zip` includes source, resources, locks, docs, the built app, MSI, and third-party license files. `SHA256SUMS.txt` checks the release files. The ZIP contains its own file checksum list.

Use `python build/package.py` for a source-only ZIP when no Windows installer has been built. It will not claim that an installer exists.

## 🛰️ Release through GitHub

The Windows workflow tests and builds each main-branch change and pull request. It saves files and test logs as workflow artifacts. A `v1.0.0` tag builds the complete package and publishes a release only after tests and installer checks pass.

```powershell
git tag -a v1.0.0 -m "🚀 Release WhiteBoard 1.0.0"
git push origin v1.0.0
```

Do not publish a passing source-only check as a Windows installer result. Files are unsigned unless a separate signing step is added with a real certificate.

## 🐧 Check from Linux

Use `.venv/bin/python`, set `QT_QPA_PLATFORM=offscreen` on headless machines, and run the test suite. `python build/build.py` builds a local executable for the current OS. It cannot produce a Windows app on Linux.

## 📜 Third-party terms

The repository license stays GPL-3.0. PySide6 and Qt have their own license terms. The package tool includes installed package notices for the built release. Qt libraries stay as separate bundled files, so they can be replaced. Source is available from [Qt](https://code.qt.io/) and [PySide](https://code.qt.io/cgit/pyside/pyside-setup.git/). Python and PyInstaller keep their own terms too. SF Pro is not bundled.
