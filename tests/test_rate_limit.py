import pytest
import respx
from httpx import AsyncClient, Response
from app.config import get_settings
from app.core.exceptions import RateLimitExceededException
from app.core.rate_limit import check_api_key_rate_limit

settings = get_settings()


@pytest.mark.asyncio
async def test_rate_limiter_blocks_on_threshold():
    prefix = "pg_test_ratelimit"
    limit = 3

    # First 3 requests pass
    for _ in range(limit):
        await check_api_key_rate_limit(key_prefix=prefix, custom_limit=limit)

    # 4th request must raise RateLimitExceededException
    with pytest.raises(RateLimitExceededException) as exc_info:
        await check_api_key_rate_limit(key_prefix=prefix, custom_limit=limit)

    assert "Rate limit exceeded" in str(exc_info.value.message)


@pytest.mark.asyncio
@respx.mock
async def test_invalid_api_key_error_handling(async_client: AsyncClient):
    res = await async_client.post(
        "/v1/orders",
        json={
            "merchant_order_id": "ORD-ERR-001",
            "amount": 1000,
            "redirect_url": "https://example.com",
        },
        headers={"X-API-Key": "pg_live_invalid_key_does_not_exist"},
    )
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "INVALID_API_KEY"


@pytest.mark.asyncio
@respx.mock
async def test_order_not_found_status(async_client: AsyncClient, sample_tenant_and_key: dict):
    raw_api_key = sample_tenant_and_key["raw_api_key"]
    res = await async_client.get(
        "/v1/orders/NON_EXISTENT_ORDER_ID",
        headers={"X-API-Key": raw_api_key},
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "ORDER_NOT_FOUND"
