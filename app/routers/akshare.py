from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_akshare_service, verify_api_key
from app.models.api_requests import AkshareKlineRequestModel
from app.services.akshare_service import AkshareService
from app.utils.exceptions import DataServiceException, handle_xtquant_exception
from app.utils.helpers import format_response

router = APIRouter(prefix="/api/v1/akshare", tags=["akshare数据"])


@router.post("/kline")
async def get_akshare_kline(
    request: AkshareKlineRequestModel,
    api_key: str | None = Depends(verify_api_key),
    akshare_service: AkshareService = Depends(get_akshare_service),
):
    try:
        items = akshare_service.get_kline(
            symbol=request.symbol,
            asset_type=request.asset_type,
            period=request.period,
            start_date=request.start_date,
            end_date=request.end_date,
            adjust=request.adjust,
        )
        return format_response(data={"symbol": request.symbol, "total": len(items), "items": items}, message="获取 akshare K 线数据成功")
    except DataServiceException as exc:
        raise handle_xtquant_exception(exc)
