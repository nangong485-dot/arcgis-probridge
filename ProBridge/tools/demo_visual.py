"""最小可视化演示：把边界和 DEM 加载进当前打开的 Pro 工程，缩放、调色、
拼一个单图框布局并导出 PNG。全程不改动工程里已有的图层。

用法（Pro 必须已经打开，且当前工程有一个地图）：
    .venv\\Scripts\\python.exe tools\\demo_visual.py

清理演示产物：
    .venv\\Scripts\\python.exe client\\cli.py clear pb_
    （布局 pb_visual 在 Pro 里手动删掉，或重启工程不保存）
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from client.probridge import ProBridge  # noqa: E402

BJ = os.path.join(ROOT, "data", "bj")
OUT = os.path.join(ROOT, "out", "demo_visual.png")


def show(label, value):
    print(f"[{label}] {json.dumps(value, ensure_ascii=False)}")


def main():
    pb = ProBridge()
    show("ping", pb.ping())

    # 0. 清掉上次演示留下的 pb_ 图层，避免叠加
    show("清理 pb_ 图层", pb.clear_layers("pb_"))

    # 1. 先加底图（DEM），拉伸显示；再加边界压在上面
    show("加载 DEM", pb.add_layer(os.path.join(BJ, "bj_dem.tif"), name="pb_dem"))
    show("DEM 拉伸", pb.set_layer_render("pb_dem", mode="stretch"))
    show("加载边界", pb.add_layer(os.path.join(BJ, "bj_boundary.shp"), name="pb_boundary"))

    # 2. 视野缩放到研究区
    show("缩放到边界", pb.fit("pb_boundary"))

    # 3. 建单图框布局（单位毫米，坐标原点在页面左下角）
    layout = "pb_visual"
    frames = [{
        "name": "pb_frame",
        "map": "Map",
        "x": 15, "y": 22, "w": 170, "h": 128,
        "title": "可视化验证 · 北京",
    }]
    show("建布局", pb.create_panel_layout(layout, 200, 170, frames))

    # 4. 图框视野对准边界图层（ratio=0.075 即四周留 7.5% 白边）
    show("绑定图框", pb.bind_map_frame(layout, map_name="Map",
                                      layer="pb_boundary", ratio=0.075, frame=0))

    # 5. 出图
    show("导出", pb.export_layout(layout, OUT, dpi=200, fmt="png"))
    print(f"done -> {OUT}")


if __name__ == "__main__":
    main()
