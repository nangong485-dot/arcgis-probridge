r"""Download the public inputs used by the Beijing study-area example.

This script only downloads files under data/bj/raw and data/bj/bound. It does
not clip, reproject, or render them. Run prepare_study_area.py with ArcGIS Pro's
Python afterward.

    python tools\fetch_study_area.py
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.request


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DATA = os.path.join(ROOT, "data", "bj")

SRTM_TILES = ("N39E115", "N39E116", "N39E117", "N40E115", "N40E116", "N40E117")
WORLDCOVER_TILES = ("N39E114", "N39E117")
BOUNDARY_CODES = ("100000", "110000", "120000", "130000")


def download(url: str, target: str, force: bool = False) -> None:
    if os.path.exists(target) and os.path.getsize(target) > 0 and not force:
        print(f"  skip  {os.path.relpath(target, ROOT)}")
        return

    os.makedirs(os.path.dirname(target), exist_ok=True)
    temporary = target + ".part"
    request = urllib.request.Request(url, headers={"User-Agent": "ProBridge-fetch/1.0"})
    print(f"  get   {url}")
    with urllib.request.urlopen(request, timeout=120) as response:
        with open(temporary, "wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
    os.replace(temporary, target)
    size_mb = os.path.getsize(target) / (1024 * 1024)
    print(f"  saved {os.path.relpath(target, ROOT)} ({size_mb:.1f} MB)")


def fetch_boundaries(data_dir: str, force: bool) -> None:
    print("DataV boundaries")
    base = "https://geo.datav.aliyun.com/areas_v3/bound"
    for code in BOUNDARY_CODES:
        name = f"{code}_full.json"
        download(f"{base}/{name}", os.path.join(data_dir, "bound", name), force)


def fetch_srtm(data_dir: str, force: bool) -> None:
    print("NASA SRTM")
    base = "https://s3.amazonaws.com/elevation-tiles-prod/skadi"
    for tile in SRTM_TILES:
        name = f"{tile}.hgt.gz"
        download(
            f"{base}/{tile[:3]}/{name}",
            os.path.join(data_dir, "raw", name),
            force,
        )


def fetch_worldcover(data_dir: str, force: bool) -> None:
    print("ESA WorldCover")
    base = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map"
    for tile in WORLDCOVER_TILES:
        name = f"ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
        download(f"{base}/{name}", os.path.join(data_dir, "raw", name), force)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dest", default=DEFAULT_DATA, help="study-area data directory")
    parser.add_argument("--force", action="store_true", help="replace existing files")
    parser.add_argument("--skip-srtm", action="store_true")
    parser.add_argument("--skip-worldcover", action="store_true")
    parser.add_argument("--skip-boundaries", action="store_true")
    args = parser.parse_args()

    data_dir = os.path.abspath(args.dest)
    if not args.skip_boundaries:
        fetch_boundaries(data_dir, args.force)
    if not args.skip_srtm:
        fetch_srtm(data_dir, args.force)
    if not args.skip_worldcover:
        fetch_worldcover(data_dir, args.force)

    print(f"done: {data_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
