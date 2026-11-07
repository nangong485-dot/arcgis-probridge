"""Local agent service for the ProBridge window.

Serves a chat UI and turns a sentence into a sequence of bridge calls against the
running ArcGIS Pro. Standard library only, so it starts instantly and needs no
key. `plan()` is the only place that understands language — swap it for an LLM
call later and nothing else changes.

    python agent/agent_server.py        # http://127.0.0.1:7799
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "client"))

from probridge import ProBridge, ProBridgeError  # noqa: E402

PORT = int(os.environ.get("PROBRIDGE_AGENT_PORT", "7799"))
DATA = os.path.join(ROOT, "data", "bj")
OUT = os.path.join(ROOT, "out")
UI = os.path.join(ROOT, "agent", "index.html")

# --------------------------------------------------------------- study areas

AREAS = {
    "北京": {
        "boundary": os.path.join(DATA, "bj_boundary.shp"),
        "provinces": os.path.join(DATA, "provinces.shp"),
        "dem": os.path.join(DATA, "bj_dem_rgb_v3.tif"),
        "lucc": os.path.join(DATA, "bj_lucc_rgb_v3.tif"),
        "dem_raw": os.path.join(DATA, "bj_dem.tif"),
        "lucc_raw": os.path.join(DATA, "bj_lucc.tif"),
    },
}


def plan(message: str) -> dict:
    """Sentence -> intent. Rule based on purpose: this is the seam an LLM plugs into."""
    text = message.strip()
    low = text.lower()

    area = next((k for k in AREAS if k in text), "北京")
    a = AREAS[area]

    wants_figure = any(k in text for k in ("研究区图", "三子图", "位置图", "出图", "成图", "整套"))
    wants_dem = any(k in text for k in ("高程", "dem", "地形", "海拔"))
    wants_lucc = any(k in text for k in ("土地", "lucc", "利用", "覆被"))
    wants_layers = any(k in text for k in ("图层", "有哪些", "看看", "列出"))

    if any(k in text for k in ("清空", "重置", "清理")):
        return {"intent": "clear", "area": area}

    if wants_figure:
        panels = [
            {"map": "Map1a", "layers": [a["provinces"], a["boundary"]],
             "caption": "(a) 研究区位置"},
            {"map": "Map1b", "layers": [a["dem"]], "caption": "(b) 高程 (m)"},
            {"map": "Map1c", "layers": [a["lucc"]], "caption": "(c) 土地利用"},
        ]
        return {"intent": "figure", "area": area, "panels": panels}

    if wants_dem:
        return {"intent": "single", "area": area, "layer": a["dem"], "caption": "高程 (m)"}

    if wants_lucc:
        return {"intent": "single", "area": area, "layer": a["lucc"], "caption": "土地利用"}

    if wants_layers:
        return {"intent": "layers", "area": area}

    return {"intent": "help", "area": area}


# ------------------------------------------------------------------ executor

def run_plan(p: dict) -> dict:
    b = ProBridge()
    steps: list[dict] = []

    def note(label, detail="", ok=True):
        steps.append({"label": label, "detail": str(detail), "ok": ok})

    try:
        info = b.ping()
        if not info.get("project"):
            note("连接 Pro", "没有打开的工程", False)
            return {"reply": "Pro 里没有打开工程，先打开一个再试。", "steps": steps, "image": None}
        note("连接 Pro", f"{info['project']}")

        if p["intent"] == "help":
            return {
                "reply": "我能做这些：\n· 画北京研究区图（1a/1b/1c 三子图）\n"
                         "· 只看高程 / 只看土地利用\n· 列出图层\n· 清空图层",
                "steps": steps, "image": None,
            }

        if p["intent"] == "layers":
            names = [l["name"] for l in b.list_layers()]
            note("读取图层", f"{len(names)} 个")
            return {"reply": "当前图层：" + ("、".join(names) if names else "（空）"),
                    "steps": steps, "image": None}

        if p["intent"] == "clear":
            removed = b.clear_layers("pb_")
            note("清空图层", f"移除 {removed['removed']} 个")
            return {"reply": f"清掉了 {removed['removed']} 个图层。", "steps": steps, "image": None}

        if p["intent"] == "single":
            if not os.path.exists(p["layer"]):
                return {
                    "reply": "研究区数据还没生成。先运行 tools/fetch_study_area.py，"
                             "再用 Pro 的 Python 运行 tools/prepare_study_area.py。",
                    "steps": steps, "image": None,
                }
            out = os.path.join(OUT, "agent_single.png")
            result = b.compose(out, layout="A4 Landscape", layers=[p["layer"]],
                               title=p["caption"])
            for step in result["steps"]:
                if "frame" in step:
                    note("绑定地图框", step["frame"]["map"])
                elif "export" in step:
                    note("导出", f"{step['export']['bytes'] / 1024:.0f} KB")
            return {"reply": f"出图完成：{p['caption']}", "steps": steps,
                    "image": "/out/" + os.path.basename(out)}

        if p["intent"] == "figure":
            missing = [
                path for panel in p["panels"] for path in panel["layers"]
                if not os.path.exists(path)
            ]
            if missing:
                return {
                    "reply": "研究区数据还没生成。先运行 tools/fetch_study_area.py，"
                             "再用 Pro 的 Python 运行 tools/prepare_study_area.py "
                             "和 tools/render_panels.py。",
                    "steps": steps, "image": None,
                }
            # layouts are cheap but names are not reusable: pick the next free one
            existing = set(b.ping().get("layouts") or [])
            i = 1
            while f"研究区图{i}" in existing:
                i += 1
            name = f"研究区图{i}"
            out = os.path.join(OUT, "agent_figure.png")
            result = b.build_figure(out, p["panels"], name=name)
            for step in result["steps"]:
                if "map" in step and "created" in step["map"]:
                    note("准备地图", step["map"]["map"])
                elif "layer" in step:
                    note("加载图层", os.path.basename(step["layer"]["path"]))
                elif "render" in step:
                    note("锁定配色", step["render"]["layer"])
                elif "layout" in step:
                    note("创建版式", f"{len(step['layout']['frames'])} 个图框")
                elif "export" in step:
                    note("导出", f"{step['export']['bytes'] / 1024:.0f} KB")
            return {"reply": "三子图完成（1a 位置 / 1b 高程 / 1c 土地利用）。",
                    "steps": steps, "image": "/out/" + os.path.basename(out)}

    except ProBridgeError as exc:
        note("失败", exc.msg, False)
        return {"reply": f"出错了：{exc.msg}", "steps": steps, "image": None}
    except Exception as exc:  # noqa: BLE001
        note("失败", str(exc), False)
        traceback.print_exc()
        return {"reply": f"出错了：{exc}", "steps": steps, "image": None}

    return {"reply": "没听懂。", "steps": steps, "image": None}


# --------------------------------------------------------------------- http

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _local_request(self) -> bool:
        hosts = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
        origins = {f"http://{host}" for host in hosts}
        host = self.headers.get("Host", "").lower()
        origin = self.headers.get("Origin")
        return host in hosts and (origin is None or origin.lower() in origins)

    def _send(self, code, body: bytes, ctype="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._local_request():
            return self._send(403, b"forbidden", "text/plain")
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            with open(UI, "rb") as fh:
                return self._send(200, fh.read(), "text/html; charset=utf-8")
        if path.startswith("/out/"):
            target = os.path.join(OUT, os.path.basename(path))
            if os.path.exists(target):
                with open(target, "rb") as fh:
                    return self._send(200, fh.read(), "image/png")
        if path == "/api/state":
            try:
                info = ProBridge(timeout=5).ping()
                return self._send(200, json.dumps(
                    {"ok": True, "data": info}, ensure_ascii=False).encode())
            except ProBridgeError as exc:
                return self._send(200, json.dumps(
                    {"ok": False, "error": exc.msg}, ensure_ascii=False).encode())
        return self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if not self._local_request():
            return self._send(403, b"forbidden", "text/plain")
        if urlparse(self.path).path != "/api/chat":
            return self._send(404, b"not found", "text/plain")
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        message = payload.get("message", "")
        p = plan(message)
        result = run_plan(p)
        result["intent"] = p["intent"]
        self._send(200, json.dumps(result, ensure_ascii=False).encode())


def main():
    os.makedirs(OUT, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"[agent] http://127.0.0.1:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
