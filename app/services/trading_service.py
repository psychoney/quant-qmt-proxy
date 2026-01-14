"""
交易服务层

提供交易相关功能：
- 账户连接/断开
- 资产查询（真实数据）
- 持仓查询（真实数据）
- 成交查询（真实数据）
- 订单查询（真实数据）
- 同步下单/撤单
- 异步下单/撤单
"""
import os
import sys
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.utils.logger import logger

# 添加xtquant包到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

try:
    from xtquant import xttrader, xtconstant
    from xtquant.xttrader import XtQuantTrader, XtQuantTraderCallback
    from xtquant.xttype import StockAccount
    XTQUANT_AVAILABLE = True
except ImportError as e:
    logger.warning(f"xtquant模块导入失败: {e}")
    XTQUANT_AVAILABLE = False
    # 创建模拟模块以避免导入错误
    class MockModule:
        def __getattr__(self, name):
            def mock_function(*args, **kwargs):
                raise NotImplementedError(f"xtquant模块未正确安装，无法调用 {name}")
            return mock_function

    xttrader = MockModule()
    xtconstant = MockModule()
    XtQuantTrader = None
    StockAccount = None

from app.config import Settings, XTQuantMode
from app.models.trading_models import (
    AccountInfo,
    AccountType,
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
    OrderStatus,
    PositionInfo,
    RiskInfo,
    StrategyInfo,
    TradeInfo,
)
from app.utils.exceptions import TradingServiceException
from app.utils.helpers import validate_stock_code
from app.utils.logger import logger


