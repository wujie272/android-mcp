"""Shell command execution with security risk assessment ⚡

Execute arbitrary shell commands in Termux with built-in safety checks.
Supports background execution with job management, output filtering,
streaming output, idle timeout, and completion notifications.

Use `FORCE=1 ` prefix to bypass risk assessment for known dangerous commands.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from android_mcp.app import mcp
from android_mcp.lib.utils import (
    async_run,
    ok,
    err,
    check_shell_permission,
    ensure_path_env,
)
from android_mcp.lib.security import get_assessment

logger = logging.getLogger("android-mcp.execute")

# ── Constants ──

MAX_TIMEOUT = 3600  # 1 hour hard cap
DEFAULT_TIMEOUT = 300  # 5 minutes default
DEFAULT_IDLE_TIMEOUT = 120  # 2 min no-output timeout
DEFAULT_MAX_LINES = 500  # output truncation limit

# ── Background Job Management ──


@dataclass
class ShellJob:
    """Represents a background shell job."""

    id: str
    cmd: str
    status: str = "pending"  # pending | running | completed | failed | cancelled | timed_out
    exit_code: int | None = None
    stdout_lines: list[str] = field(default_factory=list)
    stderr_lines: list[str] = field(default_factory=list)
    created_at: float = 0.0
    completed_at: float | None = None
    process: asyncio.subprocess.Process | None = None
    notify_on_done: bool = False
    timed_out: bool = False
    cwd: str | None = None


_jobs: dict[str, ShellJob] = {}

# ══════════════════════════════════════════════════════════════
#  Internal helpers
# ══════════════════════════════════════════════════════════════


def _run_risk_assessment(cmd: str) -> tuple[str, dict]:
    """Run risk assessment. Returns (final_cmd, assessment_dict)."""
    if cmd.startswith("FORCE=1 "):
        return cmd[len("FORCE=1 ") :].strip(), {
            "risk_level": "safe",
            "message": "✅ 用户强制绕过安全检查",
            "blocked": False,
        }
    assessment = get_assessment(cmd)
    if assessment["blocked"]:
        return None, assessment
    return cmd, assessment


def _format_output(
    rc: int | None,
    stdout: str,
    stderr: str,
    error: str,
    timed_out: bool,
    assessment: dict,
    grep: str = "",
    max_lines: int = 0,
    output_format: str = "all",
    output_file: str = "",
    timeout: int = 0,
) -> str:
    """Build the human-readable response string with optional filtering."""
    import re

    lines: list[str] = []

    # Risk warning (non-blocking)
    if assessment.get("risk_level") == "warning":
        lines.append(f"⚠️ {assessment.get('message', '高危命令')}")
        lines.append(f"   {assessment.get('suggestion', '')}")
        lines.append("")

    # Exit code
    if rc == 0:
        lines.append(f"✅ 执行成功 (exit: {rc})")
    elif rc is not None:
        lines.append(f"⚠️ 已执行，非零退出码 (exit: {rc})")
    else:
        lines.append("❌ 执行失败")

    if timed_out:
        lines.append(f"⏱ 已超时 ({timeout}s)")

    # Output file info
    if output_file:
        lines.append(f"📁 输出已保存到: {output_file}")

    # Process stdout
    output_text = ""
    if stdout:
        output_text = stdout

    # Apply grep filter
    if grep and output_text:
        try:
            pat = re.compile(grep, re.MULTILINE)
            matched = [line for line in output_text.split("\n") if pat.search(line)]
            if matched:
                output_text = "\n".join(matched)
            else:
                output_text = f"(无行匹配 `{grep}`)"
        except re.error:
            output_text = f"(grep 正则无效: {grep})\n" + output_text

    # Apply line count truncation
    if max_lines > 0 and output_text:
        split = output_text.split("\n")
        total = len(split)
        if total > max_lines:
            if output_format == "head":
                output_text = "\n".join(split[:max_lines])
                output_text += f"\n… (截断, 显示前 {max_lines}/{total} 行)"
            elif output_format == "tail":
                output_text = "\n".join(split[-max_lines:])
                output_text = f"… (截断, 显示后 {max_lines}/{total} 行)\n" + output_text
            else:
                output_text = "\n".join(split[:max_lines])
                output_text += f"\n… (截断, 显示前 {max_lines}/{total} 行)"

    if output_text:
        lines.extend(["", "─ stdout ─────────────────────", output_text])

    # stderr
    if stderr:
        lines.extend(["", "─ stderr ─────────────────────", stderr])

    # error (only if no stderr)
    if error and not stderr:
        lines.extend(["", "─ error ──────────────────────", error])

    return "\n".join(lines)


async def _run_background_job(job: ShellJob, idle_timeout: int):
    """Execute a shell command in the background with streaming output.

    Reads stdout/stderr line by line so partial output is available
    via get_job_status() while the command is still running.
    """
    job.status = "running"
    job.created_at = time.time()

    try:
        process = await asyncio.create_subprocess_shell(
            job.cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=ensure_path_env(),
            cwd=job.cwd,
        )
        job.process = process

        last_output_time = time.time()

        async def _read_stream(stream, store):
            nonlocal last_output_time
            try:
                while True:
                    line = await asyncio.wait_for(
                        stream.readline(), timeout=idle_timeout
                    )
                    if not line:
                        break
                    decoded = line.decode("utf-8", errors="replace")
                    store.append(decoded)
                    last_output_time = time.time()
            except asyncio.TimeoutError:
                # idle timeout - no output for too long
                job.timed_out = True
                job.status = "timed_out"
                store.append(
                    f"\n⏱ 空闲超时: {idle_timeout}s 内无输出\n"
                )

        await asyncio.gather(
            _read_stream(process.stdout, job.stdout_lines),
            _read_stream(process.stderr, job.stderr_lines),
            process.wait(),
        )

        if job.status != "timed_out":
            job.exit_code = process.returncode
            if process.returncode == 0:
                job.status = "completed"
            else:
                job.status = "failed"

    except asyncio.CancelledError:
        job.status = "cancelled"
        try:
            if job.process:
                job.process.kill()
                await job.process.wait()
        except Exception:
            pass
    except Exception as e:
        job.status = "failed"
        job.stderr_lines.append(f"\n❌ 异常: {e}\n")

    job.completed_at = time.time()

    # Send notification if requested
    if job.notify_on_done:
        _send_job_notification(job)


def _send_job_notification(job: ShellJob):
    """Send an Android notification about a completed job."""
    import subprocess

    if job.status == "completed":
        title = "✅ 命令执行完成"
        body = f"exit 0 | {job.cmd[:80]}"
    elif job.status == "failed":
        title = "⚠️ 命令执行失败"
        body = f"exit {job.exit_code} | {job.cmd[:80]}"
    elif job.status == "cancelled":
        title = "⏹️ 命令已取消"
        body = f"{job.cmd[:80]}"
    elif job.status == "timed_out":
        title = "⏱ 命令超时"
        body = f"{job.cmd[:80]}"
    else:
        return

    try:
        subprocess.run(
            [
                "termux-notification",
                "--title", title,
                "--content", body[:200],
                "--id", f"job-{job.id}",
                "--priority", "high",
            ],
            timeout=5,
            capture_output=True,
        )
    except Exception:
        pass  # best-effort, don't crash


# ══════════════════════════════════════════════════════════════
#  MCP Tools
# ══════════════════════════════════════════════════════════════


@mcp.tool()
async def execute_command(
    command: str = "",
    working_directory: str = ".",
    timeout: int = DEFAULT_TIMEOUT,
    background: bool = False,
    grep: str = "",
    max_lines: int = 0,
    output_format: str = "all",
    output_file: str = "",
    idle_timeout: int = DEFAULT_IDLE_TIMEOUT,
    notify_on_done: bool = False,
) -> str:
    """Execute a shell command in Termux environment ⚡

    ⚠️ 安全机制:
    - 自动评估风险等级，危险命令（rm -rf / 等）默认拦截
    - 可用 FORCE=1 前缀强制绕过: `FORCE=1 rm -rf /tmp/cache`
    - 受 ANDROID_MCP_ALLOW_SHELL 环境变量控制（默认允许）

    🏗️ 后台执行:
    - background=True 立即返回 job_id，不阻塞
    - 用 get_job_status(job_id) 查进度/输出
    - 用 cancel_job(job_id) 终止
    - notify_on_done=True 完成时发系统通知

    📊 输出控制:
    - grep='error|FAIL' — 只返回匹配行
    - max_lines=100 — 截断行数
    - output_format='head|tail|all' — 控制截断方向
    - output_file='/tmp/out.txt' — 输出直接存文件

    Args:
        command: Shell command to execute
        working_directory: Working directory (default: '.')
        timeout: Total timeout in seconds (default: 300, max: 3600)
        background: Run in background (returns job_id immediately)
        grep: Filter output with regex (only matching lines returned)
        max_lines: Truncate output to N lines (0 = no limit)
        output_format: Truncation direction: 'all', 'head', 'tail' (default: 'all')
        output_file: Save stdout to file path
        idle_timeout: Kill if no output for N seconds (default: 120)
        notify_on_done: Send Android notification when done (background only)
    """
    # ── Validation ──
    if not command or not command.strip():
        return err("命令为空", "请提供要执行的命令")

    perm_err = check_shell_permission()
    if perm_err:
        return perm_err

    cmd = command.strip()

    # ── Risk assessment ──
    final_cmd, assessment = _run_risk_assessment(cmd)
    if final_cmd is None:
        return err(
            "危险命令已被拦截",
            f"命令: `{cmd}`\n"
            f"{assessment.get('suggestion', '')}\n"
            f"💡 如需执行，请加 FORCE=1 前缀: `FORCE=1 {cmd}`",
        )

    # Cap timeout
    timeout = min(timeout, MAX_TIMEOUT)

    # Resolve working directory
    cwd = None
    if working_directory and working_directory != ".":
        cwd = str(Path(working_directory).expanduser())

    # ── Background mode ──
    if background:
        job_id = uuid.uuid4().hex[:12]
        job = ShellJob(
            id=job_id,
            cmd=final_cmd,
            cwd=cwd,
            notify_on_done=notify_on_done,
        )
        _jobs[job_id] = job

        # Launch in background
        asyncio.create_task(_run_background_job(job, idle_timeout))

        lines = [
            f"🔄 后台任务已提交",
            f"  Job ID: `{job_id}`",
            f"  命令: `{final_cmd[:200]}`",
            f"  超时: {timeout}s | 空闲超时: {idle_timeout}s",
            "",
            f"📌 查状态: 调用 get_job_status(job_id=\"{job_id}\")",
            f"⏹️  取消: 调用 cancel_job(job_id=\"{job_id}\")",
        ]

        if notify_on_done:
            lines.append("🔔 完成时将发送系统通知")

        return "\n".join(lines)

    # ── Foreground mode (blocking) ──
    try:
        r = await async_run(final_cmd, timeout=timeout, shell=True, cwd=cwd)

        rc = r.get("returncode")
        stdout = r.get("stdout", "").strip()
        stderr = r.get("stderr", "").strip()
        error = r.get("error", "")
        timed_out = r.get("timed_out", False)

        # Save to file if requested
        if output_file and stdout:
            try:
                out_path = Path(output_file).expanduser()
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(stdout, encoding="utf-8")
            except Exception as e:
                return err("输出写入失败", str(e))

        return _format_output(
            rc=rc,
            stdout=stdout,
            stderr=stderr,
            error=error,
            timed_out=timed_out,
            assessment=assessment,
            grep=grep,
            max_lines=max_lines,
            output_format=output_format,
            output_file=output_file,
            timeout=timeout,
        )

    except Exception as e:
        return err("执行异常", str(e))


@mcp.tool()
async def get_job_status(job_id: str, tail: int = 50) -> str:
    """📊 查看后台任务的状态和输出。

    Args:
        job_id: 任务 ID（由 execute_command(background=True) 返回）
        tail: 返回最后 N 行输出（默认 50, -1 返回全部）
    """
    job = _jobs.get(job_id)
    if not job:
        return err("任务不存在", f"Job ID `{job_id}` 未找到。后台任务重启后丢失。")

    elapsed = time.time() - job.created_at
    stdout_text = "".join(job.stdout_lines).strip()
    stderr_text = "".join(job.stderr_lines).strip()

    # Status icon
    status_icons = {
        "pending": "⏳",
        "running": "🔄",
        "completed": "✅",
        "failed": "⚠️",
        "cancelled": "⏹️",
        "timed_out": "⏱",
    }
    icon = status_icons.get(job.status, "❓")

    lines = [
        f"{icon} Job `{job_id}` — {job.status}",
        f"  命令: {job.cmd[:200]}",
        f"  耗时: {elapsed:.1f}s",
    ]

    if job.exit_code is not None:
        lines.append(f"  退出码: {job.exit_code}")

    # Output window
    if tail > 0 and stdout_text:
        out_lines = stdout_text.split("\n")
        total = len(out_lines)
        if len(out_lines) > tail:
            out_lines = out_lines[-tail:]
            lines.append(f"\n  ── stdout (后 {tail}/{total} 行) ──")
        else:
            lines.append(f"\n  ── stdout ({total} 行) ──")
        lines.extend(f"  {l}" for l in out_lines)
    elif tail == -1 and stdout_text:
        lines.append(f"\n  ── stdout (全部) ──")
        lines.append(stdout_text)

    if stderr_text:
        lines.append(f"\n  ── stderr ──")
        lines.append(stderr_text)

    return "\n".join(lines)


@mcp.tool()
async def cancel_job(job_id: str) -> str:
    """⏹️ 取消正在运行的后台任务。

    Args:
        job_id: 任务 ID
    """
    job = _jobs.get(job_id)
    if not job:
        return err("任务不存在", f"Job ID `{job_id}` 未找到。")

    if job.status not in ("pending", "running"):
        return ok(f"任务已 {job.status}，无需取消")

    if job.process and job.process.returncode is None:
        try:
            job.process.terminate()
            # Give it 3s to terminate gracefully, then SIGKILL
            await asyncio.sleep(0.5)
            if job.process.returncode is None:
                job.process.kill()
        except Exception as e:
            return err("取消失败", str(e))

    job.status = "cancelled"
    job.completed_at = time.time()
    return ok(f"任务已取消", f"Job ID: `{job_id}`")
