# Asset credits

Every shipped asset needs a source, an author, a licence and a URL recorded
here **as it is added**, not at the end. A hackathon is not a licence
exemption.

## Currently shipped

| File | Source | Author | Licence |
|---|---|---|---|
| `tileset.png` | generated | `infra/scripts/make_placeholder_atlas.py` | project-owned |
| `characters.png` | generated | `infra/scripts/make_placeholder_atlas.py` | project-owned |
| `office-map.json` | hand-written | this project | project-owned |

The placeholder atlas is flat-coloured diamonds and blocky figures in the
console's own ink palette. It is deliberately the *first* thing built in the
visual phase: everything in the scene works against it, so the office is never
blocked on an art decision, and real art drops in by replacing two PNGs and
their JSON with zero code change.

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
