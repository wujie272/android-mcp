"""File system tools: read, search, edit, copy, move, delete, trash, symlink."""

import shutil
import subprocess
import time as _time
from pathlib import Path
from datetime import datetime

from termux_mcp.app import mcp
from termux_mcp.lib.utils import async_run, ensure_path_env, err
from termux_mcp.lib.constants import HOME, SDCARD, SDCARD_SHORT

_TRASH_DIR = HOME / '.trash'

# ── Read / Write ──

@mcp.tool()
async def read_file(file_path: str) -> str:
    """Read a text file (up to 10MB, auto-detects encoding)."""
    try:
        path = Path(file_path).expanduser()
        if not path.exists():
            return f"Error: File not found: {file_path}"
        if path.stat().st_size > 10 * 1024 * 1024:
            return f"Error: File too large ({path.stat().st_size:,} bytes)"
        for enc in ['utf-8', 'gbk', 'gb2312', 'latin-1']:
            try:
                content = path.read_text(encoding=enc)
                return content
            except UnicodeDecodeError:
                continue
        return "Error: Cannot decode file"
    except Exception as e:
        return f"Error reading file: {e}"

#  统一搜索引擎：fd + rg + fzf 三引擎
# ══════════════════════════════════════════════

_AUTO_SKIP_DIRS = {'node_modules', '.git', '.cargo', '.gradle', '__pycache__',
                   '.venv', 'venv', 'env', 'vendor', '.trash', 'build', 'dist'}


def _build_fd_cmd(
    root: Path, pattern: str | None, exclude: set,
    max_depth: int | None, file_types: list[str] | None,
    modified_days: int | None, min_size: int | None,
    max_size: int | None, case_sensitive: bool,
    use_regex: bool, absolute: bool = False,
) -> list[str]:
    """构建 fd 命令（比 find 快 5~10x，支持原生过滤）。"""
    cmd = ['fd', '--type', 'f', '--color', 'never']
    if absolute:
        cmd.append('--absolute-path')
    if not case_sensitive:
        cmd.append('-i')
    if pattern and pattern != '*':
        if use_regex:
            cmd.extend(['--regex', pattern])
        else:
            cmd.extend(['--glob', pattern])
    else:
        cmd.append('.')
    if max_depth is not None:
        cmd.extend(['--max-depth', str(max_depth)])
    if file_types:
        for t in file_types:
            cmd.extend(['-e', t.strip('.').lower()])
    if modified_days is not None:
        cmd.extend(['--changed-within', f'{modified_days}day'])
    if min_size is not None:
        cmd.extend(['-s', str(min_size)])
    if max_size is not None:
        cmd.extend(['-S', str(max_size)])
    for exc in sorted(exclude):
        cmd.extend(['-E', exc])
    cmd.append(str(root))
    return cmd


async def _search_by_name_fd(
    root: Path, pattern: str, exclude: set,
    max_results: int, max_depth: int | None, file_types: list[str] | None,
    modified_days: int | None, min_size: int | None, max_size: int | None,
    sort_by: str, sort_order: str, case_sensitive: bool, use_regex: bool,
) -> tuple[list[dict], int]:
    """🚀 fd 高速文件名搜索（原生 C 实现，比 find 快 5~10x）。"""
    fd_cmd = _build_fd_cmd(
        root, pattern, exclude, max_depth, file_types,
        modified_days, min_size, max_size, case_sensitive, use_regex,
        absolute=True,
    )
    r = await async_run(fd_cmd, timeout=30, shell=False)
    if not r.get('success') or not r.get('stdout', '').strip():
        return [], 0

    all_lines = r['stdout'].strip().split('\n')
    results = []
    for fp in all_lines[:max_results]:
        fp = fp.strip()
        if not fp:
            continue
        try:
            st = Path(fp).stat()
            results.append({
                'path': fp, 'name': Path(fp).name,
                'size': st.st_size, 'mtime': st.st_mtime, 'is_dir': False,
            })
        except Exception:
            pass

    results.sort(key=lambda x: x['size'] if sort_by == 'size' else
                 x['mtime'] if sort_by == 'date' else x['name'].lower(),
                 reverse=(sort_order == 'desc'))
    return results, len(all_lines)


