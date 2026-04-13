"""
CoastalCaliforniaLC — Data Audit, Export & Standardization Script
==================================================================
Version  : 5.0
Author   : CoastalCaliforniaLC Project
AI Assist: Claude (Anthropic) + ArcGIS Pro AI Assistant (beta)
Project  : Coastal California Sustainable Initiative Analysis

Root cause found in v5
-----------------------
arcpy.env.addOutputsToMap = False does NOT reliably suppress auto-add
in ArcGIS Pro — the Pro application overrides this environment setting
internally between geoprocessing tool calls. Setting it has no effect.

The only reliable solution is to actively remove layers from the map
by name immediately after every tool call that could add something.
This is done via remove_from_map(), which is called:
  - after every export attempt (temp layers)
  - after Project / Rename (final outputs)
  - inside safe_delete() for cleanup of any stragglers

remove_from_map() matches by exact name AND by checking whether the
layer's dataSource ends with the target name — catching cases where
ArcGIS Pro adds the layer under a display alias that differs from the
feature class name stored on disk.
"""

import arcpy
import os
import uuid
from datetime import datetime

# =============================================================================
# SETTINGS
# =============================================================================
OUTPUT_GDB  = r"C:\arcgis\Projects\CoastalCaliforniaLC\CoastalCaliforniaLC.gdb"
TARGET_WKID = None   # None = inherit from map CRS; e.g. 3310 = CA Albers

# =============================================================================
# SETUP
# =============================================================================
aprx       = arcpy.mp.ArcGISProject("CURRENT")
active_map = aprx.listMaps()[0]
target_sr  = (
    arcpy.SpatialReference(TARGET_WKID)
    if TARGET_WKID
    else active_map.spatialReference
)

arcpy.env.overwriteOutput = True
arcpy.env.workspace       = OUTPUT_GDB

# Note: addOutputsToMap = False is unreliable in ArcGIS Pro —
# the application overrides it. We use remove_from_map() instead.

results = []