class TradingService:
    """交易服务类"""

    def __init__(self, settings: Settings):
        """初始化交易服务"""
        self.settings = settings
        self._initialized = False
        self._connected_accounts: Dict[str, Dict[str, Any]] = {}
        self._xt_traders: Dict[str, XtQuantTrader] = {}  # session_id -> XtQuantTrader
        self._orders: Dict[str, OrderResponse] = {}
        self._trades: Dict[str, TradeInfo] = {}
        self._order_counter = 1000
        self._async_seq_counter = 0
        self._seq_lock = threading.Lock()
        self._callback_manager = None
        self._try_initialize()

    def _try_initialize(self):
        """尝试初始化xttrader"""
        if not XTQUANT_AVAILABLE:
            self._initialized = False
            return

        if self.settings.xtquant.mode == XTQuantMode.MOCK:
            self._initialized = False
            return

        try:
            # 初始化回调管理器
            from app.services.trading_callback_manager import get_trading_callback_manager
            self._callback_manager = get_trading_callback_manager(self.settings)
            self._initialized = True
            logger.info("TradingService 已初始化")
        except Exception as e:
            logger.warning(f"TradingService 初始化失败: {e}")
            self._initialized = False

    def _get_next_seq(self) -> int:
        """获取下一个异步请求序号"""
        with self._seq_lock:
            self._async_seq_counter += 1
            return self._async_seq_counter

    def _should_use_real_trading(self) -> bool:
        """
        判断是否使用真实交易
        只有在 prod 模式且配置允许时才允许真实交易
        """
        return (
            self.settings.xtquant.mode == XTQuantMode.PROD and
            self.settings.xtquant.trading.allow_real_trading
        )

    def _should_use_real_data(self) -> bool:
        """
        判断是否连接xtquant获取真实数据（但不一定允许交易）
        dev 和 prod 模式都连接 xtquant
        """
        return (
            XTQUANT_AVAILABLE and
            self.settings.xtquant.mode in [XTQuantMode.DEV, XTQuantMode.PROD]
        )

    def _get_xt_trader(self, session_id: str) -> Optional[XtQuantTrader]:
        """获取 XtQuantTrader 实例"""
        return self._xt_traders.get(session_id)

    # ==================== 账户管理 ====================

    def connect_account(self, request: ConnectRequest) -> ConnectResponse:
        """连接交易账户"""
        try:
            if self._should_use_real_data() and XTQUANT_AVAILABLE and XtQuantTrader:
                # 真实连接
                return self._connect_real_account(request)
            else:
                # Mock 连接
                return self._connect_mock_account(request)

        except Exception as e:
            logger.error(f"连接账户失败: {e}", exc_info=True)
            return ConnectResponse(
                success=False,
                message=f"账户连接失败: {str(e)}"
            )

    def _connect_real_account(self, request: ConnectRequest) -> ConnectResponse:
        """真实连接账户"""
        try:
            # 获取 QMT 路径
            qmt_path = self.settings.xtquant.data.qmt_userdata_path
            if not qmt_path:
                raise TradingServiceException("未配置 QMT userdata 路径")

            # 创建 XtQuantTrader 实例
            session_id = f"session_{request.account_id}_{int(datetime.now().timestamp())}"
            xt_trader = XtQuantTrader(qmt_path, session_id)

            # 创建账户对象
            account = StockAccount(request.account_id)

            # 注册回调
            if self._callback_manager:
                self._callback_manager.start(xt_trader)

            # 启动交易线程
            xt_trader.start()

            # 连接到服务器
            connect_result = xt_trader.connect()
            if connect_result != 0:
                raise TradingServiceException(f"连接服务器失败，错误码: {connect_result}")

            # 订阅账户
            subscribe_result = xt_trader.subscribe(account)
            if subscribe_result != 0:
                raise TradingServiceException(f"订阅账户失败，错误码: {subscribe_result}")

            # 查询账户资产以验证连接
            asset = xt_trader.query_stock_asset(account)
            if asset:
                total_asset = asset.total_asset
                market_value = asset.market_value
                cash = asset.cash
            else:
                total_asset = 0.0
                market_value = 0.0
                cash = 0.0

            # 构建账户信息
            account_info = AccountInfo(
                account_id=request.account_id,
                account_type=AccountType.SECURITY,
                account_name=f"账户{request.account_id}",
                status="CONNECTED",
                balance=cash,
                available_balance=cash,
                frozen_balance=0.0,
                market_value=market_value,
                total_asset=total_asset
            )

            # 保存连接信息
            self._connected_accounts[session_id] = {
                "account_info": account_info,
                "account": account,
                "connected_time": datetime.now()
            }
            self._xt_traders[session_id] = xt_trader

            logger.info(f"账户 {request.account_id} 连接成功，session_id={session_id}")

            return ConnectResponse(
                success=True,
                message="账户连接成功",
                session_id=session_id,
                account_info=account_info
            )

        except Exception as e:
            logger.error(f"真实连接账户失败: {e}", exc_info=True)
            raise

    def _connect_mock_account(self, request: ConnectRequest) -> ConnectResponse:
        """Mock 连接账户"""
        account_info = AccountInfo(
            account_id=request.account_id,
            account_type=AccountType.SECURITY,
            account_name=f"账户{request.account_id}",
            status="CONNECTED",
            balance=1000000.0,
            available_balance=950000.0,
            frozen_balance=50000.0,
            market_value=800000.0,
            total_asset=1800000.0
        )

        session_id = f"session_{request.account_id}_{int(datetime.now().timestamp())}"
        self._connected_accounts[session_id] = {
            "account_info": account_info,
            "account": None,
            "connected_time": datetime.now()
        }

        return ConnectResponse(
            success=True,
            message="账户连接成功（Mock模式）",
            session_id=session_id,
            account_info=account_info
        )

    def disconnect_account(self, session_id: str) -> bool:
        """断开交易账户"""
        try:
            if session_id in self._xt_traders:
                xt_trader = self._xt_traders[session_id]
                try:
                    xt_trader.stop()
                except Exception as e:
                    logger.warning(f"停止 xt_trader 失败: {e}")
                del self._xt_traders[session_id]

            if session_id in self._connected_accounts:
                del self._connected_accounts[session_id]
                return True
            return False
        except Exception as e:
            raise TradingServiceException(f"断开账户失败: {str(e)}")

    def get_account_info(self, session_id: str) -> AccountInfo:
        """获取账户信息"""
        if session_id not in self._connected_accounts:
            raise TradingServiceException("账户未连接")

        return self._connected_accounts[session_id]["account_info"]

    # ==================== 资产查询（真实数据） ====================

    def get_asset_info(self, session_id: str) -> AssetInfo:
        """获取资产信息（支持真实数据）"""
        if session_id not in self._connected_accounts:
            raise TradingServiceException("账户未连接")

        if self._should_use_real_data():
            return self._get_real_asset_info(session_id)
        else:
            return self._get_mock_asset_info()

    def _get_real_asset_info(self, session_id: str) -> AssetInfo:
        """获取真实资产信息"""
        xt_trader = self._get_xt_trader(session_id)
        if not xt_trader:
            raise TradingServiceException("交易连接不存在")

        account = self._connected_accounts[session_id].get("account")
        if not account:
            raise TradingServiceException("账户对象不存在")

        try:
            asset = xt_trader.query_stock_asset(account)
            if not asset:
                raise TradingServiceException("查询资产失败")

            return AssetInfo(
                total_asset=getattr(asset, 'total_asset', 0.0),
                market_value=getattr(asset, 'market_value', 0.0),
                cash=getattr(asset, 'cash', 0.0),
                frozen_cash=getattr(asset, 'frozen_cash', 0.0),
                available_cash=getattr(asset, 'cash', 0.0) - getattr(asset, 'frozen_cash', 0.0),
                profit_loss=getattr(asset, 'profit', 0.0),
                profit_loss_ratio=0.0  # 需要计算
            )
        except Exception as e:
            logger.error(f"查询真实资产失败: {e}")
            raise TradingServiceException(f"查询资产失败: {str(e)}")

    def _get_mock_asset_info(self) -> AssetInfo:
        """获取模拟资产信息"""
        return AssetInfo(
            total_asset=1800000.0,
            market_value=800000.0,
            cash=950000.0,
            frozen_cash=50000.0,
            available_cash=900000.0,
            profit_loss=50000.0,
            profit_loss_ratio=0.028
        )

    # ==================== 持仓查询（真实数据） ====================

    def get_positions(self, session_id: str) -> List[PositionInfo]:
        """获取持仓信息（支持真实数据）"""
        if session_id not in self._connected_accounts:
            raise TradingServiceException("账户未连接")

        if self._should_use_real_data():
            return self._get_real_positions(session_id)
        else:
            return self._get_mock_positions()

    def _get_real_positions(self, session_id: str) -> List[PositionInfo]:
        """获取真实持仓信息"""
        xt_trader = self._get_xt_trader(session_id)
        if not xt_trader:
            raise TradingServiceException("交易连接不存在")

        account = self._connected_accounts[session_id].get("account")
        if not account:
            raise TradingServiceException("账户对象不存在")

        try:
            positions = xt_trader.query_stock_positions(account)
            if not positions:
                return []

            result = []
            for pos in positions:
                volume = getattr(pos, 'volume', 0)
                if volume <= 0:
                    continue

                cost_price = getattr(pos, 'open_price', 0.0)
                market_value = getattr(pos, 'market_value', 0.0)
                market_price = market_value / volume if volume > 0 else 0.0
                profit_loss = getattr(pos, 'profit', 0.0)
                profit_loss_ratio = profit_loss / (cost_price * volume) if cost_price * volume > 0 else 0.0

                result.append(PositionInfo(
                    stock_code=getattr(pos, 'stock_code', ''),
                    stock_name=getattr(pos, 'stock_name', '') or '',
                    volume=volume,
                    available_volume=getattr(pos, 'can_use_volume', 0),
                    frozen_volume=getattr(pos, 'frozen_volume', 0),
                    cost_price=cost_price,
                    market_price=market_price,
                    market_value=market_value,
                    profit_loss=profit_loss,
                    profit_loss_ratio=profit_loss_ratio
                ))

            return result
        except Exception as e:
            logger.error(f"查询真实持仓失败: {e}")
            raise TradingServiceException(f"查询持仓失败: {str(e)}")

    def _get_mock_positions(self) -> List[PositionInfo]:
        """获取模拟持仓信息"""
        return [
            PositionInfo(
                stock_code="000001.SZ",
                stock_name="平安银行",
                volume=10000,
                available_volume=10000,
                frozen_volume=0,
                cost_price=12.50,
                market_price=13.20,
                market_value=132000.0,
                profit_loss=7000.0,
                profit_loss_ratio=0.056
            ),
            PositionInfo(
                stock_code="000002.SZ",
                stock_name="万科A",
                volume=5000,
                available_volume=5000,
                frozen_volume=0,
                cost_price=18.80,
                market_price=19.50,
                market_value=97500.0,
                profit_loss=3500.0,
                profit_loss_ratio=0.037
            )
        ]

    # ==================== 成交查询（真实数据） ====================

    def get_trades(self, session_id: str) -> List[TradeInfo]:
        """获取成交记录（支持真实数据）"""
        if session_id not in self._connected_accounts:
            raise TradingServiceException("账户未连接")

        if self._should_use_real_data():
            return self._get_real_trades(session_id)
        else:
            return self._get_mock_trades()

    def _get_real_trades(self, session_id: str) -> List[TradeInfo]:
        """获取真实成交记录"""
        xt_trader = self._get_xt_trader(session_id)
        if not xt_trader:
            raise TradingServiceException("交易连接不存在")

        account = self._connected_accounts[session_id].get("account")
        if not account:
            raise TradingServiceException("账户对象不存在")

        try:
            trades = xt_trader.query_stock_trades(account)
            if not trades:
                return []

            result = []
            for trade in trades:
                traded_volume = getattr(trade, 'traded_volume', 0)
                traded_price = getattr(trade, 'traded_price', 0.0)

                result.append(TradeInfo(
                    trade_id=str(getattr(trade, 'traded_id', '')),
                    order_id=str(getattr(trade, 'order_id', '')),
                    stock_code=getattr(trade, 'stock_code', ''),
                    side=self._convert_order_type(getattr(trade, 'order_type', 0)),
                    volume=traded_volume,
                    price=traded_price,
                    amount=traded_volume * traded_price,
                    trade_time=datetime.now(),  # xtquant 返回的时间需要转换
                    commission=getattr(trade, 'commission', 0.0)
                ))

            return result
        except Exception as e:
            logger.error(f"查询真实成交失败: {e}")
            raise TradingServiceException(f"查询成交失败: {str(e)}")

    def _get_mock_trades(self) -> List[TradeInfo]:
        """获取模拟成交记录"""
        return [
            TradeInfo(
                trade_id="trade_001",
                order_id="order_1001",
                stock_code="000001.SZ",
                side="BUY",
                volume=1000,
                price=13.20,
                amount=13200.0,
                trade_time=datetime.now(),
                commission=13.20
            )
        ]

    # ==================== 订单查询（真实数据） ====================

    def get_orders(self, session_id: str) -> List[OrderResponse]:
        """获取订单列表（支持真实数据）"""
        if session_id not in self._connected_accounts:
            raise TradingServiceException("账户未连接")

        if self._should_use_real_data():
            return self._get_real_orders(session_id)
        else:
            return list(self._orders.values())

    def _get_real_orders(self, session_id: str) -> List[OrderResponse]:
        """获取真实订单列表"""
        xt_trader = self._get_xt_trader(session_id)
        if not xt_trader:
            raise TradingServiceException("交易连接不存在")

        account = self._connected_accounts[session_id].get("account")
        if not account:
            raise TradingServiceException("账户对象不存在")

        try:
            orders = xt_trader.query_stock_orders(account)
            if not orders:
                return []

            result = []
            for order in orders:
                result.append(OrderResponse(
                    order_id=str(getattr(order, 'order_id', '')),
                    stock_code=getattr(order, 'stock_code', ''),
                    side=self._convert_order_type(getattr(order, 'order_type', 0)),
                    order_type=self._convert_price_type(getattr(order, 'price_type', 0)),
                    volume=getattr(order, 'order_volume', 0),
                    price=getattr(order, 'price', 0.0),
                    status=self._convert_order_status(getattr(order, 'order_status', 0)),
                    submitted_time=datetime.now(),
                    filled_volume=getattr(order, 'traded_volume', 0),
                    filled_amount=getattr(order, 'traded_amount', 0.0),
                    average_price=getattr(order, 'traded_price', None)
                ))

            return result
        except Exception as e:
            logger.error(f"查询真实订单失败: {e}")
            raise TradingServiceException(f"查询订单失败: {str(e)}")

    # ==================== 同步下单/撤单 ====================

    def submit_order(self, session_id: str, request: OrderRequest) -> OrderResponse:
        """提交订单（同步）"""
        if session_id not in self._connected_accounts:
            raise TradingServiceException("账户未连接")

        try:
            if not validate_stock_code(request.stock_code):
                raise TradingServiceException(f"无效的股票代码: {request.stock_code}")

            # 检查是否允许真实交易
            if not self._should_use_real_trading():
                logger.warning(f"当前模式[{self.settings.xtquant.mode.value}]不允许真实交易，返回模拟订单")
                return self._get_mock_order_response(request)

            # 真实交易
            return self._submit_real_order(session_id, request)

        except Exception as e:
            raise TradingServiceException(f"提交订单失败: {str(e)}")

    def _submit_real_order(self, session_id: str, request: OrderRequest) -> OrderResponse:
        """提交真实订单"""
        xt_trader = self._get_xt_trader(session_id)
        if not xt_trader:
            raise TradingServiceException("交易连接不存在")

        account = self._connected_accounts[session_id].get("account")
        if not account:
            raise TradingServiceException("账户对象不存在")

        logger.info(f"真实交易模式：提交订单 {request.stock_code} {request.side.value} {request.volume}股")

        # 转换订单类型
        order_type = xtconstant.STOCK_BUY if request.side.value == "BUY" else xtconstant.STOCK_SELL
        price_type = xtconstant.FIX_PRICE if request.order_type.value == "LIMIT" else xtconstant.MARKET_PRICE

        order_id = xt_trader.order_stock(
            account,
            request.stock_code,
            order_type,
            request.volume,
            price_type,
            request.price or 0.0,
            request.strategy_name or 'default',
            ''
        )

        if not order_id or order_id < 0:
            raise TradingServiceException(f"下单失败，错误码: {order_id}")

        order_response = OrderResponse(
            order_id=str(order_id),
            stock_code=request.stock_code,
            side=request.side.value,
            order_type=request.order_type.value,
            volume=request.volume,
            price=request.price,
            status=OrderStatus.SUBMITTED.value,
            submitted_time=datetime.now()
        )

        self._orders[str(order_id)] = order_response
        return order_response

    def _get_mock_order_response(self, request: OrderRequest) -> OrderResponse:
        """生成模拟订单响应"""
        order_id = f"mock_order_{self._order_counter}"
        self._order_counter += 1

        order_response = OrderResponse(
            order_id=order_id,
            stock_code=request.stock_code,
            side=request.side.value,
            order_type=request.order_type.value,
            volume=request.volume,
            price=request.price,
            status=OrderStatus.SUBMITTED.value,
            submitted_time=datetime.now()
        )

        self._orders[order_id] = order_response
        return order_response

    def cancel_order(self, session_id: str, request: CancelOrderRequest) -> bool:
        """撤销订单（同步）"""
        if session_id not in self._connected_accounts:
            raise TradingServiceException("账户未连接")

        if not self._should_use_real_trading():
            logger.warning(f"当前模式[{self.settings.xtquant.mode.value}]不允许真实交易，撤单请求已拦截")
            if request.order_id in self._orders:
                self._orders[request.order_id].status = OrderStatus.CANCELLED.value
            return True

        return self._cancel_real_order(session_id, request)

    def _cancel_real_order(self, session_id: str, request: CancelOrderRequest) -> bool:
        """真实撤单"""
        xt_trader = self._get_xt_trader(session_id)
        if not xt_trader:
            raise TradingServiceException("交易连接不存在")

        account = self._connected_accounts[session_id].get("account")
        if not account:
            raise TradingServiceException("账户对象不存在")

        try:
            logger.info(f"真实交易模式：撤销订单 {request.order_id}")
            result = xt_trader.cancel_order_stock(account, int(request.order_id))

            if result == 0:
                if request.order_id in self._orders:
                    self._orders[request.order_id].status = OrderStatus.CANCELLED.value
                return True
            else:
                raise TradingServiceException(f"撤单失败，错误码: {result}")

        except Exception as e:
            raise TradingServiceException(f"撤销订单失败: {str(e)}")

    # ==================== 异步下单/撤单 ====================

    def submit_order_async(self, session_id: str, request: AsyncOrderRequest) -> AsyncOrderResponse:
        """异步下单"""
        if session_id not in self._connected_accounts:
            raise TradingServiceException("账户未连接")

        if not validate_stock_code(request.stock_code):
            raise TradingServiceException(f"无效的股票代码: {request.stock_code}")

        if not self._should_use_real_trading():
            logger.warning(f"当前模式不允许真实交易，返回模拟异步下单响应")
            return AsyncOrderResponse(
                success=True,
                message="异步下单已提交（Mock模式）",
                seq=self._get_next_seq(),
                stock_code=request.stock_code,
                side=request.side.value,
                volume=request.volume,
                price=request.price
            )

        return self._submit_real_order_async(session_id, request)

    def _submit_real_order_async(self, session_id: str, request: AsyncOrderRequest) -> AsyncOrderResponse:
        """真实异步下单"""
        xt_trader = self._get_xt_trader(session_id)
        if not xt_trader:
            raise TradingServiceException("交易连接不存在")

        account = self._connected_accounts[session_id].get("account")
        if not account:
            raise TradingServiceException("账户对象不存在")

        try:
            seq = self._get_next_seq()

            # 转换订单类型
            order_type = xtconstant.STOCK_BUY if request.side.value == "BUY" else xtconstant.STOCK_SELL
            price_type = xtconstant.FIX_PRICE if request.order_type.value == "LIMIT" else xtconstant.MARKET_PRICE

            logger.info(f"异步下单: {request.stock_code} {request.side.value} {request.volume}股, seq={seq}")

            result = xt_trader.order_stock_async(
                account,
                request.stock_code,
                order_type,
                request.volume,
                price_type,
                request.price or 0.0,
                request.strategy_name or 'default',
                ''
            )

            if result < 0:
                raise TradingServiceException(f"异步下单失败，错误码: {result}")

            return AsyncOrderResponse(
                success=True,
                message="异步下单已提交",
                seq=seq,
                stock_code=request.stock_code,
                side=request.side.value,
                volume=request.volume,
                price=request.price
            )

        except Exception as e:
            logger.error(f"异步下单失败: {e}")
            raise TradingServiceException(f"异步下单失败: {str(e)}")

    def cancel_order_async(self, session_id: str, request: AsyncCancelRequest) -> AsyncCancelResponse:
        """异步撤单"""
        if session_id not in self._connected_accounts:
            raise TradingServiceException("账户未连接")

        if not request.order_id and not request.order_sysid:
            raise TradingServiceException("order_id 和 order_sysid 至少需要提供一个")

        if not self._should_use_real_trading():
            logger.warning(f"当前模式不允许真实交易，返回模拟异步撤单响应")
            return AsyncCancelResponse(
                success=True,
                message="异步撤单已提交（Mock模式）",
                seq=self._get_next_seq(),
                order_id=request.order_id
            )

        return self._cancel_real_order_async(session_id, request)

    def _cancel_real_order_async(self, session_id: str, request: AsyncCancelRequest) -> AsyncCancelResponse:
        """真实异步撤单"""
        xt_trader = self._get_xt_trader(session_id)
        if not xt_trader:
            raise TradingServiceException("交易连接不存在")

        account = self._connected_accounts[session_id].get("account")
        if not account:
            raise TradingServiceException("账户对象不存在")

        try:
            seq = self._get_next_seq()
            logger.info(f"异步撤单: order_id={request.order_id}, order_sysid={request.order_sysid}, seq={seq}")

            if request.order_sysid:
                # 使用柜台合同编号撤单
                result = xt_trader.cancel_order_stock_sysid_async(account, request.order_sysid)
            else:
                # 使用订单ID撤单
                result = xt_trader.cancel_order_stock_async(account, int(request.order_id))

            if result < 0:
                raise TradingServiceException(f"异步撤单失败，错误码: {result}")

            return AsyncCancelResponse(
                success=True,
                message="异步撤单已提交",
                seq=seq,
                order_id=request.order_id
            )

        except Exception as e:
            logger.error(f"异步撤单失败: {e}")
            raise TradingServiceException(f"异步撤单失败: {str(e)}")

    # ==================== 其他接口 ====================

    def get_risk_info(self, session_id: str) -> RiskInfo:
        """获取风险信息"""
        if session_id not in self._connected_accounts:
            raise TradingServiceException("账户未连接")

        try:
            # 获取资产和持仓计算风险指标
            asset = self.get_asset_info(session_id)
            total = asset.total_asset if asset.total_asset > 0 else 1

            return RiskInfo(
                position_ratio=asset.market_value / total,
                cash_ratio=asset.cash / total,
                max_drawdown=0.05,
                var_95=0.02,
                var_99=0.03
            )
        except Exception as e:
            raise TradingServiceException(f"获取风险信息失败: {str(e)}")

    def get_strategies(self, session_id: str) -> List[StrategyInfo]:
        """获取策略列表"""
        if session_id not in self._connected_accounts:
            raise TradingServiceException("账户未连接")

        return [
            StrategyInfo(
                strategy_name="MA策略",
                strategy_type="TREND_FOLLOWING",
                status="RUNNING",
                created_time=datetime.now(),
                last_update_time=datetime.now(),
                parameters={"period": 20, "threshold": 0.02}
            ),
            StrategyInfo(
                strategy_name="均值回归策略",
                strategy_type="MEAN_REVERSION",
                status="STOPPED",
                created_time=datetime.now(),
                last_update_time=datetime.now(),
                parameters={"lookback": 10, "entry_threshold": 0.05}
            )
        ]

    def is_connected(self, session_id: str) -> bool:
        """检查账户是否连接"""
        return session_id in self._connected_accounts

    # ==================== 辅助方法 ====================

    def _convert_order_type(self, order_type: int) -> str:
        """转换订单类型"""
        if XTQUANT_AVAILABLE:
            if order_type == xtconstant.STOCK_BUY:
                return "BUY"
            elif order_type == xtconstant.STOCK_SELL:
                return "SELL"
        return "UNKNOWN"

    def _convert_price_type(self, price_type: int) -> str:
        """转换价格类型"""
        if XTQUANT_AVAILABLE:
            if price_type == xtconstant.FIX_PRICE:
                return "LIMIT"
            elif price_type == xtconstant.MARKET_PRICE:
                return "MARKET"
        return "LIMIT"

    def _convert_order_status(self, status: int) -> str:
        """转换订单状态"""
        status_map = {
            48: OrderStatus.PENDING.value,      # 未报
            49: OrderStatus.SUBMITTED.value,    # 待报
            50: OrderStatus.SUBMITTED.value,    # 已报
            51: OrderStatus.SUBMITTED.value,    # 已报待撤
            52: OrderStatus.PARTIAL_FILLED.value,  # 部成待撤
            53: OrderStatus.PARTIAL_FILLED.value,  # 部撤
            54: OrderStatus.CANCELLED.value,    # 已撤
            55: OrderStatus.PARTIAL_FILLED.value,  # 部成
            56: OrderStatus.FILLED.value,       # 已成
            57: OrderStatus.REJECTED.value,     # 废单
        }
        return status_map.get(status, OrderStatus.PENDING.value)
