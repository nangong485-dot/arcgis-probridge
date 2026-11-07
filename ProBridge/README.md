# ProBridge — 用外部程序操控正在运行的 ArcGIS Pro

一句话：在 Claude / Cursor / 命令行里发一条指令，**当前打开着的** Pro 窗口里图层出现、镜头推过去、模板套上、布局导出成 PNG。

已验证环境：ArcGIS Pro 3.5.2 / .NET 8 / Windows 11。

---

## 一、现在能做什么

| 命令 | 说明 |
| :-- | :-- |
| `ping` | 返回工程名、地图列表、布局列表 |
| `list_layers` | 名称 / 类型 / 可见性 |
| `add_layer` | shp / gdb 要素类 / 栅格均可 |
| `remove_layer` | 按名删除 |
| `clear_layers` | 按前缀批量删除（解决图层累积） |
| `get_layer_extent` | 返回包络框 + wkid |
| `zoom_to_extent` | 带时长参数，有动画过渡 |
| `fit` | 自动留白（先补短边再等比放大） |
| `refresh` | 强制重绘 |
| `import_layout` | 导入 `.pagx` 模板到工程 |
| `bind_map_frame` | **把布局里的地图框绑到某个 Map，并框住某个图层** |
| `open_layout` | 切换到布局视图 |
| `activate_map` | 切回地图视图 |
| `export_layout` | A4 横向 300dpi → 3508×2480 PNG；支持 png/jpg/tiff/pdf |
| `list_elements` | 列出布局元素（名称/类型/文字），找标题用 |
| `set_text` | 改文字元素（标题、副标题） |
| `set_visible` | 显隐元素（模板里两条比例尺，关掉一条） |
| `set_layer_render` | 锁定栅格渲染（`rgb` 自动绑定 0/1/2 波段并关掉 Pro 默认拉伸） |
| `set_symbology` | 走 CIM 改符号：栅格色带/拉伸、要素填充/描边、点符号、分级设色（自然断点/分位/等距） |
| `add_surrounds` | 版式收尾：公制比例尺（自绘）+ 指北针 + 图例（7pt、隐藏字段名） |
| `create_map` | 新建地图 |
| `create_panel_layout` | **新建多图框版式**（A4 横向，坐标单位 mm） |
| `save` | 保存工程（否则改动一重启就没了） |
| `run_gp` | **在 Pro 里跑任意 GP 工具**（缓冲区、叠加、坡度……），成果自动加图 |
| `run_arcpy` | **用 Pro 自带 arcpy 跑脚本**（独立进程，任意分析代码；按约定把成果加图） |

`compose()` 与 `build_figure()` 是 Python 侧的编排：

- `compose(out, template=..., layers=[...], title=..., hide=[...])` —— 套单图框模板出图
- `build_figure(out, panels=[{map, layers, caption}])` —— **三子图研究区图（1a/1b/1c）**

`run_gp()` 与 `run_arcpy()` 是两条不同的分析路线，见第四节末尾。

自检（Pro 开着、工程已加载时运行）：

```
python tools/verify_bridge.py
```

```
  PASS  ping               smoke.aprx maps=['Map'] layouts=['A4_Smoke']
  PASS  activate_map_initial back to Map
  PASS  clear_layers       removed 1
  PASS  add_layer          added pb_dem
  PASS  list_layers        layers=['pb_dem']
  PASS  get_layer_extent   116.000,39.000 -> 117.202,40.102
  PASS  zoom_to_extent     zoomed True
  PASS  refresh            redrawn True
  PASS  import_layout      imported A4 Landscape
  PASS  bind_map_frame     frame 0/1 -> map Map
  PASS  open_layout        opened A4 Landscape
  PASS  activate_map       back to Map
  PASS  export_layout      verify_flow.png 2339x1654 45942 bytes
  PASS  save               saved .../smoke.aprx
  PASS  remove_layer       removed pb_dem
  PASS  run_gp             verify_gp.tif 1640599 bytes, added to map
  PASS  run_arcpy          arcpy 3.5.2 ArcInfo python 3.11.11
  PASS  debug_threads      bg=38 ui=1 layouts=6

  18/18 passed
```

