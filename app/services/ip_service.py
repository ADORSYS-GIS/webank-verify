"""IP intelligence: geolocation (MaxMind GeoLite2) + VPN/proxy/Tor detection."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from app.core.config import settings


@dataclass
class IPAnalysis:
    ip: str
    country: str | None = None
    country_name: str | None = None
    city: str | None = None
    isp: str | None = None
    is_vpn: bool = False
    is_proxy: bool = False
    is_tor: bool = False
    risk_score: int = 0
    risk_flags: list[str] = field(default_factory=list)


_geoip_reader = None


def _get_geoip_reader():
    global _geoip_reader
    if _geoip_reader is not None:
        return _geoip_reader
    db_path = Path(settings.geoip_db_path)
    if not db_path.exists():
        return None
    try:
        import geoip2.database  # noqa: PLC0415

        _geoip_reader = geoip2.database.Reader(str(db_path))
        return _geoip_reader
    except Exception:
        return None


def _lookup_geoip(ip: str) -> tuple[str | None, str | None, str | None]:
    """Returns (country_iso, country_name, city) using MaxMind GeoLite2."""
    reader = _get_geoip_reader()
    if reader is None:
        return None, None, None
    try:
        response = reader.country(ip)
        return (
            response.country.iso_code,
            response.country.name,
            None,  # Country DB doesn't have city; use City DB for that
        )
    except Exception:
        return None, None, None


async def _lookup_ip_api(ip: str) -> dict:
    """Fallback: ip-api.com (free, 45 req/min). Returns VPN/proxy/Tor flags."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"http://ip-api.com/json/{ip}",
                params={"fields": "status,country,countryCode,city,isp,proxy,hosting"},
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    return {}


async def analyze_ip(ip: str) -> IPAnalysis:
    """Full IP intelligence: geo + VPN/proxy detection."""
    if not ip or ip in ("127.0.0.1", "::1", "localhost"):
        return IPAnalysis(ip=ip, country="CM", country_name="Cameroon (local)")

    country_iso, country_name, city = _lookup_geoip(ip)
    ip_api_data = await _lookup_ip_api(ip)

    # Merge results (GeoIP2 preferred for country, ip-api for VPN flags)
    if not country_iso:
        country_iso = ip_api_data.get("countryCode")
        country_name = ip_api_data.get("country")
        city = ip_api_data.get("city")

    is_proxy = bool(ip_api_data.get("proxy", False))
    is_hosting = bool(ip_api_data.get("hosting", False))
    isp = ip_api_data.get("isp")

    result = IPAnalysis(
        ip=ip,
        country=country_iso,
        country_name=country_name,
        city=city,
        isp=isp,
        is_vpn=is_hosting,
        is_proxy=is_proxy,
        is_tor=False,  # ip-api free tier doesn't have Tor; would need premium
    )

    # Risk scoring
    risk = 0
    if result.is_vpn:
        risk += 30
        result.risk_flags.append("VPN_DETECTED")
    if result.is_proxy:
        risk += 25
        result.risk_flags.append("PROXY_DETECTED")
    if result.is_tor:
        risk += 40
        result.risk_flags.append("TOR_DETECTED")
    if country_iso and country_iso != "CM":
        risk += 20
        result.risk_flags.append(f"NON_CAMEROON_IP:{country_iso}")
    if not country_iso:
        risk += 10
        result.risk_flags.append("UNKNOWN_COUNTRY")

    result.risk_score = min(100, risk)
    return result
