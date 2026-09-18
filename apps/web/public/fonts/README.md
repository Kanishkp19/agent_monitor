# Fonts

`Departure Mono` is self-hosted and **not committed** — it carries the SIL Open
Font License, and the licence text must ship beside it.

Download `DepartureMono-Regular.woff2` from https://departuremono.com and place
it here, alongside its `OFL.txt`. Record it in
`public/assets/office/CREDITS.md` as you add it, not at the end.

Until then the build prints one warning about the unresolved `@font-face` URL
and the pixel face falls back to `Silkscreen`, then `ui-monospace`. Nothing
breaks; the sim clock and the office HUD just look less distinctive.

Archivo and IBM Plex Mono load from Google Fonts in `index.html` and need no
local file.
