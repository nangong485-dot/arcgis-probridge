"""Prepare a study-area dataset for the 1a/1b/1c figure.

Inputs already on disk (see fetch notes at the bottom of this file):
  raw/*.hgt.gz                     SRTM 1 arc-second elevation
  raw/ESA_WorldCover_*.tif         ESA WorldCover 10 m land cover
  bound/*.json                     province / district boundaries (DataV GeoJSON)

Outputs (data/bj/):
  bj_boundary.shp      Beijing outline, EPSG:4326 and EPSG:32650
  bj_districts.shp     Beijing districts
  provinces.shp        national provinces, for the location inset
  neighbors.shp        Beijing + Hebei + Tianjin
  bj_dem.tif           30 m DEM, UTM 50N, clipped
  bj_hillshade.tif     hillshade of the DEM, same grid
  bj_lucc.tif          10 m land cover, UTM 50N, clipped

Run with Pro's Python (it has GDAL + numpy):
  "C:\\Program Files\\ArcGIS\\Pro\\bin\\Python\\envs\\arcgispro-py3\\python.exe" tools/prepare_study_area.py
"""

from __future__ import annotations

import glob
import gzip
import json
import os
import shutil
import struct

import numpy as np
from osgeo import gdal, ogr, osr

gdal.UseExceptions()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "bj")
RAW = os.path.join(DATA, "raw")
BOUND = os.path.join(DATA, "bound")

UTM50 = "EPSG:32650"      # CGCS2000 / UTM zone 50N is the natural frame for Beijing
WGS84 = "EPSG:4326"
SHP_ENCODING = ["ENCODING=UTF-8"]


def log(msg):
    print(f"[prep] {msg}", flush=True)


# ---------------------------------------------------------------- boundaries

def geojson_to_shp(src_json, out_shp, layer_name, keep_fields=("name", "adcode")):
    ds = ogr.Open(src_json)
    lyr = ds.GetLayer(0)
    src_srs = lyr.GetSpatialRef()

    drv = ogr.GetDriverByName("ESRI Shapefile")
    if os.path.exists(out_shp):
        drv.DeleteDataSource(out_shp)
    out = drv.CreateDataSource(out_shp)
    dst = out.CreateLayer(layer_name, src_srs, ogr.wkbMultiPolygon, options=SHP_ENCODING)

    src_defn = lyr.GetLayerDefn()
    for name in keep_fields:
        if src_defn.GetFieldIndex(name) >= 0:
            dst.CreateField(ogr.FieldDefn(name, ogr.OFTString))

    dst_defn = dst.GetLayerDefn()
    for feat in lyr:
        geom = feat.GetGeometryRef()
        if geom is None:
            continue
        if geom.GetGeometryType() == ogr.wkbPolygon:
            geom = ogr.ForceToMultiPolygon(geom)
        f = ogr.Feature(dst_defn)
        for name in keep_fields:
            idx = src_defn.GetFieldIndex(name)
            if idx >= 0:
                f.SetField(name, feat.GetField(idx))
        f.SetGeometry(geom)
        dst.CreateFeature(f)

    out = None
    ds = None
    return out_shp


def dissolve(shp_in, shp_out, layer_name):
    ds = ogr.Open(shp_in)
    lyr = ds.GetLayer(0)
    srs = lyr.GetSpatialRef()

    union = None
    for feat in lyr:
        g = feat.GetGeometryRef()
        if g is None:
            continue
        union = g.Clone() if union is None else union.Union(g)

    drv = ogr.GetDriverByName("ESRI Shapefile")
    if os.path.exists(shp_out):
        drv.DeleteDataSource(shp_out)
    out = drv.CreateDataSource(shp_out)
    dst = out.CreateLayer(layer_name, srs, ogr.wkbMultiPolygon, options=SHP_ENCODING)
    f = ogr.Feature(dst.GetLayerDefn())
    f.SetGeometry(ogr.ForceToMultiPolygon(union))
    dst.CreateFeature(f)
    out = None
    ds = None
    return shp_out


def reproject(shp_in, shp_out, epsg):
    gdal.VectorTranslate(
        shp_out, shp_in,
        options=gdal.VectorTranslateOptions(
            dstSRS=epsg, layerCreationOptions=SHP_ENCODING, accessMode="overwrite"
        ),
    )
    return shp_out


# -------------------------------------------------------------------- rasters

