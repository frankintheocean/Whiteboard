# 🧰 Use the new task tools

## 🔎 Search all projects

Press Ctrl+F or All projects. Search any words from a card title, note, project name, type, priority, label, or file name. Each word must match. Search ignores case and works with Unicode text. Open a result to switch to its project and edit the card.

## 🧭 Command palette

Press Ctrl+K or Commands. Find actions, projects, and cards. Start a query with `>` to show commands only. Use Up/Down to choose a result, Enter to open it, and Escape to close the palette.

## ⏰ Dates and reminders

In Add/Edit Card, turn on Due and choose a date and time. Times display in your local timezone and save as UTC timestamps. Pick a reminder at the due time, 15 minutes before, 1 hour before, or 1 day before.

Reminders work while WhiteBoard is open. The app shows missed reminders at the next launch. Windows notifications are used when the system tray is available; an in-app message is also shown. Closing the app stops reminder checks. No background service or automatic startup is installed.

A reminder is delivered once and kept in saved data. Moving or renaming a card does not deliver it again. Changing its due or reminder time schedules a new reminder. Several reminders at once are grouped into one message. Turn off Due or choose No reminder to disable it.

## 🏷️ Multiple labels

Enter comma-separated labels in the card editor. Duplicate labels are removed without changing their display case. Put a label containing a comma inside quotes, for example `"Client, Inc.", Release`.

Labels are separate from card types. Filter by label in the project toolbar or search labels across projects.

## 📎 Attachments

Use Add files in the card editor. Files are copied into WhiteBoard's data folder when the card is accepted. Deleting the original file does not remove the saved copy. Files have SHA-256 checksums and are verified when read or exported.

Open asks before handing a file to its Windows app. Opening uses a separate copy so edits in another app do not change the stored file. Use Save copy to choose a destination. Remove takes a file off the card; stored content is kept so undo and other cards can still use it.

Each file can be up to 25 MB. A project can hold 100 MB of unique attachment content. Executable files, scripts, shortcuts, and unsafe Windows names are blocked. Only open files you trust. The app does not scan files for malware.

Save As and Quick Save include attachment data in the project JSON. Shared content is included once. Open/Import verifies checksums before using those files. Local app data uses file references, so each normal card edit does not rewrite attachment bytes. Back up the whole data folder if you want its cards and attachments together.

## 📋 Board and list

Choose Board or List in the toolbar. The list has Title, Column, Type, Priority, Due, Labels, and Files columns. Click a header to sort, resize headers for more space, and double-click or press Enter to edit. Right-click a row for Edit, Duplicate, or Delete. Select rows to use the existing group-action bar.

Sorting a list does not change stored board order. Switch to Board for drag/drop and inline quick-add. Each project remembers its mode and list sort.

## 🎚️ Saved views

The project toolbar filters by words, type, priority, label, and due date. Due filters include Overdue, Due today, and No due date. Clear filters shows all cards.

Use Save view and enter a name. A view remembers board/list mode, project filters, list sort, each column's type filter and sort, and manual widths. Choose it in Saved views to restore it. Reusing a name asks before replacement. Remove view only removes the saved view, not its cards.

## ↔️ Column widths

Drag a column's right edge, or choose Set column width in its menu. Widths range from 220 to 900 pixels. Each project saves its own widths. A manual width stays fixed when the window changes size. Other columns still fit automatically. Use Auto width for one column or Auto widths for the project to reset them.

## 🌑 OLED Black

Settings → Themes offers OLED Black · Blue, Mint, and Purple. The main background, column surfaces, and cards stay black. Text and focus marks keep visible contrast. Existing paper-card themes remain available.
