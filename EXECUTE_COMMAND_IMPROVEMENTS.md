# Android MCP Server — execute_command 改进建议

> 基于 GitHub 同类项目的对比分析（2026-05-30）

---

## 📊 参考项目总览

| 项目 | 重点特性 | 代码量 | 备注 |
|:-----|:---------|:-------|:-----|
| **termuxgpt/termux-mcp** | 命令预处理、持久 cd、自动应答、HTTP chunked 流 | ~3KB | ✅ 已借鉴安全模块 + 流式 |
| **kirby44/terminals** | 持久化终端会话、输出缓冲、Session 生命周期管理 | ~20KB | 🏆 P1 最大亮点 |
| **valderan/shell-mcp** | 命令白名单(regex)、目录白名单、策略限制、shell_check | ~44KB | 最完善的安全框架 |
| **safebuffer/cli-manager-mcp** | 后台执行(ref_id 轮询)、进程监控、自动清理 | ~5KB | 🏆 P1 异步执行亮点 |
| **mount-ai-in/mount-cli-template** | CLI 模板化 | ~3KB | 亮点不多 |

---

## 🔴 P0 — 建议立即实现

### ① 工作目录持久化（源自 termuxgpt/termux-mcp）

**问题**: 每个 `execute_command` 都是独立子进程，`cd /tmp` 后下一个调用又回到默认目录。AI 无法像人类一样"先 cd 再操作"。

**termuxgpt 做法**: 全局 `_current_dir` 状态 + `handle_cd()` 拦截

```python
# termuxgpt/termux_mcp/shell.py
_current_dir: str = os.getcwd()

def handle_cd(parts):
    if os.path.isdir(new_path):
        set_current_dir(new_path)
        return True, f"📂 {_current_dir}"
```

**建议**: 在 `lib/shell_session.py` 中维护全局 CWD，`execute_command` 拦截 `cd` 命令更新状态。

**收益**: 🏆 极高 — 多步操作的基础设施
**工作量**: ⭐ 小（~50 行代码）

---

### ② 命令预处理增强（源自 termuxgpt/termux-mcp）

**termuxgpt 做法**:

```python
# termuxgpt/termux_mcp/shell.py
def preprocess(cmd):
    cmd = _inject_auto_yes(cmd)           # pkg install → pkg install -y
    cmd = _inject_noninteractive(cmd)     # export DEBIAN_FRONTEND=noninteractive
    return f"export PAGER=cat; {cmd}"     # 防止 less/more 分页器阻塞
```

同时用自动应答线程处理 `pkg install` 的交互提示：

```python
def _spawn_auto_input(process):
    def _worker():
        while process.poll() is None:
            time.sleep(AUTO_INPUT_INTERVAL)  # 每2秒输入一个 y/n
            process.stdin.write("y\n")
    threading.Thread(target=_worker, daemon=True).start()
```

**建议**:
- `export PAGER=cat` — 防止分页器阻塞
- `export DEBIAN_FRONTEND=noninteractive` — 防止 apt 交互对话框
- 自动对 `pkg install`/`apt install` 加 `-y`
- 去除 ANSI 色码（`sed -r "s/\x1B\[[0-9;]*[a-zA-Z]//g"`）

**收益**: ⭐ 高 — 减少交互失败率 80%
**工作量**: ⭐ 小（~30 行代码）

---

## 🟡 P1 — 建议下一批实现

### ③ 持久化终端会话（源自 kirby44/terminals）

**kirby44/terminals 架构**:

```
create_session(id, shell?, cwd?)           → 创建持久化 shell 进程
execute_in_session(id, command)            → 通过 stdin 发送命令
get_session_output(id, lines?, stream?)    → 从缓冲区读取历史输出
list_sessions()                            → 列出所有活跃会话
destroy_session(id)                        → 终止进程，清理资源
```

每个 Session 内部：
- 一个常驻 `ChildProcess`（通过 `spawn(shell, [], { stdio: ["pipe","pipe","pipe"] })`）
- `stdoutBuffer` / `stderrBuffer` / `combinedBuffer` 各保留最多 **1000 行**
- `EventEmitter` 发布 stdout/stderr 事件
- 输出同时写入文件备份（`/tmp/mcp-terminals/<id>/output.log`）
- 退出时通过 `process.on("SIGINT")` 清理所有 Session

**关键代码片段**（session-manager.ts）：

```typescript
class TerminalSession extends EventEmitter {
    private process: ChildProcess;
    private stdoutBuffer: string[] = [];
    private stderrBuffer: string[] = [];
    private maxBufferLines = 1000;

    async execute(command: string): Promise<ExecuteResult> {
        return new Promise((resolve, reject) => {
            const commandLine = `$ ${command}\n`;
            // 写命令到 stdin
            this.process.stdin.write(commandLine);

            // 监听 stdout 事件，直到命令完成
            const onStdout = (output: string) => { ... };
            const onClose = (code: number) => { ... };
            // 超时控制
            const timeout = setTimeout(() => { ... }, 30000);
        });
    }
}
```

**建议 Python 实现**：

