# Vendored browser libraries

The exhibition machine may have no network (spec §2), so every runtime
dependency is committed here as a UMD bundle and loaded with a plain `<script>`
tag. No CDN, no bundler, no `npm install` on site.

| File | Package | Version | Global | Licence |
|---|---|---|---|---|
| `cytoscape.min.js` | cytoscape | 3.x | `cytoscape` | MIT |
| `layout-base.js` | layout-base | 2.0.1 | `layoutBase` | MIT |
| `cose-base.js` | cose-base | 2.2.0 | `coseBase` | MIT |
| `cytoscape-fcose.js` | cytoscape-fcose | 2.2.0 | `cytoscapeFcose` | MIT |
| `cytoscape-layout-utilities.js` | cytoscape-layout-utilities | 1.1.1 | `cytoscapeLayoutUtilities` | MIT |

**Load order matters** — these UMD bundles resolve their dependencies off
`window` when there is no module loader, so every page that shows the graph
loads them in exactly this order:
`cytoscape` → `layout-base` → `cose-base` → `cytoscape-fcose` →
`cytoscape-layout-utilities`.

The `cytoscape.use()` registration is NOT repeated per page: classic scripts
run before any module, so `projection.js` registers both extensions once at
import time (`registerLayoutExtensions()`), and a page that forgets a tag gets
a named error instead of a silent fallback to a different layout.

Refresh with `npm pack <package>` and copy `package/<name>.js` out of the
tarball — these are the published UMD builds, not rebuilt here.
