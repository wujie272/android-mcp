# Android MCP — 改进计划与技术债务

> 基于 GitHub 同类 MCP 项目（termuxgpt/termux-mcp、kirby44/terminals、valderan/shell-mcp、safebuffer/cli-manager-mcp、mount-ai-in/mount-cli-template-mcp）的对比分析，整理的改进路线图。

---

## 📦 项目现状

| 维度 | 当前状态 |
|:-----|:---------|
| 框架 | FastMCP（Python），全量加载，无分层延迟 |
| 工具总数 | 100+ |
| Python 版 | ≥3.10 |
| 包名 | `android-mcp` v0.4.0 |
| 启动方式 | stdio / Streamable HTTP（端口 3000） |
| 特权模式 | Shizuku 🥇 → ADB 🥈 → 普通 🥉（自动降级） |
| 文件 | ~20 个源文件，~16KB 核心逻辑 |

### 已实现的高级特性

| 特性 | 状态 | 备注 |
|:-----|:------|:------|
| ✅ 安全审计层 | ✅ 已实现 | 2026-05-30 新增，三级风险 + FORCE=1 |
| ✅ 流式命令执行 | ✅ 已实现 | `async_run_streaming()`，超时返回部分输出 |
| ✅ 输出截断 | ✅ 已实现 | `MAX_OUTPUT_CHARS=10000` 全局阈值 |
| ✅ 超时部分输出 | ✅ 已实现 | `_extract_timeout_output()` 从 TimeoutExpired 提取 |
| ✅ 聚合工具 | ✅ 已实现 | `device_health()`, `analyze_app()`, `quick_status()` |
| ✅ 健康检查端点 | ✅ 已实现 | GET /health 用于自动重启 |

---

## 🔴 P0 — 建议立即实现

### 1. 工作目录持久化 🏆 极高收益 · 小工作量

**参考**: termuxgpt/termux-mcp 的 `_current_dir` 全局状态

**问题**:
- 当前每个 `execute_command` 是独立子进程，`cd /tmp` 后下一个调用又回到默认目录
- AI 无法像人类一样先 cd 再操作

**方案**:
在 `lib/shell_session.py` 中维护全局工作目录状态 + 拦截 `cd` 命令：

```python
# lib/shell_session.py
_current_working_dir: str | None = None

def get_working_dir() -> str:
    return _current_working_dir or str(HOME)

def handle_cd(path: str) -> str:
    """处理 cd 命令，更新全局状态。"""
    global _current_working_dir
    expanded = path.replace('~', str(HOME))
    new_path = os.path.abspath(
        expanded if os.path.isabs(expanded) 
        else os.path.join(get_working_dir(), expanded)
    )
    if os.path.isdir(new_path):
        _current_working_dir = new_path
        return f"📂 {new_path}"
    return f"❌ 目录不存在: {new_path}"
```

**改动范围**:
- 新增 `lib/shell_session.py`
- 修改 `tools/file_system.py` 的 `execute_command`
- 测试: 验证 `cd /sdcard; ls` 等效于 `ls /sdcard`

---

### 2. 命令预处理增强 ⭐ 高收益 · 小工作量

**参考**: termuxgpt/termux-mcp 的 `preprocess()`

**问题**:
- `pkg install xxx` 卡在交互提示 `[Y/n]`
- `grep --color=auto` 输出含 ANSI 色码干扰 AI 解析
- `less`/`more` 分页器阻塞执行
- `apt` 交互式对话框

**方案**: 注入环境变量和 alias：

```python
COMMAND_PREAMBLE = (
    "export PAGER=cat; "            # 防止分页器阻塞
    "export DEBIAN_FRONTEND=noninteractive; "  # 防止 apt 交互
    "export APT_LISTBUGS_FRONTEND=none; "
    "alias ll='ls -la'; "           # 常用 alias 自动可用
)

# 自动对 pkg/apt 加 -y
def _inject_auto_yes(cmd: str) -> str:
    for trigger in ['pkg install', 'pkg reinstall', 'apt install', 'apt-get install']:
        if trigger in cmd and '-y' not in cmd:
            cmd = cmd.replace(trigger, f"{trigger} -y")
    return cmd
```

**改动范围**:
- 仅修改 `tools/file_system.py` 的 `execute_command` 函数（执行前预处理）

---

### 3. 优化日志系统 🔧 中等收益 · 小工作量

