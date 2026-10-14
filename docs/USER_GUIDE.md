# 🖐️ Learn the board controls

## 🏁 Start a project

Use New Project and choose a template. The project menu is sorted by name. Its list fits normal project names even when there are many projects. Very long names can scroll sideways and have a full-name tooltip.

Each project keeps its own column order and sort choices. Open a saved project to switch to it. Import always creates a separate copy with fresh IDs.

## 🧱 Manage columns

Use Add Column to add a status. Double-click its title to rename it. Drag the column grip or use the left/right arrows to change its position. Removing a column uses the existing confirmation flow.

## 🗒️ Manage cards

Use Add Card or New Card. A card has a title, description, type, and optional priority. The note editor supports font, size, bold, italic, and underline. Double-click to edit, or use the card menu. Click a type or priority badge for a quick change.

Drag cards to another column or to a new position. Select several cards to drag them together. Card numbers follow the visible list. Filters and sorting only change the view; they do not change saved board order.

## ☑️ Work with a group

Use checkboxes, Ctrl-click, or Shift-click to select cards. The group bar offers Move, Type, Priority, Duplicate, and Delete. Escape clears the selection. Undo and redo apply to these actions too.

## ⌨️ Keyboard controls

| Key | Action |
| --- | --- |
| Tab / Shift+Tab | Move focus through controls and cards. |
| Enter on a focused card | Edit the card. |
| Space on a focused card | Toggle selection. |
| Ctrl+Z | Undo a board change. |
| Ctrl+Y / Ctrl+Shift+Z | Redo a board change. |
| Escape | Clear selected cards. |
| Ctrl+F | Search cards in all projects. |
| Ctrl+K | Open the command palette. |
| Ctrl+N | New card. |
| Ctrl+O | Open a project. |
| Ctrl+S | Quick Save to the remembered project file. |
| Ctrl+Shift+S | Save As. |

Text editors keep their normal editing shortcuts. Use the card menu if double-click editing is turned off.

## 🎛️ Set your view

Settings has General, Themes, Accessibility, What's New, and Diagnostics tabs. Pick an installed app font and description size in General. SF Pro is preferred when installed. Choose a theme, zoom, larger text, focus marks, larger click targets, or reduced motion.

The ALL CAPS setting changes display only. It does not change saved text. Existing rich-text note fonts and sizes stay intact.

## 📤 Save and share

The app saves locally after changes. Save As writes one `.fboard.json` project file. Quick Save updates its remembered file. Open switches to a matching project already in your library; it does not overwrite it with an imported copy. Import creates a new project instead. Use the existing export menu to share readable text or Markdown.

An external copy may be older than your local board. WhiteBoard warns before closing when a remembered external file has new changes.

## 🩺 Recover safely

If the footer says changes are not saved, keep the app open and check free space and folder permissions. Closing after a failed save asks before discarding changes.

Unreadable files are kept as `.bak`, `.bak.1`, and later numbered copies. Do not edit a backup in place. Copy it elsewhere first. The Diagnostics tab shows recent errors and board counts. Its Clear Board action has its own Undo action.

## 🧰 Use the new task tools

The project toolbar has Board/List, a project filter, label and due-date filters, and saved views. Ctrl+F searches all projects. Ctrl+K finds actions, projects, and cards. Add labels, dates, reminders, and files in the card editor.

Drag a column's right edge to resize it. Use its menu for a pixel width, or Auto widths to reset the project. Settings → Themes has three OLED Black options.

See [the feature guide](FEATURES.md) for reminders, attachment safety, portable files, and saved views.

## 🧹 Repair or remove

Close WhiteBoard. Run the MSI again and choose Repair to restore app files, or Remove to uninstall. Windows Settings → Apps also offers removal. Neither action deletes your data folder. Copy or delete that folder yourself only when you intend to remove your projects.
