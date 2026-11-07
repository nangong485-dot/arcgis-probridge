"""Render publication-style RGB panels from the prepared rasters.

ArcGIS Pro's default raster symbology is grey and its stretch is computed on a
sample, which makes a DEM look like a black blob. Rather than drive CIM
colorizers from the bridge, the cartographic colours are baked here — the
result is deterministic, reviewable in git, and Pro only has to place it.

  bj_dem_rgb.tif     hypsometric tint x hillshade, alpha outside the boundary
  bj_lucc_rgb.tif    land-cover palette, alpha outside the boundary
  legend_dem.png     elevation legend strip
  legend_lucc.png    land-cover legend strip

  "C:\\Program Files\\ArcGIS\\Pro\\bin\\Python\\envs\\arcgispro-py3\\python.exe" tools/render_panels.py
"""

from __future__ import annotations

import os

import numpy as np
from osgeo import gdal

gdal.UseExceptions()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "bj")
OUT = os.path.join(ROOT, "out")

# hypsometric tint, metres -> RGB
DEM_STOPS = [
    (0, (58, 120, 72)),
    (150, (110, 165, 95)),
    (350, (185, 205, 135)),
    (600, (222, 205, 140)),
    (1000, (205, 165, 115)),
    (1500, (185, 135, 105)),
    (2000, (225, 205, 190)),
    (2400, (250, 250, 250)),
]

# ESA WorldCover class -> colour (Chinese publication convention:
# cropland pale yellow, forest dark green, built-up muted red)
LUCC_COLORS = {
    10: ((85, 160, 80), "林地"),
    20: ((200, 230, 150), "灌木"),
    30: ((170, 210, 120), "草地"),
    40: ((255, 255, 190), "耕地"),
    50: ((230, 120, 120), "建设用地"),
    60: ((200, 190, 170), "裸地"),
    70: ((255, 255, 255), "冰雪"),
    80: ((100, 170, 230), "水体"),
    90: ((150, 200, 210), "湿地"),
    95: ((0, 200, 120), "红树林"),
    100: ((120, 220, 120), "苔藓"),
}


def read(path):
    ds = gdal.Open(path)
    band = ds.GetRasterBand(1)
    arr = band.ReadAsArray()
    return ds, arr


def boundary_mask(ref_ds):
    """Rasterise the study-area outline onto the raster's own grid.

    gdal_rasterize does not reproject the source, so this needs the boundary in
    the same CRS as the raster (both are UTM 50N).
    """
    gt = ref_ds.GetGeoTransform()
    xmin = gt[0]
    ymax = gt[3]
    xmax = xmin + ref_ds.RasterXSize * gt[1]
    ymin = ymax + ref_ds.RasterYSize * gt[5]

    tmp = "/vsimem/mask.tif"
    gdal.Rasterize(
        tmp, os.path.join(DATA, "bj_boundary_utm.shp"),
        outputBounds=[xmin, ymin, xmax, ymax],
        width=ref_ds.RasterXSize, height=ref_ds.RasterYSize,
        outputType=gdal.GDT_Byte, burnValues=[255],
        allTouched=False, format="GTiff",
    )
    ds = gdal.Open(tmp)
    mask = ds.GetRasterBand(1).ReadAsArray()
    ds = None
    gdal.Unlink(tmp)
    return mask


def write_rgb(path, rgb, mask, ref_ds):
    h, w, _ = rgb.shape
    if mask is not None:
        # bake the page colour outside the boundary: Pro draws an alpha band as
        # black, not transparent, so transparency is not an option here
        rgb[mask == 0] = 255

    drv = gdal.GetDriverByName("GTiff")
    ds = drv.Create(path, w, h, 3, gdal.GDT_Byte,
                    options=["TILED=YES", "COMPRESS=DEFLATE", "PHOTOMETRIC=RGB"])
    ds.SetGeoTransform(ref_ds.GetGeoTransform())
    ds.SetProjection(ref_ds.GetProjection())
    for i in range(3):
        ds.GetRasterBand(i + 1).WriteArray(rgb[:, :, i])
    ds.FlushCache()
    ds = None


def tint(elev):
    """Piecewise-linear hypsometric ramp."""
    h, w = elev.shape
    rgb = np.zeros((h, w, 3), np.float32)
    xs = np.array([s[0] for s in DEM_STOPS], np.float32)
    for c in range(3):
        ys = np.array([s[1][c] for s in DEM_STOPS], np.float32)
        rgb[:, :, c] = np.interp(elev, xs, ys)
    return rgb


