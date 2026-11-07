r"""区县面统计 → 分级设色/点符号演示数据。

把区县面（4326）投到 UTM 50N，用 ZonalStatisticsAsTable 求「建设用地密度」像元的
平均值，写回属性表字段 BUI_PCT（百分比），再导一份区县质心点。

    Pro python tools\prep_district_stats.py            # 默认用 out\bj_builtup_density.tif
    Pro python tools\prep_district_stats.py --raster ... --out-dir ...

输出（默认 ProBridge\out\demo\）：
    districts_utm.shp   16 个区县面 + BUI_PCT 字段（0-100）
    district_pts.shp    16 个区县质心点 + BUI_PCT 字段（0-100）
"""

import argparse
import os

import arcpy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--districts", default=os.path.join(ROOT, "data", "bj", "bj_districts.shp"))
    ap.add_argument("--raster", default=os.path.join(ROOT, "out", "bj_builtup_density.tif"))
    ap.add_argument("--out-dir", default=os.path.join(ROOT, "out", "demo"))
    ap.add_argument("--field", default="BUI_PCT")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    sr = arcpy.SpatialReference(32650)          # WGS 84 / UTM 50N
    arcpy.env.overwriteOutput = True

    districts = os.path.join(args.out_dir, "districts_utm.shp")
    if arcpy.Exists(districts):
        arcpy.management.Delete(districts)
    arcpy.management.Project(args.districts, districts, sr)

    d = arcpy.Describe(args.raster)
    print(f"[stats] raster {os.path.basename(args.raster)} {d.width}x{d.height} sr={d.spatialReference.name}")
    r = arcpy.Raster(args.raster)
    lo, hi, mean = r.minimum, r.maximum, r.mean
    print(f"[stats] value range {lo} .. {hi}, mean {mean}")

    table = os.path.join(args.out_dir, "zone_mean.dbf")
    if arcpy.Exists(table):
        arcpy.management.Delete(table)
    arcpy.sa.ZonalStatisticsAsTable(districts, "adcode", args.raster, table, "DATA", "MEAN")

    arcpy.management.JoinField(districts, "adcode", table, "adcode", ["MEAN"])
    if args.field in [f.name for f in arcpy.ListFields(districts)]:
        arcpy.management.DeleteField(districts, args.field)
    arcpy.management.AddField(districts, args.field, "FLOAT")
    arcpy.management.CalculateField(districts, args.field, "!MEAN! * 100", "PYTHON3")

    pts = os.path.join(args.out_dir, "district_pts.shp")
    if arcpy.Exists(pts):
        arcpy.management.Delete(pts)
    arcpy.management.FeatureToPoint(districts, pts, "INSIDE")

    with arcpy.da.SearchCursor(districts, ["name", args.field]) as cur:
        rows = sorted(cur, key=lambda t: (t[1] is None, -(t[1] or 0)))
    for name, v in rows:
        print(f"  {name:<10} {v if v is not None else 0:8.2f}")

    print(f"[stats] {districts}")
    print(f"[stats] {pts}")


if __name__ == "__main__":
    main()
