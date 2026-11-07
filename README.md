# ProBridge

用外部程序实时操控**正在运行的 ArcGIS Pro 窗口**：通过 MCP、CLI、Python SDK 或
JSON-lines 协议加载图层、缩放视图、设置符号、排版、运行 GP/arcpy，并导出地图。

项目把"写脚本、等 Pro 重开、再检查结果"的循环缩短为一次即时调用。核心服务是
一个 .NET 8 ArcGIS Pro Add-in，只监听 `127.0.0.1:7788`；Python 侧提供 MCP
服务、命令行、客户端库和示例工作流。

## 能力

- 图层：添加/删除/清空、缩放、留白适配、强制重绘
- 制图：导入 `.pagx` 模板、创建多图框版式、绑定地图框、修改文字和元素显隐
- 符号：栅格拉伸/RGB、面填充与描边、点符号、自然断点/分位/等距分级设色
- 版式要素：公制比例尺、指北针、图例
- 分析：调用 ArcGIS GP 工具，或以 Pro Python 运行受信任的 arcpy 脚本
- 输出：PNG/JPG/TIFF/PDF，默认 300 dpi
- 接入：21 个 MCP 工具、CLI、Python SDK、原始 TCP 协议和 Pro 内嵌 WebView2 面板

## 架构

```text
Agent / CLI / Python / HTTP panel
                |
       MCP / JSON-lines / TCP
                |
       127.0.0.1:7788
                |
   ProBridge.esriAddinX (C#)
       QueuedTask / Dispatcher
                |
          ArcGIS Pro 3.5
```

Pro 的 API 线程规则是项目的核心难点：图层、几何和重绘走 MCT，窗格与保存走 UI
线程，GP 工具自己管理线程。详细说明和实测踩坑见
[ProBridge/README.md](ProBridge/README.md)。

## 环境

- Windows 10/11
- ArcGIS Pro 3.5.x（开发环境为 3.5.2）
- .NET 8 SDK
- ArcGIS Pro 自带 Python 3.11 环境
- WebView2（随 ArcGIS Pro 安装）

## 快速开始

以下命令在仓库根目录执行。将 `C:\path\to\arcgispro` 换成实际克隆路径。

```powershell
cd ProBridge

# 1. 创建 Python 环境
& 'C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe' -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. 编译并部署 Add-in；执行前先退出 ArcGIS Pro
cd server
.\build.ps1

# 3. 重开 Pro，确认 7788 端口在监听
cd ..
netstat -ano | findstr 7788

# 4. 验证 MCP 服务
.\.venv\Scripts\python.exe tools\mcp_smoke.py
```

MCP 客户端配置示例：

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

加载 Add-in 后，可以先用 CLI 做一次连通性检查：

```powershell
.\.venv\Scripts\python.exe client\cli.py ping
```

## 文档

- [完整使用说明与线程模型](ProBridge/README.md)
- [接入其他 Agent](ProBridge/docs/接入其他Agent.md)
- [专题图美化规则](ProBridge/docs/美化规则.md)
- [数据下载与合规说明](ProBridge/data/bj/README.md)
- [第三方许可](THIRD_PARTY_NOTICES.md)
- [安全边界](SECURITY.md)

## 注意事项

- 服务只绑定 loopback，**没有鉴权**，不要改成 `0.0.0.0` 或暴露到局域网。
- `run_arcpy` 等价于以当前 Windows 用户权限执行任意 Python 代码，只运行可信脚本。
- 仓库不附带真实研究区数据。示例数据需通过 `fetch_study_area.py` 下载并在本地生成。
- DataV 行政边界适合演示和快速试验，不具测绘资质；正式出图需换用标准地图。
- 公开分发前应确认示例地理数据、项目文件和第三方素材的许可。

## License

本仓库原创代码和文档采用 [MIT License](LICENSE)。ArcGIS Pro、Esri SDK 及下载
的第三方数据适用各自的许可，见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
