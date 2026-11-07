"""Buffer a feature class and put the result on the current map.

  python client/cli.py run-arcpy --script buffer.py \
      --arg data/bj/bj_districts_utm.shp --arg out/buffer.shp \
      --arg "1000 Meters"
"""

from __future__ import annotations

import os
import sys

import arcpy

from _common import main


def run() -> dict:
    if len(sys.argv) < 4:
        raise SystemExit("usage: buffer.py <in_features> <out_features> <distance>")
    src, dst, distance = sys.argv[1:4]

    arcpy.env.overwriteOutput = True
    arcpy.analysis.Buffer(src, dst, distance, dissolve_option="NONE")

    count = int(arcpy.management.GetCount(dst)[0])
    return {
        "input": os.path.abspath(src),
        "output": os.path.abspath(dst),
        "distance": distance,
        "features": count,
        "layers": [os.path.abspath(dst)],
    }


if __name__ == "__main__":
    main(run)
