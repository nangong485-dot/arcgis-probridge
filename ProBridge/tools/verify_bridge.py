"""End-to-end self check for ProBridge.

Drives a running ArcGIS Pro through every bridge command in the order a real
task would use them, and prints a PASS/FAIL table.

    python tools/verify_bridge.py

Exit code 0 means every step passed. Pro must be open with smoke.aprx.
"""

from __future__ import annotations

import os
import struct
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "client"))

from probridge import ProBridge, ProBridgeError  # noqa: E402

DEM = os.path.join(ROOT, "data", "smoke", "DEM.tif")
TEMPLATE = os.path.join(ROOT, "templates", "A4_Landscape.pagx")
OUT = os.path.join(ROOT, "out", "verify_flow.png")
GP_OUT = os.path.join(ROOT, "out", "verify_gp.tif")

results: list[tuple[str, bool, str]] = []


def step(name, fn):
    try:
        detail = fn()
        results.append((name, True, detail))
    except (ProBridgeError, AssertionError, KeyError, OSError) as exc:
        results.append((name, False, str(exc)))
        raise SystemExit(report())


def png_size(path):
    with open(path, "rb") as fh:
        head = fh.read(24)
    return struct.unpack(">II", head[16:24])


def main() -> int:
    b = ProBridge()
    state = {}

    step("ping", lambda: _check_project(b, state))
    step("activate_map_initial", lambda: _activate_startup(b))
    step("clear_layers", lambda: f"removed {b.clear_layers('pb_')['removed']}")
    step("add_layer", lambda: f"added {b.add_layer(DEM, 'pb_dem')['name']}")
    step("list_layers", lambda: _check_layer(b))
    step("get_layer_extent", lambda: _check_extent(b, state))
    step("zoom_to_extent", lambda: f"zoomed {b.fit('pb_dem', ratio=0.075)['zoomed']}")
    step("refresh", lambda: f"redrawn {b.refresh()['refreshed']}")
    step("import_layout", lambda: _ensure_layout(b))
    step("bind_map_frame", lambda: _bind(b))
    step("open_layout", lambda: f"opened {b.open_layout('A4 Landscape')['opened']}")
    step("activate_map", lambda: f"back to {b.activate_map()['activated']}")
    step("export_layout", lambda: _export(b))
    step("save", lambda: f"saved {b.save()['saved']}")
    step("remove_layer", lambda: f"removed {b.remove_layer('pb_dem')['removed']}")
    step("run_gp", lambda: _run_gp(b))
    step("run_arcpy", lambda: _run_arcpy(b))
    step("debug_threads", lambda: _check_threads(b))

    return report()


def _check_project(b, state):
    # The socket can be listening before Pro has finished opening the project.
    info = b.ping()
    for _ in range(30):
        if info.get("project"):
            break
        time.sleep(1)
        info = b.ping()
    assert info["project"], "no project open"
    state["maps"] = info["maps"]
    return f"{info['project']} maps={info['maps']} layouts={info['layouts']}"


def _activate_startup(b):
    """The socket opens before Pro's UI is ready; retry the first pane creation."""
    last = None
    for _ in range(10):
        try:
            return f"back to {b.activate_map('Map')['activated']}"
        except ProBridgeError as exc:
            last = exc
            time.sleep(1)
    raise last


def _check_layer(b):
    names = [l["name"] for l in b.list_layers()]
    assert "pb_dem" in names, f"pb_dem missing from {names}"
    return f"layers={names}"


def _check_extent(b, state):
    env = b.layer_extent("pb_dem")
    assert env["wkid"] == 4326, f"unexpected wkid {env['wkid']}"
    state["env"] = env
    return f"{env['xmin']:.3f},{env['ymin']:.3f} -> {env['xmax']:.3f},{env['ymax']:.3f}"


def _ensure_layout(b):
    names = b.ping()["layouts"] or []
    if "A4 Landscape" in names:
        return "already imported"
    return f"imported {b.import_layout(TEMPLATE)['name']}"


def _bind(b):
    out = b.bind_map_frame("A4 Landscape", layer="pb_dem", ratio=0.06)
    return f"frame {out['frame']}/{out['frames']} -> map {out['map']}"


def _export(b):
    b.export_layout("A4 Landscape", OUT, dpi=200)
    w, h = png_size(OUT)
    assert w > 1000 and h > 700, f"suspicious size {w}x{h}"
    return f"{os.path.basename(OUT)} {w}x{h} {os.path.getsize(OUT)} bytes"


def _run_gp(b):
    result = b.run_gp("sa.Slope", [DEM, GP_OUT, "DEGREE"], overwrite=True)
    assert result["succeeded"], result.get("errorMessages")
    names = [layer["name"] for layer in b.list_layers()]
    assert {"verify_gp.tif", "verify_gp"} & set(names), \
        f"GP output not added to the map: {names}"
    b.remove_layer("verify_gp.tif" if "verify_gp.tif" in names else "verify_gp")
    return f"verify_gp.tif {os.path.getsize(GP_OUT)} bytes, added to map"


def _run_arcpy(b):
    result = b.run_arcpy(script="diagnose.py", add_layers=[])
    assert result["success"], result["stderr"]
    info = result["result"]
    return f"arcpy {info.get('arcpy')} {info.get('license')} python {info.get('python')}"


def _check_threads(b):
    t = b.call("debug_threads")
    assert t["same"] is False, "bridge handler is running on the UI thread"
    assert t["error"] is None, f"UI thread error: {t['error']}"
    return f"bg={t['background']} ui={t['ui']} layouts={t['layoutsOnUi']}"


def report() -> int:
    width = max(len(n) for n, _, _ in results) + 2
    print()
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name:<{width}} {detail}")
    failed = [n for n, ok, _ in results if not ok]
    print()
    print(f"  {len(results) - len(failed)}/{len(results)} passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
