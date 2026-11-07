"""Create a tiny fake dataset so the bridge can be tested before real data exists.

Run with Pro's interpreter:
  "C:\\Program Files\\ArcGIS\\Pro\\bin\\Python\\envs\\arcgispro-py3\\python.exe" tools\\make_smoke_data.py
"""

import os
import sys

import arcpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "smoke")
GDB = os.path.join(OUT, "smoke.gdb")


def main():
    os.makedirs(OUT, exist_ok=True)
    arcpy.env.overwriteOutput = True

    if arcpy.Exists(GDB):
        arcpy.management.Delete(GDB)
    arcpy.management.CreateFileGDB(OUT, "smoke.gdb")

    sr = arcpy.SpatialReference(4326)
    fc = arcpy.management.CreateFeatureclass(GDB, "Province", "POLYGON", spatial_reference=sr)
    arcpy.management.AddField(fc, "NAME", "TEXT", field_length=50)

    ring = arcpy.Array([
        arcpy.Point(116.0, 39.0),
        arcpy.Point(117.2, 39.0),
        arcpy.Point(117.2, 40.1),
        arcpy.Point(116.0, 40.1),
        arcpy.Point(116.0, 39.0),
    ])
    with arcpy.da.InsertCursor(fc, ["SHAPE@", "NAME"]) as cur:
        cur.insertRow([arcpy.Polygon(ring), "FakeProvince"])

    import numpy as np

    dem = os.path.join(OUT, "DEM.tif")
    rows, cols = 551, 601
    gradient = np.tile(np.linspace(0.0, 3000.0, cols, dtype="float32"), (rows, 1))
    raster = arcpy.NumPyArrayToRaster(gradient, arcpy.Point(116.0, 39.0), 0.002, 0.002)
    raster.save(dem)

    arcpy.management.CalculateStatistics(dem)

    print("GDB :", GDB)
    print("FC  :", fc)
    print("DEM :", dem)
    print("PROJ:", arcpy.Describe(fc).spatialReference.name)


if __name__ == "__main__":
    sys.exit(main())
