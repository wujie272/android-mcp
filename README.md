# 📱 android-mcp v0.3 — 全面重构版

通过 MCP 协议让 AI 助手直接控制你的 Android 手机 + GitHub 仓库管理。运行在 Termux 上，提供 **100+ 工具**。

由 [xlisp/termux-mcp-server](https://github.com/xlisp/termux-mcp-server) fork 重构而来。

---

## ✨ v0.4 新特性

### 📡 MCP Resources — 设备数据源

将设备状态暴露为可订阅的 Resources（**8 个**），Client 可直接读取：

| Resource | 说明 |
|:---------|:------|
| `device://battery` | 电池状态（电量、温度、充电状态） |
| `device://info` | 设备信息（型号、Android 版本、内核） |
| `device://network/wifi` | WiFi 连接（SSID、信号强度、IP） |
| `device://network/telephony` | 蜂窝网络（运营商、网络类型） |
| `device://storage` | 存储使用（总量、已用、剩余） |
| `device://health` | 健康摘要（电池+WiFi+存储快照） |
| `device://sensors` | 传感器列表 |
| `device://app/foreground` | 前台应用信息 |

### 📝 MCP Prompts — 模板化工作流（5 个）

| Prompt | 说明 |
|:-------|:------|
| `device_health_check` | 全面健康巡检向导 |
| `app_forensic_audit` | 应用安全取证分析 |
| `screen_interaction_wizard` | 屏幕操作向导（截图→识别→点击→验证） |
| `crash_investigation` | 崩溃事故调查 |
| `automation_operator` | 自动化操作员（签到/打卡等重复任务） |

### 🛠 聚合工具（4 个）

一次调用获取多维数据，告别多次轮询：

| 工具 | 说明 |
|:-----|:------|
| `device_health()` | 🔥 一站式健康检查：电池+存储+内存+网络+进程，带评分 |
| `analyze_app(package)` | 🔍 深度应用分析：权限审计+内存+Activity+进程 |
| `quick_status()` | ⚡ 极速概览：一行一个核心指标 |
| `screen_diagnostics()` | 📺 屏幕诊断：分辨率+方向+亮度+元素统计 |

### 🔒 安全门系统

环境变量控制，无需改代码：

```bash
ANDROID_MCP_READONLY=true     # 只读模式，禁止所有写入操作
ANDROID_MCP_ALLOW_SHELL=false # 禁止 shell 命令执行
```

---

## 📊 工具一览

| 分类 | 工具数 | 说明 |
|:-----|:------:|:-----|
| 📡 **Resources** | **8** 🆕 | 电池/设备/WiFi/蜂窝/存储/健康/传感器/前台 |
| 📝 **Prompts** | **5** 🆕 | 健康巡检/取证/屏幕向导/崩溃调查/自动化 |
| 🛠 **聚合工具** | **4** 🆕 | device_health/analyze_app/quick_status/screen_diagnostics |
| 🧠 **智能定位** | **8** | 按文本/ID/类名点击、查找、等待、前台应用、界面状态 |
| 📱 设备信息 | 15 | 电池、WiFi(扫描/QR码)、基站、GPS、传感器、多设备列表、健康报告 |
| 🖥️ UI 自动化 | 20 | 截图(劣化)、标注截图、dump_ui(三模式)、点击、滑动、输入、屏幕控制 |
| 📁 文件系统 | 10 | 读/写/编辑、搜索、目录树、Shell 执行 |
| 📦 应用管理 | 9 | 列应用/进程/包、启动(5级降级)、使用统计 |
| 💬 通信 | 11 | 短信、通讯录、剪贴板(ADB备选)、通知(发/列/删)、Toast、历史 |
| 🔊 系统控制 | 8 | 音量、手电筒、震动、TTS、亮度、指纹 |
| 📷 媒体 | 8 | 拍照、相册、录屏、播放、分享、下载 |
| 🔌 ADB | 2 | 状态检查、无线连接 |
| 💻 GitHub | 10 | 仓库查/列/搜、文件读、Issue、语言、分支、Token 刷新 |

**总计 100+ 工具 · 8 个 Resources · 5 个 Prompts**

---

## 🚀 快速开始

```bash
cd ~/mcp-servers/android-mcp
python3 server.py          # stdio
python3 http_server.py     # HTTP (端口 3000)
```

## ⚙️ 依赖

| 依赖 | 用途 |
|:-----|:------|
| Termux:API | 电池/WiFi/传感器/相机/短信/剪贴板/TTS |
| Shizuku（推荐） | 截图/UI dump/录屏/输入注入 |
| ADB（备选） | Shizuku 不可用时降级 |
| Pillow | 截图劣化/标注截图 |

## 🏗️ 项目结构

```
android-mcp/
├── server.py / http_server.py / http_termux_server.py
└── android_mcp/
    ├── app.py                 # FastMCP 实例 + 分层加载
    ├── prompts.py             # 🆕 MCP Prompt 模板（5 个工作流）
    ├── resources.py           # 🆕 MCP Resources（8 个设备数据源）
    ├── lib/  constants.py     # 路径常量
    │       utils.py           # 命令执行 + 日志轮转 + 🔒 安全门
    │       adb.py             # ADB 连接
    └── tools/
        ├── aggregation.py     # 🆕 聚合工具（device_health/analyze_app）
        ├── ui_smart.py        # 智能元素定位
        ├── ui_automation.py   # 截图/标注/点击/输入/屏幕控制
        ├── device_info.py     # 设备信息/多设备
        ├── file_system.py     # 文件操作
        ├── app_management.py  # 应用管理
        ├── communication.py   # 短信/通讯录/剪贴板/通知
        ├── system_control.py  # 音量/手电筒/TTS/亮度
        ├── media.py           # 相机/录屏/播放/分享
        ├── adb.py             # ADB 状态/连接
        └── github.py          # GitHub API
```

## 📄 许可

MIT — 基于 [xlisp/termux-mcp-server](https://github.com/xlisp/termux-mcp-server)
