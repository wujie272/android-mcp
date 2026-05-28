# 📱 android-mcp v0.3 — 全面重构版

通过 MCP 协议让 AI 助手直接控制你的 Android 手机 + GitHub 仓库管理。运行在 Termux 上，提供 **90+ 工具**。

由 [xlisp/termux-mcp-server](https://github.com/xlisp/termux-mcp-server) fork 重构而来。

---

## ✨ v0.3 新特性

### ♻️ 架构重构

| 改进 | 说明 |
|:-----|:------|
| 🗂️ **路径集中管理** | 新建 `constants.py` 统一管理所有硬编码路径，一处改全局生效 |
| 🔄 **日志轮转** | 改用 `RotatingFileHandler`，日志 1MB×3 自动轮转，不怕撑爆磁盘 |
| ⏱️ **健康检查** | 新增 `get_uptime()` 用于服务自愈和存活监控 |
| 🚀 **GitHub 提前加载** | GitHub 工具从第3层（延迟10s）提到第1层（立即加载），RikkaHub 启动即见 |

### 🖥️ 屏幕操作增强（6 个新工具）

| 工具 | 说明 | 特权需求 |
|:-----|:------|:---------|
| `screen_on()` | 唤醒屏幕 | Shizuku/ADB |
| `screen_off()` | 息屏 | Shizuku/ADB |
| `rotate_device(rotation)` | 0=竖屏 / 1=横屏 / 2=倒竖 / 3=倒横 | **无需特权** |
| `expand_notifications()` | 展开通知栏 | **无需特权**（有 swipe 降级） |
| `expand_settings()` | 展开快捷设置 | **无需特权**（有 swipe 降级） |
| `collapse_panels()` | 收起面板 | **无需特权**（有 swipe 降级） |

> 所有命令都有降级方案（swipe 模拟），无特权也能工作。

### 🎬 屏幕录制

| 工具 | 说明 |
|:-----|:------|
| `screen_record(duration_secs, show_taps, bit_rate_mbps)` | 录制屏幕视频，最长 180s，支持触摸反馈显示 |

### 🏷️ 标注截图 — `dump_ui_with_screenshot(scale)`

**一键三合一**：截屏 → 解析 UI → **标注编号** → 返回标注截图 + 元素列表

```
📱 共 12 个可交互元素:

  1. [Button] "发送"       → tap(540, 1200)
  2. [EditText] "输入消息"  → tap(200, 1100)
  ...
```

- 截图自动标注编号边框（随机颜色）
- 配合 scale 参数（0.25~1.0）控制 Token 消耗
- 全分辨率文件保留，只缩小 base64 数据

### 📱 多设备支持

| 工具 | 说明 |
|:-----|:------|
| `list_adb_devices()` | 列出所有 ADB 设备（USB + WiFi），含型号和状态 |
| `adb_connect(pair_code, pair_port, connect_port)` | 无线调试连接 |

### 🔑 GitHub Token 动态刷新

| 工具 | 说明 |
|:-----|:------|
| `github_refresh_token()` | 运行时刷新 GitHub Token，无需重启服务 |
| | 支持 `gh auth login` 和环境变量两种方式 |

### 🔍 工具描述全面优化

所有 90+ 工具的描述都重写了，告诉 AI：
- **返回什么数据**（标注 JSON 字段名）
- **需要什么权限**（Termux:API / Shizuku / ADB）
- **什么场景用**（附使用提示）

### 📸 截图劣化（Token 优化）

`take_screenshot(scale)` 新增 scale 参数：

| scale | 效果 | Token 消耗 |
|:------|:-----|:----------|
| 1.0 | 原始分辨率（有 1080px 上限保护） | 最大 |
| 0.5 | 半尺寸，适合布局识别 | 约 1/4 |
| 0.25 | 四分之一尺寸，适合快速预览 | 约 1/16 |

使用 Pillow `LANCZOS` 高质量缩放，文件保留全分辨率不清真。

### 📱 应用启动增强

`open_app(package)` 采用 **5 级降级策略**：

1. `MAIN/LAUNCHER` intent（最可靠，多数设备默认可用）
2. 常见 Activity 名称匹配（`.MainActivity` / `.Settings` 等）
3. `monkey` 启动器
4. `cmd package resolve-activity`（Android 13+）
5. `dumpsys package` 深度解析

---

## 📊 工具一览

| 分类 | 工具数 | 说明 |
|:-----|:------:|:-----|
| 📱 设备信息 | 14 | 电池、WiFi(扫描/QR码)、基站、GPS(自动降级)、传感器、型号、存储、多设备列表 |
| 🖥️ UI 自动化 | 20 | 截图(劣化)、标注截图、dump_ui(三模式)、点击、滑动、输入、按键、屏幕控制、导航 |
| 📁 文件系统 | 10 | 读/写/编辑、搜索、目录树、元数据、Shell 执行、权限列表 |
| 📦 应用管理 | 9 | 列应用/进程/包、启动(5级降级)、停止、打开 URL、使用统计 |
| 💬 通信 | 11 | 短信(列/发)、通讯录、剪贴板(含ADB备选)、通知(发/列/删)、Toast、剪贴板历史 |
| 🔊 系统控制 | 8 | 音量(设/读)、手电筒、震动、TTS、亮度(设/读)、指纹 |
| 📷 媒体 | 8 | 拍照、浏览相册(智能搜索)、读照片、屏幕录制、媒体播放、分享、下载 |
| 🔌 ADB | 2 | 状态检查、无线连接 |
| 💻 GitHub | 10 | 仓库查/列/搜、文件读、Issue、语言、分支、Token 刷新 |

**总计 92 个工具**

---

## 🚀 快速开始

```bash
# 标准模式 (stdio)
cd ~/mcp-servers/android-mcp
python3 server.py

# HTTP 模式 (Streamable HTTP, 端口 3000)
python3 http_server.py
```

## ⚙️ 依赖

| 依赖 | 用途 | 安装方式 |
|:-----|:-----|:---------|
| Termux:API | 电池/WiFi/传感器/相机/短信/剪贴板/TTS | F-Droid 安装 |
| Shizuku（推荐） | 截图/UI dump/屏幕录制/输入注入 | 官网安装 + 授权 |
| ADB（备选） | Shizuku 不可用时的降级方案 | `pkg install android-tools` |
| Pillow | 截图劣化/标注截图 | `pip install pillow` |

## 🏗️ 项目结构

```
android-mcp/
├── server.py                  # 入口 (stdio)
├── http_server.py             # Streamable HTTP 入口 (支持并行+保活)
├── http_termux_server.py      # Termux 版 HTTP 入口
├── android_mcp/
│   ├── app.py                 # FastMCP 实例 + 分层加载 (GitHub 立即加载)
│   ├── lib/
│   │   ├── constants.py       # 🆕 路径常量集中管理
│   │   ├── utils.py           # 命令执行 + 日志轮转 + 健康检查
│   │   └── adb.py             # ADB 连接管理
│   └── tools/
│       ├── device_info.py     # 电池/WiFi/基站/GPS/传感器/设备信息/多设备
│       ├── ui_automation.py   # 截图/标注/点击/滑动/输入/屏幕控制/导航
│       ├── file_system.py     # 文件读写编辑搜索
│       ├── app_management.py  # 应用管理(5级启动降级)
│       ├── communication.py   # 短信/通讯录/剪贴板/通知
│       ├── system_control.py  # 音量/手电筒/震动/TTS/亮度
│       ├── media.py           # 相机/相册/录屏/播放/分享
│       ├── adb.py             # ADB 状态/连接
│       └── github.py          # GitHub API 工具 + Token 刷新
```

## 📄 许可

MIT — 基于 [xlisp/termux-mcp-server](https://github.com/xlisp/termux-mcp-server)
