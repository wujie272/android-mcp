"""
╔══════════════════════════════════════════════════════╗
║  GitHub 工具集成 — Android MCP 内嵌版               ║
║  仓库/Issue/文件/搜索 — 基于 gh token               ║
║  原服务: github-mcp (port 3510) → 已合并到此处      ║
╚══════════════════════════════════════════════════════╝
"""

import os
import base64
from android_mcp.app import mcp

# ── GitHub Token 加载 ──
GH_TOKEN = None
GH_USER = "jaye2720"


def _load_gh_token():
    """从 gh CLI 配置或环境变量中读取 GitHub Token"""
    global GH_TOKEN, GH_USER
    gh_config = os.path.expanduser("~/.config/gh/hosts.yml")
    if os.path.isfile(gh_config):
        try:
            with open(gh_config, "r") as f:
                for line in f:
                    if "oauth_token:" in line:
                        GH_TOKEN = line.split(":", 1)[1].strip().strip('"').strip("'")
                    if "user:" in line:
                        user = line.split(":", 1)[1].strip()
                        if user and user != GH_USER:
                            GH_USER = user
        except Exception:
            pass
    GH_TOKEN = GH_TOKEN or os.environ.get("GITHUB_TOKEN")


def _headers():
    """构建 GitHub API 请求头"""
    return {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": f"MCP-GitHub/{GH_USER}",
        **({"Authorization": f"Bearer {GH_TOKEN}"} if GH_TOKEN else {}),
    }


def _gh_api_url(path: str) -> str:
    return f"https://api.github.com{path}"


# ============================================================
#  工具函数 — 仓库信息
# ============================================================

@mcp.tool(
    name="github_repo",
    description="获取 GitHub 仓库的详细信息（Star、Fork、描述、许可证等）",
)
async def github_repo(owner: str, repo: str) -> str:
    """获取仓库详细信息"""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(_gh_api_url(f"/repos/{owner}/{repo}"), headers=_headers())
            if resp.status_code != 200:
                return f"❌ 查询失败 (HTTP {resp.status_code}): {resp.text[:200]}"
            d = resp.json()
            return (
                f"📦 {d['full_name']}\n"
                f"   ⭐ {d['stargazers_count']}  🍴 {d['forks_count']}\n"
                f"   👁️ {d.get('subscribers_count', 'N/A')}  🐛 {d.get('open_issues_count', 0)}\n"
                f"   📝 {d.get('description', '无描述')}\n"
                f"   📅 创建: {d['created_at'][:10]}  更新: {d['updated_at'][:10]}\n"
                f"   🌐 {d.get('homepage', '无主页') or '无主页'}\n"
                f"   📋 {d.get('license', {}).get('spdx_id', '无许可证') if d.get('license') else '无许可证'}\n"
                f"   🔗 {d['html_url']}"
            )
    except Exception as e:
        return f"❌ GitHub 查询失败: {e}"


@mcp.tool(
    name="github_list_repos",
    description="列出指定 GitHub 用户的仓库，支持排序和数量控制",
)
async def github_list_repos(username: str = "", sort: str = "updated", per_page: int = 20) -> str:
    """列出用户的 GitHub 仓库"""
    import httpx
    user = username or GH_USER
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                _gh_api_url(f"/users/{user}/repos"),
                params={"sort": sort, "per_page": min(per_page, 100), "type": "owner"},
                headers=_headers(),
            )
            if resp.status_code != 200:
                return f"❌ 查询失败 (HTTP {resp.status_code})"
            repos = resp.json()
            if not repos:
                return f"用户 {user} 没有公开仓库"
            lines = [f"📋 {user} 的仓库 ({len(repos)}):\n"]
            for r in repos:
                lines.append(f"  📦 {r['name']}")
                if r.get('description'):
                    lines.append(f"     {r['description'][:60]}")
                lines.append(f"     ⭐{r['stargazers_count']}  🍴{r['forks_count']}  🔗{r['html_url']}")
                lines.append("")
            return "\n".join(lines)
    except Exception as e:
        return f"❌ 查询失败: {e}"


@mcp.tool(
    name="github_search",
    description="搜索 GitHub 上的仓库、代码或 Issue，支持 repositories / code / issues 三种类型",
)
async def github_search(query: str, search_type: str = "repositories", max_results: int = 5) -> str:
    """
    搜索 GitHub 上的仓库、代码或 Issue
    - search_type: repositories / code / issues
    """
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                _gh_api_url(f"/search/{search_type}"),
                params={"q": query, "per_page": min(max_results, 30)},
                headers=_headers(),
            )
            if resp.status_code != 200:
                return f"❌ 搜索失败 (HTTP {resp.status_code})"
            data = resp.json()
            items = data.get("items", [])
            total = data.get("total_count", 0)

            if not items:
                return f"未找到 '{query}' 的搜索结果"

            lines = [f"🔍 搜索 '{query}' ({search_type}) — 共 {total} 条结果:\n"]
            for item in items[:max_results]:
                if search_type == "repositories":
                    lines.append(f"  📦 {item['full_name']}")
                    lines.append(f"     ⭐{item['stargazers_count']}  🍴{item['forks_count']}")
                    if item.get('description'):
                        lines.append(f"     {item['description'][:80]}")
                    lines.append(f"     🔗 {item['html_url']}")
                elif search_type == "issues":
                    lines.append(f"  🐛 {item['title']}")
                    lines.append(f"     #{item['number']}  {'✅ 已关闭' if item.get('state') == 'closed' else '🟢 开放'}  "
                                 f"👤 {item['user']['login']}")
                    lines.append(f"     🔗 {item['html_url']}")
                    if item.get('body'):
                        lines.append(f"     {item['body'][:100]}...")
                elif search_type == "code":
                    lines.append(f"  📄 {item['path']}")
                    lines.append(f"     📦 {item['repository']['full_name']}")
                    lines.append(f"     🔗 {item['html_url']}")
                lines.append("")
            return "\n".join(lines)
    except Exception as e:
        return f"❌ 搜索失败: {e}"


