#!/usr/bin/env python3
"""
LDM patch: remember column widths + set progress bar to 150px
Usage: python3 patch_ldm.py /home/tanjim/linux-downloader/download_manager.py
"""

import sys
import shutil
import os

CHANGES = [
    # 1. Progress bar column width: 199 → 150
    (
        "        self.table.setColumnWidth(1, 199)\n",
        "        self.table.setColumnWidth(1, 150)\n",
        "Set progress column width to 150px",
    ),
    # 2. Restore saved column widths after the defaults block
    (
        "        self.table.horizontalHeader().setStretchLastSection(False)\n",
        (
            "        self.table.horizontalHeader().setStretchLastSection(False)\n"
            "        # ── Restore saved column widths ──────────────────────────────\n"
            "        saved_widths = self._settings.get(\"column_widths\", {})\n"
            "        for col_str, width in saved_widths.items():\n"
            "            self.table.setColumnWidth(int(col_str), width)\n"
        ),
        "Restore saved column widths on startup",
    ),
    # 3. Connect sectionResized signal
    (
        "        self.table.horizontalHeader().sectionClicked.connect(self._sort_by_column)\n",
        (
            "        self.table.horizontalHeader().sectionClicked.connect(self._sort_by_column)\n"
            "        self.table.horizontalHeader().sectionResized.connect(self._on_column_resized)\n"
        ),
        "Connect sectionResized to save handler",
    ),
    # 4. Add _on_column_resized method after _reset_column_widths
    (
        "    def _sort_by_column(self, col):\n",
        (
            "    def _on_column_resized(self, col, old_width, new_width):\n"
            "        widths = self._settings.setdefault(\"column_widths\", {})\n"
            "        widths[str(col)] = new_width\n"
            "        save_settings(self._settings)\n"
            "\n"
            "    def _sort_by_column(self, col):\n"
        ),
        "Add _on_column_resized method",
    ),
]

def patch(filepath):
    if not os.path.exists(filepath):
        print(f"ERROR: file not found: {filepath}")
        sys.exit(1)

    backup = filepath + ".bak"
    shutil.copy2(filepath, backup)
    print(f"Backup saved → {backup}")

    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()

    for old, new, description in CHANGES:
        if old not in source:
            print(f"SKIP (already applied or not found): {description}")
            continue
        source = source.replace(old, new, 1)
        print(f"OK: {description}")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(source)

    print("\nAll done. Restart LDM to apply changes.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 patch_ldm.py /path/to/main.py")
        sys.exit(1)
    patch(sys.argv[1])
