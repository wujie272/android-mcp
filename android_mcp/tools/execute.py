"""Shell command execution with security risk assessment ⚡

Execute arbitrary shell commands in Termux with built-in safety checks.
Use `FORCE=1 ` prefix to bypass risk assessment for known dangerous commands.
"""

import logging
from android_mcp.app import mcp
from android_mcp.lib.utils import async_run, ok, err, check_shell_permission
from android_mcp.lib.security import get_assessment

logger = logging.getLogger('android-mcp.execute')


@mcp.tool()
async def execute_command(command: str = "", working_directory: str = ".", timeout: int = 30) -> str:
    """Execute a shell command in Termux environment ⚡

    ⚠️ 安全机制:
    - 自动评估风险等级，危险命令（rm -rf / 等）默认拦截
    - 可用 FORCE=1 前缀强制绕过: `FORCE=1 rm -rf /tmp/cache`
    - 受 ANDROID_MCP_ALLOW_SHELL 环境变量控制（默认允许）

    Args:
        command: Shell command to execute
        working_directory: Working directory (default: current directory '.')
        timeout: Timeout in seconds (default: 30, max: 120)
    """
    if not command or not command.strip():
        return err("命令为空", "请提供要执行的命令")

    # Check global shell permission
    perm_err = check_shell_permission()
    if perm_err:
        return perm_err

    cmd = command.strip()

    # ── Risk assessment ──
    if cmd.startswith('FORCE=1 '):
        cmd_to_run = cmd[len('FORCE=1 '):].strip()
        assessment = {'risk_level': 'safe', 'message': '✅ 用户强制绕过安全检查', 'blocked': False}
    else:
        assessment = get_assessment(cmd)
        if assessment['blocked']:
            return err(
                "危险命令已被拦截",
                f"命令: `{cmd}`\n"
                f"{assessment.get('suggestion', '')}\n"
                f"💡 如需执行，请加 FORCE=1 前缀: `FORCE=1 {cmd}`"
            )
        cmd_to_run = cmd

    # ── Execute ──
    try:
        timeout = min(timeout, 120)  # cap at 120 seconds
        cwd = working_directory if working_directory and working_directory != '.' else None

        r = await async_run(cmd_to_run, timeout=timeout, shell=True, cwd=cwd)

        # Build response
        lines = []

        # Risk warning (non-blocking)
        if assessment.get('risk_level') == 'warning':
            lines.append(f"⚠️ {assessment.get('message', '高危命令')}")
            lines.append(f"   {assessment.get('suggestion', '')}")
            lines.append("")

        # Return code
        rc = r.get('returncode')
        if rc == 0:
            lines.append(f"✅ 执行成功 (exit: {rc})")
        elif rc is not None:
            lines.append(f"⚠️ 已执行，非零退出码 (exit: {rc})")
        else:
            lines.append(f"❌ 执行失败")

        if r.get('timed_out'):
            lines.append(f"⏱ 已超时 ({timeout}s)")

        # Stdout / stderr
        stdout = r.get('stdout', '').strip()
        stderr = r.get('stderr', '').strip()
        error = r.get('error', '')

        if stdout:
            lines.extend(["", "─ stdout ─────────────────────", stdout])
        if stderr:
            lines.extend(["", "─ stderr ─────────────────────", stderr])
        if error and not stderr:
            lines.extend(["", "─ error ──────────────────────", error])

        return "\n".join(lines)

    except Exception as e:
        return err("执行异常", str(e))