---

## 二、架构

```
Claude / Cursor ──MCP(stdio)──> mcp_server.py ──TCP 127.0.0.1:7788──> ProBridge.esriAddinX
                                                                          │ QueuedTask.Run / Dispatcher
                                                                          ▼
                                                                   ArcGIS Pro 界面
```

- **C# 壳**（`server/`）：只做原子操作和 GP 调用，写完基本不再动。
- **Python 侧**（`client/`、`mcp_server.py`、`scripts/`）：放所有会变的规则（留白、投影、选模板、分析脚本）。改规则不用重编译、不用重启 Pro。
- 监听循环在后台线程（纯 socket），SDK 调用按 Pro 的线程规则分流（见第五节）。

---

## 三、构建与安装

```powershell
cd ProBridge\server
.\build.ps1              # 编译 → 打包 → 注册 → 部署到 addin 目录与 AssemblyCache
```

**包结构必须是这样**（踩过的坑，写死在这里）：

```
ProBridge.esriAddinX  (zip)
├── Config.daml
├── Images\AddInDesktop32.png
└── Install\ProBridge.dll     ← DLL 必须在 Install\ 子目录
```

放在根目录时 Pro 会静默跳过，不报错、不加载、日志里什么都没有。这是 Esri 官方 `Esri.ProApp.SDK.Desktop.targets` 的打包约定。

