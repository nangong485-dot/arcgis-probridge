"""MCP server for ProBridge.

Exposes the running ArcGIS Pro session as a handful of atomic tools.
Run with any Python 3.10+ that has the `mcp` package installed (do NOT install
into Pro's arcgispro-py3 environment):

    python mcp_server.py
"""

from __future__ import annotations

import os
import sys

from mcp.server.fastmcp import FastMCP

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "client"))
# Relative dataset paths in tool calls then mean the same thing as in the CLI,
# no matter which directory the MCP client launched this server from.
os.chdir(ROOT)

from probridge import ProBridge, ProBridgeError  # noqa: E402

mcp = FastMCP("probridge")


def _bridge() -> ProBridge:
    return ProBridge(
        host=os.environ.get("PROBRIDGE_HOST", "127.0.0.1"),
        port=int(os.environ.get("PROBRIDGE_PORT", "7788")),
    )


def _fail(exc: ProBridgeError) -> dict:
    return {"ok": False, "error": {"code": exc.code, "message": exc.msg}}


@mcp.tool()
def pro_ping() -> dict:
    """Check the bridge: returns the open project, its maps and layouts.

    Call this first. A NO_BRIDGE error means ArcGIS Pro is not running or the
    ProBridge add-in is not loaded.
    """
    try:
        return {"ok": True, "data": _bridge().ping()}
    except ProBridgeError as exc:
        return _fail(exc)


@mcp.tool()
def pro_list_layers(map_name: str | None = None) -> dict:
    """List the layers of the active map (or of `map_name`)."""
    try:
        return {"ok": True, "data": _bridge().list_layers(map_name)}
    except ProBridgeError as exc:
        return _fail(exc)


@mcp.tool()
def pro_add_layer(path: str, name: str | None = None, map_name: str | None = None) -> dict:
    """Add a dataset to the map.

    `path` may be a shapefile, a feature class inside a file geodatabase
    (e.g. D:/data/China_Admin.gdb/Province), or a raster (e.g. D:/data/DEM.tif).
    Prefix `name` with pb_ so `pro_clear_layers` can remove it later.
    """
    try:
        return {"ok": True, "data": _bridge().add_layer(path, name, map_name)}
    except ProBridgeError as exc:
        return _fail(exc)


@mcp.tool()
def pro_fit_layer(layer: str, ratio: float = 0.075, duration_ms: int = 900) -> dict:
    """Zoom the map to a layer, leaving `ratio` margin on every side.

    The extent is expanded on its short side first, so the margin is even
    regardless of the layer's aspect ratio.
    """
    try:
        return {"ok": True, "data": _bridge().fit(layer, ratio, None, duration_ms)}
    except ProBridgeError as exc:
        return _fail(exc)