def hgt_to_tif(hgt_path, tif_path):
    """SRTM .hgt: 1201x1201 big-endian int16, north-up, 1 arc-second."""
    name = os.path.basename(hgt_path)[:7]          # N39E116
    lat = int(name[1:3]) * (1 if name[0] == "N" else -1)
    lon = int(name[4:7]) * (1 if name[3] == "E" else -1)

    with open(hgt_path, "rb") as fh:
        blob = fh.read()
    side = int((len(blob) // 2) ** 0.5)
    band = np.frombuffer(blob, dtype=">i2").reshape(side, side).astype(np.int16)
    band[band == -32768] = 0                       # SRTM void

    step = 1.0 / (side - 1)
    drv = gdal.GetDriverByName("GTiff")
    ds = drv.Create(tif_path, side, side, 1, gdal.GDT_Int16,
                    options=["TILED=YES", "COMPRESS=LZW"])
    ds.SetGeoTransform((lon, step, 0, lat + 1, 0, -step))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    ds.SetProjection(srs.ExportToWkt())
    out = ds.GetRasterBand(1)
    out.WriteArray(band)
    out.SetNoDataValue(0)
    ds.FlushCache()
    ds = None
    return tif_path


def build_dem(boundary_wgs):
    hgts = sorted(glob.glob(os.path.join(RAW, "*.hgt")))
    if not hgts:
        gzs = sorted(glob.glob(os.path.join(RAW, "*.hgt.gz")))
        for gz in gzs:
            target = gz[:-3]
            if not os.path.exists(target):
                with gzip.open(gz, "rb") as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
        hgts = sorted(glob.glob(os.path.join(RAW, "*.hgt")))

    tiles = []
    for hgt in hgts:
        tif = hgt[:-4] + ".tif"
        if not os.path.exists(tif):
            hgt_to_tif(hgt, tif)
        tiles.append(tif)
    log(f"{len(tiles)} SRTM tiles -> GeoTIFF")

    mosaic = os.path.join(DATA, "_dem_mosaic.tif")
    gdal.Warp(mosaic, tiles, dstSRS=WGS84, xRes=1 / 1200, yRes=1 / 1200,
              resampleAlg="bilinear", outputType=gdal.GDT_Int16)

    dem = os.path.join(DATA, "bj_dem.tif")
    gdal.Warp(dem, mosaic, dstSRS=UTM50, cutlineDSName=boundary_wgs,
              cropToCutline=True, xRes=30, yRes=30, resampleAlg="bilinear",
              outputType=gdal.GDT_Int16, creationOptions=["TILED=YES", "COMPRESS=DEFLATE"])
    os.remove(mosaic)

    shade = os.path.join(DATA, "bj_hillshade.tif")
    gdal.DEMProcessing(shade, dem, "hillshade", computeEdges=True,
                       creationOptions=["TILED=YES", "COMPRESS=DEFLATE"])
    log("DEM + hillshade written (30 m, UTM 50N)")
    return dem


def build_lucc(boundary_wgs):
    tiles = sorted(glob.glob(os.path.join(RAW, "ESA_WorldCover_*_Map.tif")))
    if not tiles:
        raise SystemExit("no WorldCover tiles in raw/")
    lucc = os.path.join(DATA, "bj_lucc.tif")
    gdal.Warp(lucc, tiles, dstSRS=UTM50, cutlineDSName=boundary_wgs,
              cropToCutline=True, xRes=10, yRes=10, resampleAlg="near",
              outputType=gdal.GDT_Byte,
              creationOptions=["TILED=YES", "COMPRESS=DEFLATE"])
    log("land cover written (10 m, UTM 50N)")
    return lucc


def main():
    os.makedirs(DATA, exist_ok=True)

    districts_json = os.path.join(BOUND, "110000_full.json")
    provinces_json = os.path.join(BOUND, "100000_full.json")

    bj_districts = geojson_to_shp(districts_json, os.path.join(DATA, "bj_districts.shp"),
                                  "districts")
    log("districts -> shapefile")

    bj_boundary = dissolve(bj_districts, os.path.join(DATA, "bj_boundary.shp"), "boundary")
    log("boundary dissolved")

    provinces = geojson_to_shp(provinces_json, os.path.join(DATA, "provinces.shp"),
                               "provinces")
    log("provinces -> shapefile")

    # Beijing + Hebei + Tianjin, for the location map's neighbourhood context
    neigh = os.path.join(DATA, "_neighbors_raw.shp")
    keep = []
    for code, name in (("130000_full", "hebei"), ("120000_full", "tianjin")):
        shp = os.path.join(DATA, f"{name}.shp")
        geojson_to_shp(os.path.join(BOUND, f"{code}.json"), shp, name)
        keep.append(shp)
    gdal.VectorTranslate(neigh, bj_boundary,
                         options=gdal.VectorTranslateOptions(
                             layerCreationOptions=SHP_ENCODING, accessMode="overwrite"))
    for shp in keep:
        gdal.VectorTranslate(neigh, shp,
                             options=gdal.VectorTranslateOptions(accessMode="append"))
    reproject(neigh, os.path.join(DATA, "neighbors.shp"), UTM50)
    for tmp in [neigh] + [p.replace(".shp", ext) for p in keep
                          for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg")]:
        if os.path.exists(tmp):
            os.remove(tmp)

    # boundaries also in UTM, so map frames and vector layers agree
    reproject(bj_boundary, os.path.join(DATA, "bj_boundary_utm.shp"), UTM50)
    reproject(bj_districts, os.path.join(DATA, "bj_districts_utm.shp"), UTM50)
    log("boundaries reprojected to UTM 50N")

    build_dem(bj_boundary)
    build_lucc(bj_boundary)

    log("done")
    for f in sorted(os.listdir(DATA)):
        if f.endswith((".shp", ".tif")):
            p = os.path.join(DATA, f)
            log(f"  {f:26s} {os.path.getsize(p) / 1e6:8.1f} MB")


# Data sources
#   SRTM 1 arc-second: https://s3.amazonaws.com/elevation-tiles-prod/skadi/N39/N39E116.hgt.gz
#     public bucket, no key, 30 m, void = -32768
#   ESA WorldCover 2021 v200 (10 m):
#     https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_N39E114_Map.tif
#   Boundaries: DataV GeoAtlas https://geo.datav.aliyun.com/areas_v3/bound/100000_full.json
#     Convenient but NOT a surveying-grade source. For publication, replace the
#     national boundary / inset with 自然资源部标准地图 (bzdt.ch.mnr.gov.cn) or
#     Tianditu, and keep 南海诸岛 in any whole-country frame.

if __name__ == "__main__":
    main()