**还有一步比打包更隐蔽：Pro 实际是从 `AssemblyCache` 加载程序集的，不从 `Install\` 加载。**

```
%LOCALAPPDATA%\ESRI\ArcGISPro\AssemblyCache\{8b1d4e2a-6f3c-4a19-9d7e-2c5b8f0a1e34}\ProBridge.dll
```

只更新 `Install\` 下的 DLL 时，新代码**完全不会生效**，你会一直对着旧程序集调试（我就这样白查了两轮）。`build.ps1` 现在两处都拷；**覆盖缓存前必须先退出 Pro**，否则报 `Device or resource busy`。

验证：
1. 启动 Pro → `netstat -ano | findstr 7788` 应有 LISTENING
2. `python client/cli.py ping` 返回工程信息
3. `python client/cli.py debug-threads` 返回线程 ID（能返回就说明是最新程序集）
4. `python client/cli.py run-gp sa.Slope data/smoke/DEM.tif out/verify_slope.tif DEGREE` 能出结果并自动加图
5. `python client/cli.py run-arcpy --script diagnose.py --no-add` 能返回 arcpy 3.5.2 / ArcInfo

如果 Add-in 与仓库分开部署，设置环境变量 `PROBRIDGE_HOME` 指向 `ProBridge/`
目录。Pro 内「AI 制图」面板会从该目录自动启动 `agent/agent_server.py`。

---

## 四、怎么用

### 命令行

```bash
python client/cli.py ping
python client/cli.py add-layer "data/smoke/DEM.tif" --name pb_dem
python client/cli.py fit pb_dem --ratio 0.075 --aspect 1.414
python client/cli.py import-layout templates/A4_Landscape.pagx
python client/cli.py bind-frame "A4 Landscape" --layer pb_dem --ratio 0.06
python client/cli.py open-layout "A4 Landscape"
python client/cli.py activate-map
python client/cli.py export "A4 Landscape" out/map.png --dpi 300
python client/cli.py save
```

### 对话驱动（MCP）

`mcp_server.py` 暴露 21 个工具。客户端配置（Claude Desktop `claude_desktop_config.json` / Cursor `mcp.json`）：

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

依赖只装在项目内的 `.venv` 里（`mcp<2`，2.x 把 `FastMCP` 改名成了 `MCPServer`），**不要装进 Pro 的 `arcgispro-py3`**。venv 丢了或换机器时这样重建（用 Pro 自带 python 当底座，`.venv/` 已在 `.gitignore` 里）：

```powershell
& 'C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe' -m venv .venv
.\.venv\Scripts\python.exe -m pip install "mcp<2"
.\.venv\Scripts\python.exe tools\mcp_smoke.py     # 握手 + 21 个工具；Pro 没开时 pro_ping 返回 NO_BRIDGE 属正常
```

> 旧的 `%USERPROFILE%\.workbuddy-ai\binaries\python\envs\probridge` 已不可用：WorkBuddy 自带的底座解释器（D 盘 `resources\vendor\python`）访问被拒，venv 启动即报 `did not find executable`。别再指过去。

`mcp_server.py` 启动时会把工作目录切到 `ProBridge/`，所以工具参数里的相对路径和命令行下含义一致。

然后就可以说："把 DEM.tif 加进来，缩放到它，留 7.5% 白边，套 A4_Landscape 模板，导出到 out/map.png"。

**换别的 agent**（Claude Code、Codex、VS Code、或不会 MCP 只认 shell 的）：四条接法（MCP / CLI / Python SDK / 裸 TCP 协议）都写在 [docs/接入其他Agent.md](docs/接入其他Agent.md)，含每家的配置片段和 7 条会被咬的坑。

### 空间分析：`run_gp` 还是 `run_arcpy`

| | `run_gp` | `run_arcpy` |
| :-- | :-- | :-- |
| 运行位置 | Pro 进程内（`Geoprocessing.ExecuteToolAsync`） | 独立的 Pro Python 进程 |
| `ArcGISProject("CURRENT")` | 通过 Pro 的当前工程间接可用 | **不可用**，只能按路径打开 `.aprx` |
| 成果加图 | 自动（`AddOutputsToMap`） | 脚本输出 `layers` 列表后自动加 |
| 适合 | 标准 GP 工具、单步分析 | 任意 arcpy、循环/批处理、复杂后处理 |

**`run_gp`**：参数按工具的“参数顺序”给，路径和线性单位用字符串：

```bash
python client/cli.py run-gp analysis.Buffer \
    data/bj/bj_districts_utm.shp out/bj_buffer.shp "1000 Meters"
python client/cli.py run-gp sa.Slope data/bj/bj_dem.tif out/bj_slope.tif DEGREE
```

MCP 里同样：

```python
pro_run_gp("analysis.Buffer",
           ["data/bj/bj_districts_utm.shp", "out/bj_buffer.shp", "1000 Meters"])
```

相对路径会先按调用者的当前目录转成绝对路径；`memory/`、`in_memory/` 例外。`timeout_s` 会同时作为客户端等待上限和 Pro 侧取消窗口；超时后 C# 会取消任务，但底层 GP 工具是否立即停止取决于工具本身。`overwrite` 默认 `False`，已有输出会让工具失败；需要覆盖时显式传 `overwrite=True`。

**`run_arcpy`**：二选一给 `code` 或 `script`，脚本目录 `scripts/` 会自动加入 `PYTHONPATH`。成果用一行约定交回：

```python
print('PROBRIDGE_RESULT: {"layers": ["D:/out/buffer.shp"]}')
```

或直接用 `scripts/_common.py`：

```python
from _common import emit
emit({"layers": [out]})
```

命令行：

```bash
python client/cli.py run-arcpy --script buffer.py \
    --arg data/bj/bj_districts_utm.shp --arg out/bj_buffer.shp --arg "1000 Meters"