@mcp.tool()
def pro_zoom_to_extent(xmin: float, ymin: float, xmax: float, ymax: float,
                       duration_ms: int = 900) -> dict:
    """Move the camera to an explicit extent, with an animation duration."""
    try:
        extent = {"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax}
        return {"ok": True, "data": _bridge().zoom_to_extent(extent, duration_ms)}
    except ProBridgeError as exc:
        return _fail(exc)


@mcp.tool()
def pro_clear_layers(prefix: str = "pb_") -> dict:
    """Remove every layer whose name starts with `prefix` (default pb_)."""
    try:
        return {"ok": True, "data": _bridge().clear_layers(prefix)}
    except ProBridgeError as exc:
        return _fail(exc)


@mcp.tool()
def pro_export_layout(name: str, path: str, dpi: int = 300, format: str = "png") -> dict:
    """Export a layout to png / jpg / tiff / pdf at the given dpi."""
    try:
        return {"ok": True, "data": _bridge().export_layout(name, path, dpi, format)}
    except ProBridgeError as exc:
        return _fail(exc)


@mcp.tool()
def pro_list_elements(layout: str) -> dict:
    """List a layout's elements (name, type, text) to find what can be edited."""
    try:
        return {"ok": True, "data": _bridge().list_elements(layout)}
    except ProBridgeError as exc:
        return _fail(exc)


@mcp.tool()
def pro_set_text(layout: str, text: str, name: str | None = None, index: int = 0) -> dict:
    """Replace a text element's content — typically the title.

    Identify the element by `name` (see pro_list_elements) or by `index` among
    text elements (0 is usually the title).
    """
    try:
        return {"ok": True, "data": _bridge().set_text(layout, text, name, index)}
    except ProBridgeError as exc:
        return _fail(exc)


@mcp.tool()
def pro_set_visible(layout: str, name: str, visible: bool = True) -> dict:
    """Show or hide one layout element.

    A4_Landscape.pagx ships two scale bars (miles and kilometres), both visible.
    Hide one with visible=False to get a single-unit scale bar.
    """
    try:
        return {"ok": True, "data": _bridge().set_visible(layout, name, visible)}
    except ProBridgeError as exc:
        return _fail(exc)


@mcp.tool()
def pro_compose(out_path: str, template: str | None = None, layout: str | None = None,
                layers: list | None = None, title: str | None = None,
                hide: list | None = None, dpi: int = 300, ratio: float = 0.075,
                format: str = "png", save: bool = False) -> dict:
    """Produce a finished map in one call.

    Clears pb_ layers, adds `layers` (paths or [path, name] pairs), imports
    `template` (.pagx) if given, binds its map frame to the last layer with an
    even `ratio` margin, hides the elements in `hide`, sets `title`, exports to
    `out_path`.
    """
    try:
        return {"ok": True, "data": _bridge().compose(
            out_path, template=template, layout=layout, layers=layers,
            title=title, hide=hide, dpi=dpi, ratio=ratio, fmt=format, save=save)}
    except ProBridgeError as exc:
        return _fail(exc)


@mcp.tool()
def pro_set_symbology(layer: str, kind: str | None = None, colors: list | None = None,
                      stretch: str | None = None, min_pct: float | None = None,
                      max_pct: float | None = None, std_dev: float | None = None,
                      gamma: float | None = None, invert: bool = False,
                      fill: str | None = None, fill_alpha: float | None = None,
                      outline: str | None = None, width: float | None = None,
                      opacity: float | None = None, red: int | None = None,
                      green: int | None = None, blue: int | None = None,
                      field: str | None = None, classes: int | None = None,
                      method: str | None = None, breaks: list | None = None,
                      min_value: float | None = None, marker: str | None = None,
                      size: float | None = None, halo: str | None = None,
                      halo_size: float | None = None,
                      map_name: str | None = None) -> dict:
    """Rewrite a layer's symbology through CIM (raster ramp/stretch, feature symbol,
    point marker, or a class-breaks choropleth).

    This is the only way to stop Pro re-stretching colours that were already baked
    into a raster — an RGB tif added by path gets a percentile stretch and its
    hypsometric tint turns teal; `stretch="none"` is what the GUI's
    "Stretch type = None" does.

    kind="raster_stretch": `colors` = 2..12 stops "#RRGGBB" low→high,
    `stretch` = none | minmax | percentclip | stddev, plus min_pct / max_pct /
    std_dev / gamma / invert.
    kind="raster_rgb": an already-coloured 3-band tif — pins the RGB colorizer with
    explicit bands 0/1/2 and no stretch, so baked colours survive. Optional
    red/green/blue overrides.
    kind="feature": `fill` = "#RRGGBB" or "none" for a hollow outline, `fill_alpha`,
    `outline`, `width` (points).
    kind="point": `marker` = circle | square | triangle | diamond | cross,
    `size` (points), `fill`, `halo` + `halo_size` (white ring keeps dots readable
    on a dark raster).
    kind="feature_breaks": choropleth — `field` (numeric column), `classes` 2..12,
    `method` = natural (Jenks, best for skewed data) | quantile | equal | manual
    (then pass `breaks`), plus `colors` (2..12 stops, ColorBrewer style), `outline`,
    `width`, `min_value`.

    `opacity` (0-100) works for every kind — that is how a hillshade is laid over a
    hypsometric tint.
    """
    payload = {"layer": layer}
    if map_name:
        payload["map_name"] = map_name
    if kind:
        payload["kind"] = kind
    if colors:
        payload["colors"] = colors
    if stretch:
        payload["stretch"] = stretch
    for value, key in ((min_pct, "min_pct"), (max_pct, "max_pct"), (std_dev, "std_dev"),
                       (gamma, "gamma"), (fill, "fill"), (fill_alpha, "fill_alpha"),
                       (outline, "outline"), (width, "width"), (opacity, "opacity"),
                       (red, "red"), (green, "green"), (blue, "blue"),
                       (field, "field"), (classes, "classes"), (method, "method"),
                       (min_value, "min"), (marker, "marker"), (size, "size"),
                       (halo, "halo"), (halo_size, "halo_size")):
        if value is not None:
            payload[key] = value
    if breaks:
        payload["breaks"] = breaks
    if invert:
        payload["invert"] = True
    try:
        return {"ok": True, "data": _bridge().call("set_symbology", **payload)}
    except ProBridgeError as exc:
        return _fail(exc)


@mcp.tool()
def pro_add_surrounds(layout: str, frame: str | None = None,
                      scale_bar: bool = True, north_arrow: bool = True,
                      legend: bool = True) -> dict:
    """Add the three finishing surrounds to a layout: metric scale bar, north arrow,
    legend.

    The scale bar is drawn by ProBridge itself in kilometres (Pro's native scale bar
    defaults to miles and its unit cannot be changed through the public API on 3.5);
    the legend is restyled to 7 pt with the class-break field name hidden, which is
    what keeps a 5-class choropleth legend readable on a 200x170 mm page.
    """
    payload = {"layout": layout, "scale_bar": scale_bar,
               "north_arrow": north_arrow, "legend": legend}
    if frame:
        payload["frame"] = frame
    try:
        return {"ok": True, "data": _bridge().call("add_surrounds", **payload)}
    except ProBridgeError as exc:
        return _fail(exc)


@mcp.tool()
def pro_open_layout(name: str) -> dict:
    """Switch Pro to the layout view of `name`."""
    try:
        return {"ok": True, "data": _bridge().open_layout(name)}
    except ProBridgeError as exc:
        return _fail(exc)


@mcp.tool()
def pro_import_layout(pagx: str) -> dict:
    """Import a .pagx layout file into the project and return the new layout name."""
    try:
        return {"ok": True, "data": _bridge().import_layout(pagx)}
    except ProBridgeError as exc:
        return _fail(exc)


@mcp.tool()
def pro_activate_map(map_name: str | None = None) -> dict:
    """Bring the map view back to the front.

    Opening a layout pane clears the active map view; call this before
    pro_fit_layer / pro_zoom_to_extent when a layout was opened last.
    """
    try:
        return {"ok": True, "data": _bridge().activate_map(map_name)}
    except ProBridgeError as exc:
        return _fail(exc)


@mcp.tool()
def pro_bind_map_frame(layout: str, map_name: str | None = None,
                       layer: str | None = None, ratio: float = 0.075,
                       frame: int = 0) -> dict:
    """Point a layout's map frame at a map, optionally framing a layer inside it.

    An imported .pagx keeps its own empty map frame, so call this after
    pro_import_layout. Passing `layer` frames that layer with an even margin
    (the extent is grown on its short side to match the frame's aspect first).
    """
    try:
        return {"ok": True, "data": _bridge().bind_map_frame(layout, map_name, layer, ratio, frame)}
    except ProBridgeError as exc:
        return _fail(exc)


@mcp.tool()
def pro_save() -> dict:
    """Save the project so imported layouts and added layers survive a restart."""
    try:
        return {"ok": True, "data": _bridge().save()}
    except ProBridgeError as exc:
        return _fail(exc)


@mcp.tool()
def pro_build_figure(out_path: str, panels: list, name: str = "研究区图",
                     title: str | None = None, dpi: int = 300,
                     format: str = "png", save: bool = False) -> dict:
    """Assemble a multi-panel study-area figure (1a / 1b / 1c) in one call.

    `panels` is a list of dicts, one per panel, in left-to-right order:
        {"map": "Map1b", "layers": ["D:/data/bj_dem_rgb.tif"], "caption": "(b) 高程 (m)"}
    Each panel gets its own map, its own layers, and a map frame on an A4
    landscape page with the caption underneath.
    """
    try:
        return {"ok": True, "data": _bridge().build_figure(
            out_path, panels, name=name, title=title, dpi=dpi, fmt=format, save=save)}
    except ProBridgeError as exc:
        return _fail(exc)


@mcp.tool()
def pro_run_gp(tool: str, params: list | None = None,
               timeout_s: int = 3600, overwrite: bool = False) -> dict:
    """Run any ArcGIS Pro geoprocessing tool in the live session.

    `tool` is the toolbox path, e.g. "analysis.Buffer", "management.Clip",
    "sa.Slope", "analysis.SpatialJoin". `params` are positional values in the
    tool's parameter order: strings for dataset paths and linear units, numbers
    for numeric parameters. Outputs are added to the active map.

    `overwrite=False` makes the tool fail if an output already exists; set it
    to True only when replacing existing data is intended. `timeout_s` also
    cancels the task inside Pro when it expires.

    Example - 1 km buffer around the districts:
        pro_run_gp("analysis.Buffer",
                   ["D:/data/bj_districts_utm.shp", "D:/out/buffer.shp",
                    "1000 Meters"])
    """
    try:
        return {"ok": True, "data": _bridge().run_gp(
            tool, params, timeout_s, overwrite=overwrite)}
    except ProBridgeError as exc:
        return _fail(exc)


@mcp.tool()
def pro_run_arcpy(code: str | None = None, script: str | None = None,
                  args: list | None = None, cwd: str | None = None,
                  timeout_s: int = 600, add_layers: list | None = None,
                  map_name: str | None = None) -> dict:
    """Run an arcpy script in Pro's Python, as a separate process.

    Give either inline `code` or a `script` name (looked up in
    ProBridge/scripts first). This is the escape hatch for analysis that the
    typed tools do not cover. It runs outside the Pro process, so
    arcpy.mp.ArcGISProject("CURRENT") is NOT available; use data paths, or open
    an .aprx by path.

    To put results on the current map, end the script with:
        print("PROBRIDGE_RESULT: " + json.dumps({"layers": ["D:/out/buffer.shp"]}))
    or write the same JSON to os.environ["PROBRIDGE_RESULT"]. `add_layers`
    overrides that list; pass [] to add nothing.

    Inline code example:
        import arcpy
        out = r"D:/out/buffer.shp"
        arcpy.analysis.Buffer(r"D:/data/bj_districts_utm.shp", out, "1000 Meters")
        print("PROBRIDGE_RESULT: " + '{"layers": ["' + out + '"]}')
    """
    try:
        return {"ok": True, "data": _bridge().run_arcpy(
            code=code, script=script, args=args, cwd=cwd,
            timeout_s=timeout_s, add_layers=add_layers, map_name=map_name)}
    except ProBridgeError as exc:
        return _fail(exc)
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": {"code": "ARCPY_ERROR", "message": str(exc)}}


if __name__ == "__main__":
    mcp.run()
