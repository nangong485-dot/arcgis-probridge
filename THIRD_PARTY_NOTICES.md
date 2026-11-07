# Third-Party Notices

The MIT license in [LICENSE](LICENSE) applies to this repository's original
source code and documentation. It does not grant rights to third-party software
or data.

## ArcGIS Pro and Esri SDK assemblies

ProBridge is an ArcGIS Pro add-in and requires a separately licensed ArcGIS Pro
installation. Esri SDK assemblies are referenced from the local ArcGIS Pro
installation and are not redistributed by this repository. Use of ArcGIS Pro is
governed by Esri's license terms.

## MCP Python SDK

The Python MCP server depends on the Model Context Protocol Python SDK
(`mcp<2`), distributed under the MIT License:
<https://github.com/modelcontextprotocol/python-sdk>

## ESA WorldCover

The optional Beijing example can download ESA WorldCover 2021 v200 data. That
dataset is distributed under the Creative Commons Attribution 4.0
International license. Attribution is required when the data is used or
redistributed.

- <https://esa-worldcover.org/en/data-access>
- <https://creativecommons.org/licenses/by/4.0/>

The dataset is not included in this repository.

## NASA SRTM

The optional example can download SRTM elevation tiles from the public AWS
Open Data bucket. SRTM data is in the public domain.

- <https://www.earthdata.nasa.gov/data/instruments/srtm>
- <https://registry.opendata.aws/terrain-tiles/>

The dataset is not included in this repository.

## DataV administrative boundaries

The optional example can download administrative boundaries from DataV
GeoAtlas for development and demonstration. No boundary files are included in
this repository, and DataV data has no explicit redistribution license.

Users are responsible for map compliance and for replacing these boundaries
with an authoritative source before publication. For Chinese maps, use the
Ministry of Natural Resources standard maps or an appropriately licensed
service, and preserve the South China Sea islands in any national-scale frame.

- <https://geo.datav.aliyun.com/areas_v3/bound/>
- <https://bzdt.ch.mnr.gov.cn/>