**问题**:
- 日志级别冗余：所有 DEBUG 日志都输出到文件，但 INFO 级别的 stderr handler 也输出到终端
- 日志文件名硬编码，不方便按日期切割
- 缺少请求 ID 追踪链（每个工具调用请求关联一条日志链）

**方案**: 引入结构化日志（JSON）和请求追踪：

```python
import uuid

_request_id = None

def set_request_id(rid: str | None = None):
    global _request_id
    _request_id = rid or uuid.uuid4().hex[:8]

class RequestFilter(logging.Filter):
    def filter(self, record):
        record.request_id = _request_id or '-'
        return True
```

日志格式改为：
```
15:07:04 [DEBUG] [req:a1b2c3] [stream] starting: echo hello world
```

**改动范围**:
- 修改 `lib/utils.py` 的日志配置

---

## 🟡 P1 — 建议下一批实现

### 4. 持久化终端会话 ⭐ 极高收益 · 中等工作量

**参考**: kirby44/terminals（完整会话管理器，~11KB TypeScript）

**问题**:
- 每次 `execute_command` 都是全新子进程，shell 历史、环境变量、别名全部丢失
- 无法做"先 `export API_KEY=xxx` 再 `curl $API_KEY/endpoint`"的多步操作
- 无法长时间运行守护进程（如 `npm run dev`、`python -m http.server`）

**设计**: 新增一组会话管理工具

```python
# ── 新增工具列表 ──

create_session(session_id, shell?="/system/bin/sh", cwd?=".")
    → 创建持久化 shell 进程（通过 asyncio.create_subprocess_shell）
    → 进程保持运行，通过 stdin/stdout/stderr 通信

execute_in_session(session_id, command, timeout?=30)
    → 向 session 的 stdin 发送命令
    → 从 stdout/stderr 读取输出（用分隔符标记命令结束）

get_session_output(session_id, lines?=50, stream?="all")
    → 获取会话的历史输出缓冲区（最多 2000 行）

list_sessions()
    → 列出所有活跃会话（ID / shell / CWD / 创建时间 / 最后活动 / 输出行数）

destroy_session(session_id)
    → 终止会话进程，清理资源

set_default_session(session_id)
    → 设置默认会话，后续 execute_command 自动路由到该会话
```

**边界情况**:
- Session 进程意外退出 → 自动标记为 stopped，下次调用自动重启
- 超时命令 → 不杀进程，只返回已有输出（适合 `npm run dev` 等长期进程）
- 会话数上限 → 默认最多 5 个，可配置
- 空闲超时 → 30 分钟无活动自动销毁

**代码架构**:

```
lib/
  session_manager.py    ← 新增：会话管理器 + Session 类
tools/
  terminal_sessions.py  ← 新增：5 个 MCP 工具
```

**参考实现**:
- kirby44/terminals 的 `session-manager.ts`（EventEmitter + 输出缓冲 + 文件持久化）
- 我们可简化：去掉文件持久化，保留内存缓冲区 + asyncio 事件循环

---

### 5. 后台命令执行 ⭐ 高收益 · 中等工作量

**参考**: safebuffer/cli-manager-mcp

**问题**:
- 长时间运行的命令（编译 APK、下载大文件、爬虫）**阻塞当前工具调用**
- AI 只能干等，无法并行做其他事

**设计**:

```python
execute_background(command, timeout?=3600)
    → 启动子进程，返回 ref_id
    → 进程在后台运行，不阻塞

get_background_result(ref_id)
    → 轮询结果：running / success / failed
    → 返回 stdout / stderr / returncode

list_background_processes()
    → 列出所有后台进程（ref_id / command / 状态 / 运行时间）

cleanup_background(ref_id)
    → 杀死进程 + 清理资源
```

**与持久化会话的区别**:

| 特性 | 持久化会话 | 后台执行 |
|:-----|:-----------|:---------|
| 交互性 | 可多次发送命令 + 读取输出 | 一次性命令 |
| 状态保持 | 保持环境变量/CWD/别名 | 无状态 |
| 适用场景 | 多步工作流 | 一次性长任务 |
| 资源消耗 | 较高（常驻 shell 进程） | 较低（完成后自动销毁） |

---

### 6. 输出标准化与分页 🔧 中等收益 · 小工作量

**参考**: valderan/shell-mcp 的 `max_output_bytes`

