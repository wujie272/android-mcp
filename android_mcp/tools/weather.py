"""🌤️ Weather MCP Tools — v2.1 (定位去除版)

Integrated directly into Android MCP (no external MCP endpoint needed).
Uses wttr.in and WAQI APIs.

Tools: get_weather, get_weather_short, get_weather_by_coords, get_air_quality
"""

import os
import time
import asyncio
import logging

import httpx
from android_mcp.app import mcp

logger = logging.getLogger("android-mcp.weather")

# ── API endpoints ──
WTTR_BASE = "https://wttr.in"
WAQI_BASE = "https://api.waqi.info/feed"
USER_AGENT = "android-mcp/0.5.0"

# ── Cache TTL ──
CACHE_TTL_WEATHER = 300  # 5 min for weather data

# ── Retry policy ──
MAX_RETRIES = 1  # retry once on 5xx


# ══════════════════════════════════════════════
#  🔗 Shared httpx client (connection pooling)
# ══════════════════════════════════════════════

class _SharedClient:
    """Module-level shared httpx client with connection pooling."""

    _client: httpx.AsyncClient | None = None
    _lock = asyncio.Lock()

    @classmethod
    async def get(cls, timeout: float = 15.0) -> httpx.AsyncClient:
        if cls._client is None:
            async with cls._lock:
                if cls._client is None:
                    limits = httpx.Limits(
                        max_keepalive_connections=8,
                        max_connections=16,
                        keepalive_expiry=30.0,
                    )
                    cls._client = httpx.AsyncClient(
                        timeout=httpx.Timeout(timeout),
                        headers={"User-Agent": USER_AGENT},
                        follow_redirects=True,
                        limits=limits,
                    )
        return cls._client

    @classmethod
    async def close(cls):
        if cls._client:
            await cls._client.aclose()
            cls._client = None


# ══════════════════════════════════════════════
#  🗄️ Simple TTL Cache
# ══════════════════════════════════════════════

class _TTLCache:
    """Thread-safe-ish in-memory cache with TTL expiry."""

    def __init__(self, default_ttl: int = 300):
        self._store: dict[str, tuple[float, object]] = {}
        self._default_ttl = default_ttl

    def get(self, key: str) -> object | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: object, ttl: int | None = None) -> None:
        ttl = ttl if ttl is not None else self._default_ttl
        self._store[key] = (time.monotonic() + ttl, value)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()


# ── Global cache ──
_weather_cache = _TTLCache(default_ttl=CACHE_TTL_WEATHER)


# ══════════════════════════════════════════════
#  🔄 Auto-retry (for transient failures)
# ══════════════════════════════════════════════

async def _fetch_with_retry(client: httpx.AsyncClient, url: str, params: dict | None = None) -> httpx.Response | None:
    """GET request with automatic retry on 5xx and network errors."""
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = await client.get(url, params=params)
            if resp.is_success:
                return resp
            if 500 <= resp.status_code < 600 and attempt < MAX_RETRIES:
                logger.debug("wttr.in 5xx (%d), retrying...", resp.status_code)
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
            return resp
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            last_error = e
            if attempt < MAX_RETRIES:
                logger.debug("Network error, retrying (%d/%d): %s", attempt + 1, MAX_RETRIES, e)
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
    logger.warning("Request failed after %d attempts: %s", MAX_RETRIES + 1, last_error)
    return None


# ══════════════════════════════════════════════
#  🌤️ 天气数据获取 (with caching)
# ══════════════════════════════════════════════

async def _weather_by_city(city: str) -> dict | None:
    """通过城市名获取天气（带缓存）. """
    cache_key = f"city:{city}"
    cached = _weather_cache.get(cache_key)
    if cached:
        logger.debug("Cache hit for city: %s", city)
        return cached

    client = await _SharedClient.get()
    try:
        resp = await _fetch_with_retry(
            client,
            f"{WTTR_BASE}/{httpx.utils.quote(city)}",
            params={"format": "j1", "m": None},
        )
        if resp and resp.is_success:
            data = resp.json()
            _weather_cache.set(cache_key, data)
            return data
    except Exception as e:
        logger.warning("get_weather(%s) failed: %s", city, e)
    return None


