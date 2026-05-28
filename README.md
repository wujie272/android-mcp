# 📱 android-mcp v0.3 — 全面重构版

通过 MCP 协议让 AI 助手直接控制你的 Android 手机 + GitHub 仓库管理。运行在 Termux 上，提供 **100+ 工具**。

由 [xlisp/termux-mcp-server](https://github.com/xlisp/termux-mcp-server) fork 重构而来。

---

## ✨ v0.3 新特性

### 🧠 智能元素定位（uiautomator2 风格）

无需 ADB，基于 Shizuku 的 uiautomator 实现智能元素查找：

| 工具 | 说明 |
|:-----|:------|
| `click_by_text("发送")` | 按文本点击（部分匹配） |
| `click_by_id("com.example:id/btn")` | 按资源 ID 点击 |
| `click_by_class("Button", index=2)` | 按类名点击（可指定第几个） |
| `find_element(text=..., resource_id=...)` | 查找元素位置和属性（不点击） |
| `wait_for_element("加载中", timeout=10)` | 轮询等待元素出现 |
| `get_foreground_app()` | 获取当前前台应用 |
| `get_ui_state(scale=0.5)` | 完整界面状态（元素+标注截图） |

### ♻️ 架构重构

| 改进 | 说明 |
|:-----|:------|
| 🗂️ **路径集中管理** | 新建 `constants.py` 统一管理所有硬编码路径 |
| 🔄 **日志轮转** | 改用 `RotatingFileHandler`，日志 1MB×3 自动轮转 |
| ⏱️ **健康检查** | 新增 `get_uptime()` 用于服务自愈和存活监控 |
| 🚀 **分层加载** | 智能定位 + GitHub 提到第1层，启动即见 |

### 🖥️ 屏幕操作增强

| 工具 | 说明 |
|:-----|:------|
| `screen_on()` / `screen_off()` | 唤醒 / 息屏 |
| `rotate_device(rotation)` | 0=竖屏 / 1=横屏 / 2=倒竖 / 3=倒横 |
| `expand_notifications()` / `expand_settings()` | 展开通知栏 / 快捷设置 |
| `collapse_panels()` | 收起面板 |

### 🎬 屏幕录制

`screen_record(duration, show_taps, bit_rate)` — 最长 180s 录制

### 🏷️ 标注截图

`dump_ui_with_screenshot(scale)` — 一键截屏+标注编号+元素列表

### 📱 多设备

`list_adb_devices()` — 列出所有 ADB 设备（USB+WiFi）

### 🔑 GitHub Token 动态刷新

`github_refresh_token()` — 运行时刷新，无需重启

### 📸 截图劣化

`take_screenshot(scale)` — scale=0.25~1.0，Token 最多省 16 倍

---

## 📊 工具一览

| 分类 | 工具数 | 说明 |
|:-----|:------:|:-----|
| 🧠 **智能定位** | **8** 🆕 | 按文本/ID/类名点击、查找、等待、前台应用、界面状态 |
| 📱 设备信息 | 15 | 电池、WiFi(扫描/QR码)、基站、GPS、传感器、多设备列表、健康报告 |
| 🖥️ UI 自动化 | 20 | 截图(劣化)、标注截图、dump_ui(三模式)、点击、滑动、输入、屏幕控制 |
| 📁 文件系统 | 10 | 读/写/编辑、搜索、目录树、Shell 执行 |
| 📦 应用管理 | 9 | 列应用/进程/包、启动(5级降级)、使用统计 |
| 💬 通信 | 11 | 短信、通讯录、剪贴板(ADB备选)、通知(发/列/删)、Toast、历史 |
| 🔊 系统控制 | 8 | 音量、手电筒、震动、TTS、亮度、指纹 |
| 📷 媒体 | 8 | 拍照、相册、录屏、播放、分享、下载 |
| 🔌 ADB | 2 | 状态检查、无线连接 |
| 💻 GitHub | 10 | 仓库查/列/搜、文件读、Issue、语言、分支、Token 刷新 |

**总计 100+ 工具**

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
    ├── lib/  constants.py     # 路径常量
    │       utils.py           # 命令执行 + 日志轮转
    │       adb.py             # ADB 连接
    └── tools/
        ├── ui_smart.py        # 🆕 智能元素定位
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
