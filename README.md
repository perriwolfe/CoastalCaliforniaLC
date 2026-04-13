# CoastalCaliforniaLC

**Coastal California Sustainable Initiative — Spatial Analysis Project**

A GeoAI-assisted spatial analysis identifying where predicted coastal erosion and sea level rise exposure intersect with California drinking water system vulnerability. Built using ArcGIS Pro, ArcPy, and AI agents (Claude + ArcGIS Pro AI Assistant beta) as a portfolio deliverable for a Masters in Business Innovation with a creative business focus.

---

## Project Goal

To map the geographic overlap between:
- **Coastal erosion and sea level rise risk** (CNRA predicted erosion, NOAA SLR inundation at 1ft / 3ft / 6ft)
- **Drinking water system vulnerability** (CA State Water Board service area boundaries)

The question driving the analysis: *where does the coastline becoming less stable make the water supply less safe — and who is living there when it does?*

---

## Repository Structure

```
CoastalCaliforniaLC/
├── README.md                        ← this file
├── .gitignore                       ← excludes GDB files, credentials, temp data
├── data_audit.py                    ← Step 2: data audit, export & standardization
├── overlay_analysis.py              ← Step 4: spatial join + intersect analysis (coming)
├── arcade_expressions.md            ← Pop-up and label expressions for ArcGIS Pro
├── /data
│   └── sources.md                   ← all dataset URLs, access dates, licenses
└── /outputs
    ├── risk_score_map.png            ← exported map (added after Step 5)
    └── slr_intersection_summary.csv ← summary table from overlay analysis
```

---

## Datasets

| ID  | Dataset | Source | Type | Status |
|-----|---------|--------|------|--------|
| CE1 | Predicted Coastal Erosion | CA Natural Resources Agency (CNRA) | REST MapServer | ✅ In GDB |
| CE2 | CSMW Sea Level Rise Impacts | CNRA / OPC | REST MapServer | ✅ In project |
| CE4 | NOAA SLR Inundation 1ft/3ft/6ft | ArcGIS Living Atlas / NOAA OCM | REST MapServer | ✅ In project |
| WA1 | CA Drinking Water System Boundaries | CA State Water Resources Control Board | Shapefile → GDB | ✅ In GDB |

---

## Scripts

### `data_audit.py`

**Purpose:** Standardizes all map layers in an ArcGIS Pro project for spatial analysis.

**What it does:**
1. Iterates every layer in the active map
2. Detects source type: Feature Service, Map Service, Shapefile, GDB, SDE
3. Flags Map Services and Image Services as visual-only (cannot be exported)
4. Exports exportable layers to the local GDB using a three-strategy fallback chain
5. Reprojects all outputs to match the map coordinate system
6. Cleans up all temporary files — no orphaned `_raw` copies left in the GDB
7. Prints a structured summary table with per-layer status

**Key fixes in v4 (current):**
- `arcpy.env.addOutputsToMap = False` — prevents ArcGIS Pro from auto-adding any output to the map contents pane during the run
- `safe_delete()` explicitly removes matching layers from the map contents pane before deleting from disk — cleans up orphans from previous runs
- `supports('DATASOURCE')` used as the primary gate — MapServer sublayers correctly appear as **Failed** in the summary, not silently skipped
- `uuid`-based temp names prevent naming collisions
- `finally` block guarantees temp cleanup whether export/projection succeeds or fails
- Unnamed layer objects (basemap internals) caught before `.name` crash kills the loop

**AI agents used:**
- Claude (Anthropic) — script generation, debugging, and iteration
- ArcGIS Pro AI Assistant (beta) — in-Pro guidance on tool selection and parameter setting
- ArcGIS Notebooks Assistant (beta) — in-notebook troubleshooting

**Run inside ArcGIS Pro Notebook:**
```python
# Open a Notebook in your CoastalCaliforniaLC project
# Paste or import data_audit.py and run
# Output will print to the Notebook console
```

**Requirements:**
- ArcGIS Pro 3.x with active project open
- ArcPy (included with ArcGIS Pro)
- Active map with layers loaded
- Write access to `CoastalCaliforniaLC.gdb`

---

## AI Agent Workflow

This project is built as a deliberate test of AI-assisted GIS workflows:

| Agent | Role |
|-------|------|
| **Claude (Anthropic)** | Script generation, debugging, README writing, LinkedIn posts |
| **ArcGIS Pro AI Assistant (beta)** | In-Pro tool navigation, parameter guidance, symbolization |
| **ArcGIS Notebooks Assistant (beta)** | In-notebook code explanation and error troubleshooting |
| **ArcGIS StoryMaps Assistant (beta)** | Narrative refinement for final public output |
| **ArcGIS Item Details Assistant** | Auto-generated metadata for published layers |

---

## Analysis Steps (in progress)

- [x] Step 1 — Data acquisition (4 datasets in GDB)
- [x] Step 2 — Data audit + projection standardization (`data_audit.py`)
- [ ] Step 3 — Clip all layers to coastal California study area
- [ ] Step 4 — Spatial overlay analysis (erosion × water systems, SLR × water systems, risk score)
- [ ] Step 5 — Symbolize and publish to ArcGIS Online
- [ ] Step 6 — Build ArcGIS StoryMap
- [ ] Step 7 — This repo complete + linked from StoryMap

---

## Key Learnings (Day 2 notes)

Working with mixed data types — live map services alongside local shapefiles and GDB layers — exposes a real friction point in GIS workflows. Map services stream visual data but resist export; the audit script learned to detect and flag these early rather than fail silently mid-process.

The same data-readiness problem appears across industries. In real estate reporting, for example, assembling zoning data, parcel records, and market data from different portals and formats requires the same kind of standardization pipeline this script is building toward.

The goal is not just to fix this project — it is to develop a reusable pattern for AI-assisted data ingestion that can be adapted to any multi-source spatial workflow.

---

## Contact

Built as a portfolio project for a Masters in Business Innovation (Creative Business focus).
Documenting the process publicly on LinkedIn.

---

## License

Analysis and scripts: MIT License
Dataset licenses: see `/data/sources.md` — all datasets are public domain or CC BY
