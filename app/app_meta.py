"""🏷️ Keep the app version and change notes."""

APP_VERSION = "1.0.0"

# 🕰️ Earlier releases stay in their original order.
CHANGELOG = [('0.1.0-pre',
  '2026-08-10',
  ['🚀 Initial release: a multi-project whiteboard-style feature tracker with drag-and-drop cards, status '
   'columns, and local JSON persistence.',
   '🎨 Redesigned with a macOS/iOS-inspired look: SF Pro-style fonts, a translucent toolbar, and rounded '
   'controls.',
   '🖥️ The board window now hugs its content. Its width follows the visible columns and grows or shrinks as '
   'columns are added or removed.',
   '📏 An empty board now reserves only enough width for a single card.',
   '🔡 The project switcher is sorted alphabetically.',
   '✨ Added smooth, animated scrolling across the board.',
   '🏷️ You can now define custom card types beyond Add/Change/Remove/Fix/Idea, each with its own '
   'laminated-note color.',
   '🗂️ Columns can now be reordered by dragging them, in addition to the move-left/move-right buttons.',
   '🔢 Cards are now numbered within their column.',
   '⚙️ Added a Settings panel with general preferences, an Accessibility tab, and 10 selectable themes.',
   '🖋️ Card descriptions now support rich text: font family, size, bold, italic, and underline.',
   '📋 Added a dedicated app icon and this in-app changelog.',
   '📜 Columns now scroll vertically on their own, so a long column no longer overflows the window and a '
   'short column leaves no dead space below its last card.',
   '➕ The "Add Card" control moved into the column header as a compact "+" icon.',
   '📂 Added Open…, Save…, and Import… to the top bar for loading and saving individual project files.',
   '🐛 Fixed a card using a brand-new custom type rendering with the wrong color until the project was '
   'reloaded.',
   '🐛 Fixed dropping a card back into its own column landing one position off from where the drop indicator '
   'was shown.',
   '⚡ Fixed adding, editing, deleting, or dragging a single card rebuilding every card in every column; only '
   'the affected column now re-renders.',
   '⚡ Fixed Settings writing the entire data file to disk up to six times when pressing OK; all settings now '
   'save together in one write.',
   '♿ Fixed theme swatches in Settings being unreachable by keyboard; they can now be Tab-focused and '
   'activated with Enter or Space.',
   '🐛 Fixed labels and icon buttons painting an opaque background box behind their content, which made them '
   'hard to read in several themes.',
   '♿ Added an Accessibility tab to Settings: larger text, reduced motion, and a visible focus outline '
   'toggle.',
   "🐛 Fixed the card context menu building a duplicate menu on right-click instead of reusing the card's "
   'existing menu.',
   '🐛 Fixed card numbers briefly rendering and then disappearing when "Show card numbers" was turned off.',
   '🐛 Fixed adding a card with a new custom type writing the data file to disk twice instead of once.',
   '🐛 Fixed the drop-position indicator re-inserting itself on every mouse movement instead of only when the '
   'target position changed.',
   '🐛 Fixed the Windows installer script reporting an outdated app version.',
   '🐛 Fixed a small leaked widget every time a column was added, renamed, deleted, or reordered.',
   '🛠️ Added a build progress popup that shows live step progress while the Windows build runs, and closes '
   'itself automatically when done.',
   '🛠️ the old build tool now runs fully silently and minimized, with a real progress bar for the '
   "PyInstaller step driven by PyInstaller's own build phases.",
   '⚡ the old build tool no longer recreates the virtual environment or upgrades pip on every run, so repeat '
   'builds start noticeably faster.',
   '🛠️ the old build tool now moves WhiteBoard.exe to the project root when the build finishes and launches '
   'it automatically.',
   '🛑 The build progress popup has a Cancel Build button that stops the build immediately, including '
   'mid-PyInstaller.',
   '🐛 Fixed Cancel Build resolving the wrong process, so it could fail to stop a running build; it now '
   'reliably targets the right process.',
   '💬 Added friendlier wording and icons to buttons, tooltips, menus, and confirmation messages throughout '
   'the app.',
   '🛡️ Saving is now crash-proof: if writing to disk fails, the app shows a clear error instead of crashing '
   'or silently losing the change.',
   '🛡️ Opening a hand-edited or corrupted project file with a malformed id or position no longer crashes the '
   'app; it now loads with safe fallbacks.',
   '🔧 The card right-click menu now uses the current Qt6 pointer API instead of a deprecated Qt5-era call.',
   '🧹 Removed a redundant theme stylesheet application at startup that was always immediately overwritten by '
   'the saved theme.',
   '⚡ Settings, project rename, and project delete no longer rewrite the data file when nothing actually '
   'changed.',
   '🛡️ Hardened card dragging against rare crashes when a column was refreshed or torn down right before or '
   'during a drag.',
   '🐛 Fixed the active project not matching the project shown as selected after loading a file with a stale '
   'saved selection.',
   '⚡ Dropping a card back into its exact starting position is now recognized as a no-op and no longer '
   'rewrites the data file.',
   '⚡ Pressing OK in Settings no longer rebuilds the whole board when only theme, text size, motion, or '
   'focus settings changed.',
   '🧹 Removed a few unused imports and a dead, never-called method left over from earlier refactors, with no '
   'behavior change.',
   '💬 All button and menu text is now bold for better readability.',
   '🖥️ The main window can now be resized horizontally as well as vertically.',
   '🛠️ The build progress bar now updates live throughout the PyInstaller step instead of appearing to stall '
   'for long stretches.',
   '⚡ Reduced the typical Windows build time by turning off UPX binary compression, which added significant '
   'time for no runtime benefit.',
   '📖 The changelog and its long entries are now paginated instead of one long scrolling list.',
   '🐛 Fixed the main window still being unable to resize horizontally or diagonally, and dead space '
   "appearing on the right on first open: the window's size constraints and initial content-fit sizing are "
   "now reapplied after the window's real on-screen geometry has settled, instead of while it was still "
   'mid-layout.',
   '🐛 Fixed the build progress bar appearing completely frozen for most of the PyInstaller step.',
   '⚡ Switched the Windows build to the slimmer PySide6-Essentials package (same modules the app actually '
   'uses), cutting first-time dependency install size and PyInstaller analysis time with no code or behavior '
   'change.',
   '🐛 Fixed horizontal and diagonal edge-drag resizing only working after a column was deleted and re-added: '
   "the window's size constraint is no longer cleared reactively after the fact, which could still lose a "
   "race against Qt's own layout system.",
   '🖥️ Resizing the window wider now grows the columns themselves to fill the extra space (evenly, up to a '
   'sensible maximum width), instead of just revealing more empty canvas to scroll into.',
   "🐛 Fixed a lingering sliver of dead space on the right of the window: the board's scroll area no longer "
   'reserves layout space for a frame it never visually drew, and an unrelated flat width fudge-factor left '
   'over from an earlier fix was removed.',
   '😀 Changelog entries now show an emoji per item.',
   '🐛 Fixed the top toolbar compressing or clipping its buttons when the window was narrowed; it now scrolls '
   'horizontally instead, and buttons never shrink below their normal size.',
   '🖥️ Narrowing the window now shrinks the columns (and their cards) evenly so every column stays visible, '
   'instead of scrolling some of them out of view.',
   '🐛 Fixed Settings tabs becoming unreachable behind scroll arrows when the Settings window was narrowed.',
   "⚡ Theme switching is now faster: each theme's stylesheet is now built once and reused, instead of being "
   'rebuilt from scratch on every preview click.',
   '🔬 Added a Diagnostics tab to Settings: app version, data file size, and column/card counts for the '
   'current project, plus a Clear Board button (with a one-step Undo) to reset the current project to a '
   'blank board.',
   "⌛ The build progress popup's timer now shows a spinning hourglass instead of plain elapsed-time text.",
   '🛠️ The build progress bar now shows live progress across all 4 build steps, not only the PyInstaller '
   'step, so it visibly advances from start to finish instead of sitting empty for 3 of the 4 steps.',
   "🖥️ Enlarged the build progress popup's hourglass timer and progress bar, with its step text sized up to "
   'match.',
   "🐛 Fixed the build progress popup's elapsed timer text visibly shifting left and right on every tick.",
   '😀 The build progress popup now shows a matching emoji next to each of the 4 build steps instead of one '
   'generic icon throughout.',
   "🎨 The build progress popup's title bar is now dark to match the rest of its already-dark window, instead "
   "of the OS's default light title bar.",
   "🖥️ The top toolbar's buttons, project selector, and title now shrink and grow together as the window is "
   'resized, so every control stays visible without needing to scroll.',
   '🐛 Fixed Add Column and New Card drifting away from the other toolbar buttons with visible dead space '
   'between them at some window widths.',
   '💬 All dropdown text (the project switcher and card-type picker, both closed and open) is now bold, '
   "matching the rest of the app's bold button and menu text.",
   "🐛 Fixed the build progress popup's spinning hourglass rendering as a thin dash instead of the actual "
   'emoji.',
   "🐛 Fixed the build progress popup's Cancel Build button having no visible box around it, unlike every "
   'other button in the app.',
   '🐛 Fixed a crash ("NameError: name \'root\' is not defined") right after a build finished and the app '
   'launched: board-canvas setup code had ended up inside the wrong method and was moved back to where it '
   'belongs.',
   "🛠️ The build progress popup's spinning hourglass is now a static hammer-and-wrench icon instead, after "
   'the hourglass glyphs continued to render inconsistently even with an explicit emoji-presentation marker.',
   '🎨 The main app window now has a dark title bar to match its dark theme, using the same approach as the '
   "build progress popup's title bar.",
   "🖥️ The build progress popup's progress bar and Cancel Build button now have rounded corners instead of "
   'hard corners.',
   "🐛 Fixed the build progress popup's hammer-and-wrench icon not appearing at all next to the elapsed "
   'timer; the box it sits in was only 1px tall, clipping the icon down to invisible.',
   "🌈 Fixed the build progress popup's title, step text, and Cancel button rendering their emoji in "
   'monochrome; they now use the same color-emoji font the spinner icon already used.',
   '♿ Fixed “Larger text” in Settings > Accessibility not enlarging the settings gear icon or column '
   "headers, which each set their own fixed text size that the general text-size setting didn't reach.",
   '🖥️ Fixed the settings gear icon and project selector silently snapping back to normal size when the '
   'window was narrowed while “Larger text” was on.',
   '🖥️ Fixed a wide gap of empty toolbar between Import… and Add Column when the window was wide or '
   'maximized; every top-bar button now sits together with the same normal spacing throughout.',
   '🖥️ Columns now grow further to fill a wide or maximized window, fixing a strip of unused dead space that '
   'used to appear to the right of the last column.',
   '🐛 Fixed a lopsided right-hand margin in the column and card “⋯” menus that left visible dead space next '
   'to each menu item.',
   '🎨 Added two more themes: Seafoam (light) and Carbon (dark), for 12 in total.',
   "✏️ The currently selected project now also renders extra-bold in the open project dropdown list, so it's "
   'easy to pick out at a glance.']),
 ('0.1.5-pre',
  '2026-08-10',
  ["🖥️ Fixed the old build tool's finished app sometimes opening minimized and unfocused; it now launches in "
   'front of everything else with focus.',
   "🐛 Fixed the project and card-type dropdown popups always matching the closed field's width, leaving dead "
   "space to the right of shorter names; popups now fit their own widest item's text.",
   '🖥️ Tightened the spacing between top toolbar buttons and section breaks so the whole row sits closer '
   'together, while every button still scales and repositions responsively as the window is resized.',
   '🐛 Fixed Settings tabs shorter than the Themes tab (General, Accessibility, Diagnostics) showing a large '
   'empty gap below their content.',
   '⚙️ The Settings button now shows "Settings" next to its gear icon instead of the icon alone.',
   "⚡ Theme switching is now faster still: re-selecting the theme that's already active (e.g.",
   "🐛 Fixed the project selector showing a fixed-width box regardless of the active project's name, leaving "
   'dead space to the right of short names inside the closed field itself.',
   '📖 The "What\'s New" tab now shows the newest version\'s notes on page one instead of the oldest, so it '
   'always opens on the current release (matching the version shown in Settings > Diagnostics) rather than '
   'requiring you to page forward to reach it.',
   '🏷️ Renamed the app from the old app name to WhiteBoard throughout: window title, taskbar/app name, file '
   'dialogs, the exported .fboard.json project-file description, the built .exe and installer, and the data '
   'folder the app reads/writes (existing the old app name installs keep their old projects under their old '
   'data folder.',
   '⚙️ Added Quick Save: re-saves the current project straight back to wherever it was last saved, with no '
   'file dialog.',
   '🐛 Fixed switching projects (or reordering columns, or anything else that rebuilds the board without '
   'changing the column count) leaving the newly rebuilt columns at their default width instead of the width '
   "you'd already resized the window to, showing dead space on the right until you manually resized again.",
   '🖥️ Card titles and descriptions are now bold and center-aligned by default, instead of left-aligned '
   'regular/semi-bold text.',
   '🖥️ Increased the default text size for buttons, the app title, the settings gear label, and column '
   'headers throughout the app.',
   "📋 Added a Duplicate option to each card's ⋯ menu, which inserts a copy of the card directly after the "
   'original in the same column.',
   '📖 The "What\'s New" tab now has a version picker instead of one long list spanning every release.',
   "🐛 Fixed the top toolbar's buttons collecting into a single lopsided gap (always just before Add Column) "
   "as the window widened or was maximized, instead of the row's extra space being shared evenly.",
   '🏷️ Each column can now be filtered to show only one card type at a time via a small dropdown under its '
   'header, so a busy column can be narrowed down to just its Bugs, just its Ideas, and so on.',
   '🎨 Each column now shows a thin color accent stripe along its left edge, cycling through a fixed palette '
   'by position, so columns are easier to tell apart at a glance on a wide board.']),
 ('0.1.6-pre',
  '2026-08-10',
  ['⚙️ Switched project storage from a single combined data file to one file per project, plus a small index '
   'file for the active project and app settings.',
   "➕ Added inline quick-add: type a title directly into a small field under any column's header and press "
   'Enter to add a card immediately, without opening the full Add Card dialog.',
   '📂 Added Export…: saves the current project as a readable Markdown (.md) or plain-text (.txt) file, '
   'grouped by column and card in the same order shown on the board, for sharing, printing, or pasting '
   'elsewhere. This is a one-way, read-only export.']),
 ('0.2.0-pre',
  '2026-08-10',
  ['⚡ Fixed Ctrl+S: it now quicksaves the current project straight back to its already-known file with no '
   "dialog, matching how Word and most editors handle Ctrl+S on a document that's already been saved once. "
   'Prompts for a location only the first time, exactly like the existing Quick Save button (which Ctrl+S '
   'now triggers).',
   '🏷️ Added board templates: New Project now offers a choice of starting column layouts (Classic, Simple, '
   'Bug Tracker, Kanban, Sprint, or a blank board with no columns) instead of always starting from the same '
   'fixed Backlog/In Progress/Review/Done set. The classic layout is still the default choice.',
   '🚩 Added an optional priority flag (P0–P3) to cards, shown as a small color-coded badge next to the type '
   'badge.',
   '🖼️ Added an empty-state illustration and “Add one” call-to-action to any column with no visible cards, '
   'so a fresh or fully-filtered column reads as intentionally empty rather than looking broken. A column '
   'narrowed down to zero cards by its type filter shows a distinct “no cards match this filter” message '
   "instead, without a CTA (since adding a card wouldn't appear under that filter anyway).",
   '🖼️ Card descriptions now support inline images in addition to font/bold/italic/underline: paste an image '
   'directly into the description editor, or use its new 🖼️ toolbar button to insert one from a file. Images '
   'are embedded directly in the saved project file (auto-downscaled to a sensible max size first) so they '
   'travel with Save As/Quick Save/Export like any other card content, with no separate attachment files to '
   'manage.']),
 ('0.2.5-pre',
  '2026-08-10',
  ['↩️ Added general Undo/Redo (Ctrl+Z / Ctrl+Y, also Ctrl+Shift+Z) covering card '
   'add/edit/delete/duplicate/move and column add/rename/delete/reorder, separate from the existing one-shot '
   'Diagnostics > Clear Board undo. Stays out of the way of normal text-field undo: while a title, '
   "description, or other text field has focus, Ctrl+Z/Ctrl+Y still do the field's own native undo instead.",
   '☑️ Added multi-select: Shift-click for a range or Ctrl-click to toggle individual cards, across columns.',
   '🔔 Save confirmations and non-fatal save/open/import/export errors now show as small, self-closing toast '
   "notifications instead of a modal OK dialog, so they no longer interrupt what you're doing. "
   'Destructive-action confirmations (deleting a card, column, or project) are unchanged and still ask '
   'first.',
   '⚠️ Closing the window now warns if any project has changes made after its last Save As…/Quick Save to an '
   "external file that haven't been saved back to that file."]),
 ('0.3.0-pre',
  '2026-08-10',
  ['☑️ Added a checkbox to every card as an explicit, always-visible way to select it, alongside the '
   'existing Shift/Ctrl-click gesture on the card body.',
   '🖱️ Shift/Ctrl-selecting several cards and then dragging any one of them now drags the whole selection '
   'together: dropping lands every selected card at the drop position, in the same relative order they '
   'already had, in a single undoable step.',
   '📎 You can now drag files or images from outside the app (Explorer/Finder, a browser, etc.) directly onto '
   'a card to attach them.',
   '🖥️ The multi-select bulk-action bar (Move to…/Set type…/Delete) now wraps its buttons onto additional '
   "rows on a narrow window instead of clipping or forcing the window wider, matching the app's existing "
   'shrink-to-fit column and top-bar behavior.']),
 ('0.3.1-pre',
  '2026-08-10',
  ["🐛 Fixed cards' drop shadow being clipped along the right edge inside every column.",
   '🐛 Fixed toast pop-ups (e.g.']),
 ('0.3.2-pre',
  '2026-08-11',
  ['🐛 Fixed dragging a card that was part of a multi-card selection (Shift/Ctrl-click or the selection '
   'checkbox) moving only that one card instead of the whole selection: a plain click on an already-selected '
   'card was collapsing the selection down to just that card the instant the mouse was pressed, before a '
   'drag could ever start, so the group-drag logic added in v3.0 never actually got a chance to see more '
   'than one selected card. Pressing on an already-selected card now keeps the whole selection intact so it '
   'can be dragged together, matching standard file-manager behavior.',
   '🔬 Added simple error logging to Diagnostics: save/open/import/export failures and any '
   'otherwise-unhandled error are now recorded to a small in-app log, viewable (and clearable) from Settings '
   '> Diagnostics, in addition to the toast notification already shown at the time.']),
 ('0.3.3-pre',
  '2026-08-11',
  ['🐛 Fixed a card (or a dragged multi-card selection) staying visibly selected, and the bulk-action bar '
   'staying open, after being dragged into a different column.',
   '🖱️ All buttons now consistently show a pointer cursor on hover, including a handful that had been '
   'missed: several top-bar buttons (New Project, Rename, Delete Project, Open…, Quick Save, Save As…, '
   "Import…, Export…, Add Column, New Card), the multi-select bulk-action bar's Move to…/Set type…/Delete "
   "buttons, and a few Settings-dialog buttons (Clear Board, Undo, Clear Log, the changelog's Prev/Next, and "
   "the description editor's Bold/Italic/Underline).",
   "🐛 Fixed the multi-select bulk-action bar's Move to…/Set type…/Delete buttons rendering with an oversized "
   'hit/paint box taller than their visible content.',
   '🖥️ The Settings button is now the same height as New Card, so the two sit vertically aligned in the top '
   'bar instead of Settings appearing noticeably larger.']),
 ('0.3.4-pre',
  '2026-08-11',
  ['🗑️ Removed file/image card attachments: cards no longer accept files or images dragged onto them from '
   "outside the app, and the small filename-chip strip under a card's description is gone.",
   '🗑️ Removed inline images from the card description editor: the 🖼️ “Insert Image” toolbar button is gone, '
   'and pasting an image into the description field no longer embeds it.',
   '🖱️ Added a pointer cursor to a few remaining spots that still showed the default arrow on hover: every '
   "dialog's OK/Cancel buttons (Add/Edit Card, New Project, rename/text prompts, Settings) and the Settings "
   "dialog's own tab bar (General/Themes/Accessibility/Diagnostics/What's New).",
   '🐛 Fixed Quick Save / Ctrl+S prompting with a Save As… dialog on the first save after reopening the app, '
   'even for a project that had already been saved to a file in a previous session.',
   '⚙️ Added a few more General preferences: remembering the last-active project on relaunch is now '
   'optional, and you can choose whether double-clicking a card opens it for editing or just selects it.',
   '♿ Added more Accessibility options: a high-contrast focus outline width control, an option to always '
   'show column drop-zone highlights (not just during an active drag), and an underline-links-on-hover '
   'toggle for better link visibility.']),
 ('1.0',
  '2026-08-11',
  ['🚀 First official release build.',
   '🗑️ Removed the "Audits" changelog category and every entry filed under it, in every version\'s history, '
   'so the "What\'s New" tab now shows only user-facing changes (bug fixes, features, performance, UI, '
   'accessibility, build/packaging) instead of internal audit notes.',
   '🛠️ Added a startup menu to the old build tool: running it now opens a popup (matching the build progress '
   "popup's own styling) offering Start Build, Uninstall, or Fix Build, instead of always starting a build "
   'immediately.']),
 ('1.1',
  '2026-08-11',
  ['🔝 Added a "Sort by" control to every column, right below its type filter: sort that column\'s cards by '
   'Type or Priority (ascending or descending, via a small direction toggle), or leave it at the default '
   '"Board order". Sorting is purely a display choice, exactly like the existing type filter.',
   '🔠 Card titles and plain-text descriptions now render in ALL CAPS by default (a new "Show card text in '
   'ALL CAPS" toggle in Settings > General, on by default).',
   '🔍 Added an adjustable UI scale / zoom control to Settings > Accessibility (80%-150%, in addition to the '
   'existing one-click "Larger text" toggle).']),
 ('1.2',
  '2026-08-14',
  ['🐛 Fixed sorting a column by Type or Priority not grouping cards on the other axis too: sorting by '
   'Priority now keeps same-type cards together within each priority group, and sorting by Type keeps '
   'same-priority cards together within each type group, instead of only ordering by the one key you picked.',
   "🖱️ Enlarged the click targets for a card's More Options (⋯) button, type badge, priority badge, and "
   'selection checkbox, so a click near any of these reliably hits the control instead of falling through '
   'and selecting the card underneath.',
   '✏️ The card type badge and priority badge are now clickable: pick a new type or priority directly from '
   'the card face via a small menu, without opening the full Edit Card dialog.',
   '☑️ The multi-select bulk-action bar gained two more actions alongside Move to…/Set type…/Delete: Set '
   'priority… (apply one priority, or clear it, across every selected card) and Duplicate (copy every '
   'selected card in place, directly after each original). Both are undoable like every other bulk action.',
   '🏷️ Renamed the priority levels from P0–P3 to plain-language labels (High Priority, Medium-High Priority, '
   "Medium-Low Priority, Low Priority) everywhere they're shown: the card badge, the Add/Edit Card dialog, "
   'and the bulk Set priority… menu. This is display-only.']),
 ('1.3',
  '2026-08-14',
  ['🐛 Fixed each column\'s "Sort by" choice resetting to "Board order" whenever you switched projects and '
   'back.',
   "🐛 Fixed low-contrast white text on brighter priority badges (Medium-Low Priority's yellow especially, "
   "Medium-High Priority's orange too) being hard to read.",
   "♿ Added color-blind-safe card type indicators: every card's type badge now shows a distinct glyph "
   'alongside its existing color and label, so type is identifiable by shape as well as color.']),
 ('1.4',
  '2026-08-14',
  ['🐛 Fixed the old build tool\'s Uninstall option reporting "nothing to uninstall" for a real, present '
   'install: it only ever checked the HKCU uninstall registry entry, but an install that was ever run '
   'elevated registers under HKLM instead even with PrivilegesRequired=lowest.']),
 ('1.5',
  '2026-08-25',
  ['🏷️ Built-in card types (Add, Change, Remove, Fix, Idea) can now be renamed or deleted from Manage Card '
   'Types, the same as custom types -- previously only custom types could be edited there.']),
 ('1.0.0',
  '2026-10-14',
  ['📋 Fixed long project names in scrollable menus.',
   '🌀 Fixed unwanted scrolling when opening or editing cards.',
   '🔤 Added an app font picker with SF Pro as the first choice.',
   '📖 Added a description text size setting.',
   '💾 Save As now replaces files only after a complete write.',
   '🔒 Prevented two app windows from overwriting the same data.',
   '🛡️ Blocked active HTML and local file links in imported descriptions.',
   '🧰 Kept malformed data for recovery and kept duplicate cards visible.',
   '⌨️ Added keyboard access to card editing and selection.',
   '📦 Added a Windows MSI installer with repair and uninstall.'])]