```python
class TerminalSession:
    def __init__(self, session_id: str, shell: str = "/system/bin/sh", cwd: str = "."):
        self.process = await asyncio.create_subprocess_shell(
            shell, stdin=PIPE, stdout=PIPE, stderr=PIPE, cwd=cwd
        )
        self.stdout_buffer = asyncio.Queue(maxsize=2000)
        self.stderr_buffer = asyncio.Queue(maxsize=2000)
        # 后台任务持续读取 stdout/stderr
        self._reader = asyncio.create_task(self._read_output())

    async def execute(self, command: str, timeout: int = 30) -> dict:
        self.process.stdin.write((command + "\n").encode())
        await self.process.stdin.drain()
        # 等待输出...（用分隔符或静默期判断命令结束）
```

**注意点**（来自 kirby44 踩过的坑）:
- 非交互模式（non-interactive shell）避免 TTY 兼容问题
- Event listener 泄漏会导致内存泄漏 → 注意清理
- 进程终止顺序：先 close stdin → 再 wait() → 最后 SIGTERM
- 输出结束判断：没有银弹，可以用静默窗口（500ms 无输出 = 命令结束）

**收益**: 🏆 极高 — 让 AI 像真人在终端里操作
**工作量**: ⭐⭐ 中（~300 行代码 + 新文件）

---

### ④ 后台命令执行（源自 safebuffer/cli-manager-mcp）

**safebuffer 设计**:

```
execute_background(cmd)                    → 返回 ref_id (UUID)
get_background_result(ref_id)              → 轮询结果
list_background_processes()                → 查看所有进程
cleanup_background(ref_id)                 → 杀死并清理
```

特性：
- 线程安全的进程管理（用锁保护 ProcessManager 内部状态）
- 1 小时自动清理已完成进程
- 可配置并发上限
- 用 `created_at` / `finished_at` 记录生命周期

**收益**: ⭐ 高 — 编译/下载/爬虫不阻塞
**工作量**: ⭐⭐ 中（~200 行代码）

---

### ⑤ 输出标准化 + 截断策略（源自 valderan/shell-mcp）

**valderan 做法**:

```python
DEFAULT_MAX_OUTPUT_BYTES = 1024 * 1024  # 1MB 上限
```

输出格式：

```
📋 执行结果
────────────────
[stdout]
<输出内容>

[stderr]
<错误信息>

[stat]
  exit code:  0
  duration:   1.23s
  lines:      42
  chars:      3,456
  truncated:  123 lines hidden（加 max_output 参数可调）
```

**收益**: 🔧 中 — 防 Token 爆炸 + 可读性提升
**工作量**: ⭐ 小（~30 行代码）

---

## 🟢 P2 — 锦上添花

### ⑥ 命令预检 `shell_check`（源自 valderan/shell-mcp）

```python
@mcp.tool()
async def shell_check(command: str) -> str:
    """检查命令是否可以安全执行，不实际运行。"""
    from android_mcp.lib.security import get_assessment
    ass = get_assessment(command)
    return f"""
命令: {command}
风险等级: {ass['risk_level']}
评估: {ass['message']}
建议: {ass['suggestion']}
"""
```

### ⑦ 白名单 + 策略框架（源自 valderan/shell-mcp）

```json
{
  "allowed_commands": [
    {"name": "ls", "pattern": "^ls(?:\\s+.*)?$", "requires_directory_check": false},
    {"name": "rm", "pattern": "^rm(?:\\s+.*)?$", "requires_directory_check": true}
  ],
  "blocked_patterns": ["&&", ";", ">", "<"],
  "policy_limits": {
    "max_output_bytes": 1048576,
    "ping": {"max_count": 4, "max_wait_seconds": 2},
    "curl": {"max_time_seconds": 10}
  },
  "whitelisted_directories": ["/sdcard", "/tmp"]
}
```

---

## 🗺 路线图总结

```
当前 v0.4.0 ──── 安全审计 + 流式执行 ✅
      │
      ▼ P0（建议立即）
v0.5.0 ──── ① 工作目录持久化 + ② 命令预处理 + 日志优化
      │
      ▼ P1（建议下一批）
v0.6.0 ──── ③ 持久化终端会话（kirby44 模式）
v0.6.1 ──── ④ 后台命令执行（safebuffer 模式）
v0.6.2 ──── ⑤ 输出标准化 + 分页
      │
      ▼ P2（锦上添花）
v0.7.0 ──── ⑥ shell_check + ⑦ 白名单策略
```

## 🔗 参考链接

| 项目 | GitHub | 借鉴要点 |
|:-----|:-------|:---------|
| termuxgpt/termux-mcp | https://github.com/termuxgpt/termux-mcp | 预处理 + 自动应答 + 持久 cd |
| kirby44/terminals | https://github.com/kirby44/terminals | 持久化会话管理 |
| valderan/shell-mcp | https://github.com/valderan/shell-mcp | 白名单 + 策略限制 |
| safebuffer/cli-manager-mcp | https://github.com/safebuffer/cli-manager-mcp | 后台执行 + 异步轮询 |
