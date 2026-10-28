#!/usr/bin/env python3
"""Build apps/web/public/characters.png from Pipoya 32x32 RPG sprites.

Layout:
  5 character columns x 4 character rows = 20 characters
  Each character is 3 frames wide (96px) x 4 directions high (128px)
  Total canvas: 480px wide x 512px high

  For character index i (0..19):
    block_col = i % 5
    block_row = i // 5
    Top-left of 3x4 block: (block_col * 3 * 32, block_row * 4 * 32)
    Standing front frame (col 1, row 0 in block):
      colIndex = block_col * 3 + 1
      rowIndex = block_row * 4
"""

import os
import shutil
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
PIPOYA = Path("/Users/kanishk_pandey/Desktop/as/PIPOYA FREE RPG Character Sprites 32x32")
PUBLIC_OUT = ROOT / "apps" / "web" / "public" / "characters.png"
OFFICE_OUT = ROOT / "apps" / "web" / "public" / "assets" / "office" / "characters.png"

# 20 Canonical Employees -> 10 Female, 10 Male Pipoya sprites
MAPPINGS = [
    ("emp_001", "Female/Female 01-1.png"),   # Sarah Chen
    ("emp_002", "Male/Male 01-1.png"),       # Marcus Vance
    ("emp_003", "Female/Female 02-1.png"),   # Elena Rostova
    ("emp_004", "Male/Male 02-1.png"),       # David Kim
    ("emp_005", "Female/Female 03-1.png"),   # Priya Patel
    ("emp_006", "Male/Male 03-1.png"),       # Alex Mercer
    ("emp_007", "Male/Male 04-1.png"),       # James Thorne
    ("emp_008", "Female/Female 04-1.png"),   # Maya Lin
    ("emp_009", "Male/Male 05-1.png"),       # Tom Wilson
    ("emp_010", "Female/Female 05-1.png"),   # Olivia Taylor
    ("emp_011", "Male/Male 06-1.png"),       # Lucas Gray
    ("emp_012", "Female/Female 06-1.png"),   # Anya Sharma
    ("emp_013", "Female/Female 07-1.png"),   # Rachel Green
    ("emp_014", "Male/Male 07-1.png"),       # Vikram Malhotra
    ("emp_015", "Female/Female 08-1.png"),   # Zoe Kastner
    ("emp_016", "Male/Male 08-1.png"),       # Daniel Park
    ("emp_017", "Female/Female 09-1.png"),   # Chloe Bennet
    ("emp_018", "Female/Female 10-1.png"),   # Samira Khan
    ("emp_019", "Male/Male 09-1.png"),       # Felix Wright
    ("emp_020", "Male/Male 10-1.png"),       # Tariq Al-Mansoor
]

def main() -> None:
    width = 5 * 3 * 32    # 480px
    height = 4 * 4 * 32   # 512px
    sheet = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    coords = {}

    for i, (eid, rel_path) in enumerate(MAPPINGS):
        img_path = PIPOYA / rel_path
        if not img_path.exists():
            raise FileNotFoundError(f"Missing sprite {img_path}")

        char_img = Image.open(img_path).convert("RGBA")
        if char_img.size != (96, 128):
            char_img = char_img.resize((96, 128), Image.Resampling.NEAREST)

        block_col = i % 5
        block_row = i // 5

        x = block_col * 96
        y = block_row * 128

        sheet.paste(char_img, (x, y), char_img)

        # The standing front frame is col 1 in this 3-col block, row 0 in this 4-row block
        stand_col = block_col * 3 + 1
        stand_row = block_row * 4

        coords[eid] = {
            "spriteCol": stand_col,
            "spriteRow": stand_row,
            "pixelX": stand_col * 32,
            "pixelY": stand_row * 32,
        }

    PUBLIC_OUT.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(PUBLIC_OUT, "PNG")
    print(f"Saved: {PUBLIC_OUT} ({width}x{height})")

    OFFICE_OUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PUBLIC_OUT, OFFICE_OUT)
    print(f"Copied to: {OFFICE_OUT}")

    for eid, c in coords.items():
        print(f"  {eid}: col={c['spriteCol']}, row={c['spriteRow']} (px: {c['pixelX']}, {c['pixelY']})")

if __name__ == "__main__":
    main()
