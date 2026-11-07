"""Clip a raster to a polygon mask and put the result on the current map.

  python client/cli.py run-arcpy --script clip_raster.py \
      --arg data/bj/bj_dem.tif --arg data/bj/bj_boundary_utm.shp \
      --arg out/dem_clip.tif
"""

from __future__ import annotations

import os
import sys

import arcpy

from _common import main


def run() -> dict:
    if len(sys.argv) < 4:
        raise SystemExit("usage: clip_raster.py <in_raster> <mask> <out_raster>")
    src, mask, dst = sys.argv[1:4]

    arcpy.env.overwriteOutput = True
    clipped = arcpy.sa.ExtractByMask(src, mask)
    clipped.save(dst)

    desc = arcpy.Describe(dst)
    return {
        "input": os.path.abspath(src),
        "mask": os.path.abspath(mask),
        "output": os.path.abspath(dst),
        "width": desc.width,
        "height": desc.height,
        "layers": [os.path.abspath(dst)],
    }


if __name__ == "__main__":
    main(run)