python client/cli.py run-arcpy --code "import arcpy; print(arcpy.ProductInfo())" --no-add
```

作业的临时目录在 `%LOCALAPPDATA%\ProBridge\jobs\<时间戳>`，环境变量 `PROBRIDGE_JOB_DIR` 指向它，`PROBRIDGE_RESULT` 指向 `result.json`。超时会用 `taskkill /F /T` 杀掉整个进程树。

> `run_arcpy` 是任意代码执行，权限等同当前 Windows 用户。只运行可信脚本；桥只绑 `127.0.0.1`，不要改成 `0.0.0.0`。

---

## 五、Pro API 的线程规则（本项目的核心难点）

同一个桥里，命令要按不同的线程规则分流。搞错就是
`This method or property must be called on the thread this object was created on`。

| 类别 | 走哪里 | 典型 API |
| :-- | :-- | :-- |
| **MCT（主计算线程）** | `QueuedTask.Run(...)` | 图层、几何、`MapFrame.SetMap/SetCamera`、`ItemFactory.Create`、`Project.AddItem`、`MapView.Redraw` |
| **UI 线程** | `Application.Current.Dispatcher` | `ProApp.Panes.CreateLayoutPaneAsync` / `CreateMapPaneAsync`、`Project.SaveAsync` |
| **GP（自己管线程）** | 直接 `await`，**不要**套 `QueuedTask` | `Geoprocessing.ExecuteToolAsync`（非模态重载 + `AddOutputsToMap`） |
| 两者都不行 | — | `arcpy.mp.ArcGISProject("CURRENT")` 只在 Pro 进程内的 Python 里有效，外部进程拿不到 |

几条硬结论，都是实测撞出来的：

1. **`Project.AddItem` 是 MCT API**。官方 XML 文档里写得很清楚："This method must be called on the MCT"。放到 Dispatcher 上必炸——这是 `import_layout` 挂掉的真正原因。
2. **`MapView.Redraw` 也是 MCT**，不是 UI。`refresh` 一度被我放在 Dispatcher 上，同样炸。
3. **`Project.SaveAsync` 相反，要在 UI 线程**。在后台线程调会报 "different thread owns it"。
4. **读 `Project.Current.GetItems<T>()` 在 UI 线程是安全的**，不必额外套 QueuedTask（`debug_threads` 已验证：`layoutsOnUi=2, error=null`）。
5. **`open_layout` 之后 `MapView.Active` 变成 null**。所有依赖活动视图的命令（`fit` / `zoom_to_extent`）都会失效，必须先 `activate_map`。`GetMap()` 已经加了兜底：无活动视图时退回工程里第一个 Map，所以增删图层不受影响。
6. **`Geoprocessing.ExecuteToolAsync` 不能套 `QueuedTask`**（会死锁），也不能用带进度框的 5 参数重载（headless 会 NRE）。当前用的是 `(tool, values, environments, CancellationToken?, GPToolExecuteEventHandler, GPExecuteToolFlags.AddOutputsToMap)`。

`debug_threads` 就是为查这些加的，保留着——以后加新命令前先跑一下，能省很多时间。

---

## 六、可视化窗口（一句话操控）

```
浏览器 / Pro 内的面板 ──> agent_server.py :7799 ──> ProBridge :7788 ──> ArcGIS Pro
                              plan() 理解意图        QueuedTask / Dispatcher
