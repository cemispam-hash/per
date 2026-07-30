"""Интеграция с PayPalych (СБП). Без токена возвращает None — оплата недоступна."""

import logging
from typing import Optional

import httpx

from config import PAYPALYCH_API, PAYPALYCH_SHOP_ID, PAYPALYCH_TOKEN

log = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(15.0)


def enabled() -> bool:
    return bool(PAYPALYCH_TOKEN and PAYPALYCH_SHOP_ID)


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {PAYPALYCH_TOKEN}",
        "Accept": "application/json",
    }


async def create_bill(order_id: str, amount: int, description: str) -> Optional[dict]:
    """Создаёт счёт. Возвращает {'id': ..., 'url': ...} или None при ошибке."""
    if not enabled():
        return None
    payload = {
        "amount": amount,
        "order_id": order_id,
        "description": description,
        "type": "normal",
        "shop_id": PAYPALYCH_SHOP_ID,
        "currency_in": "RUB",
        "payer_pays_commission": 1,
        "name": description,
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                f"{PAYPALYCH_API}/bill/create", json=payload, headers=_headers()
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:  # сеть/формат ответа — счёт просто не создаётся
        log.exception("PayPalych: не удалось создать счёт %s", order_id)
        return None

    if not data.get("success", True):
        log.error("PayPalych отклонил счёт %s: %s", order_id, data)
        return None
    url = data.get("link_page_url") or data.get("link_url")
    bill_id = data.get("bill_id") or data.get("id")
    if not url:
        log.error("PayPalych не вернул ссылку для %s: %s", order_id, data)
        return None
    return {"id": str(bill_id), "url": url}


async def bill_status(bill_id: str) -> Optional[str]:
    """Возвращает статус счёта: SUCCESS / UNDERPAID / FAIL / ... или None."""
    if not enabled():
        return None
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                f"{PAYPALYCH_API}/bill/status",
                params={"id": bill_id},
                headers=_headers(),
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        log.exception("PayPalych: не удалось получить статус счёта %s", bill_id)
        return None
    status = data.get("status") or data.get("payment_status")
    return str(status).upper() if status else None
