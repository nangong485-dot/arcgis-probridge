"""把 DEM 烤成一张"色晕 + 晕渲"的 RGB 底图，直接当普通影像图层用。

为什么要有这一步：桥的 `set_layer_render` 只有 rgb / stretch，没有色带；
arcpy 也没法在外部进程里改 Pro 已打开图层的符号（SaveToLayerFile 在 3.5 里
对栅格返回空壳）。所以干脆在**外面把效果算好**，Pro 里 add_layer 就是成品。

配色按制图学主流规则（Imhof / 国际百万分一世界地图 / Patterson & Jenny）：
低地偏绿 → 丘陵黄绿 → 山地浅棕 → 高山灰白 → 峰顶白，
再用晕渲相乘叠加。整体趋势由低到高变亮、峰顶最亮；山地棕/灰带允许局部变暗，
但暗带不能压掉晕渲——"越高越亮"指全带趋势，不是逐档单调。

用法（必须 Pro 自带 python）：
    "C:\\Program Files\\ArcGIS\\Pro\\bin\\Python\\envs\\arcgispro-py3\\python.exe" ^
        tools\\make_relief.py --dem data\\bj\\bj_dem.tif --out out\\bj_relief.tif
"""

import argparse
import os
import sys
import tempfile

import arcpy
import numpy as np

# 色晕色带：位置 0~1（按高程分位数拉伸后）→ 颜色
PALETTE = [
    (0.00, "#9FBFA3"),   # 低平原：浅绿
    (0.15, "#BCD19A"),
    (0.28, "#D9DFA6"),   # 丘陵：黄绿
    (0.42, "#EDE3B0"),
    (0.55, "#E2C99B"),   # 山地：浅黄棕
    (0.68, "#CBA983"),
    (0.80, "#B49C8C"),   # 高山：棕
    (0.92, "#DCD8D4"),   # 亚高：浅灰
    (1.00, "#FFFFFF"),   # 峰顶：白
]


def hex_to_rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


def build_lut(n=1024):
    """把分段色带插值成一张 n 长的 RGB 查找表。"""
    pos = np.array([p for p, _ in PALETTE], dtype=np.float32)
    cols = np.array([hex_to_rgb(c) for _, c in PALETTE], dtype=np.float32)
    xs = np.linspace(0.0, 1.0, n)
    return np.stack([np.interp(xs, pos, cols[:, i]) for i in range(3)], axis=1)


def hillshade(z, cell, azimuth=315.0, altitude=45.0, zfactor=2.0):
    """Horn 算法晕渲，返回 0~1 的明暗系数（1=正对光）。"""
    dy, dx = np.gradient(z, cell)
    slope = np.arctan(zfactor * np.hypot(dx, dy))
    aspect = np.arctan2(dy, -dx)
    az = np.radians(360.0 - azimuth + 90.0)
    alt = np.radians(altitude)
    shade = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    return np.clip(shade, 0.0, 1.0)


def make_relief(dem, out_tif, azimuth=315.0, altitude=45.0, zfactor=2.0,
                shade_strength=0.15, lo_pct=0.5, hi_pct=99.8, downsample=2, t_gamma=0.55):
    desc = arcpy.Describe(dem)
    cell = float(desc.meanCellWidth)
    sr = desc.spatialReference

    nodata = getattr(desc, "noDataValue", None)
    nodata = -9999 if nodata is None else nodata
    z = arcpy.RasterToNumPyArray(dem, nodata_to_value=nodata).astype(np.float32)
    d = max(1, int(downsample))
    if d > 1:
        z = z[::d, ::d].copy()
        cell *= d
    z[z == float(nodata)] = np.nan
    valid = ~np.isnan(z)

    lo, hi = np.nanpercentile(z, [lo_pct, hi_pct])
    t = np.clip((z - lo) / max(float(hi) - float(lo), 1e-6), 0.0, 1.0)
    t = np.nan_to_num(t, nan=0.0) ** t_gamma      # <1 时低海拔也有层次，平原不糊成一块

    lut = build_lut()
    idx = np.clip((t * (len(lut) - 1)).astype(np.int32), 0, len(lut) - 1)
    rgb = np.zeros(z.shape + (3,), dtype=np.float32)
    for i in range(3):
        rgb[..., i] = lut[:, i][idx]

    shade = hillshade(np.where(valid, z, lo), cell, azimuth, altitude, zfactor)
    factor = 1.0 + shade_strength * (shade - 0.5) * 2.0   # 均值≈1，避免整体压暗
    rgb *= factor[..., None]

    # 关键：每波段各自拉到 0~255。Pro 对 RGB 图层默认做"逐波段 2%~98% 拉伸"，
    # 只要各波段动态范围不一致，色相就会被改掉（浅绿变青）。先自己拉满，
    # Pro 那次拉伸就≈恒等，显示出来的颜色才和这里一致。
    if valid.any():
        for i in range(3):
            ch = rgb[..., i]
            lo_i = float(ch[valid].min())
            hi_i = float(ch[valid].max())
            if hi_i > lo_i:
                rgb[..., i] = (ch - lo_i) / (hi_i - lo_i) * 255.0
    rgb = np.clip(rgb, 0, 255)
    rgb[~valid] = 255.0          # 研究区外（DEM nodata）留白

    rgb = rgb.astype(np.uint8)
    xmin, ymin = desc.extent.XMin, desc.extent.YMin
    h, w = rgb.shape[:2]

    # 用 PIL 写"干净"的 RGB TIFF + .tfw（world file）。走 arcpy 的
    # CompositeBands 会带上 GDAL 元数据，Pro 可能据此改变显示方式。
    from PIL import Image
    img = Image.fromarray(rgb, mode="RGB")
    out_abs = os.path.abspath(out_tif)
    if os.path.splitext(out_abs)[1].lower() in (".tif", ".tiff"):
        img.save(out_abs, compression="tiff_lzw")
        tfw = os.path.splitext(out_abs)[0] + ".tfw"
        with open(tfw, "w", encoding="ascii") as f:
            f.write("\n".join(f"{v:.6f}" for v in
                              [cell, 0.0, 0.0, -cell,
                               xmin + cell / 2, ymin + h * cell - cell / 2]))
    else:
        img.save(out_abs)
    return out_tif



def main():
    ap = argparse.ArgumentParser(description="DEM → 色晕+晕渲 RGB 底图")
    ap.add_argument("--dem", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--azimuth", type=float, default=315.0, help="光照方位角，默认西北 315")
    ap.add_argument("--altitude", type=float, default=45.0)
    ap.add_argument("--zfactor", type=float, default=2.0, help="地形夸张，1=真实")
    ap.add_argument("--shade-strength", type=float, default=0.15, help="晕渲对比强度 0~0.5")
    ap.add_argument("--lo-percent", type=float, default=0.5)
    ap.add_argument("--hi-percent", type=float, default=99.8)
    ap.add_argument('--downsample', type=int, default=2, help='抽稀倍数，1=原分辨率')
    ap.add_argument('--t-gamma', type=float, default=0.55, help='高程拉伸 gamma，<1 让平原也有层次')
    a = ap.parse_args()
    out = make_relief(a.dem, a.out, a.azimuth, a.altitude, a.zfactor,
                      a.shade_strength, a.lo_percent, a.hi_percent, a.downsample, a.t_gamma)
    print(out)


if __name__ == "__main__":
    sys.exit(main())