**问题**:
- 当前返回格式是纯文本，exit_code 和 stderr 混合在末尾
- 超长输出直接截断但没告知截断了多少

**方案**: 标准化返回格式 + 智能分页

```
📋 执行结果
────────────────
[stdout]
<主输出内容>

[stderr]
<错误信息>

[stat]
  exit code:  0
  duration:   1.23s
  lines:      42
  chars:      3,456
  truncated:  123 lines, 89,234 chars (加 max_output 参数可调)
```

新增 `max_output_lines` 和 `max_output_chars` 参数：

```python
@mcp.tool()
async def execute_command(
    command: str = "",
    timeout: int = 30,
    max_output_lines: int = 500,      # ← 新增
    max_output_chars: int = 30000,    # ← 新增
    check_risk: bool = True,
    stream: bool = False,
) -> str:
```

---

## 🟢 P2 — 锦上添花

### 7. 命令预检 `shell_check` 🟢 低工作量

**参考**: valderan/shell-mcp 的 `shell_check` 工具

**设计**:

```python
@mcp.tool()
async def shell_check(command: str) -> str:
    """检查命令是否可以安全执行，不实际运行。"""
    from android_mcp.lib.security import get_assessment
    ass = get_assessment(command)
    ...
```

适合 AI 在不确定一条命令是否安全时先用它预览。

---

### 8. 命令白名单 + 策略限制框架 🟢 中等工作量

**参考**: valderan/shell-mcp 的 `config.json`（48 条命令白名单 + 策略限制）

**设计**: 可选配置文件 `config.json`：

```json
{
  "execute_command": {
    "enabled": true,
    "max_output_chars": 50000,
    "max_concurrent": 10,
    "allowed_commands": ["ls", "cat", "echo", "pwd", "cd"],
    "blocked_commands": ["reboot", "halt"],
    "env_overrides": {
      "PAGER": "cat",
      "DEBIAN_FRONTEND": "noninteractive"
    }
  }
}
```

---

## 📊 分支对比总表

| 项目 | 已借鉴 | 可借鉴亮点 |
|:-----|:-------|:-----------|
| **termuxgpt/termux-mcp** | ✅ 通信协议 / HTTP 流式 / shell 安全模式 | ⟳ 命令预处理（auto-yes, PAGER=cat） |
| | | ⟳ 持久化 `_current_dir` |
| | | ⟳ 自动应答线程 |
| **kirby44/terminals** | | ⟳ **持久化会话管理（最大亮点）** |
| | | ⟳ 独立 stdout/stderr 缓冲区 |
| | | ⟳ Session 文件持久化 |
| **valderan/shell-mcp** | | ⟳ 命令白名单 + 策略限制 |
| | | ⟳ 目录白名单 |
| | | ⟳ `shell_check` 预检工具 |
| | | ⟳ Policy limits（ping/curl/nc 限制） |
| **safebuffer/cli-manager** | | ⟳ **后台执行 + ref_id 轮询** |
| | | ⟳ 自动清理（1 小时过期） |
| | | ⟳ 并发进程数限制 |
| **mount-ai-in/mount-cli-template** | | 模板化 CLI 工具，亮点不多 |

---

## 🗺 路线图

```
v0.4.0 ──── 当前（安全审计 + 流式执行 + 输出截断）
               │
               ▼  P0（建议立即）
v0.5.0 ──── 工作目录持久化 + 命令预处理增强 + 日志优化
               │
               ▼  P1（建议下一批）
v0.6.0 ──── 持久化终端会话（create_session / execute_in_session）
v0.6.1 ──── 后台命令执行（execute_background / get_background_result）
v0.6.2 ──── 输出标准化 + 分页
               │
               ▼  P2（锦上添花）
v0.7.0 ──── shell_check 预检 + 白名单策略
```

---

## 🔗 参考项目链接

| 项目 | 地址 | Star |
|:-----|:-----|:------|
| termuxgpt/termux-mcp | https://github.com/termuxgpt/termux-mcp | ⭐5 |
| kirby44/terminals | https://github.com/kirby44/terminals | ⭐2 |
| valderan/shell-mcp | https://github.com/valderan/shell-mcp | ⭐0 |
| safebuffer/cli-manager-mcp | https://github.com/safebuffer/cli-manager-mcp | ⭐1 |
| mount-ai-in/mount-cli-template-mcp | https://github.com/mount-ai-in/mount-cli-template-mcp | ⭐0 |
