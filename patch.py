#!/usr/bin/env python3
"""
LDM Patch -- make horizontal scrollbar identical to vertical (axis-swapped).
Reads vertical lines from the file and generates matching horizontal lines.
Usage:
    cd /home/tanjim/linux-downloader
    python3 patch.py
"""
import os, sys, shutil
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DM   = os.path.join(BASE, "download_manager.py")

def backup(path):
    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, path + ".bak_" + ts)
    print("  backed up")

def main():
    print("\n-- LDM Patch -----------------------------------------------")
    if not os.path.exists(DM):
        print("[ABORT] Cannot find download_manager.py"); sys.exit(1)

    with open(DM, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Find all 5 horizontal and 5 vertical scrollbar lines
    h_lines = {}
    v_lines = {}
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("QScrollBar:horizontal"):        h_lines['bar']     = i
        if s.startswith("QScrollBar::handle:horizontal"): h_lines['handle']  = i
        if s.startswith("QScrollBar::handle:horizontal:hover"): h_lines['hover'] = i
        if s.startswith("QScrollBar::add-line:horizontal"): h_lines['add']   = i
        if s.startswith("QScrollBar::sub-line:horizontal"): h_lines['sub']   = i
        if s.startswith("QScrollBar:vertical"):           v_lines['bar']     = i
        if s.startswith("QScrollBar::handle:vertical") and "hover" not in s: v_lines['handle'] = i
        if s.startswith("QScrollBar::handle:vertical:hover"): v_lines['hover'] = i
        if s.startswith("QScrollBar::add-line:vertical"): v_lines['add']     = i
        if s.startswith("QScrollBar::sub-line:vertical"): v_lines['sub']     = i

    missing = [k for k in ['bar','handle','hover','add','sub'] if k not in v_lines or k not in h_lines]
    if missing:
        print(f"[ERROR] Could not find lines: {missing}"); sys.exit(1)

    print("  Found all scrollbar lines. Generating horizontal from vertical...")
    backup(DM)

    indent = "            "

    def get_v(key):
        return lines[v_lines[key]].rstrip()

    # Build horizontal lines by transforming vertical lines
    # vertical → horizontal transformations:
    #   width → height
    #   height → width  
    #   top → left, bottom → right
    #   min-height → min-width
    #   margin: 18px 2px → margin: 2px 18px
    #   border-top → border-left, border-bottom → border-right
    #   subcontrol-position: bottom → right, top → left
    #   :vertical → :horizontal

    def v_to_h(line):
        s = line
        s = s.replace("QScrollBar:vertical", "QScrollBar:horizontal")
        s = s.replace("QScrollBar::handle:vertical", "QScrollBar::handle:horizontal")
        s = s.replace("QScrollBar::handle:vertical:hover", "QScrollBar::handle:horizontal:hover")
        s = s.replace("QScrollBar::add-line:vertical", "QScrollBar::add-line:horizontal")
        s = s.replace("QScrollBar::sub-line:vertical", "QScrollBar::sub-line:horizontal")
        # Swap dimensions
        s = s.replace("width: 14px", "TMPWIDTH")
        s = s.replace("height: 18px", "width: 18px")
        s = s.replace("height: 14px", "TMPHEIGHT")
        s = s.replace("TMPWIDTH", "height: 14px")
        s = s.replace("TMPHEIGHT", "width: 14px")
        s = s.replace("min-height: 20px", "min-width: 20px")
        # Swap margin axes
        s = s.replace("margin: 18px 2px", "margin: 2px 18px")
        # Swap border sides
        s = s.replace("border-bottom: 1px solid #cbd5e1", "TMPBORDER")
        s = s.replace("border-top: 1px solid #cbd5e1", "border-left: 1px solid #cbd5e1")
        s = s.replace("TMPBORDER", "border-right: 1px solid #cbd5e1")
        # Swap subcontrol positions
        s = s.replace("subcontrol-position: bottom", "TMPSUB")
        s = s.replace("subcontrol-position: top", "subcontrol-position: left")
        s = s.replace("TMPSUB", "subcontrol-position: right")
        return s

    new_h = {
        'bar':    v_to_h(get_v('bar')),
        'handle': v_to_h(get_v('handle')),
        'hover':  v_to_h(get_v('hover')),
        'add':    v_to_h(get_v('add')),
        'sub':    v_to_h(get_v('sub')),
    }

    # Replace horizontal lines in place
    new_lines = list(lines)
    for key in ['bar', 'handle', 'hover', 'add', 'sub']:
        new_lines[h_lines[key]] = new_h[key] + "\n"
        print(f"  [ok]  horizontal {key}")

    with open(DM, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    print("\n-- Done ----------------------------------------------------")
    print("Horizontal scrollbar is now identical to vertical (axes swapped).")

if __name__ == "__main__":
    main()