async def _fuzzy_search(
    root: Path, pattern: str, exclude: set,
    max_results: int, max_depth: int | None, file_types: list[str] | None,
    modified_days: int | None, min_size: int | None, max_size: int | None,
    sort_by: str, sort_order: str,
) -> tuple[list[dict], int]:
    """🔮 fzf 模糊文件名搜索 + fd 前置过滤。"""
    # Step 1: fd 快速列出候选文件（带过滤条件）
    fd_cmd = _build_fd_cmd(
        root, None, exclude, max_depth, file_types,
        modified_days, min_size, max_size, case_sensitive=False,
        use_regex=False,
    )
    r = await async_run(fd_cmd, timeout=30, shell=False)
    if not r.get('success') or not r.get('stdout', '').strip():
        return [], 0

    # Step 2: fzf -f 非交互式模糊匹配
    all_paths = r['stdout'].strip()
    try:
        import subprocess
        fzf_proc = subprocess.run(
            ['fzf', '-f', pattern],
            input=all_paths, capture_output=True, text=True, timeout=15,
        )
        if fzf_proc.returncode != 0 or not fzf_proc.stdout.strip():
            return [], 0
        matched = fzf_proc.stdout.strip().split('\n')
    except FileNotFoundError:
        return [], 0
    except Exception:
        return [], 0

    results = []
    for fp in matched[:max_results]:
        fp = fp.strip()
        if not fp:
            continue
        full = str(root / fp) if not Path(fp).is_absolute() else fp
        try:
            st = Path(full).stat()
            results.append({
                'path': full, 'name': Path(full).name,
                'size': st.st_size, 'mtime': st.st_mtime, 'is_dir': False,
            })
        except Exception:
            pass

    results.sort(key=lambda x: x['size'] if sort_by == 'size' else
                 x['mtime'] if sort_by == 'date' else x['name'].lower(),
                 reverse=(sort_order == 'desc'))
    return results, len(matched)


async def _search_by_content_rg(
    query: str, root: Path, pattern: str | None, exclude: set,
    max_results: int, file_types: list[str] | None,
    modified_days: int | None, min_size: int | None, max_size: int | None,
    sort_by: str, sort_order: str, case_sensitive: bool,
    use_regex: bool, context_lines: int, fuzzy: bool = False,
) -> tuple[list[dict], int]:
    """🔬 rg 内容搜索 → fd 元数据过滤（rg 最快，fd 次优）。"""

    # Step 1: rg 找出所有含内容的文件
    rg_cmd = ['rg', '-l', '--no-heading', '--color', 'never']
    if use_regex:
        rg_cmd.append('-P')
    if not case_sensitive:
        rg_cmd.append('-i')
    if pattern:
        rg_cmd.extend(['-g', pattern])
    for exc in sorted(exclude):
        rg_cmd.extend(['-g', f'!{exc}', '-g', f'!**/{exc}/**'])
    rg_cmd.extend(['--', query, str(root)])

    rg_result = await async_run(rg_cmd, timeout=60, shell=False)
    if not rg_result.get('success') or not rg_result.get('stdout', '').strip():
        return [], 0

    matched_paths = set()
    for line in rg_result['stdout'].strip().split('\n'):
        p = line.strip()
        if p:
            matched_paths.add(p)
    total_matched = len(matched_paths)

    # Step 2: 元数据过滤（仅在已匹配文件上操作，量少则快）
    results = []
    for fp in sorted(matched_paths)[:max_results]:
        p = Path(fp)
        try:
            st = p.stat()
        except OSError:
            continue

        # 扩展名过滤
        if file_types:
            ext = p.suffix.lower().lstrip('.')
            if ext not in [t.strip('.').lower() for t in file_types]:
                continue
        # 时间过滤
        if modified_days is not None:
            age = (_time.time() - st.st_mtime) / 86400
            if age > modified_days:
                continue
        # 大小过滤
        if min_size is not None and st.st_size < min_size:
            continue
        if max_size is not None and st.st_size > max_size:
            continue

        results.append({
            'path': str(p), 'name': p.name,
            'size': st.st_size, 'mtime': st.st_mtime, 'is_dir': False,
        })

    results.sort(key=lambda x: x['size'] if sort_by == 'size' else
                 x['mtime'] if sort_by == 'date' else x['name'].lower(),
                 reverse=(sort_order == 'desc'))
    return results, total_matched


