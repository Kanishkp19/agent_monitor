# AgentShield Office — Structured Layout & Visual Spec

> Derived from reference screenshot `image.png` and `h.html` prototype.
> Defines room zones, grid coordinates, employee desk assignments, badge states, and UI components.

---

## 1. Coordinate System & Projection

- **Projection Type**: 2:1 Isometric Projection
- **Tile Dimensions**: `TW = 64px`, `TH = 32px`
- **Formulas**:
  - `iso(tx, ty)`: `x = (tx - ty) * (TW / 2)`, `y = (tx + ty) * (TH / 2)`
  - `depth(tx, ty, layer)`: `(tx + ty) * 10 + layer` (layer 0: floor, 1: furniture/props, 2: actor/avatar, 3: HUD/popovers)
- **Wall Height**: `WALL_H = 62px`
- **Brick Wall Styling**:
  - Mortar: `#5E3229`
  - Brick shades: `['#8E4C3C', '#96523F', '#874536', '#9A5744', '#823F33']`
  - Island slab base: `#2B1F1A`, highlight `#3A2A22`

---

## 2. Room Zones & Grid Coordinates

| Room ID | Display Label | Origin `(tx, ty)` | Size `(w, h)` | Floor Pattern | Key Furniture & Props |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `ceo_office` | **CEO OFFICE** | `(2, 2)` | `10 × 8` | Warm oak tiles `['#9C7B50', '#93744B']` | Executive wood desk `(7, 5)`, monitor, CEO chair, green bordered rug, bookshelf, potted plant `(3, 3)`, wall portrait |
| `managers` | **MANAGERS** | `(18, 2)` | `12 × 7` | Slate grey tiles `['#4B6578', '#456073']` | Two L-shaped manager desks `(21, 5)` & `(25, 5)`, monitors, chairs, bookshelf `(19, 3)`, printer `(28, 3)`, plant, window to sky |
| `devops` | **DEVOPS** | `(2, 14)` | `10 × 8` | Industrial stone `['#8C7A66', '#857261']` | 3 server racks with blinking LEDs `(3, 15..17)`, retro green terminal CRT monitors, work desk, shelf, printer, plant |
| `meeting_room` | **MEETING ROOM** | `(8, 26)` | `16 × 12` | Blue grid tiles `['#53718B', '#4D6B85']` | Large conference table `(13.4, 31.4)` with 8 chairs, whiteboard on wheels `(22, 28)`, wall TV screen, plants |
| `dev_floor` | **DEVELOPMENT FLOOR** | `(30, 8)` | `20 × 20` | Light beige tiles `['#C7B698', '#C0AE90']` | Cubicle clusters with grey partitions, desks, monitors, office chairs, water coolers `(48, 9)` & `(49, 19)`, coffee machine `(48, 10.2)`, plants |

---

## 3. Employee Desk Assignments & Initial States

| Employee ID | Name | Role | Room | Desk `(tx, ty)` | Facing | Default FSM | Initial Badge / Indicator |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `emp_001` | Vikram Nair | CEO | `ceo_office` | `(6, 5)` | East (`e`) | `working` | Nameplate `CEO \| Vikram` |
| `emp_002` | Sara Iyer | Senior Manager | `managers` | `(21, 5)` | East (`e`) | `working` | Nameplate `Sara` |
| `emp_003` | Ben Mathew | Manager | `managers` | `(25, 5)` | East (`e`) | `working` | Nameplate `Ben` |
| `emp_004` | Sarah Khan | Senior Eng. | `dev_floor` | `(33, 11)` | East (`e`) | `waiting` | Nameplate `Sarah \| Senior Eng.` + Pill `● Waiting Approval` (Amber) |
| `emp_005` | Arjun Menon | Senior Eng. | `dev_floor` | `(37, 11)` | East (`e`) | `working` | Nameplate `Senior Eng.` + Pill `● Working` (Green) |
| `emp_006` | Neha Gupta | Senior Eng. | `dev_floor` | `(41, 11)` | East (`e`) | `idle` | Nameplate `Neha` |
| `emp_007` | Priya Sharma | Engineer | `dev_floor` | `(45, 11)` | East (`e`) | `working` | Nameplate `Priya \| Engineer` + Pill `● Working` (Green) |
| `emp_008` | Aman Verma | Engineer | `dev_floor` | `(33, 16)` | East (`e`) | `working` | Nameplate `Aman` |
| `emp_009` | Rohit Das | Engineer | `dev_floor` | `(37, 16)` | East (`e`) | `idle` | Nameplate `Rohit` |
| `emp_012` | Ananya Roy | Engineer | `dev_floor` | `(41, 16)` | East (`e`) | `working` | Nameplate `Ananya` |
| `emp_013` | Rahul Sharma | Engineering Intern | `dev_floor` | `(45, 16)` | East (`e`) | `blocked` | Nameplate `Rahul \| Engineer` + Pill `✕ BLOCKED` (Red) + Popover Card |
| `emp_014` | Ishaan Bose | Engineering Intern | `dev_floor` | `(33, 21)` | East (`e`) | `working` | Nameplate `Ishaan` |
| `emp_017` | Nikhil Rao | Engineer | `dev_floor` | `(37, 21)` | East (`e`) | `working` | Nameplate `Nikhil` |
| `emp_018` | Zoya Ahmed | Engineering Intern | `dev_floor` | `(41, 21)` | East (`e`) | `working` | Nameplate `Zoya` |
| `emp_020` | Lakshmi Iyer | Engineer | `dev_floor` | `(45, 21)` | East (`e`) | `idle` | Nameplate `Lakshmi` |
| `emp_019` | Mark Dsouza | DevOps | `devops` | `(6, 17)` | East (`e`) | `working` | Nameplate `Dev \| Mark` |
| `emp_010` | Meera Pillai | Engineer | `meeting_room` | `(12, 30)` | South (`s`) | `meeting` | Attending meeting |
| `emp_011` | Kabir Shah | Engineer | `meeting_room` | `(16, 30)` | South (`s`) | `meeting` | Attending meeting |
| `emp_015` | Tara Nair | Engineering Intern | `meeting_room` | `(12, 34)` | North (`n`) | `meeting` | Attending meeting |
| `emp_016` | Dev Malhotra | Engineering Intern | `meeting_room` | `(16, 34)` | North (`n`) | `meeting` | Attending meeting |

