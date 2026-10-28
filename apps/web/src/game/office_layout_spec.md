# Office Layout Specification

Structured spec from reference screenshot `image.png` for building the isometric office scene:

## 1. Rooms & Coordinates (2:1 Isometric, TW=64, TH=32)
- **CEO OFFICE**: origin (2,2), size (10x8), floor ['#9C7B50','#93744B'], occupant: Vikram (emp_001) at (6,5).
- **MANAGERS**: origin (18,2), size (12x7), floor ['#4B6578','#456073'], occupants: Sara (emp_002) at (21,5), Ben (emp_003) at (25,5).
- **DEVOPS**: origin (2,14), size (10x8), floor ['#8C7A66','#857261'], occupant: Mark (emp_019) at (6,17).
- **MEETING ROOM**: origin (8,26), size (16x12), floor ['#53718B','#4D6B85'], occupants: Meera, Kabir, Tara, Dev at conference table.
- **DEVELOPMENT FLOOR**: origin (30,8), size (20x20), floor ['#C7B698','#C0AE90'], occupants: Sarah (33,11), Arjun (37,11), Neha (41,11), Priya (45,11), Aman (33,16), Rohit (37,16), Ananya (41,16), Rahul (45,16), Ishaan (33,21), Nikhil (37,21), Zoya (41,21), Lakshmi (45,21).

## 2. Badges & Overlays
- **Green Pill / Halo**: `● Working` (#3FCF8E) — working status with typing animation.
- **Amber Pill / Halo**: `● Waiting Approval` (#F2A73B) — waiting status with pulsing halo.
- **Red Pill / Halo**: `✕ BLOCKED` (#E5484D) — blocked task indicator.
- **Magenta Pill / Halo**: `◆ Risk XX` (#E668C3) — anomaly indicator.
- **Floating Popover Card**: Dark card with triangle icon, employee name, role, status heading (e.g. `WAITING FOR APPROVAL`), and detail (e.g. `Agent attempted production deployment`).

## 3. Chrome & Controls
- **Top Tab Bar**: `OFFICE`, `LIVE FEED`, `APPROVALS`, `CONTROL CENTER`.
- **Top-Right Controls**: `▶ REAL TIME`, `▶▶ 10×`, `⏸ PAUSE`.
- **Right Rail**: `SYSTEM LOG` with timestamped entries and status-colored action highlights.
