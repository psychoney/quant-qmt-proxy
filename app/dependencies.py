"""依赖注入模块。"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings, XTQuantMode, get_settings
from app.services.akshare_service import AkshareService
from app.services.market_data_service import MarketDataService
from app.services.reference_data_service import ReferenceDataService
from app.services.trading_event_hub import TradingEventHub
from app.services.trading_session_manager import TradingSessionManager
from app.services.ui_subscription_service import UiSubscriptionService
from app.services.xtdata_gateway import XtDataGateway
from app.services.xtdata_subscription_hub import XtDataSubscriptionHub
from app.utils.exceptions import AuthenticationException
from app.utils.logger import logger

security = HTTPBearer(auto_error=False)

_xtdata_gateway: XtDataGateway | None = None
_subscription_hub: XtDataSubscriptionHub | None = None
_market_data_service: MarketDataService | None = None
_reference_data_service: ReferenceDataService | None = None
_ui_subscription_service: UiSubscriptionService | None = None
_trading_event_hub: TradingEventHub | None = None
_trading_session_manager: TradingSessionManager | None = None
_akshare_service: AkshareService | None = None


def get_xtdata_gateway(settings: Settings = Depends(get_settings)) -> XtDataGateway:
    global _xtdata_gateway
    if _xtdata_gateway is None:
        _xtdata_gateway = XtDataGateway(settings)
    return _xtdata_gateway


def get_subscription_hub(settings: Settings = Depends(get_settings)) -> XtDataSubscriptionHub:
    global _subscription_hub
    if _subscription_hub is None:
        _subscription_hub = XtDataSubscriptionHub(settings, get_xtdata_gateway(settings))
    return _subscription_hub


def get_market_data_service(settings: Settings = Depends(get_settings)) -> MarketDataService:
    global _market_data_service
    if _market_data_service is None:
        _market_data_service = MarketDataService(
            get_xtdata_gateway(settings),
            get_subscription_hub(settings),
        )
    return _market_data_service


def get_reference_data_service(settings: Settings = Depends(get_settings)) -> ReferenceDataService:
    global _reference_data_service
    if _reference_data_service is None:
        _reference_data_service = ReferenceDataService(get_xtdata_gateway(settings))
    return _reference_data_service


def get_ui_subscription_service(settings: Settings = Depends(get_settings)) -> UiSubscriptionService:
    global _ui_subscription_service
    if _ui_subscription_service is None:
        _ui_subscription_service = UiSubscriptionService(get_subscription_hub(settings))
    return _ui_subscription_service


def get_trading_event_hub() -> TradingEventHub:
    global _trading_event_hub
    if _trading_event_hub is None:
        _trading_event_hub = TradingEventHub()
    return _trading_event_hub


def get_trading_session_manager(settings: Settings = Depends(get_settings)) -> TradingSessionManager:
    global _trading_session_manager
    if _trading_session_manager is None:
        _trading_session_manager = TradingSessionManager(settings, get_trading_event_hub())
    return _trading_session_manager


# Backward-compatible aliases used by some existing modules/tests.
get_data_service = get_market_data_service
get_subscription_manager = get_subscription_hub
get_trading_service = get_trading_session_manager


def get_akshare_service() -> AkshareService:
    global _akshare_service
    if _akshare_service is None:
        _akshare_service = AkshareService()
    return _akshare_service


async def get_api_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    settings: Settings = Depends(get_settings),
) -> Optional[str]:
    if not credentials:
        return None
    return credentials.credentials


async def verify_api_key(
    api_key: Optional[str] = Depends(get_api_key),
    settings: Settings = Depends(get_settings),
) -> Optional[str]:
    configured_keys = settings.security.api_keys
    if not configured_keys:
        return api_key
    if not api_key:
        logger.warning("API key verification failed: missing bearer token")
        raise AuthenticationException("缺少 API 密钥")
    if api_key not in configured_keys:
        logger.warning("API key verification failed: invalid bearer token")
        raise AuthenticationException("无效的 API 密钥")
    return api_key


def is_real_trading_allowed(settings: Settings = Depends(get_settings)) -> bool:
    if settings.xtquant.mode == XTQuantMode.DEV:
        return any(
            profile.enabled and profile.account_kind.value == "simulated" and XTQuantMode.DEV in profile.allowed_modes
            for profile in settings.xtquant.trading.accounts
        )
    if settings.xtquant.mode == XTQuantMode.PROD:
        return any(
            profile.enabled and profile.account_kind.value == "real" and XTQuantMode.PROD in profile.allowed_modes
            for profile in settings.xtquant.trading.accounts
        ) and settings.xtquant.trading.enable_prod_orders
    return settings.xtquant.mode == XTQuantMode.MOCK


def reset_services() -> None:
    global _xtdata_gateway
    global _subscription_hub
    global _market_data_service
    global _reference_data_service
    global _ui_subscription_service
    global _trading_event_hub
    global _trading_session_manager

    if _subscription_hub is not None:
        try:
            _subscription_hub.shutdown()
        except Exception:
            pass
    if _trading_session_manager is not None:
        try:
            _trading_session_manager.shutdown()
        except Exception:
            pass

    _xtdata_gateway = None
    _subscription_hub = None
    _market_data_service = None
    _reference_data_service = None
    _ui_subscription_service = None
    _trading_event_hub = None
    _trading_session_manager = None
    _akshare_service = None