def _format_search_results(results: list[dict], root_str: str,
                           pattern: str, total_found: int, max_results: int) -> str:
    """统一格式化搜索结果。"""
    if not results:
        return "🔍 未找到匹配的文件"

    ext_count: dict[str, int] = {}
    total_size = 0
    for r in results:
        ext = Path(r['name']).suffix.lower() or '(无后缀)'
        ext_count[ext] = ext_count.get(ext, 0) + 1
        total_size += r['size']

    lines = [
        f"🔍 搜索: {root_str} 匹配: '{pattern}'",
        f"📊 共 {total_found} 项" +
        (f"，显示前 {max_results} 项" if total_found > max_results else "") +
        f" | 总大小: {_fmt_size(total_size)}",
        "",
    ]

    top_exts = sorted(ext_count.items(), key=lambda x: -x[1])[:8]
    if len(top_exts) > 1:
        ext_summary = "  ".join(f"{ext} ×{cnt}" for ext, cnt in top_exts)
        lines.append(f"📈 类型分布: {ext_summary}")
        if len(ext_count) > 8:
            lines.append(f"   ...及其他 {len(ext_count) - 8} 种类型")
        lines.append("")

    for r in results:
        size_str = _fmt_size(r['size']) if r['size'] >= 0 else ""
        date_str = ""
        if r.get('mtime'):
            date_str = datetime.fromtimestamp(r['mtime']).strftime('%Y-%m-%d %H:%M')
        rel = r['path']
        if rel.startswith(root_str):
            rel = rel[len(root_str):].lstrip('/')
        lines.append(f"📄 {rel:<50s} {size_str:>10s}  {date_str}")

    return "\n".join(lines)


@mcp.tool()
async def search_files(
    query: str | None = None,
    path: str | None = None,
    pattern: str | None = None,
    exclude_patterns: list[str] | None = None,
    max_results: int = 200,
    max_depth: int | None = None,
    file_types: list[str] | None = None,
    modified_days: int | None = None,
    min_size: int | None = None,
    max_size: int | None = None,
    sort_by: str = "name",
    sort_order: str = "asc",
    case_sensitive: bool = False,
    use_regex: bool = False,
    context_lines: int = 0,
    fuzzy: bool = False,
) -> str:
    """🔍 统一搜索：文件名 + 内容 + 元数据全维度过滤。

    三合一引擎：
    · 无 query → 文件名搜索（fd，比 find 快 5~10x）
    · 有 query → 内容搜索（ripgrep）→ 元数据过滤
    · fuzzy=True → 模糊文件名搜索（fzf）

    自动跳过 node_modules/.git/.cargo 等大目录。

    Args:
        query: 内容关键词（不传则仅按文件名搜索）
        path: 搜索目录（默认当前目录）
        pattern: 文件名 glob 模式，如 "*.md"、"*test*"（默认 "*"）
        exclude_patterns: 排除模式，如 ["node_modules", ".git"]
        max_results: 最大返回数（默认 200）
        max_depth: 最大搜索深度
        file_types: 扩展名过滤，如 ["md", "py"]
        modified_days: 最近 N 天内修改
        min_size: 大小下限（字节）
        max_size: 大小上限（字节）
        sort_by: "name" / "size" / "date"（默认 "name"）
        sort_order: "asc" / "desc"（默认 "asc"）
        case_sensitive: 大小写敏感（默认 False）
        use_regex: 将 pattern/query 视为正则（默认 False）
        context_lines: 内容匹配上下文行数（默认 0，仅 query 时有效）
        fuzzy: 启用 fzf 模糊文件名匹配（默认 False）
    """
    if path is None:
        path = "."
    if pattern is None:
        pattern = "*"
    root = Path(path).expanduser()
    if not root.exists() or not root.is_dir():
        return f"❌ 无效目录: {path}"

    exclude = set(exclude_patterns or [])
    exclude.update(_AUTO_SKIP_DIRS - exclude)

    has_query = query is not None and query.strip()

    if fuzzy and not has_query:
        # 🔮 fzf 模糊文件名搜索
        results, total_found = await _fuzzy_search(
            root, pattern, exclude, max_results, max_depth, file_types,
            modified_days, min_size, max_size, sort_by, sort_order,
        )
    elif not has_query:
        # 🚀 fd 文件名搜索
        results, total_found = await _search_by_name_fd(
            root, pattern, exclude, max_results, max_depth, file_types,
            modified_days, min_size, max_size, sort_by, sort_order,
            case_sensitive, use_regex,
        )
    else:
        # 🔬 rg 内容搜索 + 元数据过滤
        results, total_matched = await _search_by_content_rg(
            query.strip(), root, pattern if pattern != "*" else None,
            exclude, max_results, file_types,
            modified_days, min_size, max_size, sort_by, sort_order,
            case_sensitive, use_regex, context_lines, fuzzy,
        )
        if not results and total_matched == 0:
            try:
                r = await async_run(['rg', '--version'], timeout=5, shell=False)
                has_rg = r.get('success', False)
            except Exception:
                has_rg = False
            if not has_rg:
                return "❌ 系统中未安装 ripgrep（rg），请执行: pkg install ripgrep\n💡 或不传 query 使用纯文件名搜索"
            return f"🔍 未找到包含 '{query}' 的文件"
        return _format_search_results(results, str(root), pattern or "*", total_matched, max_results)

    return _format_search_results(results, str(root), pattern, total_found, max_results)


