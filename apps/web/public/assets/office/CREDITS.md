# Asset credits

Every shipped asset needs a source, an author, a licence and a URL recorded
here **as it is added**, not at the end. A hackathon is not a licence
exemption.

## Currently shipped

| File | Source | Author | Licence |
|---|---|---|---|
| `rooms/*.png` | generated via Nano Banana (Gemini Image Model), then warped to the canonical 64x32 projection by `infra/scripts/normalize_rooms.py` | AgentShield / Google DeepMind | project-owned |
| `characters/atlas.png` + `atlas.json` | procedural pixel-art generator (walk/idle/type/sit, 4 facings, outlines + accessories) | `infra/scripts/make_character_atlas.py` | project-owned |
| `characters/*.png` (single-pose fallbacks) | procedural | `infra/scripts/make_placeholder_atlas.py` | project-owned |
| `meeting_crop_grid.png`, `seats.html`, `crop.html`, `calibrate.html` | dev-only calibration artifacts | `infra/scripts/extract_furniture.py` / harness pages | project-owned, not shipped UI |

Originals of the room art (pre-warp) are kept in `office/rooms_original/` —
`normalize_rooms.py` re-derives `rooms/*.png` from them, so never edit the
normalized PNGs by hand.

The 5 office rooms (`ceo_office`, `managers`, `dev_floor`, `devops`, `meeting_room`)
are pre-rendered 2:1 isometric cutaway diorama PNGs with transparent outer voids,
generated via Nano Banana and composited directly onto the canvas.

## Fonts

| Font | Use | Licence |
|---|---|---|
| Archivo | console chrome | OFL, via Google Fonts |
| IBM Plex Mono | data, numbers, ids | OFL, via Google Fonts |
| Departure Mono | sim clock and office HUD only | OFL, self-hosted — see `public/fonts/README.md` |

## If you swap in real art

Options, from safest to closest-to-the-reference:

| Route | Licence | Notes |
|---|---|---|
| **Kenney** (`kenney.nl`) — Isometric Miniature Library, Isometric City, Tiny Town | CC0, no attribution required | Safest default. Cleaner and less detailed than the reference; accept that. |
| **OpenGameArt**, filtered to CC0 / CC-BY | varies per asset — check each | CC-BY needs attribution recorded here. |
| **itch.io interior packs** (e.g. LimeZu *Modern Interiors*) | commercial, paid | Closest to the reference look. Buy the licence and record it here. |
| Commission or generate your own | yours | Slowest, fully safe, exactly the rooms you need. |

Whichever route: add the row to the table above in the same commit that adds
the file.
