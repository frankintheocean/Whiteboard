# 🗺️ Find the purpose of each source file

| File | Purpose |
| --- | --- |
| `app/card_tools.py` | 🔖 Read labels, dates, and searchable card text. |
| `app/attachments.py` | 📎 Store verified file copies and portable exports. |
| `app/card_details.py` | 🗓️ Edit labels, due times, reminders, and files. |
| `app/card_table.py` | 📊 Sort and filter task rows without reordering the board. |
| `app/quick_find.py` | 🔎 Find cards, projects, and actions from the keyboard. |
| `app/reminders.py` | ⏰ Deliver saved reminder schedules once. |
| `app/view_state.py` | 🎚️ Capture and restore named project views. |
| `app/workspace_panel.py` | 🧮 Show project filters and board/list controls. |
| `app/column_resize.py` | ↔️ Resize columns with a mouse handle. |
| `tests/test_features.py` | 🧭 Check the new tools and their saved state. |
| `app/main.py` | 🚪 Starts the app, icon, data lock, and error handling. |
| `app/main_window.py` | 🪟 Shows projects, board actions, file tools, and undo/redo. |
| `app/column_widget.py` | 🧱 Shows columns, sorting, filtering, and drop targets. |
| `app/card_widget.py` | 🗒️ Shows cards, badges, selection, and keyboard actions. |
| `app/dialogs.py` | 🗣️ Builds editors, settings, type tools, and project menus. |
| `app/models.py` | 🧬 Defines projects, columns, cards, and loaded-data checks. |
| `app/storage.py` | 🗃️ Saves local projects and migrates old data. |
| `app/file_io.py` | 💾 Replaces JSON files only after complete writes. |
| `app/safe_html.py` | 🛡️ Keeps safe rich text and embedded images. |
| `app/smooth_scroll.py` | 🌀 Shares scroll animation and cancellation rules. |
| `app/styles.py` | 🎛️ Defines the 10 themes and focus styles. |
| `app/toast.py` | 🔔 Shows short status messages. |
| `app/error_log.py` | 🩺 Keeps a bounded local error log. |
| `app/app_meta.py` | 🏷️ Stores the app version and in-app change notes. |
| `build/build_utils.py` | 🌐 Reads the app version and sets UTF-8 build output. |
| `build/build.py` | 🔧 Builds the app and Windows MSI. |
| `build/whiteboard.spec` | 🏗️ Lists the app files for PyInstaller. |
| `build/installer.wxs` | 📦 Defines install, repair, and removal. |
| `build/version_info.txt` | 🆔 Sets Windows file version details. |
| `build/validate_windows.py` | ✅ Checks the real installer and installed app. |
| `build/collect_licenses.py` | ⚖️ Copies license notices from build packages. |
| `build/package.py` | 🎁 Makes the single-root ZIP and checksums. |
| `tests/conftest.py` | 🧪 Keeps tests away from real user data. |
| `tests/test_storage.py` | 💽 Tests saved files, recovery, and large projects. |
| `tests/test_models_and_html.py` | 🔍 Tests malformed data and unsafe content. |
| `tests/test_ui.py` | 🖱️ Tests menus, scroll, fonts, themes, and board actions. |

Build output, virtual environments, and user data are ignored by Git. Release ZIPs include the Windows app and MSI only when those files were built.
