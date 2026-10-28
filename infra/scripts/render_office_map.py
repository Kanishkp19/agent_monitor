#!/usr/bin/env python3
"""Generate a unified, pre-assembled isometric office background image.

Creates apps/web/public/office_map.png with 5 connected rooms:
  1. CEO Office (Top-Left)
  2. Managers Suite (Top-Center)
  3. DevOps Center (Bottom-Left)
  4. Meeting Room (Bottom-Center)
  5. Development Floor (Right Half)
"""

import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = ROOT / "apps" / "web" / "public" / "office_map.png"

W, H = 1400, 900

def draw_iso_diamond(draw, cx, cy, hw, hh, fill, outline=None):
    pts = [
        (cx, cy - hh),
        (cx + hw, cy),
        (cx, cy + hh),
        (cx - hw, cy),
    ]
    draw.polygon(pts, fill=fill, outline=outline)

def draw_iso_cube(draw, cx, cy, hw, hh, height, top_color, left_color, right_color):
    # Left face
    draw.polygon([
        (cx - hw, cy),
        (cx, cy + hh),
        (cx, cy + hh - height),
        (cx - hw, cy - height),
    ], fill=left_color)
    # Right face
    draw.polygon([
        (cx, cy + hh),
        (cx + hw, cy),
        (cx + hw, cy - height),
        (cx, cy + hh - height),
    ], fill=right_color)
    # Top face
    draw_iso_diamond(draw, cx, cy - height, hw, hh, fill=top_color)