async def _weather_by_coords(lat: float, lon: float) -> dict | None:
    """通过经纬度获取天气（带缓存）. wttr.in 支持坐标查询."""
    cache_key = f"coords:{lat:.4f},{lon:.4f}"
    cached = _weather_cache.get(cache_key)
    if cached:
        logger.debug("Cache hit for coords: %.4f, %.4f", lat, lon)
        return cached

    client = await _SharedClient.get()
    try:
        resp = await _fetch_with_retry(
            client,
            f"{WTTR_BASE}/{lat},{lon}",
            params={"format": "j1", "m": None},
        )
        if resp and resp.is_success:
            data = resp.json()
            _weather_cache.set(cache_key, data)
            return data
    except Exception as e:
        logger.warning("get_weather(%.4f,%.4f) failed: %s", lat, lon, e)
    return None


async def _weather_short_by_city(city: str) -> str:
    """简版天气文本."""
    cache_key = f"short:{city}"
    cached = _weather_cache.get(cache_key)
    if cached:
        return cached

    client = await _SharedClient.get()
    try:
        resp = await _fetch_with_retry(
            client,
            f"{WTTR_BASE}/{httpx.utils.quote(city)}",
            params={"format": "%C+%t+💧%h+🌬️%w", "m": None},
        )
        if resp and resp.is_success:
            text = resp.text.strip()
            _weather_cache.set(cache_key, text, ttl=180)
            return text
        return "获取失败"
    except Exception as e:
        return f"获取失败: {e}"


async def _weather_short_by_coords(lat: float, lon: float) -> str:
    """通过坐标获取简版天气."""
    cache_key = f"short:{lat:.4f},{lon:.4f}"
    cached = _weather_cache.get(cache_key)
    if cached:
        return cached

    client = await _SharedClient.get()
    try:
        resp = await _fetch_with_retry(
            client,
            f"{WTTR_BASE}/{lat},{lon}",
            params={"format": "%C+%t+💧%h+🌬️%w", "m": None},
        )
        if resp and resp.is_success:
            text = resp.text.strip()
            _weather_cache.set(cache_key, text, ttl=180)
            return text
        return "获取失败"
    except Exception as e:
        return f"获取失败: {e}"


# ══════════════════════════════════════════════
#  📋 格式化
# ══════════════════════════════════════════════

def _format_weather(data: dict, city: str, location_hint: str = "") -> str:
    """格式化天气 JSON → Markdown."""
    cur = (data.get("current_condition") or [{}])[0]
    loc = (data.get("nearest_area") or [{}])[0]
    if not cur:
        return f"❌ 未找到 {city} 的天气数据"

    name = (loc.get("areaName") or [{}])[0].get("value", city)
    region = (loc.get("region") or [{}])[0].get("value", "")
    country = (loc.get("country") or [{}])[0].get("value", "")

    lines = [
        f"🌤️ **{name}**{f', {region}' if region else ''}{f', {country}' if country else ''}",
    ]
    if location_hint:
        lines.append(f"   📡 _{location_hint}_")
    lines.extend([
        "",
        "📊 当前天气:",
        f"   • 🌡️ 温度: {cur.get('temp_C', '?')}°C (体感 {cur.get('FeelsLikeC', '?')}°C)",
        f"   • ☁️ 天气: {(cur.get('weatherDesc') or [{}])[0].get('value', '未知')}",
        f"   • 💧 湿度: {cur.get('humidity', '?')}%",
        f"   • 🌬️ 风速: {cur.get('windspeedKmph', '?')} km/h ({cur.get('winddir16Point', '?')})",
        f"   • 👁️ 能见度: {cur.get('visibility', '?')} km",
        f"   • 🔽 气压: {cur.get('pressure', '?')} mb",
    ])
    uv = cur.get("uvIndex")
    if uv:
        lines.append(f"   • ☀️ 紫外线指数: {uv}")

    forecast = (data.get("weather") or [])[:3]
    if forecast:
        lines.extend(["", "📅 未来3天预报:"])
        for d in forecast:
            desc = (d.get("hourly") or [{}])[0].get("weatherDesc") or [{}]
            lines.append(
                f"   • {d['date']}: {desc[0].get('value', '')}, "
                f"{d.get('mintempC', '?')}~{d.get('maxtempC', '?')}°C"
            )
    return "\n".join(lines)


