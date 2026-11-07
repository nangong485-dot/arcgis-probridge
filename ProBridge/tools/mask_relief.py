"""用面矢量把烘好的底图裁成"只保留研究区内"的形状。

为什么不直接用 arcpy.management.Clip：它的输出是 U16 三波段，加进 Pro 之后
`set_symbology --kind raster_rgb` 会整张渲成黑色（8 bit 的 PIL 输出正常）。
所以这里只借 arcpy 读顶点 + 拿网格参数，抠图用 numpy + PIL，输出仍是验证过能
正常显示的 8 bit TIFF（附 .tfw / .prj）。

命令行用法（要用 Pro 自带 python，因为要 arcpy）：
    "C:\\Program Files\\ArcGIS\\Pro\\bin\\Python\\envs\\arcgispro-py3\\python.exe" `
        tools\\mask_relief.py --raster out\\bj_relief_pb.tif `
        --boundary data\\bj\\bj_boundary.shp --out out\\bj_relief_masked.tif

也可以 import 用：`from mask_relief import mask_raster`。
"""
import argparse
import os
import tempfile

import numpy as np
from PIL import Image, ImageDraw


def _project_boundary(arcpy, bnd, target_sr):
    """把边界转到栅格坐标系，返回可用的 shp 路径。"""
    if arcpy.Describe(bnd).spatialReference.name == target_sr.name:
        return bnd
    out = os.path.join(tempfile.gettempdir(), "_mask_bnd.shp")
    for ext in (".shp", ".dbf", ".shx", ".prj", ".cpg"):
        p = out[:-4] + ext
        if os.path.exists(p):
            os.remove(p)
    arcpy.management.Project(bnd, out, target_sr)
    return out


def mask_raster(raster, boundary, out, outside="white", target_sr=32650):
    """把 raster 中 boundary 之外的部分涂白/清零，输出 8bit RGB TIFF（带 tfw/prj）。"""
    import arcpy  # 只在 Pro 的 python 里可用

    raster = os.path.abspath(raster)
    out = os.path.abspath(out)
    sr = arcpy.SpatialReference(target_sr)

    # 底图是 PIL 写的，内嵌坐标系可能缺失；先声明，让 arcpy 能对齐边界
    try:
        arcpy.management.DefineProjection(raster, sr)
    except Exception:
        pass

    rr = arcpy.Raster(raster)
    ext = rr.extent
    cw, ch = rr.meanCellWidth, rr.meanCellHeight
    W = int(round((ext.XMax - ext.XMin) / cw))
    H = int(round((ext.YMax - ext.YMin) / ch))

    proj = _project_boundary(arcpy, os.path.abspath(boundary), rr.spatialReference)

    # 不用 PolygonToRaster：它出的栅格上万像素，RasterToNumPyArray 会报
    # "The pixel block exceeds the maximum size allowed"。直接按网格画多边形。
    mask_img = Image.new("L", (W, H), 0)
    draw = ImageDraw.Draw(mask_img)
    with arcpy.da.SearchCursor(proj, ["SHAPE@"]) as cur:
        for (geom,) in cur:
            for part in geom:
                pts = [((p.X - ext.XMin) / cw, (ext.YMax - p.Y) / ch) for p in part]
                if len(pts) >= 3:
                    draw.polygon(pts, fill=255)
    inside = np.asarray(mask_img) > 0

    arr = np.array(Image.open(raster).convert("RGB"))  # 复制：np.asarray 是只读视图
    h, w = arr.shape[:2]
    if inside.shape != (h, w):
        raise SystemExit(f"掩膜尺寸 {inside.shape} 与底图 {(h, w)} 不一致")
    arr[~inside] = 255 if outside == "white" else 0
    Image.fromarray(arr, "RGB").save(out, compression="tiff_lzw")

    base = os.path.splitext(out)[0]
    with open(base + ".tfw", "w", encoding="ascii") as fh:
        fh.write(f"{cw}\n0.0\n0.0\n{-ch}\n{ext.XMin + cw / 2.0}\n{ext.YMax - ch / 2.0}\n")
    with open(base + ".prj", "w", encoding="utf-8") as fh:
        fh.write(rr.spatialReference.exportToString())

    print(f"{out}  {os.path.getsize(out)} bytes  "
          f"inside={inside.mean():.1%}  sr={rr.spatialReference.name}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raster", required=True)
    ap.add_argument("--boundary", required=True, help="polygon shapefile")
    ap.add_argument("--out", required=True)
    ap.add_argument("--outside", default="white", choices=["white", "nodata"])
    ap.add_argument("--target-sr", type=int, default=32650,
                    help="EPSG，只用来说明底图坐标系（默认 UTM 50N）")
    args = ap.parse_args()
    mask_raster(args.raster, args.boundary, args.out, args.outside, args.target_sr)


if __name__ == "__main__":
    main()