```

启动：

```bash
python agent/agent_server.py          # 窗口服务，http://127.0.0.1:7799
python client/cli.py show-agent       # 让 Pro 里弹出面板窗口
```

界面里可以直接说：「画北京研究区图」「只看高程」「列出图层」「清空图层」。
左边是对话，右边是**执行过程**（每一步真实的 SDK 调用结果）和出图预览。

- 语言理解在 `agent/agent_server.py` 的 `plan()` 里，目前是关键词规则；换成 LLM 调用只改这一个函数，其余不动。
- `AgentPaneView` 用 WebView2 承载这个页面；WebView2 的 user-data 目录必须指到 `%LOCALAPPDATA%\ProBridge\WebView2`，否则在 Pro 里初始化会直接崩。
- 面板**不自动弹出**（曾经因为开机自动初始化 WebView2 把 Pro 弄崩），只通过 `show_agent` 或 Add-In 标签页的「AI 制图」按钮打开。
- 当前 Pro 没有注册 DAML 里的 dockPane（`debug_ui` 返回 `found:false`），所以走保底路径弹**浮动窗口**；停靠面板待修。

---

## 七、三子图研究区图（1a / 1b / 1c）

目标形态：一句话 → 位置图 + 高程 + 土地利用 三子图，带图例，直接出图。

### 数据准备（一次性）

仓库不附带真实 DEM、土地利用和行政边界文件：它们体积较大，且 DataV 边界没有
明确的再分发许可。先下载公开输入，再在本地生成研究区数据：

```powershell
# 仅用 Python 标准库下载，约 300 MB
.\.venv\Scripts\python.exe tools\fetch_study_area.py
```

```bash
# Pro 自带 GDAL 3.10 + numpy，不需要额外安装依赖
"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe" tools/prepare_study_area.py
"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe" tools/render_panels.py
```

数据源（都免密钥）：

| 数据 | 来源 | 说明 |
| :-- | :-- | :-- |
| DEM 30m | `s3.amazonaws.com/elevation-tiles-prod/skadi/` | SRTM 1″，公开桶 |
| 土地利用 10m | `esa-worldcover.s3.eu-central-1.amazonaws.com` | ESA WorldCover 2021 |
| 行政区划 | `geo.datav.aliyun.com/areas_v3/bound/` | 便捷但**非测绘级**，见下方合规提示 |

`prepare_study_area.py` 做：GeoJSON→shp、市界融合、SRTM 拼接、按边界裁剪、投影到 UTM 50N。
`render_panels.py` 做：分层设色×山体阴影、土地利用配色、边界外烧白底。

### 出图

```python
from probridge import ProBridge
ProBridge().build_figure("out/figure.png", [
    {"map": "Map1a", "layers": ["data/bj/provinces.shp", "data/bj/bj_boundary.shp"],
     "caption": "(a) 研究区位置"},
    {"map": "Map1b", "layers": ["data/bj/bj_dem_rgb.tif"], "caption": "(b) 高程 (m)"},
    {"map": "Map1c", "layers": ["data/bj/bj_lucc_rgb.tif"], "caption": "(c) 土地利用"},
])
```

**合规提示**：`bj_boundary.shp` / `provinces.shp` 来自 DataV，方便但不具测绘资质。正式发表前必须换成自然资源部标准地图（bzdt.ch.mnr.gov.cn）或天地图底图；任何全国图幅必须保留南海诸岛。

### 为什么配色不在 Pro 里做（以及怎么让 Pro 不改色）

Pro 对 RGB 栅格默认套百分比拉伸，会把已经定好的配色拉偏（分层设色被拉成青绿/灰）。实测：**即使把三波段都拉到 0–255、换 PIL 写干净的 TIFF + `.tfw`，Pro 3.5 仍然改色**——所以"只把数据做对"这条路走不通。

v0.2.0 起桥里有 `set_symbology`，走 CIM 直接写 `StretchType` 和波段映射：

```powershell
# 烘好的 RGB 底图：显式指定三波段 + 关掉拉伸，颜色才和源图一致
python client/cli.py symbology pb_relief --kind raster_rgb

# DEM 直接出分层设色（不用烘图，色带还能改）
python client/cli.py symbology pb_dem --kind raster_stretch --stretch minmax --gamma 0.55 `
    --colors "#9FBFA3" "#BCD19A" "#D9DFA6" "#EDE3B0" "#E2C99B" "#CBA983" "#B49C8C" "#DCD8D4" "#FFFFFF"

# 边界线改空心描边（0.6 pt）
python client/cli.py symbology pb_boundary --kind feature --fill none --outline "#3F3F3F" --width 0.6
```

