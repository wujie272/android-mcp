"""GitHub tools: repo info, search, files, issues, languages, branches."""

import os
import base64
from termux_mcp.app import mcp

GH_TOKEN = None
GH_USER = "jaye2720"


def _load_token():
    global GH_TOKEN, GH_USER
    gh_cfg = os.path.expanduser("~/.config/gh/hosts.yml")
    if os.path.isfile(gh_cfg):
        try:
            with open(gh_cfg) as f:
                for line in f:
                    if "oauth_token:" in line:
                        GH_TOKEN = line.split(":", 1)[1].strip().strip('"').strip("'")
                    if "user:" in line:
                        u = line.split(":", 1)[1].strip()
                        if u:
                            GH_USER = u
        except Exception:
            pass
    GH_TOKEN = GH_TOKEN or os.environ.get("GITHUB_TOKEN")


def _headers():
    return {"Accept": "application/vnd.github.v3+json", "User-Agent": f"MCP-GitHub/{GH_USER}"} | \
           ({"Authorization": f"Bearer {GH_TOKEN}"} if GH_TOKEN else {})


def _url(path: str) -> str:
    return f"https://api.github.com{path}"


_load_token()


@mcp.tool()
async def github_repo(owner: str, repo: str) -> str:
    """Get repo info: stars, forks, description, license."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(_url(f"/repos/{owner}/{repo}"), headers=_headers())
            if r.status_code != 200:
                return f"❌ HTTP {r.status_code}: {r.text[:200]}"
            d = r.json()
            return (f"📦 {d['full_name']}\n   ⭐ {d['stargazers_count']}  🍴 {d['forks_count']}\n"
                    f"   👁️ {d.get('subscribers_count', '?')}  🐛 {d.get('open_issues_count', 0)}\n"
                    f"   📝 {d.get('description', '无描述')}\n"
                    f"   📅 {d['created_at'][:10]}  📋 {d.get('license', {}).get('spdx_id', '无') if d.get('license') else '无'}\n"
                    f"   🔗 {d['html_url']}")
    except Exception as e:
        return f"❌ {e}"


@mcp.tool()
async def github_list_repos(username: str = "", sort: str = "updated", per_page: int = 20) -> str:
    """List user's repos. sort: updated/created/pushed/full_name."""
    import httpx
    user = username or GH_USER
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(_url(f"/users/{user}/repos"),
                            params={"sort": sort, "per_page": min(per_page, 100), "type": "owner"},
                            headers=_headers())
            if r.status_code != 200:
                return f"❌ HTTP {r.status_code}"
            repos = r.json()
            if not repos:
                return f"{user} has no public repos"
            lines = [f"📋 {user} ({len(repos)} repos):"]
            for rp in repos:
                lines.append(f"\n  📦 {rp['name']}")
                if rp.get('description'):
                    lines.append(f"     {rp['description'][:60]}")
                lines.append(f"     ⭐{rp['stargazers_count']}  🍴{rp['forks_count']}  🔗{rp['html_url']}")
            return "\n".join(lines)
    except Exception as e:
        return f"❌ {e}"