@mcp.tool(
    name="github_get_file",
    description="读取 GitHub 仓库中的文件内容或列出目录结构",
)
async def github_get_file(owner: str, repo: str, path: str, branch: str = "main") -> str:
    """读取仓库中的文件内容"""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                _gh_api_url(f"/repos/{owner}/{repo}/contents/{path}"),
                params={"ref": branch},
                headers=_headers(),
            )
            if resp.status_code != 200:
                return f"❌ 读取失败 (HTTP {resp.status_code}): {resp.text[:200]}"
            d = resp.json()
            if isinstance(d, list):
                # 是目录
                lines = [f"📂 {path} 的内容:\n"]
                for item in d:
                    icon = "📁" if item["type"] == "dir" else "📄"
                    lines.append(f"  {icon} {item['name']}")
                return "\n".join(lines)
            else:
                # 是文件
                content = base64.b64decode(d["content"]).decode("utf-8", errors="replace")
                size = d["size"]
                return f"📄 {path}  ({size} 字节, {d.get('sha', '')[:7]})\n\n---\n\n{content[:5000]}" + (
                    "\n\n... (内容过长已截断)" if size > 5000 else ""
                )
    except Exception as e:
        return f"❌ 读取失败: {e}"


@mcp.tool(
    name="github_list_issues",
    description="列出 GitHub 仓库的 Issue，支持按状态过滤（open / closed / all）",
)
async def github_list_issues(owner: str, repo: str, state: str = "open", max_results: int = 10) -> str:
    """列出仓库的 Issue"""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                _gh_api_url(f"/repos/{owner}/{repo}/issues"),
                params={"state": state, "per_page": min(max_results, 100)},
                headers=_headers(),
            )
            if resp.status_code != 200:
                return f"❌ 查询失败 (HTTP {resp.status_code})"
            issues = resp.json()
            if not issues:
                return f"{owner}/{repo} 没有 {state} 的 Issue"
            lines = [f"🐛 {owner}/{repo} 的 Issue ({state}, {len(issues)} 条):\n"]
            for i in issues:
                lines.append(f"  #{i['number']} {i['title']}")
                lines.append(f"     👤 {i['user']['login']}  🏷️ {', '.join([l['name'] for l in i.get('labels', [])]) or '无标签'}")
                lines.append(f"     🔗 {i['html_url']}")
                lines.append("")
            return "\n".join(lines)
    except Exception as e:
        return f"❌ 查询失败: {e}"


@mcp.tool(
    name="github_repo_languages",
    description="获取 GitHub 仓库的编程语言占比统计",
)
async def github_repo_languages(owner: str, repo: str) -> str:
    """获取仓库的语言占比"""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                _gh_api_url(f"/repos/{owner}/{repo}/languages"),
                headers=_headers(),
            )
            if resp.status_code != 200:
                return f"❌ 查询失败 (HTTP {resp.status_code})"
            langs = resp.json()
            if not langs:
                return f"{owner}/{repo} 未检测到编程语言"
            total = sum(langs.values())
            lines = [f"📊 {owner}/{repo} 语言占比:\n"]
            for lang, bytes_count in sorted(langs.items(), key=lambda x: -x[1]):
                pct = bytes_count / total * 100
                bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
                lines.append(f"  {lang:15s} {bar} {pct:.1f}%")
            return "\n".join(lines)
    except Exception as e:
        return f"❌ 查询失败: {e}"


@mcp.tool(
    name="github_list_branches",
    description="列出 GitHub 仓库的所有分支",
)
async def github_list_branches(owner: str, repo: str, max_results: int = 20) -> str:
    """列出仓库的分支"""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                _gh_api_url(f"/repos/{owner}/{repo}/branches"),
                params={"per_page": min(max_results, 100)},
                headers=_headers(),
            )
            if resp.status_code != 200:
                return f"❌ 查询失败 (HTTP {resp.status_code})"
            branches = resp.json()
            if not branches:
                return f"{owner}/{repo} 没有分支"
            lines = [f"🌿 {owner}/{repo} 的分支 ({len(branches)}):\n"]
            for b in branches:
                protected = "🔒" if b.get("protected") else "  "
                lines.append(f"  {protected} {b['name']}  →  {b['commit']['sha'][:7]}")
            return "\n".join(lines)
    except Exception as e:
        return f"❌ 查询失败: {e}"


# ── 启动时加载 Token ──
_load_gh_token()