def build_dem(suffix=""):
    dem_ds, elev = read(os.path.join(DATA, "bj_dem.tif"))
    shade_ds, shade = read(os.path.join(DATA, "bj_hillshade.tif"))
    mask = boundary_mask(dem_ds)

    rgb = tint(elev.astype(np.float32))
    # hillshade modulates brightness without washing out the tint
    factor = 0.55 + 0.45 * (shade.astype(np.float32) / 255.0)
    rgb = np.clip(rgb * factor[:, :, None], 0, 255).astype(np.uint8)

    write_rgb(os.path.join(DATA, f"bj_dem_rgb{suffix}.tif"), rgb, mask, dem_ds)
    print(f"[panel] dem rgb {rgb.shape[1]}x{rgb.shape[0]}  elev {elev.min()}-{elev.max()} m")
    return int(elev.min()), int(elev.max())


def build_lucc(suffix=""):
    ds, cls = read(os.path.join(DATA, "bj_lucc.tif"))
    mask = boundary_mask(ds)
    rgb = np.zeros(cls.shape + (3,), np.uint8)
    for code, (color, _) in LUCC_COLORS.items():
        rgb[cls == code] = color

    # thin class boundaries make the patchwork readable at print size
    edge = np.zeros(cls.shape, bool)
    edge[1:, :] |= cls[1:, :] != cls[:-1, :]
    edge[:, 1:] |= cls[:, 1:] != cls[:, :-1]
    rgb[edge] = (90, 90, 90)

    write_rgb(os.path.join(DATA, f"bj_lucc_rgb{suffix}.tif"), rgb, mask, ds)
    print(f"[panel] lucc rgb {rgb.shape[1]}x{rgb.shape[0]}")


# ------------------------------------------------------------------- legends

def legend_dem(path, lo, hi):
    """Vertical colour strip with tick labels, drawn into a PNG."""
    width, height = 150, 520
    strip_w, pad = 46, 12
    img = np.full((height, width, 3), 255, np.uint8)

    steps = 256
    vals = np.linspace(hi, lo, steps)               # top = high
    strip = tint(vals.reshape(-1, 1).astype(np.float32)).astype(np.uint8)
    for i in range(steps):
        y0 = pad + i * (height - 2 * pad) // steps
        y1 = pad + (i + 1) * (height - 2 * pad) // steps
        img[y0:y1, pad:pad + strip_w] = strip[i, 0]

    # ticks every 500 m
    for value in range(int(lo // 500) * 500, hi + 1, 500):
        if value < lo:
            continue
        y = pad + int((hi - value) / max(hi - lo, 1) * (height - 2 * pad))
        img[y:y + 1, pad + strip_w:pad + strip_w + 6] = 60

    write_png(path, img)


def legend_lucc(path):
    rows = [(c, n) for c, (_, n) in LUCC_COLORS.items()]
    row_h, pad, box = 26, 10, 18
    width, height = 190, pad * 2 + row_h * len(rows)
    img = np.full((height, width, 3), 255, np.uint8)
    for i, (code, _) in enumerate(rows):
        color = LUCC_COLORS[code][0]
        y = pad + i * row_h
        img[y:y + box, pad:pad + box] = color
        img[y:y + box, pad:pad + box] = np.where(
            np.indices((box, box)).sum(0)[:, :, None] % 7 == 0, 255, img[y:y + box, pad:pad + box])
    write_png(path, img)


def write_png(path, rgb):
    h, w, _ = rgb.shape
    # this GDAL build has no PNG create method, only CreateCopy
    mem = gdal.GetDriverByName("MEM").Create("", w, h, 3, gdal.GDT_Byte)
    for i in range(3):
        mem.GetRasterBand(i + 1).WriteArray(rgb[:, :, i])
    gdal.GetDriverByName("PNG").CreateCopy(path, mem)
    mem = None
    print(f"[panel] {os.path.basename(path)} {w}x{h}")


def main():
    import sys
    suffix = sys.argv[1] if len(sys.argv) > 1 else ""
    os.makedirs(OUT, exist_ok=True)
    lo, hi = build_dem(suffix)
    build_lucc(suffix)
    legend_dem(os.path.join(OUT, f"legend_dem{suffix}.png"), lo, hi)
    legend_lucc(os.path.join(OUT, f"legend_lucc{suffix}.png"))


if __name__ == "__main__":
    main()
