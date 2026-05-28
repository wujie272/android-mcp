"""File system tools: read, write, edit, search, list, execute commands."""

import os
import json
import shutil
import time as _time
from pathlib import Path
from datetime import datetime

from android_mcp.app import mcp
from android_mcp.lib.utils import async_run, ensure_path_env
from android_mcp.lib.constants import HOME, SDCARD, SDCARD_SHORT

_TRASH_DIR = HOME / '.trash'

MAX_OUTPUT_CHARS = 10000


# ── Read / Write ──

@mcp.tool()
async def read_file(file_path: str) -> str:
    """Read a text file (up to 10MB, auto-detects encoding)."""
    try:
        path = Path(file_path)
        if not path.exists():
            return f"Error: File not found: {file_path}"
        if path.stat().st_size > 10 * 1024 * 1024:
            return f"Error: File too large ({path.stat().st_size:,} bytes)"
        for enc in ['utf-8', 'gbk', 'gb2312', 'latin-1']:
            try:
                content = path.read_text(encoding=enc)
                if len(content) > MAX_OUTPUT_CHARS:
                    content = (content[:MAX_OUTPUT_CHARS]
                               + f"\n\n⚠️ [截断: 共 {len(content):,} 字符, 仅显示前 {MAX_OUTPUT_CHARS:,}]")
                return content
            except UnicodeDecodeError:
                continue
        return "Error: Cannot decode file"
    except Exception as e:
        return f"Error reading file: {e}"


@mcp.tool()
async def write_file(file_path: str, content: str) -> str:
    """Write text to a file (creates parent directories)."""
    try:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        return f"Written {len(content)} chars to {file_path}"
    except Exception as e:
        return f"❌ 写入失败: {e}"


# ── Edit ──

@mcp.tool()
async def edit_file(file_path: str, old_text: str, new_text: str, dry_run: bool = False) -> str:
    """Replace first occurrence of old_text with new_text. Use dry_run=True to preview."""
    path = Path(file_path)
    if not path.exists():
        return f"Error: File not found: {file_path}"
    try:
        content = path.read_text(encoding='utf-8')
    except Exception as e:
        return f"Error reading file: {e}"
    if old_text not in content:
        return f"Error: Text not found in {file_path}"
    new_content = content.replace(old_text, new_text, 1)
    if dry_run:
        import difflib
        diff = difflib.unified_diff(content.splitlines(keepends=True), new_content.splitlines(keepends=True))
        return "--- DRY RUN (NOT applied) ---\n" + "".join(diff)
    try:
        path.write_text(new_content, encoding='utf-8')
        return f"✅ Edited: replaced \"{old_text[:50]}\" → \"{new_text[:50]}\""
    except Exception as e:
        return f"Error writing file: {e}"


# ── Search ──

@mcp.tool()
async def search_files(path: str | None = None, pattern: str | None = None,
                       exclude_patterns: list[str] | None = None) -> str:
    """Recursively search files matching a glob pattern."""
    import fnmatch
    if path is None:
        path = "."
    if pattern is None:
        pattern = "*"
    root = Path(path)
    if not root.exists() or not root.is_dir():
        return f"Error: Invalid directory: {path}"
    exclude = exclude_patterns or []
    results = []
    try:
        for f in sorted(root.rglob(pattern)):
            rel = str(f.relative_to(root)) if f != root else ''
            if any(fnmatch.fnmatch(rel, exc) for exc in exclude) or any(fnmatch.fnmatch(f.name, exc) for exc in exclude):
                continue
            try:
                stat = f.stat()
                kind = "📁" if f.is_dir() else "📄"
                size = f"({stat.st_size:,} bytes)" if f.is_file() else ""
                results.append(f"{kind} {f} {size}")
            except Exception:
                results.append(f"? {f}")
    except PermissionError:
        return f"Error: Permission denied: {path}"
    if not results:
        return f"No files matching '{pattern}' in {root}"
    return f"Found {len(results)} in {root}:\n\n" + "\n".join(results)


