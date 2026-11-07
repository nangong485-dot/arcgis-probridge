"""Report the arcpy runtime that ProBridge jobs actually use.

  python client/cli.py run-arcpy --script diagnose.py --no-add
"""

from __future__ import annotations

import os
import platform
import sys

import arcpy

from _common import main


def run() -> dict:
    install = arcpy.GetInstallInfo()
    extensions = {}
    for name in ("Spatial", "3D", "Network", "GeoStats", "ImageAnalyst"):
        try:
            extensions[name] = arcpy.CheckExtension(name)
        except Exception as exc:  # noqa: BLE001 - diagnostic output
            extensions[name] = f"error: {exc}"

    return {
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "platform": platform.platform(),
        "arcpy": install.get("Version"),
        "product": install.get("ProductName"),
        "install_dir": install.get("InstallDir"),
        "license": arcpy.ProductInfo(),
        "extensions": extensions,
        "cwd": os.getcwd(),
        "job_dir": os.environ.get("PROBRIDGE_JOB_DIR"),
    }


if __name__ == "__main__":
    main(run)