@mcp.tool()
async def github_search(query: str, search_type: str = "repositories", max_results: int = 5) -> str:
    """Search GitHub. search_type: repositories/code/issues."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(_url(f"/search/{search_type}"),
                            params={"q": query, "per_page": min(max_results, 30)},
                            headers=_headers())
            if r.status_code != 200:
                return f"❌ HTTP {r.status_code}"
            data = r.json()
            items = data.get("items", [])
            if not items:
                return f"Not found: '{query}'"
            lines = [f"🔍 '{query}' ({search_type}) — {data.get('total_count', 0)} results:"]
            for item in items[:max_results]:
                if search_type == "repositories":
                    lines.append(f"\n  📦 {item['full_name']}  ⭐{item['stargazers_count']}  🍴{item['forks_count']}")
                    if item.get('description'):
                        lines.append(f"     {item['description'][:80]}")
                elif search_type == "issues":
                    lines.append(f"\n  🐛 #{item['number']} {item['title']}")
                    lines.append(f"     {'✅' if item.get('state') == 'closed' else '🟢'} 👤{item['user']['login']}")
                elif search_type == "code":
                    lines.append(f"\n  📄 {item['path']}  📦 {item['repository']['full_name']}")
                lines.append(f"     🔗 {item['html_url']}")
            return "\n".join(lines)
    except Exception as e:
        return f"❌ {e}"


@mcp.tool()
async def github_get_file(owner: str, repo: str, path: str, branch: str = "main") -> str:
    """Read repo file or list directory."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(_url(f"/repos/{owner}/{repo}/contents/{path}"),
                            params={"ref": branch}, headers=_headers())
            if r.status_code != 200:
                return f"❌ HTTP {r.status_code}: {r.text[:200]}"
            d = r.json()
            if isinstance(d, list):
                lines = [f"📂 {path}:"]
                for item in d:
                    lines.append(f"  {'📁' if item['type'] == 'dir' else '📄'} {item['name']}")
                return "\n".join(lines)
            content = base64.b64decode(d["content"]).decode("utf-8", errors="replace")
            size = d["size"]
            return f"📄 {path} ({size}B, {d.get('sha', '')[:7]})\n\n---\n\n{content[:5000]}" + \
                   ("\n\n... (截断)" if size > 5000 else "")
    except Exception as e:
        return f"❌ {e}"


@mcp.tool()
async def github_list_issues(owner: str, repo: str, state: str = "open", max_results: int = 10) -> str:
    """List repo issues. state: open/closed/all."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(_url(f"/repos/{owner}/{repo}/issues"),
                            params={"state": state, "per_page": min(max_results, 100)},
                            headers=_headers())
            if r.status_code != 200:
                return f"❌ HTTP {r.status_code}"
            issues = r.json()
            if not issues:
                return f"No {state} issues in {owner}/{repo}"
            lines = [f"🐛 {owner}/{repo} ({state}, {len(issues)}):"]
            for i in issues:
                labels = ', '.join([l['name'] for l in i.get('labels', [])]) or '无标签'
                lines.append(f"\n  #{i['number']} {i['title']}")
                lines.append(f"     👤{i['user']['login']}  🏷️ {labels}")
                lines.append(f"     🔗 {i['html_url']}")
            return "\n".join(lines)
    except Exception as e:
        return f"❌ {e}"


@mcp.tool()
async def github_repo_languages(owner: str, repo: str) -> str:
    """Get repo language breakdown."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(_url(f"/repos/{owner}/{repo}/languages"), headers=_headers())
            if r.status_code != 200:
                return f"❌ HTTP {r.status_code}"
            langs = r.json()
            if not langs:
                return f"No languages detected."
            total = sum(langs.values())
            lines = [f"📊 {owner}/{repo}:"]
            for lang, bytes_count in sorted(langs.items(), key=lambda x: -x[1]):
                pct = bytes_count / total * 100
                bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
                lines.append(f"  {lang:15s} {bar} {pct:.1f}%")
            return "\n".join(lines)
    except Exception as e:
        return f"❌ {e}"


@mcp.tool()
async def github_list_branches(owner: str, repo: str, max_results: int = 20) -> str:
    """List repo branches."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(_url(f"/repos/{owner}/{repo}/branches"),
                            params={"per_page": min(max_results, 100)},
                            headers=_headers())
            if r.status_code != 200:
                return f"❌ HTTP {r.status_code}"
            branches = r.json()
            if not branches:
                return "No branches found."
            lines = [f"🌿 {owner}/{repo} ({len(branches)} branches):"]
            for b in branches:
                sha = b['commit']['sha'][:7]
                lines.append(f"  🌱 {b['name']:<30} {sha}")
            return "\n".join(lines)
    except Exception as e:
        return f"❌ {e}"


@mcp.tool()
async def github_refresh_token() -> str:
    """Manually refresh GitHub token (re-reads gh CLI config and env vars)."""
    GH_TOKEN = None
    _load_token()
    return f"Token refreshed. User: {GH_USER}" + ("" if GH_TOKEN else " (no token)")