def main():
    img = Image.new("RGBA", (W, H), (11, 15, 23, 255)) # Dark ink background
    draw = ImageDraw.Draw(img)

    # 1. Base floor boundary - large unified floorplate
    floor_margin_x = 40
    floor_margin_y = 30
    fw = W - floor_margin_x * 2
    fh = H - floor_margin_y * 2

    # Draw ambient floor grid
    grid_size = 35
    for x in range(floor_margin_x, floor_margin_x + fw, grid_size):
        for y in range(floor_margin_y, floor_margin_y + fh, grid_size):
            draw.rectangle([x, y, x + grid_size - 1, y + grid_size - 1], fill=(22, 30, 44, 255), outline=(28, 38, 56, 255))

    # Room definitions [name, x1, y1, x2, y2, floor_color, border_color, accent_color]
    rooms = [
        ("CEO OFFICE", 70, 60, 380, 360, (38, 30, 24, 255), (65, 52, 40, 255), (180, 130, 60, 255)),
        ("MANAGERS SUITE", 420, 60, 850, 360, (32, 36, 46, 255), (55, 62, 78, 255), (61, 123, 255, 255)),
        ("DEVOPS CENTER", 70, 420, 410, 840, (20, 28, 42, 255), (42, 58, 84, 255), (229, 72, 77, 255)),
        ("MEETING ROOM", 450, 420, 850, 840, (24, 32, 48, 255), (45, 60, 88, 255), (63, 207, 142, 255)),
        ("DEVELOPMENT FLOOR", 890, 60, 1330, 840, (25, 34, 50, 255), (48, 64, 92, 255), (160, 100, 240, 255)),
    ]

    for name, x1, y1, x2, y2, fcol, bcol, acol in rooms:
        # Room floor
        draw.rectangle([x1, y1, x2, y2], fill=fcol, outline=bcol, width=3)
        # Inner accent line
        draw.rectangle([x1 + 6, y1 + 6, x2 - 6, y2 - 6], outline=(bcol[0] + 15, bcol[1] + 15, bcol[2] + 15, 255), width=1)
        # Room label header plate
        draw.rectangle([x1 + 14, y1 + 12, x1 + 180, y1 + 34], fill=(15, 20, 30, 230), outline=bcol, width=1)
        draw.rectangle([x1 + 14, y1 + 12, x1 + 18, y1 + 34], fill=acol)
        draw.text((x1 + 25, y1 + 17), name, fill=(200, 210, 225, 255))

    # Room-specific furniture & details
    # 1. CEO Office Rug & Desk
    draw.rectangle([130, 140, 320, 300], fill=(62, 30, 38, 255), outline=(90, 45, 55, 255), width=2) # Rug
    # CEO Desk
    draw.rectangle([170, 190, 280, 250], fill=(70, 48, 35, 255), outline=(95, 65, 48, 255), width=2)
    draw.rectangle([180, 200, 270, 240], fill=(45, 32, 24, 255)) # Desk mat
    draw.rectangle([210, 182, 240, 188], fill=(15, 20, 30, 255)) # Monitor
    # Bookshelves along CEO back wall
    for by in range(75, 280, 50):
        draw.rectangle([78, by, 95, by + 38], fill=(55, 40, 30, 255), outline=(80, 60, 45, 255))

    # 2. Managers Desks
    draw.rectangle([470, 190, 580, 250], fill=(50, 58, 72, 255), outline=(75, 86, 105, 255), width=2)
    draw.rectangle([480, 200, 570, 240], fill=(35, 40, 50, 255))
    draw.rectangle([510, 182, 540, 188], fill=(15, 20, 30, 255))

    draw.rectangle([680, 190, 790, 250], fill=(50, 58, 72, 255), outline=(75, 86, 105, 255), width=2)
    draw.rectangle([690, 200, 780, 240], fill=(35, 40, 50, 255))
    draw.rectangle([720, 182, 750, 188], fill=(15, 20, 30, 255))

    # Coffee Bar in Managers suite
    draw.rectangle([435, 80, 540, 115], fill=(45, 52, 65, 255), outline=(65, 75, 95, 255))
    draw.text((445, 90), "☕ COFFEE & TEA", fill=(160, 175, 195, 255))

    # 3. DevOps Server Racks & Workstations
    # Server Racks along left wall
    for ry in range(450, 780, 65):
        draw.rectangle([80, ry, 115, ry + 50], fill=(18, 25, 38, 255), outline=(40, 60, 90, 255), width=2)
        # Blinking LED strips
        for led_y in range(ry + 8, ry + 45, 10):
            draw.line([(88, led_y), (107, led_y)], fill=(63, 207, 142, 255), width=2)
    # DevOps Desks
    draw.rectangle([170, 510, 280, 570], fill=(38, 48, 64, 255), outline=(58, 74, 98, 255), width=2)
    draw.rectangle([180, 520, 270, 560], fill=(26, 32, 44, 255))
    draw.rectangle([210, 502, 240, 508], fill=(15, 20, 30, 255))

    draw.rectangle([270, 640, 380, 700], fill=(38, 48, 64, 255), outline=(58, 74, 98, 255), width=2)
    draw.rectangle([280, 650, 370, 690], fill=(26, 32, 44, 255))
    draw.rectangle([310, 632, 340, 638], fill=(15, 20, 30, 255))

    # 4. Meeting Room - Conference Table
    draw.rectangle([520, 510, 780, 740], fill=(55, 42, 32, 255), outline=(85, 65, 50, 255), width=3)
    draw.rectangle([540, 530, 760, 720], fill=(42, 32, 25, 255))
    # Presentation Display screen on top wall
    draw.rectangle([580, 425, 720, 435], fill=(30, 50, 80, 255), outline=(61, 123, 255, 255), width=2)
    draw.text((610, 440), "PROJECTOR DISPLAY", fill=(100, 140, 200, 255))

    # 5. Development Floor - 12 Workstations arranged in 6 pods
    dev_rows = [
        (950, 150), (1140, 150),
        (950, 280), (1140, 280),
        (950, 410), (1140, 410),
        (950, 540), (1140, 540),
        (950, 670), (1140, 670),
        (950, 770), (1140, 770),
    ]

    for dx, dy in dev_rows:
        draw.rectangle([dx, dy, dx + 130, dy + 55], fill=(40, 50, 68, 255), outline=(65, 82, 110, 255), width=2)
        draw.rectangle([dx + 10, dy + 8, dx + 120, dy + 47], fill=(26, 33, 46, 255))
        # Dual monitors
        draw.rectangle([dx + 25, dy + 2, dx + 60, dy + 7], fill=(12, 16, 24, 255))
        draw.rectangle([dx + 70, dy + 2, dx + 105, dy + 7], fill=(12, 16, 24, 255))

    # Water cooler & snack station in dev floor
    draw.rectangle([1260, 80, 1310, 130], fill=(30, 45, 65, 255), outline=(50, 75, 105, 255))
    draw.ellipse([1275, 90, 1295, 110], fill=(61, 123, 255, 200))
    draw.text((1255, 135), "WATER", fill=(120, 150, 190, 255))

    # Save to public directory
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT_PATH, "PNG")
    print(f"Created: {OUT_PATH} ({W}x{H})")

if __name__ == "__main__":
    main()
