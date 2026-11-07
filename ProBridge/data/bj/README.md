# Beijing Study-Area Data

The study-area rasters and vector boundaries are intentionally not committed:

- The DEM and land-cover rasters are large and can be reproduced from public
  sources.
- The DataV boundary files do not have an explicit redistribution license.

Download the public inputs:

```powershell
.\.venv\Scripts\python.exe tools\fetch_study_area.py
```

Build the clipped, projected, map-ready files with ArcGIS Pro's Python:

```powershell
& 'C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe' tools\prepare_study_area.py
& 'C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe' tools\render_panels.py
```

Files under this directory are ignored by Git. See
[THIRD_PARTY_NOTICES.md](../../../THIRD_PARTY_NOTICES.md) for data licenses and
map-compliance notes.

For a small synthetic test that does not download anything, use
`tools\make_smoke_data.py` and the existing `data\smoke\` fixtures.
