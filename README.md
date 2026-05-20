# 📱 android-mcp v2.0 — 优化版

通过 MCP 协议让 AI 助手直接控制你的 Android 手机 + GitHub 仓库管理。运行在 Termux 上，提供 **75+ 工具**。

由 [xlisp/termux-mcp-server](https://github.com/xlisp/termux-mcp-server) fork 重构而来。

## 🚀 v2.0 优化内容

### 🎯 三大问题修复

| 问题 | 修复方案 |
|:-----|:---------|
| 🐢 **响应慢** | 所有阻塞调用改为 `async_run()` 异步线程池 + Uvicorn `limit_concurrency=20` |
| 🔄 **频繁重连** | Uvicorn `timeout_keep_alive=65` + 保活守护进程 |
| 💥 **偶尔崩溃** | 所有 75+ 工具添加 `try/except` + GPS 超时自动降级 |

### 🧩 新增功能

- **GitHub 工具集成** — 9 个 GitHub 工具合并到 Android MCP 内部，不再需要独立服务
- **破坏性降级** — GPS 超时自动切 passive/last，不崩
- **保活守护** — `mcp-keepalive.sh` 自动检测崩溃并重启

## 🆕 v0.2.1 改进（之前）

- **模块化重构** — 单文件 41KB → 7 个工具模块 + lib 层
- **dump_ui 三模式** — `summary`（默认，节省 80% token）/ `full` / `json`
- **文件操作增强** — 新增 `edit_file` / `search_files` / `directory_tree` 等
- **45 → 65 工具** — 新增 20 个工具

## 🎯 功能一览

| 分类 | 工具数 | 说明 |
|------|:------:|------|
| 📱 设备信息 | 9 | 电池、WiFi、基站、GPS、传感器、型号、存储 |
| 🖥️ UI 自动化 | 11 | 截图、`dump_ui`(三模式)、点击、滑动、输入、按键、导航 |
| 📁 文件系统 | 9 | 读/写/编辑、搜索、目录树、元数据、Shell 执行 |
| 📦 应用管理 | 7 | 列应用/进程、启动/停止、打开 URL、使用统计 |
| 💬 通信 | 8 | 短信、通讯录、剪贴板、通知(发/读/删) |
| 🔊 系统控制 | 8 | 音量、手电筒、震动、TTS、亮度、指纹 |
| 📷 媒体 | 7 | 拍照、浏览相册、媒体播放、分享、下载 |
| 🔌 ADB | 3 | 无线调试连接/管理/状态 |
| 📍 其他 | 3 | 定位、传感器、存储信息 |
| 💻 GitHub | 9 | 仓库查询、列表、搜索、文件读取、Issue、语言、分支 |

## 🚀 快速开始

```bash
# 标准模式 (stdio)
cd ~/mcp-servers/android-mcp
python3 server.py

# HTTP 模式 (Streamable HTTP, 端口 3000)
python3 http_server.py
```

## 🏗️ 项目结构

```
android-mcp/
├── server.py                  # 入口 (stdio)
├── http_server.py             # Streamable HTTP 入口 v2.0 (支持并行+保活)
├── android_mcp/
│   ├── app.py                 # FastMCP 实例 (含 GitHub 注册)
│   ├── lib/
│   │   ├── utils.py           # 命令执行 v2.0 (含 async_run 异步包装)
│   │   └── adb.py             # ADB 连接管理
│   └── tools/
│       ├── device_info.py     # v2.0 异常保护+超时降级
│       ├── ui_automation.py   # v2.0 异常保护
│       ├── file_system.py     # v2.0 async_run
│       ├── app_management.py
│       ├── communication.py
│       ├── system_control.py
│       ├── media.py
│       ├── adb.py
│       └── github.py          # 🆕 9 个 GitHub 工具 (原独立服务)
```

## 📄 许可

MIT — 基于 [xlisp/termux-mcp-server](https://github.com/xlisp/termux-mcp-server)