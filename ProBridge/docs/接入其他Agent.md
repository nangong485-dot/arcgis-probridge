# 让别的 Agent 使用 ProBridge

一句话：**Pro 里跑的 addin 就是服务端（127.0.0.1:7788），谁都能连；MCP / CLI / Python / 裸 TCP 只是四种接法。**
接法选择取决于"你的 agent 会什么"：会 MCP 就用 MCP，只会跑命令就用 CLI，什么都不行就直接发 JSON。

---

## 0. 唯一的前提

```powershell
$repo = 'C:\path\to\arcgispro\ProBridge'

# ArcGIS Pro 必须开着，且 addin 已加载（Pro 内能看到「AI 制图」标签）
& "$repo\.venv\Scripts\python.exe" "$repo\client\cli.py" ping
```

返回 `bridge` / `project` / `maps` 就说明 7788 在听。连不上只有一个原因：Pro 没开，或 addin 没加载
（部署：退 Pro → `cd ProBridge\server; .\build.ps1 -SkipRegister` → 重开 Pro）。

---

## 1. 路线 A：MCP（推荐，21 个工具）

MCP 服务端是 stdio 进程，**每个 agent 客户端自己拉起一份**，互不干扰；它们共享同一个 7788。

### 通用 JSON（Claude Desktop / 多数客户端）

```json
{
  "mcpServers": {
    "probridge": {
      "command": "C:\\path\\to\\arcgispro\\ProBridge\\.venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\arcgispro\\ProBridge\\mcp_server.py"]
    }
  }
}
```

### Claude Code（本机已装 2.1.270）

```powershell
claude mcp add probridge --scope user -- `
  "C:\path\to\arcgispro\ProBridge\.venv\Scripts\python.exe" `
  "C:\path\to\arcgispro\ProBridge\mcp_server.py"
claude mcp list
```

（`--scope user` 全局可用；去掉则只对当前项目生效。）

### Codex（`%USERPROFILE%\.codex\config.toml` 追加）

```toml
[mcp_servers.probridge]
command = "C:\\path\\to\\arcgispro\\ProBridge\\.venv\\Scripts\\python.exe"
args = ["C:\\path\\to\\arcgispro\\ProBridge\\mcp_server.py"]
```

### Cursor

项目级 `.cursor/mcp.json`（自行创建），或全局 `%USERPROFILE%\.cursor\mcp.json`，内容同上面的通用 JSON。

### VS Code（`.vscode/mcp.json`）

```json
{
  "servers": {
    "probridge": {
      "type": "stdio",
      "command": "C:\\path\\to\\arcgispro\\ProBridge\\.venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\arcgispro\\ProBridge\\mcp_server.py"]
    }
  }
}
```

### 可用工具（21）

`pro_ping` `pro_list_layers` `pro_add_layer` `pro_fit_layer` `pro_zoom_to_extent` `pro_clear_layers`
`pro_export_layout` `pro_list_elements` `pro_set_text` `pro_set_visible` `pro_compose` `pro_open_layout`
`pro_import_layout` `pro_activate_map` `pro_bind_map_frame` `pro_save` `pro_build_figure`
`pro_run_gp` `pro_run_arcpy` **`pro_set_symbology`** **`pro_add_surrounds`**

环境变量可选：`PROBRIDGE_HOST`（默认 127.0.0.1）、`PROBRIDGE_PORT`（默认 7788）。

---

## 2. 路线 B：CLI（agent 只要能跑 shell）

24 个子命令，**全部输出 JSON**，用 `--help` 自查：

```powershell
$repo = 'C:\path\to\arcgispro\ProBridge'
$py = "$repo\.venv\Scripts\python.exe"
$cli = "$repo\client\cli.py"
& $py $cli layers
& $py $cli add-layer "C:\...\bj_boundary.shp" --name pb_boundary
& $py $cli symbology pb_boundary --kind feature --fill none --outline "#262626" --width 1.2
& $py $cli surrounds pb_final --legend-x 144 --legend-y 60
& $py $cli export pb_final "C:\...\out.png" --dpi 300
```

给 agent 的提示词里只要写清「用这份 CLI，先 ping 再干活，路径一律绝对路径」即可。

---

## 3. 路线 C：Python SDK（嵌进 agent 的逻辑）

```python
import sys
sys.path.insert(0, r"C:\path\to\arcgispro\ProBridge")
from client.probridge import ProBridge, ProBridgeError

pb = ProBridge("127.0.0.1", 7788, timeout=120)
pb.ping()
pb.add_layer(r"C:\...\bj_dem.tif", name="pb_dem")
pb.call("set_symbology", layer="pb_dem", kind="raster_stretch",
        stretch="minmax", gamma=0.55, colors=["#9FBFA3", "#BCD19A", "#D9DFA6"])
pb.export_layout("pb_final", r"C:\...\out.png", dpi=300)
```

`pb.call(cmd, **args)` 是万能入口，命令名与 CLI 的连字符形式互转（`add-layer` ↔ `add_layer`）。

---

## 4. 路线 D：裸 TCP（非 Python、无 MCP 的 agent）

**一行一个 JSON，UTF-8，无长度头**，连 `127.0.0.1:7788`：

```
→ {"id":"1","cmd":"ping","args":{}}
← {"id":"1","ok":true,"data":{"bridge":"0.3.0","project":"MyProject.aprx", ...}}

→ {"id":"2","cmd":"add_layer","args":{"path":"C:\\...\\bj_boundary.shp","name":"pb_boundary"}}
← {"id":"2","ok":true,"data":{"name":"pb_boundary","path":"..."}}
```

- 失败：`{"id":"2","ok":false,"error":{"code":"EXCEPTION","msg":"..."}}`
- 命令名是 **下划线** 形式（`add_layer` / `set_symbology` / `add_surrounds` …），共 34 个
- 服务端每连接一个 Task，**多个 agent 可同时连**；但真正操作 Pro 的调用都进 `QueuedTask`（UI 线程串行），所以并发会排队，不要指望并行加速
- 超时自己定：`run_gp` / `run_arcpy` 可能跑几十秒

---

## 5. 路线 E：HTTP 面板（7799）——只适合人用

`python agent/agent_server.py` 起 `http://127.0.0.1:7799`，只有两个端点：

- `GET /api/state`：当前工程/图层/版式快照
- `POST /api/chat`：`{"text": "把北京边界加进来并裁剪"}`，`plan()` 是规则式解析

它是给人点的面板，**不适合 agent 编排**（一次一句话，没有工具清单）。

---

## 6. 给 agent 的注意事项（都会真的咬人）

1. **路径全用绝对路径**；中文路径没问题（UTF-8 传输）。
2. **Pro 必须在前台跑着**，机器锁屏/睡眠不影响，但 Pro 崩了桥就断。
3. **`run_arcpy` 是任意代码执行**，桥只监听 loopback、无鉴权 —— 不要把这个端口暴露到局域网。
4. **改图层顺序**：桥只能"后加的在上"，要重排就 `remove-layer` 再 `add-layer`。
5. **导出前先 `bind-frame`**：布局图框会缓存范围，不重绑就导出旧范围。
6. **改完记得 `save`**：Pro 不 save，一关就丢。
7. 每次出图前 `clear --prefix pb_`，否则上一轮的 `pb_*` 图层会叠在上面。
