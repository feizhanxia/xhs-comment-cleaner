from __future__ import annotations

from playwright.async_api import Page

from app.core.exceptions import LoginExpired, RiskControlDetected
from app.xhs import selectors


async def detect_risk_control(page: Page) -> None:
    body = page.locator("body")
    try:
        text = (await body.inner_text(timeout=2_000))[:20_000]
    except Exception:
        return
    if any(marker in text for marker in selectors.RISK_TEXT):
        raise RiskControlDetected("小红书要求人工处理。请在 Edge 中完成验证。")
    if any(marker in text for marker in selectors.LOGIN_EXPIRED_TEXT):
        raise LoginExpired("登录状态已失效，请重新登录小红书。")