# ── Directory Tree ──

@mcp.tool()
async def directory_tree(path: str | None = None, exclude_patterns: list[str] | None = None) -> str:
    """Get directory tree as JSON."""
    import fnmatch
    if path is None:
        path = "."

    def build_tree(dir_path: Path):
        items = []
        try:
            for item in sorted(dir_path.iterdir()):
                if exclude_patterns and any(fnmatch.fnmatch(item.name, exc) for exc in exclude_patterns):
                    continue
                if item.is_dir():
                    items.append({'name': item.name, 'type': 'directory', 'children': build_tree(item)})
                else:
                    items.append({'name': item.name, 'type': 'file'})
        except PermissionError:
            items.append({'name': '(denied)', 'type': 'file'})
        return items

    root = Path(path)
    if not root.exists() or not root.is_dir():
        return f"Error: Invalid directory: {path}"
    tree = [{'name': str(root.absolute()), 'type': 'directory', 'children': build_tree(root)}]
    return json.dumps(tree, indent=2, ensure_ascii=False)


# ── File Info ──

@mcp.tool()
async def get_file_info(file_path: str) -> str:
    """Get file/directory metadata: size, dates, permissions, owner."""
    path = Path(file_path)
    if not path.exists():
        return f"Error: File not found: {file_path}"
    try:
        stat = path.stat()
        info = {'name': path.name, 'path': str(path.absolute()),
                'type': 'directory' if path.is_dir() else 'file',
                'size_bytes': stat.st_size,
                'created': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'permissions': oct(stat.st_mode)[-3:]}
        try:
            import pwd
            info['owner'] = pwd.getpwuid(stat.st_uid).pw_name
        except Exception:
            info['owner'] = str(stat.st_uid)
        try:
            import grp
            info['group'] = grp.getgrgid(stat.st_gid).gr_name
        except Exception:
            info['group'] = str(stat.st_gid)
        if path.is_symlink():
            info['symlink_target'] = str(path.resolve())
        return json.dumps(info, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Error: {e}"


# ── List Directory ──

@mcp.tool()
async def list_directory(directory_path: str | None = None, show_hidden: bool = False) -> str:
    """List directory contents with sizes and modification times."""
    if directory_path is None:
        directory_path = "."
    path = Path(directory_path)
    if not path.exists() or not path.is_dir():
        return f"Error: Invalid directory: {directory_path}"
    items = []
    try:
        for item in sorted(path.iterdir()):
            if not show_hidden and item.name.startswith('.'):
                continue
            try:
                stat = item.stat()
                kind = "DIR " if item.is_dir() else "FILE"
                size = stat.st_size if item.is_file() else 0
                mtime = datetime.fromtimestamp(stat.st_mtime).strftime('%m-%d %H:%M')
                items.append(f"{kind} {item.name:<45} {size:>12,} bytes  {mtime}")
            except Exception:
                items.append(f"ERR  {item.name}")
    except PermissionError:
        return f"Error: Permission denied: {directory_path}"
    if not items:
        return f"Directory is empty: {path.absolute()}"
    return f"Contents of: {path.absolute()}\n{'─' * 70}\n" + "\n".join(items)


@mcp.tool()
async def list_directory_with_sizes(path: str | None = None, sort_by: str = "name") -> str:
    """List directory sorted by name or size."""
    if path is None:
        path = "."
    root = Path(path)
    if not root.exists() or not root.is_dir():
        return f"Error: Invalid directory: {path}"
    items = []
    total_files = total_dirs = total_size = 0
    try:
        for item in root.iterdir():
            try:
                stat = item.stat()
                entry = {'name': item.name, 'type': 'directory' if item.is_dir() else 'file',
                         'size': stat.st_size, 'modified': datetime.fromtimestamp(stat.st_mtime).isoformat()}
                items.append(entry)
                if item.is_file():
                    total_files += 1
                    total_size += stat.st_size
                else:
                    total_dirs += 1
            except Exception:
                pass
    except PermissionError:
        return f"Error: Permission denied: {path}"
    items.sort(key=lambda x: (x['size'] if 'size' else 0) if sort_by == 'size' else x['name'].lower(),
               reverse=(sort_by == 'size'))
    lines = [f"Contents of {root} (sorted by {sort_by})\n"]
    for item in items:
        size_str = f"{item['size']:>12,} bytes" if item['type'] == 'file' else ""
        icon = "📁" if item['type'] == 'directory' else "📄"
        lines.append(f"{icon} {item['name']:<45} {size_str}  {item['modified']}")
    lines.append(f"\nFiles: {total_files}  Dirs: {total_dirs}  Total: {total_size:,} bytes")
    return "\n".join(lines)


# ── Allowed Directories ──

@mcp.tool()
async def list_allowed_directories() -> str:
    """List accessible directories."""
    accessible = []
    for p in [str(HOME), str(SDCARD_SHORT), str(SDCARD)]:
        path = Path(p)
        if path.exists():
            rw = "R/W" if os.access(p, os.R_OK | os.W_OK) else ("R/O" if os.access(p, os.R_OK) else "N/A")
            accessible.append(f"  {rw}  {p}")
    return "Accessible:\n" + "\n".join(accessible) if accessible else "None found."


# ── Execute Command ──

@mcp.tool()
async def execute_command(
    command: str = "",
    working_directory: str = ".",
    timeout: int = 30,
    check_risk: bool = True,
    stream: bool = False,
) -> str:
    """Execute a shell command.

    🔒 Security audit: auto-blocks dangerous commands (rm -rf /, fork bomb, etc.).
       Use FORCE=1 prefix to bypass: FORCE=1 rm -rf /tmp/cache
    ⚡ Streaming mode: reads line-by-line, returns partial output on timeout.

    Args:
        command: Shell command to execute
        working_directory: Working directory (default: current)
        timeout: Timeout in seconds (default: 30)
        check_risk: Enable security audit (default: True)
        stream: Use streaming execution (default: False)
    """
    if not command.strip():
        return ("❌ 错误：`command` 参数不能为空。\n"
                "正确用法：execute_command(command='ls -la', working_directory='.', timeout=30)")

    if check_risk:
        from android_mcp.lib.security import assess_risk, RiskLevel
        level, msg, sugg = assess_risk(command)
        if level == RiskLevel.DANGEROUS:
            return f"{msg}\n命令: `{command}`\n\n{sugg}\n\n💡 如需执行: `FORCE=1 {command}`"
        if level == RiskLevel.WARNING:
            return f"{msg}\n命令: `{command}`\n\n{sugg}\n\n💡 如需执行加 FORCE=1 前缀"

    try:
        if stream:
            from android_mcp.lib.utils import async_run_streaming
            result = await async_run_streaming(command, timeout=timeout)
        else:
            result = await async_run(command, timeout=timeout, shell=True, cwd=working_directory)

        output = []
        if result.get('stdout', '').strip():
            output.append(result['stdout'].strip())
        if result.get('stderr', '').strip():
            output.append(f"[stderr] {result['stderr'].strip()}")
        if result.get('timed_out'):
            output.append(f"⏱️ [超时 {timeout}s，已返回部分输出]")
        output.append(f"[exit code: {result.get('returncode', '?')}]")
        return "\n".join(output)
    except Exception as e:
        return f"❌ 命令执行失败 (timeout={timeout}s): {e}"

# ── Search Content (grep) ──

@mcp.tool()
async def search_content(
    query: str,
    path: str | None = None,
    pattern: str | None = None,
    use_regex: bool | None = None,
    case_sensitive: bool | None = None,
    context_lines: int | None = None,
    max_results: int | None = None,
    exclude_patterns: list[str] | None = None,
) -> str:
    """🔍 搜索文件内容（基于 ripgrep）。支持正则、上下文行、排除模式。

    Args:
        query: 要搜索的关键词或正则表达式
        path: 搜索目录（默认 "."）
        pattern: 文件名 glob 过滤，如 "*.md"（可选）
        use_regex: 是否将 query 视为正则（默认 False）
        case_sensitive: 大小写敏感（默认 False）
        context_lines: 匹配行上下文的行数，如 2 表示前后各 2 行（默认 0）
        max_results: 最大返回结果数（默认 50）
        exclude_patterns: 排除的文件模式，如 ["*.trash", "node_modules"]
    """
    from android_mcp.lib.utils import async_run

    if not query or not query.strip():
        return "❌ query（搜索内容）不能为空"

    if path is None:           path = "."
    if max_results is None:    max_results = 50
    if context_lines is None:  context_lines = 0
    if use_regex is None:      use_regex = False
    if case_sensitive is None: case_sensitive = False

    # 构建 rg 命令参数列表
    cmd = ["rg", "--no-heading", "-n"]
    if use_regex:
        cmd.append("-P")               # PCRE 正则
    if not case_sensitive:
        cmd.append("-i")               # 忽略大小写
    if context_lines > 0:
        cmd.extend(["-C", str(context_lines)])
    # 排除目录/文件
    if exclude_patterns:
        for ep in exclude_patterns:
            cmd.extend(["-g", f"!{ep}"])
    # 文件名过滤
    if pattern:
        cmd.extend(["-g", pattern])
    # 每个文件最多显示 50 个匹配，防止大文件刷屏
    cmd.extend(["--max-count", "50"])
    cmd.extend(["--", query, path])

    result = await async_run(cmd, timeout=30, shell=False)

    if result.get('success'):
        lines = [l for l in result['stdout'].strip().split('\n') if l.strip()]
        total = len(lines)
        if total == 0:
            return f"🔍 未找到匹配 '{query}' 的内容"

        if total > max_results:
            display = lines[:max_results]
            summary = f"🔍 找到至少 {total} 处匹配（显示前 {max_results} 条，共 {total} 处）"
        else:
            display = lines
            summary = f"🔍 找到 {total} 处匹配"

        output_parts = [f"{summary} 在 {path}:\n"]
        output_parts.extend(display)
        return "\n".join(output_parts)

    elif result.get('returncode') == 1:
        return f"🔍 未找到匹配 '{query}' 的内容"
    else:
        err_msg = result.get('stderr', '').strip()[:300] or result.get('error', '未知错误')
        if 'not found' in err_msg.lower() or 'no such file' in err_msg.lower():
            return "❌ 系统中未安装 ripgrep（rg），请执行: pkg install ripgrep"
        return f"❌ 搜索出错: {err_msg}"


# ── Search Advanced (复合搜索) ──

@mcp.tool()
async def search_advanced(
    query: str | None = None,
    path: str | None = None,
    pattern: str | None = None,
    use_regex: bool | None = None,
    case_sensitive: bool | None = None,
    max_results: int | None = None,
    sort_by: str | None = None,
    sort_order: str | None = None,
    max_depth: int | None = None,
    modified_days: int | None = None,
    min_size: int | None = None,
    max_size: int | None = None,
    file_types: list[str] | None = None,
    context_lines: int | None = None,
    exclude_patterns: list[str] | None = None,
) -> str:
    """🔍 高级复合搜索：文件名 + 内容 + 时间 + 大小 + 类型 多维度组合。

    支持全维度过滤和排序，适合复杂搜索需求。

    Args:
        query: 文件内容关键词（不传则仅按文件名/元数据搜索）
        path: 搜索目录（默认 "."）
        pattern: 文件名 glob 模式，如 "*.md"、"*MCP*"（可选）
        use_regex: 是否将 query 视为正则（默认 False）
        case_sensitive: 文件名/内容大小写敏感（默认 False）
        max_results: 最大返回结果数（默认 200）
        sort_by: 排序字段 "name" / "size" / "date"（默认 "date"）
        sort_order: 排序方向 "asc" / "desc"（默认 "desc"）
        max_depth: 最大搜索深度，如 3 表示最多 3 层子目录（默认不限）
        modified_days: 最近 N 天内修改过的文件（如 7 = 最近一周）
        min_size: 文件大小下限（字节），如 1024 = 至少 1KB
        max_size: 文件大小上限（字节），如 1048576 = 最多 1MB
        file_types: 文件扩展名过滤，如 ["md", "py", "txt"]
        context_lines: 内容匹配时的上下文行数（默认 0，仅 query 时有效）
        exclude_patterns: 排除的文件/目录模式，如 [".trash", ".git"]
    """
    import os, fnmatch
    from datetime import datetime

    if path is None:           path = "."
    if max_results is None:    max_results = 200
    if sort_by is None:        sort_by = "date"
    if sort_order is None:     sort_order = "desc"
    if case_sensitive is None: case_sensitive = False
    if use_regex is None:      use_regex = False
    if context_lines is None:  context_lines = 0

    root_path = Path(path)
    if not root_path.exists() or not root_path.is_dir():
        return f"❌ 无效目录: {path}"

    # 规范化 file_types（去掉点号）
    if file_types:
        file_types = [t.lstrip(".").lower() for t in file_types]

    base_depth = str(root_path.resolve()).count("/")
    candidates = []  # [(path, size, mtime)]

    try:
        for root_str, dirs, files in os.walk(str(root_path)):
            # ── 深度控制 ──
            if max_depth is not None:
                current_depth = root_str.count("/") - base_depth
                if current_depth >= max_depth:
                    dirs.clear()
                    continue

            dirs.sort()

            for fname in sorted(files):
                fullpath = os.path.join(root_str, fname)

                # ── 文件名匹配 ──
                if pattern:
                    if case_sensitive:
                        if not fnmatch.fnmatch(fname, pattern):
                            continue
                    else:
                        if not fnmatch.fnmatch(fname.lower(), pattern.lower()):
                            continue

                # ── 扩展名过滤 ──
                if file_types:
                    ext = os.path.splitext(fname)[1].lstrip(".").lower()
                    if ext not in file_types:
                        continue

                # ── 排除模式 ──
                if exclude_patterns:
                    excluded = False
                    for ep in exclude_patterns:
                        if fnmatch.fnmatch(fname, ep) or fnmatch.fnmatch(fullpath, f"*{ep}*"):
                            excluded = True
                            break
                    if excluded:
                        continue

                try:
                    st = os.stat(fullpath)
                except OSError:
                    continue

                # ── 时间过滤 ──
                if modified_days is not None:
                    age_days = (datetime.now().timestamp() - st.st_mtime) / 86400
                    if age_days > modified_days:
                        continue

                # ── 大小过滤 ──
                if min_size is not None and st.st_size < min_size:
                    continue
                if max_size is not None and st.st_size > max_size:
                    continue

                candidates.append((fullpath, st.st_size, st.st_mtime))

                if len(candidates) >= max_results * 2:
                    break
            if len(candidates) >= max_results * 2:
                break
    except PermissionError:
        pass

    if not candidates:
        return "🔍 未找到匹配任何条件的文件"

    # ── 内容过滤（如果有 query） ──
    need_content_filter = query is not None and query.strip()

    if need_content_filter:
        from android_mcp.lib.utils import async_run

        # 分批次用 rg 过滤
        matched_set = set()
        batch_size = 200

        for i in range(0, len(candidates), batch_size):
            batch_paths = [c[0] for c in candidates[i:i+batch_size]]
            if not batch_paths:
                continue

            cmd = ["rg", "-l"]
            if use_regex:
                cmd.append("-P")
            if not case_sensitive:
                cmd.append("-i")
            cmd.extend(["--", query.strip()])
            cmd.extend(batch_paths)

            rg_result = await async_run(cmd, timeout=30, shell=False)

            if rg_result.get('success') and rg_result['stdout'].strip():
                for matched_path in rg_result['stdout'].strip().split('\n'):
                    matched_path = matched_path.strip()
                    if matched_path:
                        matched_set.add(matched_path)
            elif rg_result.get('returncode') == 1:
                continue  # 这批没匹配
            else:
                err = rg_result.get('stderr', '').strip()[:200]
                if 'not found' in err.lower():
                    return "❌ 系统中未安装 ripgrep（rg），请执行: pkg install ripgrep"

        candidates = [c for c in candidates if c[0] in matched_set]

        if not candidates:
            return f"🔍 未找到包含 '{query}' 的文件"

    # ── 排序 ──
    reverse = sort_order == "desc"
    if sort_by == "size":
        candidates.sort(key=lambda x: x[1], reverse=reverse)
    elif sort_by == "name":
        candidates.sort(key=lambda x: x[0].lower(), reverse=reverse)
    else:  # date
        candidates.sort(key=lambda x: x[2], reverse=reverse)

    # ── 截取 ──
    total = len(candidates)
    if total > max_results:
        candidates = candidates[:max_results]

    # ── 格式化输出 ──
    # 构建过滤条件摘要
    filters = []
    if pattern:       filters.append(f"文件名=「{pattern}」")
    if query:         filters.append(f"内容=「{query}」")
    if modified_days: filters.append(f"最近{modified_days}天")
    if min_size:      filters.append(f"≥{_fmt_size(min_size)}")
    if max_size:      filters.append(f"≤{_fmt_size(max_size)}")
    if file_types:    filters.append(f"类型=「{','.join(file_types)}」")
    if max_depth:     filters.append(f"深度≤{max_depth}")
    filter_str = " · ".join(filters) if filters else "无条件"

    header = f"🎯 复合搜索: {filter_str}"
    if total > max_results:
        header += f"\n📊 找到 {total} 个文件（显示前 {max_results} 个）"
    else:
        header += f"\n📊 找到 {total} 个文件"
    header += f" 在 {path}\n"

    lines = [header]
    for fpath, size, mtime in candidates:
        mtime_str = datetime.fromtimestamp(mtime).strftime("%m-%d %H:%M")
        ext = os.path.splitext(fpath)[1] or " "
        lines.append(f"  📄 {mtime_str}  {_fmt_size(size):>8}  {fpath}")

    lines.append(f"\n💡 提示: 支持 query/pattern/sort_by/sort_order/max_depth/modified_days/min_size/max_size/file_types")
    return "\n".join(lines)


# ══════════════════════════════════════════════
#  安全文件操作链
# ══════════════════════════════════════════════


def _add_suffix(path: Path) -> Path:
    """如果目标路径已存在，自动加日期后缀防覆盖。"""
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    ts = _time.strftime("%Y%m%d_%H%M%S")
    return path.with_name(f"{stem}_{ts}{suffix}")


def _preview_item(path: Path) -> str:
    """预览文件/目录信息（用于删除/回收前的展示）。"""
    if not path.exists():
        return f"❌ 路径不存在: {path}"
    if path.is_dir():
        try:
            total = sum(1 for _ in path.rglob('*'))
            size = sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
            return f"📁 目录: {path} ({total} 个项目, {_fmt_size(size)})"
        except Exception:
            return f"📁 目录: {path}"
    else:
        size = path.stat().st_size
        return f"📄 文件: {path} ({_fmt_size(size)})"


_SYSTEM_PATHS = {'/', '/system', '/vendor', '/proc', '/sys', '/boot'}
_SYSTEM_PREFIXES = {'/system/', '/vendor/', '/proc/', '/sys/', '/boot/'}

# 允许的 /data 子路径（白名单）
_ALLOWED_DATA_PATHS = [
    '/data/data/com.termux',       # Termux 用户目录
    '/data/local/tmp',             # 临时目录
]


def _is_system_path(path: str) -> bool:
    """检查是否为系统关键路径（拒绝操作）。

    安全策略：
    - 精确匹配 _SYSTEM_PATHS（如 /、/system、/proc）
    - 前缀匹配 _SYSTEM_PREFIXES（如 /system/xxx、/proc/xxx）
    - /data 路径仅拦截 /data 根目录本身，允许 /data/data/com.termux 等用户路径
    """
    try:
        resolved = str(Path(path).resolve())

        # 精确匹配系统根路径
        if resolved in _SYSTEM_PATHS:
            return True

        # 前缀匹配系统路径（/system/xxx, /proc/xxx 等）
        for prefix in _SYSTEM_PREFIXES:
            if resolved.startswith(prefix):
                return True

        # /data 路径：仅拦截 /data 本身，允许白名单子路径
        if resolved == '/data':
            return True
        if resolved.startswith('/data/'):
            # 检查是否在白名单中
            for allowed in _ALLOWED_DATA_PATHS:
                if resolved == allowed or resolved.startswith(allowed + '/'):
                    return False
            # 不在白名单的 /data 子路径视为系统路径
            return True

        return False
    except Exception:
        return False


@mcp.tool()
async def file_copy(source: str, dest: str, recursive: bool = False) -> str:
    """📋 复制文件或目录。自动创建父目录。目标已存在时自动加后缀防覆盖。

    Args:
        source: 源路径（文件或目录）
        dest: 目标路径（已存在时自动加 _YYYYMMDD_HHMMSS 后缀）
        recursive: 复制目录时需要设为 True
    """
    src = Path(source)
    if not src.exists():
        return f"❌ 源文件不存在: {source}"

    dst = Path(dest)
    dst = _add_suffix(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)

    try:
        if src.is_dir():
            if not recursive:
                return (f"❌ {source} 是目录，请设置 recursive=True 来复制目录\n"
                        f"💡 提示: file_copy(source='{source}', dest='{dest}', recursive=True)")
            shutil.copytree(src, dst, symlinks=True)
            total = sum(1 for _ in dst.rglob('*'))
            return f"✅ 目录已复制: {source} → {dst} ({total} 个项目)"
        else:
            shutil.copy2(src, dst)
            return f"✅ 文件已复制: {source} → {dst} ({_fmt_size(dst.stat().st_size)})"
    except FileExistsError:
        # _add_suffix 应该已经处理了，但 copytree 可能在中间步骤有冲突
        alt = _add_suffix(dst)
        return f"⚠️ 目标已存在，请使用: file_copy(source='{source}', dest='{alt}')"
    except Exception as e:
        return f"❌ 复制失败: {e}"


@mcp.tool()
async def file_move(source: str, dest: str) -> str:
    """📦 移动/重命名文件或目录。自动创建父目录。目标已存在时自动加后缀防覆盖。

    Args:
        source: 源路径
        dest: 目标路径（已存在时自动加 _YYYYMMDD_HHMMSS 后缀）
    """
    src = Path(source)
    if not src.exists():
        return f"❌ 源文件不存在: {source}"

    if _is_system_path(source):
        return f"🚨 拒绝操作系统关键路径: {source}"

    dst = Path(dest)
    dst = _add_suffix(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)

    try:
        shutil.move(str(src), str(dst))
        kind = "目录" if dst.is_dir() else "文件"
        return f"✅ {kind}已移动: {source} → {dst}"
    except Exception as e:
        return f"❌ 移动失败: {e}"


@mcp.tool()
async def file_delete(path: str, confirm: bool = False) -> str:
    """🗑️ 安全删除文件或目录（不可恢复！）。

    安全模式：先不传 confirm（默认）预览要删除的内容，
    确认无误后再调用并设置 confirm=True 执行永久删除。

    Args:
        path: 要删除的文件/目录路径
        confirm: 确认删除。False（默认）仅预览；True 执行删除
    """
    target = Path(path)
    if not target.exists():
        return f"❌ 路径不存在: {path}"

    if _is_system_path(path):
        return f"🚨 拒绝删除系统关键路径: {path}"

    if not confirm:
        # ── 预览模式 ──
        preview = _preview_item(target)
        return (f"📋 **删除预览**\n"
                f"{preview}\n\n"
                f"⚠️ **这是永久删除，不可恢复！**\n"
                f"如需执行，再次调用并设置 confirm=True\n\n"
                f"💡 如不确定，考虑用 file_trash() 移到回收站")

    # ── 执行删除 ──
    try:
        if target.is_dir():
            shutil.rmtree(target)
            return f"✅ 已永久删除目录: {path}"
        else:
            target.unlink()
            return f"✅ 已永久删除文件: {path}"
    except Exception as e:
        return f"❌ 删除失败: {e}"


@mcp.tool()
async def dir_create(path: str) -> str:
    """📁 创建目录（mkdir -p 行为）。自动创建所有父目录，已存在不报错。

    Args:
        path: 要创建的目录路径
    """
    try:
        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)
        return f"✅ 目录已就绪: {target}"
    except PermissionError:
        return f"❌ 权限不足，无法创建目录: {path}"
    except Exception as e:
        return f"❌ 目录创建失败: {e}"


