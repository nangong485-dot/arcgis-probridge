"""ProBridge client: drive a running ArcGIS Pro session over localhost.

Standard library only, so it runs in any Python 3.9+ interpreter.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import uuid
from typing import Any

# Pro's own interpreter. It is the only one that has arcpy, and the only one
# allowed to run analysis scripts (do not install mcp/arcpy into each other).
PRO_PYTHON = os.environ.get(
    "PROBRIDGE_PYTHON",
    r"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe",
)
SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
JOBS_DIR = os.path.join(
    os.path.expanduser("~"), "AppData", "Local", "ProBridge", "jobs"
)


class ProBridgeError(RuntimeError):
    def __init__(self, code: str, msg: str):
        super().__init__(f"{code}: {msg}")
        self.code = code
        self.msg = msg


class ProBridge:
    def __init__(self, host: str = "127.0.0.1", port: int = 7788, timeout: float = 120.0):
        self.host = host
        self.port = port
        self.timeout = timeout

    def call(self, cmd: str, timeout: float | None = None, **args: Any) -> Any:
        payload = json.dumps(
            {"id": uuid.uuid4().hex[:8], "cmd": cmd, "args": args},
            ensure_ascii=False,
        ) + "\n"

        try:
            with socket.create_connection(
                (self.host, self.port), timeout=timeout or self.timeout
            ) as sock:
                sock.sendall(payload.encode("utf-8"))
                with sock.makefile("rb") as fh:
                    line = fh.readline()
        except OSError as exc:
            raise ProBridgeError(
                "NO_BRIDGE",
                f"无法连接 {self.host}:{self.port}（Pro 是否已启动、ProBridge 是否已加载？）: {exc}",
            ) from exc

        if not line:
            raise ProBridgeError("EMPTY_RESPONSE", "桥没有返回任何内容")

        resp = json.loads(line.decode("utf-8"))
        if not resp.get("ok"):
            err = resp.get("error") or {}
            raise ProBridgeError(err.get("code", "UNKNOWN"), err.get("msg", ""))

        return resp.get("data")

    def ping(self) -> dict:
        return self.call("ping")

    def list_layers(self, map_name: str | None = None) -> list:
        return self.call("list_layers", map=map_name)

    def add_layer(self, path: str, name: str | None = None, map_name: str | None = None) -> dict:
        return self.call("add_layer", path=os.path.abspath(path), name=name, map=map_name)

    def remove_layer(self, name: str, map_name: str | None = None) -> dict:
        return self.call("remove_layer", name=name, map=map_name)

    def clear_layers(self, prefix: str = "pb_", map_name: str | None = None) -> dict:
        return self.call("clear_layers", prefix=prefix, map=map_name)

    def layer_extent(self, layer: str, map_name: str | None = None) -> dict:
        return self.call("get_layer_extent", layer=layer, map=map_name)

    def zoom_to_extent(self, extent: dict, duration_ms: int = 800) -> dict:
        return self.call("zoom_to_extent", duration_ms=duration_ms, **extent)

    def fit(self, layer: str, ratio: float = 0.075, aspect: float | None = None,
            duration_ms: int = 800) -> dict:
        extent = self.layer_extent(layer)
        padded = pad_extent(extent, ratio=ratio, aspect=aspect)
        return self.zoom_to_extent(padded, duration_ms=duration_ms)

    def refresh(self) -> dict:
        return self.call("refresh")

    def activate_map(self, map_name: str | None = None) -> dict:
        return self.call("activate_map", map=map_name)

    def import_layout(self, pagx: str) -> dict:
        return self.call("import_layout", pagx=os.path.abspath(pagx))

    def open_layout(self, name: str) -> dict:
        return self.call("open_layout", name=name)

    def export_layout(self, name: str, path: str, dpi: int = 300, fmt: str = "png") -> dict:
        return self.call("export_layout", name=name, path=os.path.abspath(path),
                         dpi=dpi, format=fmt)

    def list_elements(self, layout: str) -> list:
        return self.call("list_elements", layout=layout)

    def set_text(self, layout: str, text: str, name: str | None = None,
                 index: int = 0) -> dict:
        return self.call("set_text", layout=layout, text=text, name=name, index=index)

    def set_visible(self, layout: str, name: str, visible: bool = True) -> dict:
        return self.call("set_visible", layout=layout, name=name, visible=visible)

    def set_layer_render(self, layer: str, mode: str = "rgb",
                         map_name: str | None = None) -> dict:
        return self.call("set_layer_render", layer=layer, mode=mode, map=map_name)

    def create_map(self, name: str) -> dict:
        return self.call("create_map", name=name)

    def create_panel_layout(self, name: str, page_w: float, page_h: float,
                            frames: list) -> dict:
        return self.call("create_panel_layout", name=name, page_w=page_w,
                         page_h=page_h, frames=frames)

    def build_figure(self, out_path: str, panels: list, name: str = "研究区图",
                     title: str | None = None, dpi: int = 300,
                     fmt: str = "png", save: bool = False) -> dict:
        """Assemble a multi-panel study-area figure.

        `panels` is a list of dicts: {map, layers: [path, ...], caption}.
        A4 landscape, three equal panels across the top, captions underneath.
        """
        page_w, page_h = 297.0, 210.0
        margin, gap, cap_h = 10.0, 6.0, 6.0
        panel_h = 92.0
        top = page_h - margin - cap_h
        y = top - panel_h
        width = (page_w - 2 * margin - gap * (len(panels) - 1)) / len(panels)

        steps = []
        frames = []
        for i, panel in enumerate(panels):
            map_name = panel["map"]
            steps.append({"map": self.create_map(map_name)})
            for layer in panel.get("layers", []):
                added = self.add_layer(layer, map_name=map_name)
                steps.append({"layer": added})
                if layer.lower().endswith((".tif", ".tiff")):
                    # keep the colours baked into the raster instead of letting
                    # Pro stretch them
                    steps.append({"render": self.set_layer_render(added["name"], "rgb", map_name)})

            x = margin + i * (width + gap)
            frames.append({
                "name": f"1{'abc'[i] if i < 3 else i}",
                "map": map_name,
                "x": round(x, 2), "y": round(y, 2),
                "w": round(width, 2), "h": round(panel_h, 2),
                "title": panel.get("caption", ""),
            })

        steps.append({"layout": self.create_panel_layout(name, page_w, page_h, frames)})

        if title:
            steps.append({"title": self.set_text(name, title, name="图题")})

        steps.append({"export": self.export_layout(name, out_path, dpi=dpi, fmt=fmt)})

        if save:
            steps.append({"save": self.save()})

        return {"layout": name, "out": os.path.abspath(out_path), "steps": steps}

    def bind_map_frame(self, layout: str, map_name: str | None = None,
                       layer: str | None = None, ratio: float = 0.075,
                       frame: int = 0) -> dict:
        return self.call("bind_map_frame", layout=layout, map=map_name,
                         layer=layer, ratio=ratio, frame=frame)

    def save(self) -> dict:
        return self.call("save")

    def run_gp(self, tool: str, params: list | None = None,
               timeout_s: float = 3600, overwrite: bool = False) -> dict:
        """Run any geoprocessing tool in the live Pro session.

        `params` are positional values in the tool's parameter order, e.g.
        ["D:/in.shp", "D:/out.shp", "1000 Meters"] for analysis.Buffer.
        The C# side uses GPExecuteToolFlags.AddOutputsToMap, so vector and
        raster outputs appear in the active map automatically.

        `timeout_s` is both the socket wait and the GP cancellation window:
        when it expires, the C# side cancels the task. Whether the underlying
        tool stops immediately depends on the tool itself. The default is an hour.

        `overwrite` defaults to False: an existing output makes the tool fail
        instead of being replaced. Pass overwrite=True only when replacement is
        intended.

        Relative dataset paths are made absolute against the caller's cwd,
        because Pro resolves them against its own working directory instead.
        """
        resolved = [_resolve_gp_value(v) for v in (params or [])]
        return self.call("run_gp", timeout=timeout_s, tool=tool, params=resolved,
                         timeout_s=timeout_s, overwrite=overwrite)

    def run_arcpy(self, code: str | None = None, script: str | None = None,
                  args: list | None = None, cwd: str | None = None,
                  timeout_s: float = 600, add_layers: list | None = None,
                  map_name: str | None = None) -> dict:
        """Run an arcpy script in Pro's own Python, as a separate process.

        Give either inline `code` or a `script` path (relative paths are looked
        up in ProBridge/scripts first). The process cannot see the live
        ArcGISProject("CURRENT"); it works with data paths and can open an
        .aprx by path with arcpy.mp. To put results on the current map, print

            PROBRIDGE_RESULT: {"layers": ["D:/out/buffer.shp"]}

        or write the same JSON to the path in the PROBRIDGE_RESULT env var.
        `add_layers` overrides that list; pass [] to add nothing.

        Returns exit code, captured output, parsed result and the layers that
        were added. A timeout kills the whole process tree.
        """
        if bool(code) == bool(script):
            raise ValueError("code 和 script 必须二选一（不能同时给或都不给）")

        if not os.path.isfile(PRO_PYTHON):
            raise FileNotFoundError(
                f"找不到 Pro 的 Python: {PRO_PYTHON}。"
                "可用环境变量 PROBRIDGE_PYTHON 指定。"
            )

        job_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        job_dir = os.path.join(JOBS_DIR, job_id)
        os.makedirs(job_dir, exist_ok=True)

        if code is not None:
            script_path = os.path.join(job_dir, "job.py")
            with open(script_path, "w", encoding="utf-8") as fh:
                fh.write(code)
        else:
            script_path = self._resolve_script(script)

        result_path = os.path.join(job_dir, "result.json")
        env = os.environ.copy()
        env["PROBRIDGE_RESULT"] = result_path
        env["PROBRIDGE_JOB_DIR"] = job_dir
        env["PROBRIDGE_SCRIPT_DIR"] = SCRIPTS_DIR
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONPATH"] = os.pathsep.join(
            [SCRIPTS_DIR] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
        )

        cmd = [PRO_PYTHON, "-u", script_path] + [str(a) for a in (args or [])]
        # Relative paths in arguments resolve against the caller's cwd, which is
        # what a CLI user expects. The job directory is for scratch output and
        # is exposed as PROBRIDGE_JOB_DIR / _common.job_dir().
        run_cwd = os.path.abspath(cwd) if cwd else os.getcwd()
        if not os.path.isdir(run_cwd):
            raise FileNotFoundError(f"工作目录不存在: {run_cwd}")

        started = time.time()
        timed_out = False
        proc = subprocess.Popen(
            cmd, cwd=run_cwd, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._kill_tree(proc.pid)
            try:
                stdout, stderr = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate()

        duration_s = round(time.time() - started, 2)
        payload, result_source, warnings = self._read_arcpy_result(result_path, stdout)

        wanted = add_layers if add_layers is not None else payload.get("layers") or []
        if isinstance(wanted, (str, dict)):
            wanted = [wanted]
        added = []
        for item in wanted:
            if isinstance(item, str):
                layer_path, layer_name, layer_map = item, None, map_name
            elif isinstance(item, dict):
                layer_path = item.get("path") or item.get("layer")
                layer_name = item.get("name")
                layer_map = item.get("map") or map_name
            else:
                warnings.append(f"跳过无法识别的图层项: {item!r}")
                continue
            if not layer_path:
                continue
            try:
                added.append(self.add_layer(layer_path, layer_name, layer_map))
            except ProBridgeError as exc:
                warnings.append(
                    f"成果已生成，但未能加入地图: {layer_path} ({exc.code}: {exc.msg})"
                )

        success = not timed_out and proc.returncode == 0 and not payload.get("error")

        return {
            "success": success,
            "exit_code": proc.returncode,
            "timed_out": timed_out,
            "duration_s": duration_s,
            "script": script_path,
            "job_dir": job_dir,
            "stdout": _tail(stdout),
            "stderr": _tail(stderr),
            "result": payload,
            "result_source": result_source,
            "layers": added,
            "warnings": warnings,
        }

    @staticmethod
    def _resolve_script(script: str) -> str:
        candidates = (
            [script] if os.path.isabs(script) else
            [os.path.join(SCRIPTS_DIR, script), os.path.abspath(script)]
        )
        for candidate in candidates:
            if os.path.isfile(candidate):
                return os.path.abspath(candidate)
        raise FileNotFoundError(
            f"找不到脚本 {script}，已查找: {', '.join(candidates)}"
        )

    @staticmethod
    def _read_arcpy_result(path: str, stdout: str | None):
        payload = None
        source = None
        warnings = []

        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    payload = json.load(fh)
                source = "file"
            except (OSError, json.JSONDecodeError) as exc:
                warnings.append(f"读取 result.json 失败: {exc}")

        if payload is None:
            for line in reversed((stdout or "").splitlines()):
                line = line.strip()
                if line.startswith("PROBRIDGE_RESULT:"):
                    raw = line[len("PROBRIDGE_RESULT:"):].strip()
                    try:
                        payload = json.loads(raw)
                        source = "stdout"
                    except json.JSONDecodeError as exc:
                        warnings.append(f"PROBRIDGE_RESULT 不是合法 JSON: {exc}")
                    break

        if payload is None:
            payload = {}
        elif not isinstance(payload, dict):
            payload = {"value": payload}
        return payload, source, warnings

    @staticmethod
    def _kill_tree(pid: int) -> None:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return
        try:
            os.kill(pid, 9)
        except OSError:
            pass

    def compose(self, out_path: str, template: str | None = None,
                layout: str | None = None, layers=None, title: str | None = None,
                hide=None, dpi: int = 300, ratio: float = 0.075,
                clear_prefix: str = "pb_", fmt: str = "png",
                save: bool = False) -> dict:
        """One call: reset layers, add data, import the template, bind its map frame,
        set the title, export.

        `layers` accepts a path, or (path, name) pairs. The last layer added is the
        one the map frame gets framed on.
        """
        steps: list[dict] = []

        if clear_prefix:
            steps.append({"clear": self.clear_layers(clear_prefix)})

        added = []
        for item in layers or []:
            if isinstance(item, (tuple, list)):
                path = item[0]
                name = item[1] if len(item) > 1 else None
            else:
                path, name = item, None
            if not name:
                # pb_ prefix is what clear_layers sweeps up next run
                name = "pb_" + os.path.splitext(os.path.basename(path))[0]
            added.append(self.add_layer(path, name))
        if added:
            steps.append({"layers": added})

        if layout is None:
            if not template:
                raise ValueError("template 和 layout 至少给一个")
            try:
                imported = self.import_layout(template)
                steps.append({"import": imported})
                layout = imported["name"]
            except ProBridgeError as exc:
                # Re-running the same job should not create "A4 Landscape 1".
                guess = os.path.splitext(os.path.basename(template))[0].replace("_", " ")
                if guess in (self.ping().get("layouts") or []):
                    layout = guess
                    steps.append({"import": f"reused {guess}"})
                else:
                    raise exc

        target = added[-1]["name"] if added else None
        steps.append({"frame": self.bind_map_frame(layout, layer=target, ratio=ratio)})

        for element in hide or []:
            steps.append({"hide": self.set_visible(layout, element, False)})

        if title:
            steps.append({"title": self.set_text(layout, title)})

        steps.append({"export": self.export_layout(layout, out_path, dpi=dpi, fmt=fmt)})

        if save:
            steps.append({"save": self.save()})

        return {"layout": layout, "out": os.path.abspath(out_path), "steps": steps}


_PATH_EXT = {
    ".shp", ".dbf", ".shx", ".prj", ".cpg", ".tif", ".tiff", ".img",
    ".jpg", ".jpeg", ".png", ".pdf", ".gdb", ".mdb", ".sqlite",
    ".geojson", ".json", ".csv", ".xlsx", ".lyrx", ".aprx", ".pagx",
    ".las", ".laz", ".txt", ".xml",
}


def _resolve_gp_value(value):
    """Make dataset paths absolute for a GP call, leave field names/units alone."""
    if not isinstance(value, str):
        return value
    s = value.strip()
    if not s or s.lower().startswith(("memory\\", "memory/", "in_memory\\", "in_memory/")):
        return value
    if os.path.exists(s):
        return os.path.abspath(s)

    low = s.lower()
    has_sep = "\\" in s or "/" in s
    looks_like_path = has_sep and (
        os.path.splitext(low)[1] in _PATH_EXT
        or ".gdb" in low
        or s.endswith(("\\", "/"))
    )
    return os.path.abspath(s) if looks_like_path else value


def _tail(text: str | None, max_chars: int = 20000) -> str:
    """Keep the end of long logs: tracebacks and GP messages are there."""
    text = text or ""
    if len(text) <= max_chars:
        return text
    return f"...[{len(text) - max_chars} chars truncated]...\n" + text[-max_chars:]


def pad_extent(extent: dict, ratio: float = 0.075, aspect: float | None = None) -> dict:
    """Expand an extent by `ratio` on every side.

    If `aspect` (width / height of the target frame) is given, the extent is first
    grown on its short side to match that aspect, then scaled uniformly. Scaling a
    non-matching aspect by a single factor does not produce even margins.
    """
    xmin, ymin = float(extent["xmin"]), float(extent["ymin"])
    xmax, ymax = float(extent["xmax"]), float(extent["ymax"])

    w, h = xmax - xmin, ymax - ymin
    if w <= 0 or h <= 0:
        raise ValueError("extent 宽或高为 0")

    if aspect:
        current = w / h
        if current < aspect:
            w = h * aspect
        else:
            h = w / aspect

    cx, cy = (xmin + xmax) / 2.0, (ymin + ymax) / 2.0
    w *= 1.0 + 2.0 * ratio
    h *= 1.0 + 2.0 * ratio

    return {
        "xmin": cx - w / 2.0,
        "ymin": cy - h / 2.0,
        "xmax": cx + w / 2.0,
        "ymax": cy + h / 2.0,
    }
