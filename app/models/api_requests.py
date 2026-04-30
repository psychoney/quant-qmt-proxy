from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class OpenSessionRequestModel(BaseModel):
    account_id: str = Field(..., description="资金账号")
    account_type: str = Field("STOCK", description="账户类型")


class SubmitStockOrderRequestModel(BaseModel):
    stock_code: str
    side: str
    price_type: int
    volume: int
    price: float = 0.0
    strategy_name: str = ""
    order_remark: str = ""

    @field_validator("side")
    @classmethod
    def validate_side(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"BUY", "SELL"}:
            raise ValueError("side 必须是 BUY 或 SELL")
        return normalized


class CancelStockOrderRequestModel(BaseModel):
    order_id: str | None = None
    market: str | int | None = None
    order_sysid: str | None = None

    @field_validator("market")
    @classmethod
    def validate_market(cls, value: str | int | None):
        if value is None:
            return value
        if isinstance(value, int):
            return value
        normalized = value.strip().upper()
        return normalized or None


class KlineHistoryRequestModel(BaseModel):
    symbols: list[str]
    period: str = "1d"
    start_time: str = ""
    end_time: str = ""
    fields: list[str] = Field(default_factory=list)
    adjust_type: str = "none"
    fill_data: bool = True


class TickHistoryRequestModel(BaseModel):
    symbols: list[str]
    start_time: str = ""
    end_time: str = ""
    fields: list[str] = Field(default_factory=list)
    adjust_type: str = "none"


class FinancialDataRequestModel(BaseModel):
    symbols: list[str]
    table_names: list[str]
    start_time: str = ""
    end_time: str = ""


class IndexWeightRequestModel(BaseModel):
    index_code: str


class TradingCalendarRequestModel(BaseModel):
    market: str
    start_time: str = ""
    end_time: str = ""


class L2RequestModel(BaseModel):
    symbols: list[str]
    start_time: str = ""
    end_time: str = ""


class QuoteSubscriptionRequestModel(BaseModel):
    symbols: list[str]
    period: str = "tick"
    start_time: str = ""
    adjust_type: str = "none"
    count: int = 0

    @field_validator("count")
    @classmethod
    def validate_count(cls, value: int) -> int:
        if value < -1:
            raise ValueError("count 必须大于等于 -1")
        return value


class WholeQuoteSubscriptionRequestModel(BaseModel):
    markets: list[str] = Field(default_factory=lambda: ["SH", "SZ"])


class AkshareKlineRequestModel(BaseModel):
    symbol: str
    asset_type: str = "index"
    period: str = "daily"
    start_date: str = ""
    end_date: str = ""
    adjust: str = ""

    @field_validator("asset_type")
    @classmethod
    def validate_asset_type(cls, value: str) -> str:
        if value not in {"index", "stock"}:
            raise ValueError("asset_type must be 'index' or 'stock'")
        return value