两个坑：
- `--kind raster_stretch --stretch none` 用在 RGB 上会**全黑**——必须用 `raster_rgb`（它带 `UseRedBand/GreenBand/BlueBand` 和 0/1/2 索引），只写 stretch 是不够的。
- `--stretch percentclip` 会把 99% 以上的山头直接顶到色带顶端（一片白），DEM 出图用 `minmax` + `--gamma 0.55` 更稳。

图例仍然只有色块、没有分级——分级图例得用图形元素补，见"下一步"。

---

## 八、一条命令出成品图（分层设色 + 晕渲）

`tools/make_hypso_map.py` 把整条链串起来：DEM → 分层设色+晕渲烘图 → 按边界裁成研究区形状 → 进 Pro（加图层 + 上符号）→ 建版式 + 绑图框 → 导出 PNG。

```powershell
& 'C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe' `
    tools\make_hypso_map.py `
    --dem data\bj\bj_dem.tif --boundary data\bj\bj_boundary.shp `
    --out out\bj_hypso_map.png --title "分层设色 · 北京" --dpi 300
```

前置条件只有一条：Pro 开着、桥在听。中间产物落在 `out/pb_relief_raw.tif`（矩形）和 `out/pb_relief_masked.tif`（按边界裁好）。

配色规则见 [docs/美化规则.md](docs/美化规则.md)（Patterson & Jenny 高程色带 + ArcGIS Pro 晕渲参数），脚本里可调 `--t-gamma`（平原层次）、`--zfactor`（地形夸张）、`--shade-strength`（晕渲强度）、`--downsample`（1 = 原分辨率，慢）。

两个数据侧的坑，脚本里已经绕开：

1. **`arcpy.management.Clip` 的输出加进 Pro 会整张全黑**。它出来的是 U16 三波段，`set_symbology --kind raster_rgb` 也不认；`tools/mask_relief.py` 因此只借 arcpy 读顶点、按网格画掩膜，再用 numpy+PIL 抠图，输出 8 bit TIFF（附 `.tfw`/`.prj`）。
2. **`PolygonToRaster` + `RasterToNumPyArray` 会报 `The pixel block exceeds the maximum size allowed`**（上万像素的掩膜读不进内存）。同理改成按顶点直接画到 PIL 的 1-bit 掩膜上。

### 相关工具

| 脚本 | 做什么 |
| :-- | :-- |
| `tools/make_relief.py` | 单步：DEM → 分层设色 + 晕渲的 8bit TIFF（PIL 写，附 `.tfw`） |
| `tools/mask_relief.py` | 单步：按面要素裁成研究区形状（`--outside white/nodata`） |
| `tools/make_hypso_map.py` | 全流程：上面两步 + 桥操作 + 导出 |
| `tools/make_density_map.py` | 密度图：分类栅格某一类 → 聚合+平滑的密度面 → 连续色带上色 → 导出 |
| `tools/render_panels.py` | 土地利用/分层设色的配色调图（烘成 RGB，配 `raster_rgb` 用） |
| `tools/prep_district_stats.py` | 栅格密度 → 区县属性字段（`BUI_PCT`），并转成 UTM 50N + 生成驻地圆心点 |

### 密度图：`make_density_map.py`

把分类栅格里的某一类算成"密度"面（建设用地密度、林地密度、水体密度……都是同一套）：

```powershell
& 'C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe' `
    tools\make_density_map.py --raster data\bj\bj_lucc.tif --class-value 50 `
    --boundary data\bj\bj_boundary.shp --out out\bj_builtup_density.png `
    --title "建设用地密度 · 北京" --dpi 300
```

`--class-value` 是 ESA WorldCover 类别（10 林地 20 灌丛 30 草地 40 耕地 50 建成区 60 裸地 80 水体 90 湿地），换数字就换主题。想看更平滑的大格用 `--agg 100 --window 7`。