# ══════════════════════════════════════════════


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
    src = Path(source).expanduser()
    if not src.exists():
        return f"❌ 源文件不存在: {source}"

    dst = Path(dest).expanduser()
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
    src = Path(source).expanduser()
    if not src.exists():
        return f"❌ 源文件不存在: {source}"

    if _is_system_path(str(src)):
        return f"🚨 拒绝操作系统关键路径: {source}"

    dst = Path(dest).expanduser()
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
    target = Path(path).expanduser()
    if not target.exists():
        return f"❌ 路径不存在: {path}"

    if _is_system_path(str(target)):
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
        target = Path(path).expanduser()
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
    src = Path(source).expanduser()
    if not src.exists():
        return f"❌ 源文件不存在: {source}"

    link = Path(link_name).expanduser()
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
    target = Path(path).expanduser()
    if not target.exists():
        return f"❌ 路径不存在: {path}"

    if _is_system_path(str(target)):
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

# ── cache original content for diff ──
_file_cache: dict[str, str] = {}


def _detect_encoding(path: Path) -> str:
    """Detect text file encoding by trying common encodings."""
    raw = path.read_bytes()
    if raw[:3] == b'\xef\xbb\xbf':
        return 'utf-8-sig'
    for enc in ['utf-8', 'gbk', 'gb2312', 'shift-jis', 'latin-1']:
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return 'utf-8'


def _esc_pat(s: str) -> str:
    """Escape string for sed s/// pattern side."""
    for c in '\\/&*.+?^${}()|[]':
        s = s.replace(c, '\\' + c)
    return s


def _esc_rep(s: str) -> str:
    """Escape string for sed s/// replacement side."""
    s = s.replace('\\', '\\\\')
    s = s.replace('/', '\\/')
    s = s.replace('&', '\\&')
    return s


def _esc_ln(s: str) -> str:
    """Escape string for sed line commands (conservative superset)."""
    for c in '\\/&*.+?^${}()|[]':
        s = s.replace(c, '\\' + c)
    return s


def _mk_fuzzy(s: str) -> str:
    """Build [[:space:]]\\+ separated fuzzy pattern from words."""
    return '[[:space:]]\\+'.join(_esc_pat(w) for w in s.split())


def _sed_run(expr: str, file: str, extended: bool = False) -> tuple[bool, str]:
    """Run sed -i with expression. Returns (ok, error_msg)."""
    cmd = ['sed', '-i']
    if extended:
        cmd.append('-E')
    cmd.append(expr)
    cmd.append(file)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return False, (r.stderr or r.stdout or '').strip()
        return True, ''
    except subprocess.TimeoutExpired:
        return False, 'timeout'
    except Exception as e:
        return False, str(e)


def _python_diff(before: str, after: str) -> str:
    """diff using Python difflib (no subprocess)."""
    import difflib as _dl
    diff = ''.join(_dl.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile='before', tofile='after', lineterm=''
    ))
    return diff if diff else '(identical)'



