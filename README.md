# 🤖 Android MCP Server

> **让 AI 直接操控你的 Android 手机** — 120+ 工具的 MCP 服务，运行在 Termux 上

[![Version](https://img.shields.io/badge/version-0.4.0-blue.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)]()
[![Python](https://img.shields.io/badge/python-3.10+-orange.svg)]()
[![PRs](https://img.shields.io/badge/MCP-FastMCP-purple.svg)]()

基于 [xlisp/termux-mcp-server](https://github.com/xlisp/termux-mcp-server) 全面重构，采用 **FastMCP** 框架，分层加载、智能重试、安全门控。

---

## ✨ 亮点速览

| 特性 | 说明 |
|:-----|:------|
| 🛠 **120+ 工具** | 屏幕操控 · 文件管理 · 应用管理 · 通信 · 传感器 · 媒体 · 天气 · Shizuku · GitHub |
| 📡 **8 个 Resources** | 电池/设备/WiFi/蜂窝/存储/健康/传感器/前台 — 可直接订阅 |
| 📝 **5 个 Prompts** | 健康巡检/取证分析/屏幕向导/崩溃调查/自动化操作 — 模板化工作流 |
| 🚀 **分层加载** | 核心工具 0s → 常用 3s → 低频 10s，启动即用不等待 |
| 🔒 **安全门控** | 只读模式 + Shell 开关，环境变量控制，零代码入侵 |
| 🧠 **智能定位** | 按文本/ID/类名找元素，一次调用定位+点击+验证 |
| 🏗 **三层特权** | Shizuku (rish) 🥇 → ADB 🥈 → Direct (Termux) 🥉，自动降级，最高权限优先 |

---

## 📡 快速开始

```bash
# 通过管理工具（推荐）
bash ~/mcp-manager.sh android

# 或直接运行
cd ~/mcp-servers/android-mcp

# stdio 模式（适合 Claude Desktop 本地调用）
python3 server.py

# HTTP/SSE 模式（适合远程访问，端口 3000）
python3 http_server.py

# 健康检查
curl http://手机IP:3000/health
```

### MCP 客户端配置

```json
{
  "mcpServers": {
    "android-mcp": {
      "type": "sse",
      "url": "http://192.168.1.102:3000/sse"
    }
  }
}
```

> ⚠️ 将 `192.168.1.102` 替换为手机实际 IP（可用 `bash ~/mcp-manager.sh wifi-ip` 查看）

---

## 🏗 架构设计

```
┌─────────────────────────────────────────────────────┐
│                   MCP Client                         │
│           (Claude Desktop / RikkaHub / Cursor)       │
└────────────────────┬────────────────────────────────┘
                     │ MCP Protocol (SSE / stdio)
                     ▼
┌─────────────────────────────────────────────────────┐
│              android-mcp (FastMCP)                    │
│                                                       │
│  ┌─────────────────────────────────────────────┐     │
│  │  🚀 Layer 1: 核心工具 (0s)                    │     │
│  │  device_info · ui_automation · ui_smart      │     │
│  │  github · aggregation · prompts · resources  │     │
│  ├─────────────────────────────────────────────┤     │
│  │  ⏳ Layer 2: 常用工具 (3s)                    │     │
│  │  file_system · app_management               │     │
│  │  communication · system_control             │     │
│  ├─────────────────────────────────────────────┤     │
│  │  🐌 Layer 3: 低频工具 (10s)                  │     │
│  │  media · adb                                 │     │
│  └─────────────────────────────────────────────┘     │
│                                                       │
│  ┌─── 🔒 Security Gate ─────────────────────────┐   │
│  │  ANDROID_MCP_READONLY    → 禁止写入操作       │   │
│  │  ANDROID_MCP_ALLOW_SHELL → 禁止 Shell 执行    │   │
│  └──────────────────────────────────────────────┘   │
│                                                       │
│  ┌─── 🏗 Privilege Chain ───────────────────────┐   │
│  │  Shizuku (rish) 🥇 → ADB 🥈 → Direct 🥉   │   │
│  │  自动降级，最高权限优先                      │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
         │                  │                  │
         ▼                  ▼                  ▼
   ┌──────────┐    ┌──────────────┐    ┌────────────┐
   │ Termux:API│    │ Shizuku/rish │    │    ADB     │
   │ 传感器/相机│    │ 截图/UI dump │    │ 无线调试   │
   │ 短信/TTS  │    │ 输入注入     │    │ (备选)     │
   └──────────┘    └──────────────┘    └────────────┘
```

---

## 📡 MCP Resources — 设备数据源

Resources 是**可订阅的声明式数据源**，Client 可主动读取或订阅更新。

| Resource | URI | 说明 |
|:---------|:----|:------|
| 🔋 电池 | `device://battery` | 电量/温度/充电状态/电压/电流/健康度 |
| 📱 设备 | `device://info` | 型号/品牌/Android版本/SDK/内核/架构/运行时间 |
| 📶 WiFi | `device://network/wifi` | SSID/信号强度/速率/频段/IP |
| 📡 蜂窝 | `device://network/telephony` | 运营商/网络类型/SIM状态/漫游 |
| 💾 存储 | `device://storage` | 总量/已用/剩余/使用率 |
| 🩺 健康 | `device://health` | 电池+WiFi+存储一键快照 |
| 🎯 传感器 | `device://sensors` | 可用传感器列表及数量 |
| 📌 前台 | `device://app/foreground` | 当前前台运行的 App |

---

## 📝 MCP Prompts — 模板化工作流

5 个预定义工作流模板，Client 调用后 AI 自动执行多步骤任务：

| Prompt | 适用场景 | 执行流程 |
|:-------|:---------|:---------|
| `device_health_check` | 设备卡顿/发热/耗电快时排查 | 电池→健康→存储→网络→设备→前台 → 报告 |
| `app_forensic_audit` | 审计第三方 App 安全性 | 包信息→权限审计→内存→Activity→数据 → 审计报告 |
| `screen_interaction_wizard` | 多步骤 UI 自动操作 | 截图→识别→点击→验证(循环) |
| `crash_investigation` | App 闪退/系统异常排查 | 健康基线→内存→存储→近期变更 → 事故报告 |
| `automation_operator` | 签到/打卡等重复任务 | 拆解步骤→逐个执行→验证→报告 |

---

## 🛠 聚合工具

一次调用获取多维数据，告别多次轮询：

| 工具 | 说明 | 数据来源数 |
|:-----|:------|:----------|
| `device_health()` | 🔥 **设备健康报告** — 电池 + 存储 + 内存 + WiFi + CPU + 进程，7路异步并发 | ⚡ 7 |
| `analyze_app(pkg)` | 🔍 包信息 + 权限 + 内存 + Activity + 进程（全维度审计） | 📋 5 |
| `screen_diagnostics()` | 📺 分辨率 + 方向 + 亮度 + 前台 + UI 节点统计 | 🖥️ 5 |

---

## 🔒 安全门系统

环境变量控制，**无需改代码**：

```bash
# 只读模式 — 禁止所有写入操作（截图/点击/发短信/删文件等）
ANDROID_MCP_READONLY=true

# Shell 控制 — 禁止 Shell/ADB 命令执行
ANDROID_MCP_ALLOW_SHELL=false
```

每个工具标注安全等级：

| 等级 | 标识 | 示例 |
|:-----|:-----|:-----|
| ⚡ 中风险 | 交互操作 | `tap_screen()`, `input_text()`, `swipe_screen()` |
| 🚨 高风险 | 数据变更 | `send_sms()`, `write_file()`, `force_stop_app()` |

---

## 🛠 全部工具一览（100+）

### 🧠 智能定位（8 个）

| 工具 | 说明 |
|:-----|:------|
| `find_element(text)` | 按文本/ID/类名/描述查找 UI 元素，返回坐标和属性 |
| `click_by_text(text)` | 按文本查找并点击（不受布局变化影响，最稳健） |
| `click_by_id(id)` | 按资源 ID 查找并点击 |
| `click_by_class(cls)` | 按类名（Button/Switch 等）查找并点击 |
| `wait_for_element(text)` | 等待元素出现（轮询，超时可配，适合异步加载） |
| `get_foreground_app()` | 获取当前前台应用包名+Activity |
| `get_ui_state(scale)` | 结构化界面状态 + 可选标注截图（一键到位） |
| `dump_ui_with_screenshot(scale)` | 标注所有可交互元素的截图 + 完整元素列表 |

### 🖥️ UI 自动化（20 个）

| 工具 | 说明 |
|:-----|:------|
| `dump_ui(mode)` | UI 树分析（summary / full / json 三模式） |
| `tap_screen(x, y)` | 精确点击指定坐标 |
| `long_press(x, y, ms)` | 长按（可设时长） |
| `swipe_screen(x1,y1 → x2,y2)` | 滑动操作（可调速） |
| `input_text(text)` | 输入 ASCII 文本 |
| `input_chinese_text(text)` | 输入中文/多语言文本（剪贴板+Paste 方案） |
| `input_keyevent(keycode)` | 发送按键事件（3=Home / 4=Back / 26=Power / 66=Enter / 67=Del / 187=Recent） |
| `go_home()` / `go_back()` | 主页 / 返回 |
| `open_recent_apps()` | 最近应用 |
| `screen_on()` / `screen_off()` | 亮屏 / 息屏 |
| `rotate_device(rot)` | 旋转屏幕（0=竖屏 / 1=横屏 / 2=反向竖屏 / 3=反向横屏） |
| `expand_notifications()` | 下拉通知栏 |
| `expand_settings()` | 展开快捷设置面板 |
| `collapse_panels()` | 收起通知栏/设置面板 |
| `screen_record(secs)` | 录屏（最长 180s，可显示触摸点） |

### 📱 设备信息（18 个）

| 工具 | 说明 |
|:-----|:------|
| `get_battery_status()` | 电池电量/温度/充电状态/电压/电流/健康度 |
| `get_battery_health()` | 深度电池健康：循环次数/容量/电压（dumpsys） |
| `get_wifi_info()` | WiFi 连接详情（SSID/BSSID/信号/速率/频段/IP） |
| `scan_wifi()` | 扫描附近 WiFi 热点 |
| `wifi_qr_code()` | 生成当前 WiFi 二维码（可扫码连接） |
| `get_telephony_info()` | 蜂窝网络信息（运营商/4G/5G/SIM 状态/IMEI） |
| `get_telephony_cell_info()` | 基站信息（CID/LAC/信号强度/ARFCN） |
| `get_location(provider)` | GPS 定位（gps/network/passive · 单次/持续/最近） |
| `get_sensor_list()` | 列出所有可用传感器 |
| `read_sensor(name)` | 读取传感器实时数据 |
| `get_device_info()` | 全面设备信息（型号/Android 版本/内核/架构/运行时间） |
| `get_screen_size()` | 屏幕分辨率 |
| `get_screen_brightness()` | 当前亮度（需 Shizuku/ADB） |
| `set_screen_brightness(level)` | 设置亮度 0-255（需 Shizuku/ADB） |
| `device_health_report()` | MCP 服务健康状态（运行时间/PID/日志大小） |
| `list_adb_devices()` | 列出所有 ADB 连接设备（USB + WiFi，含型号） |
| `restart_android(reason)` | 重启 android-mcp 服务（~2-3s 自愈） |

### 📁 文件系统（15 个）

| 工具 | 说明 |
|:-----|:------|
| `read_file(path)` | 读取文本文件（自动检测编码） |
| `write_file(path, content)` | 写入文件（自动创建父目录） |
| `edit_file(path, old, new)` | 文本替换编辑（支持 dry-run 预览） |
| `file_editor(path, action, ...)` | 🔧 **智能行级编辑** — 插入/删除/替换/正则/注释/撤销。预览 → 确认 → 备份 → 回滚全程保护 |
| `search_files(query)` | 🔍 统一搜索引擎：文件名(fd) + 内容(rg) + 元数据过滤 + 模糊匹配(fzf) |
| `file_copy(source, dest)` | 复制文件/目录（自动防覆盖加后缀） |
| `file_move(source, dest)` | 移动/重命名文件/目录 |
| `file_delete(path)` | 安全删除（先预览再确认，不可恢复） |
| `file_trash(path)` | 移到回收站 `~/.trash/`（可还原） |
| `file_symlink(source, link)` | 创建符号链接 |
| `dir_create(path)` | 创建目录（mkdir -p 行为） |
| `get_file_info(path)` | 文件元信息（大小/日期/权限） |
| `list_directory(path)` | 列出目录内容 |
| `list_allowed_directories()` | 列出可访问的目录白名单 |

### 📦 应用管理（9 个）

| 工具 | 说明 |
|:-----|:------|
| `list_installed_packages()` | 列出 Termux 已装包（dpkg） |
| `list_android_packages(keyword)` | 列出 Android 应用（可关键词过滤） |
| `list_running_apps()` | 运行中进程 + CPU + 内存占用 |
| `app_usage_stats(days)` | 应用使用统计（近 N 天） |
| `open_app(package)` | 启动应用（MAIN intent → 已知 Activity → monkey，多级降级） |
| `force_stop_app(package)` | 强制停止应用 |
| `get_current_app()` | 当前聚焦应用（包名+Activity） |
| `analyze_app(package)` | 🔍 深度分析：包信息+权限+内存+Activity+进程 |

### 💬 通信（15 个）

| 工具 | 说明 |
|:-----|:------|
| `list_sms(limit, type)` | 短信列表（inbox/sent/draft/all） |
| `send_sms(number, msg)` | 发送短信（会产生实际费用） |
| `list_contacts()` | 通讯录（姓名/电话/邮箱） |
| `get_clipboard()` | 读取剪贴板（Termux:API → 内存回退） |
| `set_clipboard(text)` | 写入剪贴板 |
| `clipboard_history(limit)` | 剪贴板历史记录 |
| `clipboard_history_clear()` | 清空历史 |
| `send_notification(title, msg)` | 发送通知（可振动） |
| `dismiss_notification(id)` | 按 ID 移除通知 |
| `list_notifications()` | 列出所有活跃通知 |
| `show_toast(text)` | 显示 Toast 消息 |

### 🔊 系统控制（9 个）

| 工具 | 说明 |
|:-----|:------|
| `get_volume()` | 查看所有音频流音量（music/ring/alarm/notification/system/call） |
| `set_volume(stream, level)` | 设置音量（0-15） |
| `toggle_torch(on)` | 手电筒开关 |
| `vibrate(ms, force)` | 震动（支持静音模式强制震动） |
| `text_to_speech(text, lang)` | 文字转语音朗读（支持多语言） |
| `get_fingerprint()` | 指纹认证 |
| `open_url(url)` | 浏览器打开 URL |

### 📷 媒体（7 个）

| 工具 | 说明 |
|:-----|:------|
| `take_photo(camera_id)` | 拍照（0=后置 / 1=前置） |
| `get_camera_info()` | 可用相机列表及参数 |
| `list_photos(dir, limit)` | 列出照片文件（jpg/png/gif/webp/heic） |
| `media_player(action, path)` | 媒体播放控制（play/pause/stop/info） |
| `share_file(path)` | 分享文件（系统分享面板） |
| `download_file(url)` | 下载文件（系统下载管理器） |

### 🌤️ 天气（5 个）

| 工具 | 说明 |
|:-----|:------|
| `get_weather(city)` | 详细天气：温度/湿度/风速/气压 + 未来 3 天预报 |
| `get_weather_short(city)` | 一句话快速获取当前天气概况（支持城市名或坐标） |
| `get_weather_by_coords(lat, lng)` | 通过 GPS 经纬度精准查天气 |
| `get_air_quality(city)` | 空气质量指数 AQI + PM2.5/PM10/O₃ 等污染物 |

### 🔌 ADB（2 个）

| 工具 | 说明 |
|:-----|:------|
| `adb_status()` | ADB/Shizuku 安装和连接状态诊断 |
| `adb_connect(pair_code, ports)` | Android 12+ 无线调试配对连接 |

### 🎭 Shizuku 管理（6 个）

| 工具 | 说明 |
|:-----|:------|
| `shizuku_status()` | 查看 Shizuku 全面状态：App 进程/守护进程/rish 可用性/小窗位置 |
| `shizuku_hide()` | 隐藏 Shizuku 小窗（缩到右上角极小尺寸 + force-stop UI） |
| `shizuku_show()` | 显示/启动 Shizuku App 窗口 |
| `shizuku_resize(l,t,r,b)` | 调整小窗位置和大小（可从全屏到小点自由控制） |
| `shizuku_restart()` | 重启 Shizuku App（卡死时恢复，守护进程不受影响） |

### 💻 GitHub（10 个）

| 工具 | 说明 |
|:-----|:------|
| `github_repo(owner, repo)` | 仓库详情（Star/Fork/描述/许可证） |
| `github_list_repos(username)` | 列出用户仓库 |
| `github_search(query, type)` | 搜索仓库/代码/Issue |
| `github_get_file(owner, repo, path)` | 读取文件或列目录 |
| `github_list_issues(owner, repo)` | 列出 Issue |
| `github_repo_languages(owner, repo)` | 编程语言占比 |
| `github_list_branches(owner, repo)` | 列出分支 |
| `github_refresh_token()` | 手动刷新 GitHub Token |

---

## ⚙️ 依赖

| 依赖 | 用途 | 安装方式 |
|:-----|:------|:----------|
| **Termux:API** | 电池/WiFi/传感器/相机/短信/TTS/剪贴板 | `pkg install termux-api` + 安装 [Termux:API App](https://f-droid.org/packages/com.termux.api/) |
| **Shizuku** 🥇 | 截图/UI dump/录屏/输入注入（推荐） | [Shizuku 官网](https://shizuku.rikka.app/) 开启 + 将 `rish` 放入 `$HOME` |
| **ADB** 🥈 | Shizuku 不可用时的降级方案 | `pkg install android-tools` + 开启无线调试 |
| **Pillow** | 截图劣化/标注截图 | `pip install Pillow` |

### 特权配置

```bash
# 方案 A：Shizuku（推荐）
# 1. 安装 Shizuku App 并授权
# 2. 确保 ~/rish 文件存在且可执行
# 3. 服务自动检测，无需额外配置

# 方案 B：ADB 无线调试（备选）
# 1. 开启 开发者选项 → 无线调试
# 2. adb connect 192.168.1.102:5555
# 3. adb devices 确认连接
```

---

## 🏗️ 项目结构

```
android-mcp/
├── server.py                    # 🚀 stdio 入口
├── http_server.py               # 🌐 HTTP/SSE 入口（端口 3000）
├── http_termux_server.py        # 🔄 HTTP 兼容版
├── pyproject.toml               # 📦 项目配置（v0.4.0）
├── diagnose.sh                  # 🔧 环境诊断脚本
├── keepalive.sh                 # ♻️ 保活监控（30s 自愈）
├── _scan_tools.py               # 📋 工具扫描
└── android_mcp/                 # 🧠 核心代码
    ├── __init__.py              # 包入口
    ├── __main__.py              # python -m 支持
    ├── app.py                   # FastMCP 实例 + 分层加载策略
    ├── prompts.py               # 📝 5 个 Prompt 模板
    ├── resources.py             # 📡 8 个 Resource 数据源
    ├── lib/
    │   ├── constants.py         # 📌 集中路径常量
    │   ├── utils.py             # 🔧 命令执行 + 日志轮转 + 安全门
    │   └── adb.py               # 🔌 ADB 连接管理
    └── tools/
        ├── aggregation.py       # 🔥 聚合工具（device_health 等 3 个）
        ├── ui_smart.py          # 🧠 智能元素定位（find/click by text 等）
        ├── ui_automation.py     # 🖥️ 截图/点击/输入/屏幕控制（20 个）
        ├── device_info.py       # 📱 设备信息（18 个）
        ├── file_system.py       # 📁 文件操作（15 个，含 file_editor）
        ├── app_management.py    # 📦 应用管理（9 个）
        ├── communication.py     # 💬 通信（15 个）
        ├── system_control.py    # 🔊 系统控制（9 个）
        ├── media.py             # 📷 相机/媒体（7 个）
        ├── weather.py           # 🌤️ 天气（5 个）
        ├── shizuku.py           # 🎭 Shizuku 管理（6 个）
        ├── adb.py               # 🔌 ADB 工具（2 个）
        └── github.py            # 💻 GitHub（10 个）
```

---

## 🔧 环境变量

| 变量 | 默认值 | 说明 |
|:-----|:-------|:------|
| `ANDROID_MCP_READONLY` | `false` | 设为 `true` 禁止所有写入操作 |
| `ANDROID_MCP_ALLOW_SHELL` | `true` | 设为 `false` 禁止 Shell 命令执行 |
| `HOST` | `0.0.0.0` | HTTP 服务监听地址 |
| `PORT` | `3000` | HTTP 服务监听端口 |

---

## 🩺 健康检查

HTTP 模式下提供 `/health` 端点：

```bash
curl http://localhost:3000/health

# 返回:
# {
#   "status": "ok",
#   "service": "android-mcp",
#   "uptime_sec": 3600,
#   "uptime_str": "1h 0m 0s",
#   "version": "0.2.0"
# }
```

保活监控脚本 `keepalive.sh` 每 30 秒轮询一次，服务挂了自动拉起，与内部重启形成「双层保险」。

---

## ❓ 常见问题

### 工具执行失败？

```bash
# 运行诊断脚本
cd ~/mcp-servers/android-mcp && bash diagnose.sh
```

### Shizuku 连接失败？

```bash
# 检查 rish 是否存在
ls -la ~/rish

# 测试 rish 连通性
~/rish -c "echo ok"
```

### 截图/点击不生效？

确保 Shizuku 或 ADB 已连接：

```bash
# 检查特权状态
bash ~/mcp-manager.sh status

# 测试截屏
screencap -p /sdcard/test.png && ls -la /sdcard/test.png
```

### 端口被占用？

```bash
lsof -i :3000
```

---

## 📄 许可

MIT — 基于 [xlisp/termux-mcp-server](https://github.com/xlisp/termux-mcp-server)

---

<p align="center">
  <b>🤖 Android MCP Server v0.4</b><br>
  <i>让你的手机成为 AI 的双手</i>
</p>