三个坑（都写进脚本注释了）：

1. **`--agg` 开小会崩**：10 m 底图有 3.2 亿像元，`--agg 5` 时 `Aggregate` 直接访问越界，进程以 `0xC0000005` 挂掉。默认 `50`（=500 m 格）稳定。
2. **`arcpy.CheckInExtension("Spatial")` 也会 `0xC0000005`**：文件已经写好了，但脚本后面的桥操作一步都跑不到，表现为"只打印了 1/5 就退出、错误码 1、没有任何 traceback"。脚本里已经去掉这句。
3. **浮点密度栅格不能走 `mask_relief.py`**：那个函数是给 8bit RGB 底图的，浮点单波段喂给 PIL 会变成乱码色（区外一片深红）。密度图用 `ExtractByMask` 让区外变 NoData，Pro 里自然透白。

---

## 九、分级设色与版式要素（面 + 点 + 图例）

### 分级设色 + 图例 / 比例尺 / 指北针

面状数据的常用套路（区县建设用地密度这种）：

```powershell
# 1) 算统计：把栅格密度按区县汇总成属性字段（arcpy 侧的活）
& 'C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe' `
    tools\prep_district_stats.py --raster out\pb_density_50.tif

# 2) 分级设色：自然断点 5 级 + ColorBrewer 顺序色阶（黄→红）
python client/cli.py symbology 区县建设用地密度 --kind feature_breaks `
    --field BUI_PCT --classes 5 --method natural `
    --colors "#FFFFB2" "#FECC5C" "#FD8D3C" "#F03B20" "#BD0026" --width 0.4

# 3) 点符号：圆点 + 白描边，压在底图上不糊
python client/cli.py symbology 区县驻地 --kind point --marker circle --size 7 `
    --fill "#333333" --halo "#FFFFFF" --halo-size 1.2

# 4) 版式要素：公制比例尺 + 指北针 + 图例（7pt，自动隐藏字段名标题）
python client/cli.py surrounds pb_choropleth --frame pb_frame_choropleth `
    --legend-x 144 --legend-y 60 --legend-w 50 --legend-h 86