print("=" * 65)
print("  CoastalCaliforniaLC — Data Audit v5.0")
print(f"  Target GDB : {OUTPUT_GDB}")
print(f"  Target CRS : {target_sr.name}")
print(f"  Run time   : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 65)


# =============================================================================
# HELPERS
# =============================================================================

def remove_from_map(fc_path: str):
    """
    Remove any map layer whose name or dataSource matches fc_path.
    Called immediately after every tool call that could add a layer.
    Matches on:
      - layer.name == basename of fc_path  (display name match)
      - layer.dataSource ends with basename (path match, catches aliases)
    """
    target_name = os.path.basename(fc_path).lower()
    to_remove = []

    for lyr in active_map.listLayers():
        try:
            lyr_name = lyr.name.lower()
        except Exception:
            continue

        matched = False

        # Match on display name
        if lyr_name == target_name:
            matched = True

        # Match on dataSource path ending
        if not matched:
            try:
                if lyr.supports("DATASOURCE"):
                    ds = lyr.dataSource.lower()
                    if ds.endswith(target_name) or ds.endswith(target_name + ".shp"):
                        matched = True
            except Exception:
                pass

        if matched:
            to_remove.append(lyr)

    for lyr in to_remove:
        try:
            active_map.removeLayer(lyr)
        except Exception:
            pass


def safe_delete(fc_path: str):
    """Remove from map contents then delete from disk. Never raises."""
    remove_from_map(fc_path)
    try:
        if arcpy.Exists(fc_path):
            arcpy.management.Delete(fc_path)
        # Delete also adds to map in some versions — remove again after
        remove_from_map(fc_path)
    except Exception:
        pass


def clean_name(raw: str) -> str:
    """Return a valid ArcGIS feature class name, max 50 chars."""
    cleaned = "".join(c if (c.isalnum() or c == "_") else "_" for c in raw)
    cleaned = cleaned.lstrip("_0123456789")
    return (cleaned or "layer_unnamed")[:50]


def detect_source_type(source: str) -> tuple:
    """
    Returns (label: str, is_exportable: bool).
    is_exportable = False → visual only, never touch the GDB.
    """
    s = source.lower()
    if "mapserver"        in s: return ("Map Service (MapServer) — visual only",  False)
    if "imageserver"      in s: return ("Image Service — visual only",            False)
    if "tiles.arcgis.com" in s: return ("Tile Cache Service — visual only",       False)
    if "wmts"             in s: return ("WMTS Tile Service — visual only",        False)
    if "featureserver"    in s: return ("Feature Service (FeatureServer)",         True)
    if s.endswith(".shp"):      return ("Shapefile",                               True)
    if ".gdb"             in s: return ("File Geodatabase",                        True)
    if ".sde"             in s: return ("Enterprise GDB (SDE)",                    True)
    return ("Unknown / Other",                                                     True)


def get_src_crs(layer) -> str:
    try:
        desc = arcpy.da.Describe(layer.dataSource)
        return desc.get("spatialReference", {}).get("name", "Unknown")
    except Exception:
        return "Unreadable"


def try_export(layer, source: str, temp_path: str) -> tuple:
    """
    Three-strategy export. After each attempt, immediately removes
    any layer the tool auto-added to the map.
    Returns (success: bool, method_label: str).
    """
    temp_dir  = OUTPUT_GDB
    temp_name = os.path.basename(temp_path)

    strategies = [
        ("FeatureClassToFeatureClass (layer object)",
         lambda: arcpy.conversion.FeatureClassToFeatureClass(
             layer, temp_dir, temp_name)),

        ("CopyFeatures (layer object)",
         lambda: arcpy.management.CopyFeatures(
             layer, temp_path)),

        ("FeatureClassToFeatureClass (dataSource string)",
         lambda: arcpy.conversion.FeatureClassToFeatureClass(
             source, temp_dir, temp_name)),
    ]

    for label, fn in strategies:
        safe_delete(temp_path)   # clean before each attempt
        try:
            fn()
            # Immediately remove whatever the tool just added to the map
            remove_from_map(temp_path)
            if arcpy.Exists(temp_path):
                return True, label
        except Exception:
            remove_from_map(temp_path)
            continue

    return False, "all strategies failed"


# =============================================================================
# PROCESS ONE LAYER
# =============================================================================

def process_layer(layer) -> dict:

    rec = {
        "name":        "UNKNOWN",
        "source_type": "—",
        "src_crs":     "—",
        "status":      "Not processed",
        "method":      "—",
        "output":      "—",
        "notes":       "",
    }

    # ── 0. Layer name — must be first; some objects don't support .name ───────
    try:
        rec["name"] = layer.name
    except AttributeError:
        rec["status"] = "Failed"
        rec["notes"]  = (
            "Layer object does not support .name — internal basemap "
            "tile sublayer. Visual only, cannot be exported."
        )
        print("  ❌ Unnamed layer object — internal basemap/tile sublayer")
        return rec

    name = rec["name"]
    print(f"\n{'─' * 65}")
    print(f"  Layer : {name}")

    # ── 1. Group layers — skip, children processed individually ───────────────
    try:
        if layer.isGroupLayer:
            print("  ⏭  Skipped — group layer (children processed individually)")
            rec["status"] = "Skipped"
            rec["notes"]  = "Group layer — children processed individually"
            return rec
    except Exception:
        pass

    # ── 2. DATASOURCE support — primary gate ──────────────────────────────────
    try:
        supports_ds = layer.supports("DATASOURCE")
    except Exception:
        supports_ds = False

    if not supports_ds:
        print("  ❌ Failed — no DATASOURCE support")
        print("     (basemap tile sublayer, MapServer sublayer, or reference layer)")
        rec["status"] = "Failed"
        rec["notes"]  = (
            "Layer does not support the DATASOURCE attribute. "
            "This is a basemap tile sublayer, Living Atlas reference layer, "
            "or internal MapServer sublayer — visual only, cannot be exported. "
            "To use this data for analysis, find a FeatureServer version "
            "or download a local copy from the data provider."
        )
        return rec

    # ── 3. Read dataSource ────────────────────────────────────────────────────
    try:
        source = layer.dataSource
    except Exception as e:
        print(f"  ❌ Failed — dataSource read error: {e}")
        rec["status"] = "Failed"
        rec["notes"]  = f"dataSource attribute threw an exception: {e}"
        return rec

    # ── 4. Classify source type ───────────────────────────────────────────────
    source_type, is_exportable = detect_source_type(source)
    rec["source_type"] = source_type
    print(f"  Type  : {source_type}")
    print(f"  Source: {source[:80]}{'...' if len(source) > 80 else ''}")

    # ── 5. Visual-only — flag immediately, touch nothing ─────────────────────
    if not is_exportable:
        print(f"  ⚠️  Flagged — visual-only, cannot export")
        print("  TIP: Find a FeatureServer equivalent or download a local copy.")
        rec["status"]  = "Flagged — visual only"
        rec["src_crs"] = get_src_crs(layer)
        rec["notes"]   = (
            f"{source_type}. Cannot be exported or used in geoprocessing. "
            "Replace with a FeatureServer equivalent or downloaded local copy "
            "before running spatial analysis."
        )
        return rec

    # ── 6. Must be a feature layer ────────────────────────────────────────────
    try:
        if not layer.isFeatureLayer:
            print("  ⏭  Skipped — has a dataSource but is not a feature layer")
            rec["status"] = "Skipped"
            rec["notes"]  = (
                "Has a readable dataSource but isFeatureLayer = False. "
                "May be a raster, annotation, or network dataset layer."
            )
            return rec
    except Exception:
        print("  ⏭  Skipped — isFeatureLayer unreadable")
        rec["status"] = "Skipped"
        rec["notes"]  = "isFeatureLayer property unreadable"
        return rec

    # ── 7. Source CRS ─────────────────────────────────────────────────────────
    rec["src_crs"] = get_src_crs(layer)
    print(f"  Src CRS : {rec['src_crs']}")
    print(f"  Tgt CRS : {target_sr.name}")

    # ── 8. Duplicate guard ────────────────────────────────────────────────────
    out_name = clean_name(name)
    final_fc = os.path.join(OUTPUT_GDB, out_name)

    if arcpy.Exists(final_fc):
        print(f"  ⏭  Skipped — already exists in GDB: {out_name}")
        print("     Delete from GDB to reprocess.")
        rec["status"] = "Skipped — already in GDB"
        rec["output"] = out_name
        rec["notes"]  = (
            "Output feature class already exists in the GDB. "
            "Delete it first if you want to reprocess this layer."
        )
        return rec

    # ── 9. Export → Project → Cleanup ─────────────────────────────────────────
    temp_name = f"_TEMP_{uuid.uuid4().hex[:8]}"
    temp_path = os.path.join(OUTPUT_GDB, temp_name)

    print("  Exporting...")
    exported, method = try_export(layer, source, temp_path)
    rec["method"] = method

    if not exported:
        safe_delete(temp_path)
        print("  ❌ Failed — all export strategies exhausted")
        rec["status"] = "Failed — export"
        rec["notes"]  = (
            "All three export strategies failed. Check layer permissions "
            "and source availability."
        )
        return rec

    print(f"  ✅ Exported via : {method}")

    # Project or rename
    crs_match = (rec["src_crs"] == target_sr.name)

    try:
        if crs_match:
            arcpy.management.Rename(temp_path, out_name)
            # Rename can add to map — remove immediately
            remove_from_map(final_fc)
            remove_from_map(temp_path)
            print("  ℹ️  CRS matches — rename only, no reprojection needed")
            rec["status"] = "Success — CRS matched"
        else:
            print("  Reprojecting...")
            arcpy.management.Project(temp_path, final_fc, target_sr)
            # Project can add to map — remove immediately
            remove_from_map(final_fc)
            remove_from_map(temp_path)
            print(f"  ✅ Projected → {out_name}")
            rec["status"] = "Success"

        rec["output"] = out_name

    except Exception as e:
        print(f"  ❌ Project/Rename failed: {e}")
        rec["status"] = "Failed — projection"
        rec["notes"]  = str(e)

    finally:
        # Always clean temp from disk and map — unconditionally
        safe_delete(temp_path)

    return rec


# =============================================================================
# RUN
# =============================================================================

for lyr in active_map.listLayers():
    rec = process_layer(lyr)
    results.append(rec)


# =============================================================================
# SUMMARY TABLE
# =============================================================================

print("\n\n" + "=" * 65)
print("  FINAL SUMMARY")
print("=" * 65)

W = {"name": 32, "type": 30, "status": 28, "output": 25}
print(
    f"{'Layer':<{W['name']}}"
    f"{'Source Type':<{W['type']}}"
    f"{'Status':<{W['status']}}"
    f"{'Output FC':<{W['output']}}"
)
print("─" * sum(W.values()))

counts = {"Success": 0, "Skipped": 0, "Flagged": 0, "Failed": 0}

for r in results:
    s = r["status"]
    if   "Success" in s: counts["Success"] += 1
    elif "Skipped" in s: counts["Skipped"] += 1
    elif "Flagged" in s: counts["Flagged"] += 1
    else:                counts["Failed"]  += 1

    print(
        f"{r['name'][:W['name']-1]:<{W['name']}}"
        f"{r['source_type'][:W['type']-1]:<{W['type']}}"
        f"{s[:W['status']-1]:<{W['status']}}"
        f"{r['output'][:W['output']-1]:<{W['output']}}"
    )
    if r["notes"]:
        indent = " " * 4
        words  = r["notes"].split()
        line   = indent + "NOTE: "
        for w in words:
            if len(line) + len(w) + 1 > 84:
                print(line)
                line = indent + "      " + w + " "
            else:
                line += w + " "
        if line.strip():
            print(line)

print("\n" + "─" * sum(W.values()))
print(f"  ✅ Success  : {counts['Success']:>3}  — exported + projected, ready for analysis")
print(f"  ⏭  Skipped  : {counts['Skipped']:>3}  — group layers, already in GDB, non-feature layers")
print(f"  ⚠️  Flagged  : {counts['Flagged']:>3}  — visual-only services (MapServer / tile / image)")
print(f"                       → find FeatureServer versions or download locally")
print(f"  ❌ Failed   : {counts['Failed']:>3}  — no DATASOURCE support, or export/projection error")
print(f"\n  GDB         : {OUTPUT_GDB}")
print(f"  CRS         : {target_sr.name}")
print(f"  Run time    : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 65)
print("\nNext step: run overlay analysis on ✅ Success layers only.")
print("For ⚠️  Flagged / ❌ Failed layers: see notes above.")
