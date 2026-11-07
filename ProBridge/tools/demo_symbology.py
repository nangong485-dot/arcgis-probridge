"""验证 set_symbology：给 DEM 直接上分层设色色带（不烘 RGB），边界（面）改空心描边。

这条路绕开了"Pro 会重新拉伸烘好的 RGB"这个坑：色带由 CIM 写进图层，
图例和颜色都还能改。

用法（Pro 已打开，当前工程有一个地图）：
    .venv\\Scripts\\python.exe tools\\demo_symbology.py

清理：
    .venv\\Scripts\\python.exe client\\cli.py clear pb_
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from client.probridge import ProBridge  # noqa: E402

BJ = os.path.join(ROOT, "data", "bj")
OUT = os.path.join(ROOT, "out", "demo_symbology.png")

# Imhof / IMW 风格的色晕：低地绿 → 丘陵黄绿 → 山地黄棕 → 高山灰 → 峰顶白
RAMP = ["#9FBFA3", "#BCD19A", "#D9DFA6", "#EDE3B0", "#E2C99B",
        "#CBA983", "#B49C8C", "#DCD8D4", "#FFFFFF"]


def show(label, value):
    print(f"[{label}] {json.dumps(value, ensure_ascii=False)}")


def main():
    pb = ProBridge()
    show("ping", pb.ping())
    show("清理 pb_", pb.clear_layers("pb_"))

    show("加载 DEM", pb.add_layer(os.path.join(BJ, "bj_dem.tif"), name="pb_dem"))
    show("DEM 分层设色", pb.call(
        "set_symbology", layer="pb_dem", kind="raster_stretch",
        stretch="percentclip", min_pct=0.5, max_pct=99.8, colors=RAMP))

    show("加载边界", pb.add_layer(os.path.join(BJ, "bj_boundary.shp"), name="pb_boundary"))
    show("边界空心描边", pb.call(
        "set_symbology", layer="pb_boundary", kind="feature",
        fill="none", outline="#3F3F3F", width=0.6))

    show("缩放到边界", pb.fit("pb_boundary"))

    layout = "pb_symbol"
    frames = [{"name": "pb_frame", "map": "Map",
               "x": 15, "y": 22, "w": 170, "h": 128,
               "title": "分层设色 · 北京"}]
    show("建布局", pb.create_panel_layout(layout, 200, 170, frames))
    show("绑定图框", pb.bind_map_frame(layout, map_name="Map",
                                       layer="pb_boundary", ratio=0.075, frame=0))
    show("导出", pb.export_layout(layout, OUT, dpi=200, fmt="png"))
    print(f"done -> {OUT}")


if __name__ == "__main__":
    main()
