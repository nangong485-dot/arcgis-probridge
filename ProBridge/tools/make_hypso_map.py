"""一条命令出成品图：DEM → 分层设色+晕渲底图 → 按边界裁 → 进 Pro → 排版 → 导出 PNG。

这是把前面手工跑的每一步串起来的"可复制流程"，也顺便当成用法示例。

要用 Pro 自带的 python（要 arcpy）：
    "C:\\Program Files\\ArcGIS\\Pro\\bin\\Python\\envs\\arcgispro-py3\\python.exe" `
        tools\\make_hypso_map.py `
        --dem data\\bj\\bj_dem.tif --boundary data\\bj\\bj_boundary.shp `
        --out out\\bj_hypso_map.png --title "分层设色 · 北京"

前置条件：ArcGIS Pro 已经打开、ProBridge 已加载（127.0.0.1:7788 在听）。
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from make_relief import make_relief          # noqa: E402
from mask_relief import mask_raster          # noqa: E402
from client.probridge import ProBridge       # noqa: E402


def step(msg):
    print(f"[hypso] {msg}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dem", required=True)
    ap.add_argument("--boundary", required=True, help="研究区面要素（用于裁剪和描边）")
    ap.add_argument("--out", required=True, help="导出的 PNG 路径")
    ap.add_argument("--work", default=os.path.join(ROOT, "out"), help="中间文件目录")
    ap.add_argument("--title", default="分层设色 · 研究区")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--map", default=None, help="地图名，默认用当前活动地图")
    ap.add_argument("--layout", default="pb_hypso", help="布局名")
    ap.add_argument("--relief-name", default="pb_relief")
    ap.add_argument("--boundary-name", default="pb_boundary")
    ap.add_argument("--downsample", type=int, default=2, help="1=DEM 原分辨率")
    ap.add_argument("--t-gamma", type=float, default=0.55)
    ap.add_argument("--zfactor", type=float, default=2.0)
    ap.add_argument("--shade-strength", type=float, default=0.15)
    ap.add_argument("--lo-percent", type=float, default=0.5)
    ap.add_argument("--hi-percent", type=float, default=99.8)
    ap.add_argument("--outline", default="#262626")
    ap.add_argument("--outline-width", type=float, default=1.5)
    ap.add_argument("--ratio", type=float, default=0.06, help="图框外扩比例")
    ap.add_argument("--no-mask", action="store_true", help="不按边界裁剪（出矩形图）")
    args = ap.parse_args()

    work = os.path.abspath(args.work)
    os.makedirs(work, exist_ok=True)
    relief_tif = os.path.join(work, "pb_relief_raw.tif")
    final_tif = os.path.join(work, "pb_relief_masked.tif")

    step("1/6 DEM → 分层设色 + 晕渲")
    make_relief(args.dem, relief_tif,
                zfactor=args.zfactor, shade_strength=args.shade_strength,
                lo_pct=args.lo_percent, hi_pct=args.hi_percent,
                downsample=args.downsample, t_gamma=args.t_gamma)

    if args.no_mask:
        final_tif = relief_tif
        step("2/6 跳过裁剪")
    else:
        step("2/6 按边界裁剪")
        mask_raster(relief_tif, args.boundary, final_tif, outside="white")

    pb = ProBridge()
    info = pb.ping()
    if not info.get("project"):
        raise SystemExit("连上了 7788，但 Pro 没有打开工程；先开一个 .aprx")
    step(f"3/6 已连上 Pro：{os.path.basename(info['project'])}")

    pb.clear_layers(prefix="pb_", map_name=args.map)
    pb.add_layer(final_tif, name=args.relief_name, map_name=args.map)
    pb.call("set_symbology", layer=args.relief_name, map_name=args.map,
            kind="raster_rgb", red=0, green=1, blue=2, stretch="none")
    pb.add_layer(os.path.abspath(args.boundary), name=args.boundary_name, map_name=args.map)
    pb.call("set_symbology", layer=args.boundary_name, map_name=args.map,
            kind="feature", fill="none", outline=args.outline,
            width=args.outline_width)
    step("4/6 图层与符号已就位")

    try:
        pb.activate_map(args.map)
    except Exception:
        pass
    pb.fit(args.boundary_name, ratio=args.ratio)

    frames = [{"name": "pb_frame", "map": args.map or "Map",
               "x": 15, "y": 22, "w": 170, "h": 128, "title": args.title}]
    try:
        pb.create_panel_layout(args.layout, 200, 170, frames)
    except Exception as exc:
        step(f"    布局 {args.layout} 已存在，直接复用（{exc}）")
    pb.bind_map_frame(args.layout, map_name=args.map, layer=args.boundary_name,
                      ratio=args.ratio, frame=0)
    step("5/6 布局与图框已绑定")

    out = os.path.abspath(args.out)
    res = pb.export_layout(args.layout, out, dpi=args.dpi, fmt="png")
    step(f"6/6 导出 {out}  {res.get('bytes', '?')} bytes  {args.dpi}dpi")
    print(out)


if __name__ == "__main__":
    main()
