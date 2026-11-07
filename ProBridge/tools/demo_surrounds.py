r"""版式要素演示：分级设色面 + 点符号 + 图例 / 比例尺 / 指北针。

前置（数据已经在 out/demo 里）：
    Pro python tools\prep_district_stats.py --raster out\pb_density_50.tif

运行：
    .venv\Scripts\python.exe tools\demo_surrounds.py

出图：out\bj_choropleth.png
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from client.probridge import ProBridge  # noqa: E402

OUT = os.path.join(ROOT, "out")
DEMO = os.path.join(OUT, "demo2")

# ColorBrewer YlOrRd（5 级）：低值浅、高值深，顺序型数据只能这么走
YlOrRd = ["#FFFFB2", "#FECC5C", "#FD8D3C", "#F03B20", "#BD0026"]

LAYOUT = "pb_choropleth"
FRAME = "pb_frame_choropleth"


def main():
    pb = ProBridge()

    pb.clear_layers(prefix="pb_")

    pb.add_layer(os.path.join(DEMO, "districts_utm.shp"), name="区县建设用地密度")
    print(pb.call("set_symbology",
                  layer="区县建设用地密度", kind="feature_breaks",
                  field="BUI_PCT", classes=5, method="natural",
                  colors=YlOrRd, outline="#8C6D62", width=0.4))

    pb.add_layer(os.path.join(DEMO, "district_pts.shp"), name="区县驻地")
    print(pb.call("set_symbology",
                  layer="区县驻地", kind="point",
                  fill="#333333", size=7, marker="circle",
                  halo="#FFFFFF", halo_size=1.2))

    pb.add_layer(os.path.join(ROOT, "data", "bj", "bj_boundary.shp"), name="北京界")
    print(pb.call("set_symbology",
                  layer="北京界", kind="feature", fill="none",
                  outline="#262626", width=1.2))

    pb.activate_map()
    pb.fit("北京界", ratio=0.02)

    frames = [{
        "name": FRAME, "map": "Map",
        "x": 14, "y": 32, "w": 122, "h": 116,
        "title": "区县建设用地密度 · 北京",
    }]
    pb.create_panel_layout(LAYOUT, 200, 170, frames)
    pb.bind_map_frame(LAYOUT, map_name="Map", layer="北京界", ratio=0.02, frame=0)

    print(pb.call("add_surrounds", layout=LAYOUT, frame=FRAME,
                  scale_bar=True, north_arrow=True, legend=True,
                  scale_x=16, scale_y=14, scale_width=42,
                  arrow_x=176, arrow_y=18, arrow_height=15,
                  legend_x=144, legend_y=60, legend_w=50, legend_h=86))

    print(pb.export_layout(LAYOUT, os.path.join(OUT, "bj_choropleth.png"),
                           dpi=200, fmt="png"))


if __name__ == "__main__":
    main()