def _format_weather_short(data: dict, city: str) -> str:
    """极简版格式化（一行概括）. """
    cur = (data.get("current_condition") or [{}])[0]
    loc = (data.get("nearest_area") or [{}])[0]
    if not cur:
        return f"🌤️ {city}: 暂无数据"

    name = (loc.get("areaName") or [{}])[0].get("value", city)
    temp = cur.get("temp_C", "?")
    desc = (cur.get("weatherDesc") or [{}])[0].get("value", "?")
    feels = cur.get("FeelsLikeC", "?")
    humid = cur.get("humidity", "?")
    wind = cur.get("windspeedKmph", "?")
    return f"🌤️ {name}: {desc}, {temp}°C (体感{feels}°C), 💧{humid}% 🌬️{wind}km/h"


def _format_aqi(result: dict) -> str:
    """格式化 AQI 结果."""
    if result.get("error"):
        txt = f"❌ {result['error']}"
        if result.get("hint"):
            txt += f"\n💡 {result['hint']}"
        return txt
    if "data" not in result:
        return "❌ 无可用数据"

    d = result["data"]
    iaqi = d.get("iaqi") or {}
    aqi = d.get("aqi")
    city_name = result.get("city", "?")
    time_str = (d.get("time") or {}).get("s", "未知")

    def level(v):
        if v <= 50:  return "🟢 优"
        if v <= 100: return "🟡 良"
        if v <= 150: return "🟠 轻度污染"
        if v <= 200: return "🔴 中度污染"
        if v <= 300: return "🟣 重度污染"
        return "⚫ 严重污染"

    lines = [
        f"🌍 **{city_name}** — 空气质量",
        "",
        f"📊 AQI: **{aqi}** {level(int(aqi)) if aqi is not None else '?'}",
        f"⏱️ 更新时间: {time_str}",
        "",
        "📋 主要污染物:",
    ]
    for key, label in [
        ("pm25", "PM2.5"), ("pm10", "PM10"), ("o3", "O₃"),
        ("no2", "NO₂"), ("so2", "SO₂"), ("co", "CO"),
    ]:
        v = (iaqi.get(key) or {}).get("v")
        if v is not None:
            lines.append(f"   • {label}: {v} µg/m³")
    return "\n".join(lines)


# ══════════════════════════════════════════════
#  🎯 AQI 获取
# ══════════════════════════════════════════════

async def _fetch_aqi(city: str) -> dict:
    """获取 AQI 数据."""
    token = os.environ.get("WAQI_TOKEN") or ""
    if not token:
        return {
            "error": "需要 WAQI Token",
            "hint": "免费注册: https://aqicn.org/data-platform/token/ ，"
                    "然后设置环境变量 WAQI_TOKEN",
        }

    client = await _SharedClient.get()

    # 🥇 方案一：直接用城市名查 WAQI
    try:
        resp = await client.get(
            f"{WAQI_BASE}/{httpx.utils.quote(city)}/",
            params={"token": token},
        )
        if resp.is_success:
            data = resp.json()
            if data.get("status") == "ok":
                return {"data": data["data"], "city": city}
    except Exception as e:
        logger.debug("WAQI city query failed: %s", e)

    # 🥈 方案二：通过 wttr.in 获取坐标再查 WAQI（回退方案）
    weather = await _weather_by_city(city)
    if not weather:
        return {"error": f"未知城市: {city}"}

    loc = (weather.get("nearest_area") or [{}])[0]
    lat, lon = loc.get("latitude"), loc.get("longitude")
    name = (loc.get("areaName") or [{}])[0].get("value", city)

    if not lat or not lon:
        return {"error": f"无法获取 {city} 的坐标"}

    try:
        resp = await client.get(
            f"{WAQI_BASE}/geo:{lat};{lon}/",
            params={"token": token},
        )
        if resp.is_success:
            data = resp.json()
            if data.get("status") == "ok":
                return {"data": data["data"], "city": name}
            return {"error": data.get("data", "AQI 数据不可用")}
        return {"error": f"AQI API 返回 {resp.status_code}"}
    except Exception as e:
        return {"error": str(e)}