---

## 4. Badge States & Visual Indicators

1. **Working (Green)**:
   - Halo: `#3FCF8E` with opacity `0.8`
   - Pill: `● Working` (green text, `#3FCF8E1F` background, `#3FCF8E` border)
   - Monitor: Screen glows green with alternating cursor/typing block
   - Avatar: Active typing arm movements

2. **Waiting Approval (Amber)**:
   - Halo: `#F2A73B` with pulsing sine-wave opacity (`0.45` to `0.95`)
   - Pill: `● Waiting Approval` (amber text, `#F2A73B1F` background, `#F2A73B` border)
   - Monitor: Screen glows amber

3. **Blocked (Red)**:
   - Halo: `#E5484D` with pulsating glow
   - Pill: `✕ BLOCKED` (red text, `#E5484D1F` background, `#E5484D` border)
   - Monitor: Screen glows red

4. **Anomaly / High Risk (Magenta)**:
   - Halo: `#E668C3` with pulsing glow
   - Pill: `◆ Risk XX` (magenta text, `#E668C31F` background, `#E668C3` border)

5. **Idle / Meeting (Slate / Blue)**:
   - Halo: None or subtle blue for meeting
   - Dimmed nameplate opacity (`0.45`)

---

## 5. Floating Inspection Card (Clickcard / Popover)

When an avatar is clicked or selected (e.g. Rahul):
- **Card Box**:
  - Background: `rgba(13, 20, 32, 0.96)`
  - Border: `1px solid #33455F` (`--line-strong`)
  - Shadow: `0 4px 12px rgba(0, 0, 0, 0.35)`
  - Font: `Silkscreen` / `IBM Plex Mono` / pixel font
- **Card Header**:
  - Icon: Status-colored warning/info triangle (`#F2A73B` for review/waiting, `#E5484D` for blocked)
  - Title: Employee Name (`Rahul`)
  - Subtitle: Role (`Engineering Intern`) + avatar glyph
- **Card Body**:
  - State Label: `WAITING FOR APPROVAL` (or `BLOCKED BY POLICY`)
  - Reason Text: e.g. `Agent attempted production deployment`

---

## 6. Top Bar & Side Panel Specs

- **Header Bar**:
  - Left: Shield logo (`#3D7BFF`)
  - Navigation Tabs:
    - `OFFICE` (Active, underlined with `#3D7BFF`)
    - `LIVE FEED`
    - `APPROVALS` (with counter badge if `pending > 0`)
    - `CONTROL CENTER`
  - Right:
    - Sim Clock (e.g. `09:25`, font Departure Mono / Silkscreen)
    - Speed Toggle Segmented Control: `▶ REAL TIME`, `▶▶ 10×`, `⏸ PAUSE`
    - Connection Dot (Green for live WebSocket)
    - Role Selector dropdown (`Security`, `Manager`, `CEO`, `Engineer`)

- **Right Panel (System Log)**:
  - Width: `340px`
  - Background: `#141E2E` (`--ink-800`) / `#0D1420` (`--ink-900`)
  - Header: Centered `SYSTEM LOG`, tracking `0.12em`
  - Log Entries:
    - `[09:15] Intern Rahul requested 'Fix payment API error'`
    - `[09:20] Codex Agent usage: 184K tokens`
    - `[09:21] Task 'Fix payment...' - Blocked by AGENTSHIELD Gate 2` (bright red `#E5484D` on blocked phrase)
    - `[09:25] Manager Ben review request for Rahul` (amber `#F2A73B`)
