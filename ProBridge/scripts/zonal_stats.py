"""Zonal statistics of a raster inside polygon zones.

  python client/cli.py run-arcpy --script zonal_stats.py \
      --arg data/bj/bj_districts_utm.shp --arg data/bj/bj_dem.tif \
      --arg out/zonal.dbf

The zone field defaults to the feature class OID. Pass a field name as the
fourth argument to group by it instead (e.g. NAME).
"""

from __future__ import annotations

import os
import sys

import arcpy

from _common import main


def run() -> dict:
    if len(sys.argv) < 4:
        raise SystemExit(
            "usage: zonal_stats.py <zones> <value_raster> <out_table> [zone_field]"
        )
    zones, value_raster, out_table = sys.argv[1:4]
    zone_field = sys.argv[4] if len(sys.argv) > 4 else arcpy.Describe(zones).OIDFieldName

    arcpy.env.overwriteOutput = True
    arcpy.sa.ZonalStatisticsAsTable(
        zones, zone_field, value_raster, out_table,
        ignore_nodata="DATA", statistics_type="ALL",
    )

    rows = int(arcpy.management.GetCount(out_table)[0])
    return {
        "zones": os.path.abspath(zones),
        "value_raster": os.path.abspath(value_raster),
        "zone_field": zone_field,
        "table": os.path.abspath(out_table),
        "rows": rows,
        "layers": [],
    }


if __name__ == "__main__":
    main(run)
