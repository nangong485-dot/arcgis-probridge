"""Command line front end for ProBridge, mainly for debugging.

  python client/cli.py ping
  python client/cli.py add-layer data/smoke/smoke.gdb/Province --name pb_prov
  python client/cli.py fit pb_prov --ratio 0.075
  python client/cli.py export "Layout" out/test.png --dpi 300
"""

from __future__ import annotations

import argparse
import json
import sys

from probridge import ProBridge, ProBridgeError


def dump(value):
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _coerce(value: str):
    """Turn "30", "true", "null" into JSON scalars; leave paths and units alone."""
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def main(argv=None):
    parser = argparse.ArgumentParser(prog="cli.py")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7788)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ping")
    sub.add_parser("layers")
    sub.add_parser("refresh")
    sub.add_parser("debug-threads")
    sub.add_parser("save")
    sub.add_parser("show-agent")

    p = sub.add_parser("activate-map")
    p.add_argument("--map", dest="map_name", default=None)

    p = sub.add_parser("add-layer")
    p.add_argument("path")
    p.add_argument("--name", default=None)
    p.add_argument("--map", dest="map_name", default=None)

    p = sub.add_parser("remove-layer")
    p.add_argument("name")

    p = sub.add_parser("clear")
    p.add_argument("--prefix", default="pb_")

    p = sub.add_parser("extent")
    p.add_argument("layer")

    p = sub.add_parser("fit")
    p.add_argument("layer")
    p.add_argument("--ratio", type=float, default=0.075)
    p.add_argument("--aspect", type=float, default=None)
    p.add_argument("--duration", type=int, default=800)

    p = sub.add_parser("import-layout")
    p.add_argument("pagx")

    p = sub.add_parser("open-layout")
    p.add_argument("name")

    p = sub.add_parser("export")
    p.add_argument("name")
    p.add_argument("path")
    p.add_argument("--dpi", type=int, default=300)
    p.add_argument("--format", default="png", choices=["png", "jpg", "tiff", "pdf"])

    p = sub.add_parser("elements")
    p.add_argument("layout")

    p = sub.add_parser("set-text")
    p.add_argument("layout")
    p.add_argument("text")
    p.add_argument("--name", default=None)
    p.add_argument("--index", type=int, default=0)

    p = sub.add_parser("set-visible")
    p.add_argument("layout")
    p.add_argument("name")
    p.add_argument("--off", action="store_true")

    p = sub.add_parser("compose")
    p.add_argument("out")
    p.add_argument("--template", default=None)
    p.add_argument("--layout", default=None)
    p.add_argument("--layer", action="append", default=[])
    p.add_argument("--title", default=None)
    p.add_argument("--hide", action="append", default=[])
    p.add_argument("--dpi", type=int, default=300)
    p.add_argument("--ratio", type=float, default=0.075)
    p.add_argument("--format", default="png", choices=["png", "jpg", "tiff", "pdf"])
    p.add_argument("--save", action="store_true")

    p = sub.add_parser("bind-frame")
    p.add_argument("layout")
    p.add_argument("--map", dest="map_name", default=None)
    p.add_argument("--layer", default=None)
    p.add_argument("--ratio", type=float, default=0.075)
    p.add_argument("--frame", type=int, default=0)

    p = sub.add_parser("symbology")
    p.add_argument("layer")
    p.add_argument("--kind", default=None,
                   choices=["raster_stretch", "raster_rgb", "feature", "feature_breaks", "point"])
    p.add_argument("--colors", nargs="+", default=[], metavar="#RRGGBB",
                   help="colour ramp stops, low to high")
    p.add_argument("--stretch", default=None,
                   choices=["none", "minmax", "percentclip", "stddev"])
    p.add_argument("--min-pct", type=float, default=None)
    p.add_argument("--max-pct", type=float, default=None)
    p.add_argument("--std-dev", type=float, default=None)
    p.add_argument("--gamma", type=float, default=None)
    p.add_argument("--invert", action="store_true")
    p.add_argument("--fill", default=None, help="#RRGGBB or none (hollow)")
    p.add_argument("--fill-alpha", type=float, default=None)
    p.add_argument("--outline", default=None, help="#RRGGBB")
    p.add_argument("--width", type=float, default=None, help="outline width in points")
    p.add_argument("--opacity", type=float, default=None,
                   help="0-100, 100 = opaque (use for hillshade overlays)")
    p.add_argument("--red", type=int, default=None)
    p.add_argument("--green", type=int, default=None)
    p.add_argument("--blue", type=int, default=None)
    p.add_argument("--field", default=None, help="numeric field for feature_breaks")
    p.add_argument("--classes", type=int, default=None, help="number of classes (2-12)")
    p.add_argument("--method", default=None,
                   choices=["natural", "quantile", "equal", "manual"],
                   help="classification method for feature_breaks")
    p.add_argument("--breaks", nargs="+", type=float, default=None,
                   help="explicit upper bounds (method=manual)")
    p.add_argument("--min-value", type=float, default=None,
                   help="lower bound of the first class (feature_breaks)")
    p.add_argument("--marker", default=None,
                   choices=["circle", "square", "triangle", "diamond", "cross"],
                   help="point symbol shape")
    p.add_argument("--size", type=float, default=None, help="point symbol size in points")
    p.add_argument("--halo", default=None, help="#RRGGBB or none (halo behind markers)")
    p.add_argument("--halo-size", type=float, default=None)
    p.add_argument("--map", dest="map_name", default=None)

    p = sub.add_parser("surrounds")
    p.add_argument("layout")
    p.add_argument("--frame", default=None, help="map frame element name (default: first)")
    p.add_argument("--no-scale-bar", dest="scale_bar", action="store_false")
    p.add_argument("--no-north-arrow", dest="north_arrow", action="store_false")
    p.add_argument("--no-legend", dest="legend", action="store_false")
    p.add_argument("--scale-style", default=None)
    p.add_argument("--arrow-style", default=None)
    p.add_argument("--scale-x", type=float, default=None)
    p.add_argument("--scale-y", type=float, default=None)
    p.add_argument("--scale-width", type=float, default=None)
    p.add_argument("--arrow-x", type=float, default=None)
    p.add_argument("--arrow-y", type=float, default=None)
    p.add_argument("--arrow-height", type=float, default=None)
    p.add_argument("--legend-x", type=float, default=None)
    p.add_argument("--legend-y", type=float, default=None)
    p.add_argument("--legend-w", type=float, default=None)
    p.add_argument("--legend-h", type=float, default=None)
    p.add_argument("--scale-height", type=float, default=None,
                   help="自绘比例尺条高（mm，默认 1.6）")
    p.add_argument("--scale-divisions", type=int, default=None,
                   help="自绘比例尺分段数（默认 4）")
    p.add_argument("--legend-font", type=float, default=None,
                   help="图例正文字号（pt，默认 7）")
    p.add_argument("--legend-name-font", type=float, default=None,
                   help="图例图层名字号（pt，默认 7.5）")
    p.add_argument("--legend-title", action="store_true",
                   help="显示图例标题")

    p = sub.add_parser("run-gp")
    p.add_argument("tool")
    p.add_argument("params", nargs="*", help="positional tool parameters")
    p.add_argument("--timeout", type=float, default=3600)
    p.add_argument("--overwrite", action="store_true",
                   help="replace existing outputs (default: fail if output exists)")

    p = sub.add_parser("run-arcpy")
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--code", help="inline arcpy code")
    source.add_argument("--script", help="script name in ProBridge/scripts or a path")
    p.add_argument("--arg", action="append", default=[], help="script argument")
    p.add_argument("--cwd", default=None)
    p.add_argument("--timeout", type=float, default=600)
    p.add_argument("--add-layer", action="append", default=[],
                   help="layer to add after the run; overrides PROBRIDGE_RESULT")
    p.add_argument("--no-add", action="store_true",
                   help="do not add the layers listed in PROBRIDGE_RESULT")
    p.add_argument("--map", dest="map_name", default=None)

    args = parser.parse_args(argv)
    bridge = ProBridge(args.host, args.port)

    try:
        if args.cmd == "ping":
            dump(bridge.ping())
        elif args.cmd == "layers":
            dump(bridge.list_layers())
        elif args.cmd == "refresh":
            dump(bridge.refresh())
        elif args.cmd == "debug-threads":
            dump(bridge.call("debug_threads"))
        elif args.cmd == "save":
            dump(bridge.save())
        elif args.cmd == "show-agent":
            dump(bridge.call("show_agent"))
        elif args.cmd == "activate-map":
            dump(bridge.activate_map(args.map_name))
        elif args.cmd == "add-layer":
            dump(bridge.add_layer(args.path, args.name, args.map_name))
        elif args.cmd == "remove-layer":
            dump(bridge.remove_layer(args.name))
        elif args.cmd == "clear":
            dump(bridge.clear_layers(args.prefix))
        elif args.cmd == "extent":
            dump(bridge.layer_extent(args.layer))
        elif args.cmd == "fit":
            dump(bridge.fit(args.layer, args.ratio, args.aspect, args.duration))
        elif args.cmd == "import-layout":
            dump(bridge.import_layout(args.pagx))
        elif args.cmd == "open-layout":
            dump(bridge.open_layout(args.name))
        elif args.cmd == "export":
            dump(bridge.export_layout(args.name, args.path, args.dpi, args.format))
        elif args.cmd == "elements":
            dump(bridge.list_elements(args.layout))
        elif args.cmd == "set-text":
            dump(bridge.set_text(args.layout, args.text, args.name, args.index))
        elif args.cmd == "set-visible":
            dump(bridge.set_visible(args.layout, args.name, not args.off))
        elif args.cmd == "compose":
            dump(bridge.compose(args.out, template=args.template, layout=args.layout,
                                layers=args.layer, title=args.title, hide=args.hide,
                                dpi=args.dpi, ratio=args.ratio, fmt=args.format,
                                save=args.save))
        elif args.cmd == "bind-frame":
            dump(bridge.bind_map_frame(args.layout, args.map_name, args.layer,
                                       args.ratio, args.frame))
        elif args.cmd == "symbology":
            payload = {"layer": args.layer}
            if args.map_name:
                payload["map_name"] = args.map_name
            if args.kind:
                payload["kind"] = args.kind
            if args.colors:
                payload["colors"] = args.colors
            if args.stretch:
                payload["stretch"] = args.stretch
            for src, dst in ((args.min_pct, "min_pct"), (args.max_pct, "max_pct"),
                             (args.std_dev, "std_dev"), (args.gamma, "gamma"),
                             (args.fill, "fill"), (args.fill_alpha, "fill_alpha"),
                             (args.outline, "outline"), (args.width, "width"),
                             (args.opacity, "opacity"), (args.red, "red"),
                             (args.green, "green"), (args.blue, "blue"),
                             (args.field, "field"), (args.classes, "classes"),
                             (args.method, "method"), (args.breaks, "breaks"),
                             (args.min_value, "min"), (args.marker, "marker"),
                             (args.size, "size"), (args.halo, "halo"),
                             (args.halo_size, "halo_size")):
                if src is not None:
                    payload[dst] = src
            if args.invert:
                payload["invert"] = True
            dump(bridge.call("set_symbology", **payload))
        elif args.cmd == "surrounds":
            payload = {"layout": args.layout,
                       "scale_bar": args.scale_bar,
                       "north_arrow": args.north_arrow,
                       "legend": args.legend}
            for src, dst in ((args.frame, "frame"), (args.scale_style, "scale_style"),
                             (args.arrow_style, "arrow_style"),
                             (args.scale_x, "scale_x"), (args.scale_y, "scale_y"),
                             (args.scale_width, "scale_width"),
                             (args.arrow_x, "arrow_x"), (args.arrow_y, "arrow_y"),
                             (args.arrow_height, "arrow_height"),
                             (args.legend_x, "legend_x"), (args.legend_y, "legend_y"),
                             (args.legend_w, "legend_w"), (args.legend_h, "legend_h")):
                if src is not None:
                    payload[dst] = src
            dump(bridge.call("add_surrounds", **payload))
        elif args.cmd == "run-gp":
            params = [_coerce(v) for v in args.params]
            result = bridge.run_gp(args.tool, params, args.timeout,
                                   overwrite=args.overwrite)
            dump(result)
            return 0 if result.get("succeeded") else 1
        elif args.cmd == "run-arcpy":
            if args.no_add:
                add_layers = []
            else:
                add_layers = args.add_layer or None
            result = bridge.run_arcpy(
                code=args.code, script=args.script, args=args.arg,
                cwd=args.cwd, timeout_s=args.timeout,
                add_layers=add_layers, map_name=args.map_name)
            dump(result)
            return 0 if result.get("success") else 1
    except ProBridgeError as exc:
        print(f"ERROR {exc.code}: {exc.msg}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
