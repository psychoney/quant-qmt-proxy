from __future__ import annotations

from typing import Any

from app.utils.exceptions import DataServiceException
from app.utils.logger import logger

try:
    import akshare as ak

    AKSHARE_AVAILABLE = True
except ImportError:
    ak = None
    AKSHARE_AVAILABLE = False


FIELD_MAP = {"日期": "time", "开盘": "open", "收盘": "close", "最高": "high", "最低": "low", "成交量": "volume", "成交额": "amount", "振幅": "amplitude", "涨跌幅": "change_pct", "涨跌额": "change", "换手率": "turnover"}


class AkshareService:
    def _ensure_available(self) -> None:
        if not AKSHARE_AVAILABLE:
            raise DataServiceException("akshare is not installed", error_code="AKSHARE_UNAVAILABLE")

    def get_kline(
        self,
        symbol: str,
        asset_type: str,
        period: str,
        start_date: str,
        end_date: str,
        adjust: str,
    ) -> list[dict[str, Any]]:
        self._ensure_available()
        try:
            if asset_type == "index":
                df = ak.index_zh_a_hist(symbol=symbol, period=period, start_date=start_date, end_date=end_date)
            else:
                df = ak.stock_zh_a_hist(symbol=symbol, period=period, start_date=start_date, end_date=end_date, adjust=adjust)
        except Exception as exc:
            logger.warning(f"akshare request failed: {exc}")
            raise DataServiceException(f"akshare request failed: {exc}", error_code="AKSHARE_REQUEST_FAILED") from exc

        if df is None or len(df) == 0:
            return []

        renamed = {cn: en for cn, en in FIELD_MAP.items() if cn in df.columns}
        df = df.rename(columns=renamed)

        records: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            item: dict[str, Any] = {}
            for col in df.columns:
                val = row[col]
                mapped = FIELD_MAP.get(col, col)
                if hasattr(val, "isoformat"):
                    item[mapped] = val.isoformat()
                elif hasattr(val, "item"):
                    item[mapped] = val.item()
                else:
                    item[mapped] = val
            records.append(item)
        return records
