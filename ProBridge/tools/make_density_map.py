"""密度图：把分类栅格里的某一类，算成"建成密度"这样的连续分布面。

流程：分类栅格 → 只要目标类（Con）→ 聚合成较粗的"占比"格 → 移动窗口平滑 → 密度栅格
→ 进 Pro 上连续色带 → 排版 → 导出 PNG。整条链不需要重编译 addin，只用现有 verb。

用法（要用 Pro 自带 python，要 arcpy + Spatial Analyst）：
    & 'C:\\Program Files\\ArcGIS\\Pro\\bin\\Python\\envs\\arcgispro-py3\\python.exe' `
        tools\\make_density_map.py --raster data\\bj\\bj_lucc.tif --class-value 50 `
        --boundary data\\bj\\bj_boundary.shp --out out\\bj_builtup_density.png `
        --title "建设用地密度 · 北京"

ESA WorldCover 类别：10 林地 20 灌丛 30 草地 40 耕地 50 建成区 60 裸地 80 水体 90 湿地

内存坑：Aggregate 的倍数别开小。10 m 底图有 1.7 万×1.8 万像元（3.2 亿格），
`--agg 5` 会在 Aggregate 里直接访问越界崩掉（exit -1073741819）；用 `--agg 50`
（500 m 粗格）稳定。
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from client.probridge import ProBridge       # noqa: E402

DEFAULT_COLORS = ["#FFFFB2", "#FED976", "#FEB24C", "#FD8D3C",
                  "#FC4E2A", "#E31A1C", "#B10026"]


def step(msg):
    print(f"[density] {msg}", flush=True)


def build_density(raster, class_value, out_tif, boundary=None, agg=50, window=5):
    """分类栅格 → 目标类占比 → 移动窗口平滑的密度栅格（0~1，区外 NoData）。"""
    import arcpy
    from arcpy.sa import Con, FocalStatistics, NbrRectangle, Aggregate, ExtractByMask
    from arcpy.sa import Raster as SaRaster

    arcpy.CheckOutExtension("Spatial")
    arcpy.env.overwriteOutput = True

    src = SaRaster(raster)
    # 目标类 = 1，其它 = 0
    mask = Con(src == class_value, 1, 0)
    # 按 agg×agg 求平均 → 每个粗格里"该类占多大比例"
    agg_r = Aggregate(mask, agg, "MEAN")
    # 再平滑一次，抹掉格网痕迹，读起来才像"密度"
    focal = FocalStatistics(agg_r, NbrRectangle(window, window, "CELL"), "MEAN")
    # 注意：这里不能走 tools/mask_relief.py —— 那是给 8bit RGB 底图用的，
    # 对浮点单波段做 PIL 转换会变成乱码色（外面一片深红）。粗格只有几百像素，
    # 直接用 ExtractByMask 让区外变 NoData，Pro 那边自然透出白底。
    if boundary:
        focal = ExtractByMask(focal, boundary)
    focal.save(out_tif)
    # 不要在这里 CheckInExtension：实测这一步会让进程以 0xC0000005 直接崩掉
    # （输出文件已经写好了，但脚本后面的步骤再也跑不到）。让它随进程退出自然释放。
    return out_tif


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raster", required=True, help="分类栅格（整数类别）")
    ap.add_argument("--class-value", type=int, required=True, help="要统计的类别值")
    ap.add_argument("--boundary", default=None, help="研究区面要素，给了就裁+描边")
    ap.add_argument("--out", required=True)
    ap.add_argument("--work", default=os.path.join(ROOT, "out"))
    ap.add_argument("--title", default="密度图")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--agg", type=int, default=50,
                    help="聚合倍数，50=把 10m 并成 500m（太小会崩，见文件头）")
    ap.add_argument("--window", type=int, default=5, help="平滑窗口（粗格数）")
    ap.add_argument("--stretch", default="minmax",
                    choices=["none", "minmax", "percentclip", "stddev"])
    ap.add_argument("--min-pct", type=float, default=2.0)
    ap.add_argument("--max-pct", type=float, default=98.0)
    ap.add_argument("--colors", nargs="*", default=DEFAULT_COLORS)
    ap.add_argument("--layout", default="pb_density")
    ap.add_argument("--opacity", type=float, default=None, help="0~100，合并底图时用")
    args = ap.parse_args()

    work = os.path.abspath(args.work)
    os.makedirs(work, exist_ok=True)
    final = os.path.join(work, f"pb_density_{args.class_value}.tif")
    bnd = os.path.abspath(args.boundary) if args.boundary else None

    step("1/5 分类栅格 → 密度栅格")
    build_density(os.path.abspath(args.raster), args.class_value, final,
                  boundary=bnd, agg=args.agg, window=args.window)
    step(f"    密度栅格：{final}")

    pb = ProBridge()
    info = pb.ping()
    if not info.get("project"):
        raise SystemExit("连上了 7788，但 Pro 没打开工程")
    step(f"2/5 已连上 Pro：{os.path.basename(info['project'])}")

    pb.clear_layers(prefix="pb_")
    pb.add_layer(final, name="pb_density")
    pb.call("set_symbology", layer="pb_density", kind="raster_stretch",
            stretch=args.stretch, min_pct=args.min_pct, max_pct=args.max_pct,
            colors=args.colors, opacity=args.opacity)
    if args.boundary:
        pb.add_layer(os.path.abspath(args.boundary), name="pb_boundary")
        pb.call("set_symbology", layer="pb_boundary", kind="feature",
                fill="none", outline="#262626", width=1.2)
    try:
        pb.activate_map()
    except Exception:
        pass
    pb.fit("pb_boundary" if args.boundary else "pb_density", ratio=0.06)
    step("3/5 图层与色带已就位")

    frames = [{"name": "pb_frame", "map": "Map", "x": 15, "y": 22,
               "w": 170, "h": 128, "title": args.title}]
    try:
        pb.create_panel_layout(args.layout, 200, 170, frames)
    except Exception as exc:
        step(f"    布局 {args.layout} 已存在，复用（{exc}）")
    pb.bind_map_frame(args.layout, map_name="Map",
                      layer="pb_boundary" if args.boundary else "pb_density",
                      ratio=0.06, frame=0)

    out = os.path.abspath(args.out)
    res = pb.export_layout(args.layout, out, dpi=args.dpi, fmt="png")
    step(f"4/5 导出 {out}  {res.get('bytes', '?')} bytes  {args.dpi}dpi")
    print(out)


if __name__ == "__main__":
    main()