def _anchor_to_line(
    lines: list[str],
    anchor: str,
    occurrence: int | None = None,
    context_above: str | None = None,
    context_below: str | None = None,
    use_regex: bool = False,
    case_sensitive: bool | None = None,
) -> int | None:
    """Resolve anchor text to 1-based line number. Returns None if no match."""
    import re as _re
    matched = []
    for idx, line in enumerate(lines):
        if use_regex:
            flags = _re.IGNORECASE if (case_sensitive is False) else 0
            if _re.search(anchor, line, flags):
                matched.append(idx)
        else:
            if case_sensitive is False:
                if anchor.lower() in line.lower():
                    matched.append(idx)
            else:
                if anchor in line:
                    matched.append(idx)

    if context_above is not None:
        matched = [idx for idx in matched
                   if idx > 0 and context_above in lines[idx - 1]]
    if context_below is not None:
        matched = [idx for idx in matched
                   if idx < len(lines) - 1 and context_below in lines[idx + 1]]
    if occurrence is not None:
        if occurrence < 1 or occurrence > len(matched):
            return None
        matched = [matched[occurrence - 1]]

    if not matched:
        return None
    return matched[0] + 1  # 1-based


def _snapshot(file: str) -> str:
    cache = _file_cache.get(file)
    if cache is not None:
        return cache
    try:
        c = Path(file).read_text()
        _file_cache[file] = c
        return c
    except Exception:
        return ''


def _changed(file: str) -> bool:
    """Check if file changed since snapshot."""
    try:
        cur = Path(file).read_text()
        org = _file_cache.get(file, cur)
        return cur != org
    except Exception:
        return False


