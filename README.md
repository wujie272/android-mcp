# 📱 android-mcp

通过 MCP 协议让 AI 助手直接控制你的 Android 手机。运行在 Termux 上，提供 **65+ 工具**，覆盖 UI 自动化、文件系统、设备控制、通信等。

由 [xlisp/termux-mcp-server](https://github.com/xlisp/termux-mcp-server) fork 重构而来。

## 🆕 v0.2 改进

- **模块化重构** — 单文件 41KB → 7 个工具模块 + lib 层，易维护易扩展
- **dump_ui 三模式** — `summary`（默认，节省 80% token）/ `full` / `json`
- **文件操作增强** — 新增 `edit_file` / `search_files` / `directory_tree` / `get_file_info` / `list_directory_with_sizes`
- **应用管理** — 新增 `force_stop_app` / `app_usage_stats`
- **通知管理** — 新增 `list_notifications` / `dismiss_notification`
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

## 🚀 快速开始

### 1. 安装

```bash
# 手机端 Termux
pkg install python android-tools termux-api
pip install "mcp[cli]"

# 从 F-Droid 安装 Termux:API app
# 授予存储权限
termux-setup-storage
```

### 2. 运行

```bash
# 标准模式 (stdio)
cd ~/mcp-servers/android-mcp
python3 server.py

# HTTP 模式 (SSE, 端口 3000)
python3 http_server.py
```

### 3. Claude Desktop 配置

```json
{
  "mcpServers": {
    "android-mcp": {
      "command": "ssh",
      "args": [
        "-p", "8022",
        "u0_a123@192.168.1.100",
        "cd ~/mcp-servers/android-mcp && python3 server.py"
      ]
    }
  }
}
```

> 免密登录：`ssh-keygen` → `ssh-copy-id -p 8022 u0_a123@192.168.1.100`

## 🖥️ UI 自动化工作流

```
take_screenshot → AI 看到屏幕内容
      ↓
dump_ui(mode='summary') → 获取可交互元素及坐标 (节省 80% token)
      ↓
tap_screen(x, y) → 点击目标位置
input_text("内容") → 输入文字
      ↓
take_screenshot → 确认结果，继续下一步
```

## 🏗️ 项目结构

```
android-mcp/
├── server.py                  # 入口 (stdio)
├── http_server.py             # HTTP/SSE 入口
├── termux_mcp_server.py       # 兼容 shim (旧脚本仍可用)
├── pyproject.toml
├── android_mcp/
│   ├── app.py                 # FastMCP 实例
│   ├── lib/
│   │   ├── utils.py           # 命令执行、Termux API 包装
│   │   └── adb.py             # ADB 连接管理
│   └── tools/
│       ├── device_info.py     # 电池/WiFi/定位/传感器
│       ├── ui_automation.py   # 截图/dump_ui/点击/输入
│       ├── file_system.py     # 文件读/写/编辑/搜索/树
│       ├── app_management.py  # 应用/进程/包管理
│       ├── communication.py   # 短信/通讯录/剪贴板/通知
│       ├── system_control.py  # 音量/手电筒/震动/TTS
│       └── media.py           # 相机/相册/播放器/分享
└── scripts/                   # 工具脚本
```

## 📄 许可

MIT — 基于 [xlisp/termux-mcp-server](https://github.com/xlisp/termux-mcp-server)