@mcp.tool()
async def file_symlink(source: str, link_name: str) -> str:
    """🔗 创建符号链接。自动创建父目录。链接名已存在时自动加后缀。

    Args:
        source: 源文件/目录路径
        link_name: 符号链接路径
    """
    src = Path(source)
    if not src.exists():
        return f"❌ 源文件不存在: {source}"

    link = Path(link_name)
    link = _add_suffix(link)
    link.parent.mkdir(parents=True, exist_ok=True)

    try:
        link.symlink_to(src.resolve())
        return f"✅ 符号链接已创建: {link_name} → {source}"
    except Exception as e:
        return f"❌ 符号链接创建失败: {e}"


@mcp.tool()
async def file_trash(path: str, confirm: bool = False) -> str:
    """🗑️ 将文件/目录移到回收站 ~/.trash/（可通过 file_move 还原）。

    安全模式：先不传 confirm（默认）预览，再 confirm=True 执行移入回收站。

    Args:
        path: 要回收的文件/目录路径
        confirm: 确认回收。False（默认）预览；True 执行
    """
    target = Path(path)
    if not target.exists():
        return f"❌ 路径不存在: {path}"

    if _is_system_path(path):
        return f"🚨 拒绝回收系统关键路径: {path}"

    if not confirm:
        # ── 预览模式 ──
        preview = _preview_item(target)
        return (f"📋 **回收预览**\n"
                f"{preview}\n\n"
                f"📦 将移入: {_TRASH_DIR}/\n"
                f"💡 可通过 file_move() 还原\n"
                f"如需执行，再次调用并设置 confirm=True")

    # ── 执行回收 ──
    try:
        _TRASH_DIR.mkdir(parents=True, exist_ok=True)
        ts = _time.strftime("%Y%m%d_%H%M%S")
        trash_path = _TRASH_DIR / f"{ts}_{target.name}"
        trash_path = _add_suffix(trash_path)

        shutil.move(str(target), str(trash_path))
        return (f"✅ 已移到回收站: {path} → {trash_path}\n"
                f"💡 还原: file_move(source='{trash_path}', dest='{path}')")
    except Exception as e:
        return f"❌ 回收失败: {e}"


def _fmt_size(size: int) -> str:
    """格式化文件大小为人类可读格式（内部工具函数）"""
    if size >= 1_073_741_824:
        return f"{size/1_073_741_824:.1f}GB"
    elif size >= 1_048_576:
        return f"{size/1_048_576:.1f}MB"
    elif size >= 1024:
        return f"{size/1024:.1f}KB"
    return f"{size}B"