```

`--method` 四选一：`natural`（Jenks，偏态数据首选）、`quantile`（等数量）、`equal`（等间距）、`manual`（配 `--breaks`）。规则出处见 [docs/美化规则.md](docs/美化规则.md)。

三个实测坑：

1. **Pro 自带比例尺默认是英里，而且改不动**。`CIMScaleBar.Units` 在 3.5 的公开 API 里没有可赋值类型：元素上的 `SetDefinition` 只收 `CIMElement`，`CIMScaleBar` 不是；`Map` 也没有 `SetLocationUnitFormat` 的公里常量。所以 `add_surrounds` **自己按 `frame.Camera.Scale` 算长度画比例尺**（1 页面毫米 = 比例尺分母 / 1000 米，黑白交替 4 段 + 端点标注 `km`）。
2. **图例默认字号会盖住地图**：图层名 10pt 起，5 类分级再加字段名标题（`BUI_PCT`）。`Legend.GetDefinition()` 拿到 `CIMLegend` 后把每项压到 7pt、`ShowHeading=false`，再用 `legend.SetDefinition((CIMElement)(object)lg)` 写回（这个显式转型必须写，否则编译不过）。
3. **分级设色不要再给渲染器挂 `ColorRamp`**：挂了会在图例里多出一块与分级无关的空色块。默认 `ramp=false`，每级颜色由 `breaks[].Symbol` 直接决定。

---

## 十、已知限制

1. **`run_arcpy` 等于任意代码执行**：脚本以当前 Windows 用户权限运行，能读写本机文件。只运行可信脚本，不要把桥暴露到局域网。
2. **只绑 127.0.0.1**，不做鉴权——本机任何进程都能连。不要改成 0.0.0.0。
3. **不会自动保存**。导入的布局、加的图层都在内存里，必须显式调 `save`，否则 Pro 一关就没了。
4. 路径在客户端侧转成绝对路径再发——服务端的相对路径会按 Pro 的工作目录解析。`run_gp` 也会把形似数据集的相对路径转成绝对路径。
5. `bind_map_frame` 只处理第一个（或指定序号的）地图框，不管图例/比例尺的自动更新。模板里的图例项是静态的，加图层不会自动补进去。
6. `run_gp` 的参数是**位置参数**，没有命名参数；`timeout_s` 现在会传到 C# 并在超时后取消任务（底层 GP 是否立即停止取决于工具）；`overwrite` 默认 `False`，不会静默覆盖已有输出。
7. `run_arcpy` 拿不到 `ArcGISProject("CURRENT")`；需要操作当前工程对象时用 `run_gp` 或 C# 命令。超时会杀整个进程树，但已经写出的半成品文件不会自动清理。

---

## 十一、目录

```
ProBridge/
├── server/
│   ├── ProBridge.csproj      # net8.0-windows，引用 Pro\bin 与 Extensions\*
│   ├── Config.daml           # 命名空间必须是 DADF/Registry
│   ├── Module.cs             # 模块入口，启动监听
│   ├── BridgeServer.cs       # TCP + JSON-lines
│   ├── Handlers.cs           # 34 个命令 + 线程分流（含 run_gp / set_symbology / add_surrounds）
│   ├── MinModule.cs          # 诊断用最小模块（-Minimal 编译）
│   └── build.ps1             # 编译 → 打包 → 注册 → 部署两处
├── client/
│   ├── probridge.py          # 同步客户端 + run_gp() / run_arcpy() + pad_extent()
│   └── cli.py                # 24 个子命令（含 symbology / surrounds）
├── scripts/
│   ├── _common.py            # PROBRIDGE_RESULT / job_dir / out_path
│   ├── diagnose.py           # arcpy 版本、许可、扩展模块
│   ├── buffer.py             # 缓冲区
│   ├── zonal_stats.py        # 分区统计
│   └── clip_raster.py        # 按掩膜裁剪栅格
├── mcp_server.py             # 21 个 MCP 工具（含 pro_set_symbology / pro_add_surrounds）
├── tools/
│   ├── make_smoke_data.py    # 造假省界 + 假 DEM，不依赖真实数据
│   ├── prepare_study_area.py # 真实数据：下载后的裁剪/投影/融合
│   ├── render_panels.py      # 制图级配色：分层设色+山影、土地利用
│   ├── make_relief.py        # DEM → 分层设色 + 晕渲的 8bit TIFF
│   ├── mask_relief.py        # 按面要素裁成研究区形状
│   ├── make_hypso_map.py     # 一条命令出成品图（全流程）
│   ├── make_density_map.py   # 密度图：某类占比 -> 密度面上色
│   ├── fetch_study_area.py   # 下载 SRTM / WorldCover / DataV 输入
│   └── verify_bridge.py      # 命令端到端自检
├── data/bj/                  # 本地生成的研究区数据（不提交）
├── templates/A4_Landscape.pagx
├── data/smoke/               # 冒烟数据
└── out/                      # 导出产物
```

---

## 十二、下一步

1. **图例样式**：`add_surrounds` 已能出 7pt 图例，但图例项顺序跟图层顺序（自下而上）走，还不能手工排序；色带图例（栅格分幅色带）也只能靠 Pro 的默认渲染。
2. **1a 位置图**：现在是全国缩略，北京只是个小点；要改成"华北范围 + 北京高亮 + 全国小插图"。
3. 分级图例：把 `make_relief.py` 的高程色带、地类色块放进版式（图片元素）。
4. 边界换标准地图，去掉 DataV 依赖。
5. 一句自然语言串起"选省 → 下载 → 预处理 → 出图"。