# ══════════════════════════════════════════════
#  🛠️ MCP Tools
# ══════════════════════════════════════════════

@mcp.tool()
async def get_weather(city: str) -> str:
    """获取指定城市的详细天气信息，包括温度、湿度、风速、气压和未来3天预报。

    支持中文城市名，如「北京」「上海」「Tokyo」「London」「New York」。
    """
    if not city:
        return "❌ 请提供城市名，如 city='北京'"
    data = await _weather_by_city(city)
    if not data:
        return f"❌ 无法获取 {city} 的天气数据\n\n💡 可能原因:\n  1. 城市名拼写错误？试试英文名如 'Beijing'\n  2. 网络连接问题，稍后重试"
    return _format_weather(data, city)


@mcp.tool()
async def get_weather_short(city: str = "", latitude: float | None = None, longitude: float | None = None) -> str:
    """一句话快速获取当前天气概况（简洁版，适合快速查看或通知栏展示）。

    至少提供 city 或 (latitude + longitude) 其中之一。

    参数:
        city: 城市名，如 '北京' / 'Tokyo'
        latitude: 纬度（需配合 longitude 使用）
        longitude: 经度（需配合 latitude 使用）

    示例:
        get_weather_short(city='北京')
        get_weather_short(latitude=39.9042, longitude=116.4074)
    """
    # 坐标模式
    if latitude is not None and longitude is not None:
        text = await _weather_short_by_coords(latitude, longitude)
        return f"📍 ({latitude:.4f}, {longitude:.4f}): {text}"

    # 城市名模式
    if city:
        text = await _weather_short_by_city(city)
        return f"🌤️ {city}: {text}"

    return "❌ 请提供 city 参数或 (latitude + longitude) 参数"


@mcp.tool()
async def get_weather_by_coords(latitude: float, longitude: float) -> str:
    """通过经纬度获取天气（精准定位版）。

    适合从 GPS / 地图坐标直接查天气，支持负值（南纬/西经）。
    示例: latitude=39.9042, longitude=116.4074
    """
    data = await _weather_by_coords(latitude, longitude)
    if not data:
        return f"❌ 无法获取坐标 ({latitude}, {longitude}) 的天气数据"
    loc_hint = f"坐标: {latitude:.4f}, {longitude:.4f}"
    return _format_weather(data, f"{latitude},{longitude}", location_hint=loc_hint)


@mcp.tool()
async def get_air_quality(city: str) -> str:
    """获取指定城市的空气质量指数（AQI）和污染物数据（PM2.5、PM10、O₃等）。

    需要 WAQI API Token（免费注册: https://aqicn.org/data-platform/token/）。
    设置环境变量 WAQI_TOKEN 即可使用。
    """
    if not city:
        return "❌ 请提供城市名"
    result = await _fetch_aqi(city)
    return _format_aqi(result)


# ══════════════════════════════════════════════
#  🧹 清理
# ══════════════════════════════════════════════

async def cleanup():
    """释放共享 httpx 连接池. 在服务退出时调用."""
    await _SharedClient.close()
    _weather_cache.clear()
