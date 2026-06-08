"""Tests for IP intelligence service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ip_service import IPAnalysis, analyze_ip


@pytest.mark.asyncio
async def test_localhost_returns_cameroon():
    result = await analyze_ip("127.0.0.1")
    assert result.country == "CM"


@pytest.mark.asyncio
@patch("app.services.ip_service._lookup_geoip", return_value=("CM", "Cameroon", "Yaoundé"))
@patch("app.services.ip_service._lookup_ip_api", new_callable=AsyncMock, return_value={
    "countryCode": "CM", "country": "Cameroon", "city": "Yaoundé", "isp": "Camtel", "proxy": False, "hosting": False,
})
async def test_cameroon_ip_low_risk(mock_api, mock_geo):
    result = await analyze_ip("197.1.2.3")
    assert result.country == "CM"
    assert result.is_vpn is False
    assert result.risk_score == 0
    assert len(result.risk_flags) == 0


@pytest.mark.asyncio
@patch("app.services.ip_service._lookup_geoip", return_value=("FR", "France", "Paris"))
@patch("app.services.ip_service._lookup_ip_api", new_callable=AsyncMock, return_value={
    "countryCode": "FR", "country": "France", "city": "Paris", "isp": "OVH", "proxy": False, "hosting": True,
})
async def test_non_cameroon_vpn_high_risk(mock_api, mock_geo):
    result = await analyze_ip("51.75.1.2")
    assert result.country == "FR"
    assert result.is_vpn is True
    assert result.risk_score > 30
    assert any("NON_CAMEROON_IP" in f for f in result.risk_flags)
    assert "VPN_DETECTED" in result.risk_flags


@pytest.mark.asyncio
@patch("app.services.ip_service._lookup_geoip", return_value=(None, None, None))
@patch("app.services.ip_service._lookup_ip_api", new_callable=AsyncMock, return_value={})
async def test_unknown_ip_moderate_risk(mock_api, mock_geo):
    result = await analyze_ip("0.0.0.0")
    assert result.risk_score > 0
