# 🛰️ Run Windows checks and publish releases

The workflow tests each change, builds Windows files, and checks the installer. Tags publish releases only after the checks pass. App, installer, and artifact versions are read from the app metadata. A release tag must match that version. Already published files are kept when a tag build runs again.

Use the bug form to report a problem. Use the feature form for a new idea. Pull requests should explain the change, checks, and limits. Never include private project data.
