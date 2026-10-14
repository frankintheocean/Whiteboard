# 🆕 Changes

## 🥇 Version 1.0.0 — 14 October 2026

This release uses version 1.0.0 and keeps existing project data compatible.

- 📋 Fixed full project names in large dropdown lists. Long names can scroll and show a tooltip.
- 🌀 Stopped scroll animation when a card is clicked or opened. Cleared stale wheel targets.
- 📐 Kept short cards at their natural height and made narrow column titles wrap.
- 📍 Kept column scroll position after card edits and other targeted refreshes.
- 🔤 Added an app font picker. SF Pro stays the preferred font when installed.
- 📖 Added a description text size setting.
- 🖋️ Kept font-only and size-only rich text changes on save.
- ⌨️ Added Tab focus, Enter to edit, and Space to select cards.
- 💾 Made Save As and local saves use complete temporary writes before replacement.
- 🔒 Blocked a second app instance from writing to the same data folder.
- 🧰 Kept numbered recovery copies without replacing earlier backups.
- 🧲 Kept duplicate-ID and orphaned cards visible when reading malformed project files.
- 🛡️ Blocked scripts, unsafe links, and local file images in imported rich text.
- 🚧 Showed failed saves in a persistent footer and warned before closing.
- 🧩 Pinned app and build packages with SHA-256 hashes.
- 🎨 Added a simple matte board icon with several Windows sizes.
- 📦 Replaced batch build tooling with a Windows MSI build, repair, and uninstall workflow.
- 🧪 Added data, UI, scroll, and workflow tests, plus real Windows installer checks.

## 🕰️ Earlier builds

The in-app What's New tab keeps earlier WhiteBoard change notes. Existing templates, types, priorities, drag/drop, rich text, undo/redo, import/export, themes, and settings remain available.
