"""
交易服务路由

所有路由使用 run_sync 将同步 xttrader 调用放入线程池执行，
防止阻塞 FastAPI 事件循环导致服务卡死。
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import Settings, get_settings
from app.dependencies import get_trading_service, verify_api_key
from app.models.trading_models import (
    AccountInfo,
    AssetInfo,
    AsyncCancelRequest,
    AsyncCancelResponse,
    AsyncOrderRequest,
    AsyncOrderResponse,
    CancelOrderRequest,
    ConnectRequest,
    ConnectResponse,
    OrderRequest,
    OrderResponse,
    PositionInfo,
    RiskInfo,
    StrategyInfo,
    TradeInfo,
)
from app.services.trading_service import TradingService
from app.utils.async_utils import run_sync
from app.utils.exceptions import TradingServiceException, handle_xtquant_exception
from app.utils.helpers import format_response

router = APIRouter(prefix="/api/v1/trading", tags=["交易服务"])


@router.post("/connect", response_model=ConnectResponse)
async def connect_account(
    request: ConnectRequest,
    api_key: str = Depends(verify_api_key),
    trading_service: TradingService = Depends(get_trading_service),
    settings: Settings = Depends(get_settings)
):
    """连接交易账户"""
    try:
        result = await run_sync(
            trading_service.connect_account, request,
            timeout=settings.request_timeout.trading
        )
        return result
    except TradingServiceException as e:
        raise handle_xtquant_exception(e)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": f"连接账户失败: {str(e)}"}
        )


@router.post("/disconnect/{session_id}")
async def disconnect_account(
    session_id: str,
    api_key: str = Depends(verify_api_key),
    trading_service: TradingService = Depends(get_trading_service),
    settings: Settings = Depends(get_settings)
):
    """断开交易账户"""
    try:
        success = await run_sync(
            trading_service.disconnect_account, session_id,
            timeout=settings.request_timeout.trading
        )
        return format_response(
            data={"success": success},
            message="断开账户成功" if success else "断开账户失败"
        )
    except TradingServiceException as e:
        raise handle_xtquant_exception(e)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": f"断开账户失败: {str(e)}"}
        )


@router.get("/account/{session_id}", response_model=AccountInfo)
async def get_account_info(
    session_id: str,
    api_key: str = Depends(verify_api_key),
    trading_service: TradingService = Depends(get_trading_service),
    settings: Settings = Depends(get_settings)
):
    """获取账户信息"""
    try:
        result = await run_sync(
            trading_service.get_account_info, session_id,
            timeout=settings.request_timeout.trading
        )
        return result
    except TradingServiceException as e:
        raise handle_xtquant_exception(e)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": f"获取账户信息失败: {str(e)}"}
        )


@router.get("/positions/{session_id}", response_model=List[PositionInfo])
async def get_positions(
    session_id: str,
    api_key: str = Depends(verify_api_key),
    trading_service: TradingService = Depends(get_trading_service),
    settings: Settings = Depends(get_settings)
):
    """获取持仓信息"""
    try:
        results = await run_sync(
            trading_service.get_positions, session_id,
            timeout=settings.request_timeout.trading
        )
        return results
    except TradingServiceException as e:
        raise handle_xtquant_exception(e)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": f"获取持仓信息失败: {str(e)}"}
        )


@router.post("/order/{session_id}", response_model=OrderResponse)
async def submit_order(
    session_id: str,
    request: OrderRequest,
    api_key: str = Depends(verify_api_key),
    trading_service: TradingService = Depends(get_trading_service),
    settings: Settings = Depends(get_settings)
):
    """提交订单"""
    try:
        result = await run_sync(
            trading_service.submit_order, session_id, request,
            timeout=settings.request_timeout.trading
        )
        return result
    except TradingServiceException as e:
        raise handle_xtquant_exception(e)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": f"提交订单失败: {str(e)}"}
        )


@router.post("/cancel/{session_id}")
async def cancel_order(
    session_id: str,
    request: CancelOrderRequest,
    api_key: str = Depends(verify_api_key),
    trading_service: TradingService = Depends(get_trading_service),
    settings: Settings = Depends(get_settings)
):
    """撤销订单"""
    try:
        success = await run_sync(
            trading_service.cancel_order, session_id, request,
            timeout=settings.request_timeout.trading
        )
        return format_response(
            data={"success": success},
            message="撤销订单成功" if success else "撤销订单失败"
        )
    except TradingServiceException as e:
        raise handle_xtquant_exception(e)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": f"撤销订单失败: {str(e)}"}
        )


@router.get("/orders/{session_id}", response_model=List[OrderResponse])
async def get_orders(
    session_id: str,
    api_key: str = Depends(verify_api_key),
    trading_service: TradingService = Depends(get_trading_service),
    settings: Settings = Depends(get_settings)
):
    """获取订单列表"""
    try:
        results = await run_sync(
            trading_service.get_orders, session_id,
            timeout=settings.request_timeout.trading
        )
        return results
    except TradingServiceException as e:
        raise handle_xtquant_exception(e)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": f"获取订单列表失败: {str(e)}"}
        )


@router.get("/trades/{session_id}", response_model=List[TradeInfo])
async def get_trades(
    session_id: str,
    api_key: str = Depends(verify_api_key),
    trading_service: TradingService = Depends(get_trading_service),
    settings: Settings = Depends(get_settings)
):
    """获取成交记录"""
    try:
        results = await run_sync(
            trading_service.get_trades, session_id,
            timeout=settings.request_timeout.trading
        )
        return results
    except TradingServiceException as e:
        raise handle_xtquant_exception(e)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": f"获取成交记录失败: {str(e)}"}
        )


@router.get("/asset/{session_id}", response_model=AssetInfo)
async def get_asset_info(
    session_id: str,
    api_key: str = Depends(verify_api_key),
    trading_service: TradingService = Depends(get_trading_service),
    settings: Settings = Depends(get_settings)
):
    """获取资产信息"""
    try:
        result = await run_sync(
            trading_service.get_asset_info, session_id,
            timeout=settings.request_timeout.trading
        )
        return result
    except TradingServiceException as e:
        raise handle_xtquant_exception(e)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": f"获取资产信息失败: {str(e)}"}
        )


@router.get("/risk/{session_id}", response_model=RiskInfo)
async def get_risk_info(
    session_id: str,
    api_key: str = Depends(verify_api_key),
    trading_service: TradingService = Depends(get_trading_service),
    settings: Settings = Depends(get_settings)
):
    """获取风险信息"""
    try:
        result = await run_sync(
            trading_service.get_risk_info, session_id,
            timeout=settings.request_timeout.trading
        )
        return result
    except TradingServiceException as e:
        raise handle_xtquant_exception(e)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": f"获取风险信息失败: {str(e)}"}
        )


@router.get("/strategies/{session_id}", response_model=List[StrategyInfo])
async def get_strategies(
    session_id: str,
    api_key: str = Depends(verify_api_key),
    trading_service: TradingService = Depends(get_trading_service),
    settings: Settings = Depends(get_settings)
):
    """获取策略列表"""
    try:
        results = await run_sync(
            trading_service.get_strategies, session_id,
            timeout=settings.request_timeout.trading
        )
        return results
    except TradingServiceException as e:
        raise handle_xtquant_exception(e)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": f"获取策略列表失败: {str(e)}"}
        )


@router.get("/status/{session_id}")
async def get_connection_status(
    session_id: str,
    api_key: str = Depends(verify_api_key),
    trading_service: TradingService = Depends(get_trading_service),
    settings: Settings = Depends(get_settings)
):
    """获取连接状态"""
    try:
        is_connected = await run_sync(
            trading_service.is_connected, session_id,
            timeout=settings.request_timeout.trading
        )
        return format_response(
            data={"connected": is_connected},
            message="连接状态查询成功"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": f"查询连接状态失败: {str(e)}"}
        )


# ==================== 异步交易接口 ====================

@router.post("/order-async/{session_id}", response_model=AsyncOrderResponse)
async def submit_order_async(
    session_id: str,
    request: AsyncOrderRequest,
    api_key: str = Depends(verify_api_key),
    trading_service: TradingService = Depends(get_trading_service),
    settings: Settings = Depends(get_settings)
):
    """
    异步提交订单

    异步下单后立即返回，订单结果通过 WebSocket 回调推送。
    返回的 seq 字段用于匹配回调中的订单。
    """
    try:
        result = await run_sync(
            trading_service.submit_order_async, session_id, request,
            timeout=settings.request_timeout.trading
        )
        return result
    except TradingServiceException as e:
        raise handle_xtquant_exception(e)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": f"异步下单失败: {str(e)}"}
        )


@router.post("/cancel-async/{session_id}", response_model=AsyncCancelResponse)
async def cancel_order_async(
    session_id: str,
    request: AsyncCancelRequest,
    api_key: str = Depends(verify_api_key),
    trading_service: TradingService = Depends(get_trading_service),
    settings: Settings = Depends(get_settings)
):
    """
    异步撤销订单

    异步撤单后立即返回，撤单结果通过 WebSocket 回调推送。
    可以使用 order_id 或 order_sysid 撤单（二选一）。
    """
    try:
        result = await run_sync(
            trading_service.cancel_order_async, session_id, request,
            timeout=settings.request_timeout.trading
        )
        return result
    except TradingServiceException as e:
        raise handle_xtquant_exception(e)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": f"异步撤单失败: {str(e)}"}
        )