@mcp.tool()
async def edit_file(file_path: str, operations: list[dict]) -> str:
    """Edit a file using Python native operations (no sed).
    Supports all operation types: replace, replace_line, insert_before, insert_after, delete.
    Full Unicode support — Chinese, multi-byte, special characters all handled correctly.

    Operation dicts:
      type: "replace" | "replace_line" | "insert_before" | "insert_after" | "delete"

    "replace":
      {"type":"replace","old":"...","new":"...","global":true, "use_regex":false, "fuzzy":false}
      - use_regex=true: old → regex pattern (Python re.sub, full Unicode support)
      - fuzzy=true: auto normalise whitespace differences
      - occurrence=N: target the N-th matching line (1-based)
      - context_above/below: anchor match by verifying surrounding line content
      - dry_run=true: preview matched lines without modifying the file
      - max_matches=N: safety cap — refuse to modify if more than N lines match
      - case_sensitive: explicit control (default: case-sensitive in line mode)
    "replace_line":   {"type":"replace_line", "line":5, "text":"new"}
                     {"type":"replace_line", "anchor":"// TODO", "text":"new"}
    "insert_before":  {"type":"insert_before","line":3,"text":"..."}
                     {"type":"insert_before","anchor":"private fun","occurrence":2,"text":"..."}
    "insert_after":   {"type":"insert_after","line":3,"text":"..."}
                     {"type":"insert_after","anchor":"fun onCreate","text":"..."}
    "delete":         {"type":"delete","line":5} or {"type":"delete","start":5,"end":8}
                     {"type":"delete","anchor":"import deprecated"}

    For all operations above, "anchor" replaces "line" with text-based matching.
    Supports: occurrence (1-based), context_above, context_below, use_regex, case_sensitive.

    Args:
        file_path: File to edit
        operations: List of operation dicts
    """
    import difflib as _difflib
    import re as _re

    path = Path(file_path).expanduser()
    if not path.exists():
        return err("File not found", file_path)

    # ── 1. Read with encoding detection ──
    raw = path.read_bytes()
    encoding = _detect_encoding(path)
    content = raw.decode(encoding)
    before = content
    is_modified = False


    report_parts = [f"\U0001f4c4 {file_path}  \u7f16\u7801: {encoding}"]

    for i, op in enumerate(operations):
        op_type = op.get('type', '')
        report_parts.append(f"\n[{i+1}] {op_type}")

        try:
            if op_type == 'replace':
                old = op.get('old', '')
                new = op.get('new', '')
                is_global = op.get('global', False)
                use_regex = op.get('use_regex', False)
                fuzzy = op.get('fuzzy', False)
                occurrence = op.get('occurrence')
                context_above = op.get('context_above')
                context_below = op.get('context_below')
                dry_run = op.get('dry_run', False)
                max_matches = op.get('max_matches')
                cs = op.get('case_sensitive')

                if not old:
                    report_parts.append("  \u26a0\ufe0f  missing 'old'")
                    continue

                use_line_mode = (occurrence is not None or context_above is not None or
                                 context_below is not None or dry_run or max_matches is not None)

                if use_line_mode:
                    lines = content.splitlines(keepends=True)
                    matched = []

                    for idx, line in enumerate(lines):
                        if use_regex:
                            flags = _re.IGNORECASE if (cs is False) else 0
                            if _re.search(old, line, flags):
                                matched.append(idx)
                        else:
                            if cs is False:
                                if old.lower() in line.lower():
                                    matched.append(idx)
                            else:
                                if old in line:
                                    matched.append(idx)

                    if context_above is not None:
                        matched = [idx for idx in matched
                                   if idx > 0 and context_above in lines[idx - 1]]

                    if context_below is not None:
                        matched = [idx for idx in matched
                                   if idx < len(lines) - 1 and context_below in lines[idx + 1]]

                    if occurrence is not None:
                        if occurrence < 1 or occurrence > len(matched):
                            report_parts.append(f"  \u26a0\ufe0f  occurrence {occurrence} out of range (total {len(matched)})")
                            continue
                        matched = [matched[occurrence - 1]]

                    if max_matches is not None and len(matched) > max_matches:
                        report_parts.append(f"  \u26a0\ufe0f  {len(matched)} matches exceed max_matches={max_matches}")
                        continue

                    if dry_run:
                        for idx in matched:
                            report_parts.append(f"  \U0001f4cb line {idx+1}: {lines[idx].rstrip()}")
                        report_parts.append(f"  \u2139\ufe0f  {len(matched)} match(es), dry_run=True")
                        continue

                    for idx in matched:
                        if use_regex:
                            flags = _re.IGNORECASE if (cs is False) else 0
                            count = 0 if is_global else 1
                            lines[idx] = _re.sub(old, new, lines[idx], count=count, flags=flags)
                        else:
                            if is_global:
                                lines[idx] = lines[idx].replace(old, new)
                            else:
                                lines[idx] = lines[idx].replace(old, new, 1)

                    content = ''.join(lines)
                    is_modified = True
                    line_nums = ', '.join(str(idx + 1) for idx in matched)
                    report_parts.append(f"  \u2705 replaced on line(s): {line_nums}")
                    continue

                # ── Full-text replace ──
                if use_regex:
                    flags = _re.IGNORECASE if (cs is False) else 0
                    count = 0 if is_global else 1
                    new_content = _re.sub(old, new, content, count=count, flags=flags)
                else:
                    if is_global:
                        new_content = content.replace(old, new)
                    else:
                        new_content = content.replace(old, new, 1)

                if new_content == content:
                    if fuzzy:
                        old_ws = r'\s+'.join(_re.escape(w) for w in old.split())
                        new_content = _re.sub(old_ws, new, content, count=0 if is_global else 1)
                        if new_content == content:
                            report_parts.append("  \u26a0\ufe0f  text not found (fuzzy also failed)")
                            continue
                        report_parts.append("  done (fuzzy)")
                        content = new_content
                        is_modified = True
                        continue
                    else:
                        report_parts.append("  \u26a0\ufe0f  text not found")
                        continue

                content = new_content
                is_modified = True
                report_parts.append("  done")

            elif op_type == 'replace_line':
                anchor = op.get('anchor')
                ln = op.get('line', 0)
                text = op.get('text', '')
                lines = content.splitlines(keepends=True)

                # anchor 优先于 line
                if anchor:
                    resolved = _anchor_to_line(
                        lines, anchor,
                        occurrence=op.get('occurrence'),
                        context_above=op.get('context_above'),
                        context_below=op.get('context_below'),
                        use_regex=op.get('use_regex', False),
                        case_sensitive=op.get('case_sensitive'),
                    )
                    if resolved is None:
                        report_parts.append(f"  \u26a0\ufe0f  anchor '{anchor}' not found")
                        continue
                    ln = resolved

                if ln < 1 or ln > len(lines):
                    report_parts.append(f"  \u26a0\ufe0f  line {ln} out of range (file has {len(lines)} lines)")
                    continue
                eol = '\n' if lines[ln - 1].endswith('\n') else ''
                lines[ln - 1] = text + eol
                content = ''.join(lines)
                is_modified = True
                report_parts.append(f"  line {ln}")

            elif op_type == 'insert_before':
                anchor = op.get('anchor')
                ln = op.get('line', 0)
                text = op.get('text', '')
                lines = content.splitlines(keepends=True)

                # anchor 优先于 line
                if anchor:
                    resolved = _anchor_to_line(
                        lines, anchor,
                        occurrence=op.get('occurrence'),
                        context_above=op.get('context_above'),
                        context_below=op.get('context_below'),
                        use_regex=op.get('use_regex', False),
                        case_sensitive=op.get('case_sensitive'),
                    )
                    if resolved is None:
                        report_parts.append(f"  \u26a0\ufe0f  anchor '{anchor}' not found")
                        continue
                    ln = resolved

                if ln < 1 or ln > len(lines) + 1:
                    report_parts.append(f"  \u26a0\ufe0f  line {ln} out of range")
                    continue
                insert_lines = text.split('\n')
                for j in range(len(insert_lines)):
                    if j < len(insert_lines) - 1 and not insert_lines[j].endswith('\n'):
                        insert_lines[j] += '\n'
                    elif j == len(insert_lines) - 1 and insert_lines[j]:
                        insert_lines[j] += '\n'
                lines[ln - 1:ln - 1] = insert_lines
                content = ''.join(lines)
                is_modified = True
                report_parts.append(f"  before {ln}")

            elif op_type == 'insert_after':
                anchor = op.get('anchor')
                ln = op.get('line', 0)
                text = op.get('text', '')
                lines = content.splitlines(keepends=True)

                # anchor 优先于 line
                if anchor:
                    resolved = _anchor_to_line(
                        lines, anchor,
                        occurrence=op.get('occurrence'),
                        context_above=op.get('context_above'),
                        context_below=op.get('context_below'),
                        use_regex=op.get('use_regex', False),
                        case_sensitive=op.get('case_sensitive'),
                    )
                    if resolved is None:
                        report_parts.append(f"  \u26a0\ufe0f  anchor '{anchor}' not found")
                        continue
                    ln = resolved

                if ln < 1 or ln > len(lines):
                    report_parts.append(f"  \u26a0\ufe0f  line {ln} out of range")
                    continue
                insert_lines = text.split('\n')
                for j in range(len(insert_lines)):
                    if j < len(insert_lines) - 1 and not insert_lines[j].endswith('\n'):
                        insert_lines[j] += '\n'
                    elif j == len(insert_lines) - 1 and insert_lines[j]:
                        insert_lines[j] += '\n'
                lines[ln:ln] = insert_lines
                content = ''.join(lines)
                is_modified = True
                report_parts.append(f"  after {ln}")

            elif op_type == 'delete':
                anchor = op.get('anchor')
                s = op.get('start', op.get('line', 0))
                e = op.get('end', s)
                lines = content.splitlines(keepends=True)

                # anchor 优先于 line/start
                if anchor:
                    resolved = _anchor_to_line(
                        lines, anchor,
                        occurrence=op.get('occurrence'),
                        context_above=op.get('context_above'),
                        context_below=op.get('context_below'),
                        use_regex=op.get('use_regex', False),
                        case_sensitive=op.get('case_sensitive'),
                    )
                    if resolved is None:
                        report_parts.append(f"  \u26a0\ufe0f  anchor '{anchor}' not found")
                        continue
                    s = resolved
                    e = resolved  # anchor 只匹配单行

                if s < 1 or s > len(lines) or e < 1 or e > len(lines):
                    report_parts.append(f"  \u26a0\ufe0f  line range {s}-{e} out of range")
                    continue
                del lines[s - 1:e]
                content = ''.join(lines)
                is_modified = True
                report_parts.append(f"  deleted {s}-{e}")

            else:
                report_parts.append(f"  \u26a0\ufe0f  unknown type '{op_type}'")

        except Exception as e:
            report_parts.append(f"  \u26a0\ufe0f  error: {e}")

    # ── 3. Write back & diff ──
    if not is_modified and content == before:
        report_parts.append("\n\u2139\ufe0f  No changes (content identical)")
        return '\n'.join(report_parts)

    path.write_bytes(content.encode(encoding))

    diff = _python_diff(before, content)
    report_parts.append(f"\n\U0001f4cb diff:\n{diff}")
    return '\n'.join(report_parts)
