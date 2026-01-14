"""
交易回调管理器

负责：
1. 管理 XtQuantTraderCallback，接收 xtquant 的交易回调
2. 管理 WebSocket 客户端连接
3. 将交易回调推送到所有订阅的 WebSocket 客户端
"""
import asyncio
import threading
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

from app.config import Settings, XTQuantMode
from app.models.trading_models import (
    AssetCallback,
    OrderCallback,
    PositionCallback,
    TradeCallback,
    TradingCallback,
    TradingCallbackType,
)
from app.utils.logger import logger

# 尝试导入 xtquant
try:
    from xtquant import xttrader
    from xtquant.xttrader import XtQuantTrader, XtQuantTraderCallback
    XTQUANT_AVAILABLE = True
except ImportError:
    XTQUANT_AVAILABLE = False
    XtQuantTraderCallback = object  # 使用空基类


class TradingCallbackHandler(XtQuantTraderCallback if XTQUANT_AVAILABLE else object):
    """
    交易回调处理器

    继承 XtQuantTraderCallback，接收 xtquant 的所有交易回调事件
    """

    def __init__(self, manager: "TradingCallbackManager"):
        if XTQUANT_AVAILABLE:
            super().__init__()
        self._manager = manager

    def on_connected(self):
        """连接成功推送"""
        logger.info("xttrader 连接成功")
        self._manager._dispatch_callback(
            TradingCallbackType.CONNECTED,
            account_id="",
            data={"status": "connected"}
        )

    def on_disconnected(self):
        """连接断开推送"""
        logger.warning("xttrader 连接断开")
        self._manager._dispatch_callback(
            TradingCallbackType.DISCONNECTED,
            account_id="",
            data={"status": "disconnected"}
        )

    def on_account_status(self, status):
        """账号状态推送"""
        logger.info(f"账号状态变更: {status}")
        self._manager._dispatch_callback(
            TradingCallbackType.ACCOUNT_STATUS,
            account_id=getattr(status, 'account_id', ''),
            data=self._convert_to_dict(status)
        )

    def on_stock_asset(self, asset):
        """资金变动推送"""
        logger.debug(f"资金变动: {asset}")
        account_id = getattr(asset, 'account_id', '')
        self._manager._dispatch_callback(
            TradingCallbackType.ASSET,
            account_id=account_id,
            data=AssetCallback(
                account_id=account_id,
                total_asset=getattr(asset, 'total_asset', 0.0),
                market_value=getattr(asset, 'market_value', 0.0),
                cash=getattr(asset, 'cash', 0.0),
                frozen_cash=getattr(asset, 'frozen_cash', 0.0),
                available_cash=getattr(asset, 'available_cash', 0.0)
            ).model_dump()
        )

    def on_stock_order(self, order):
        """委托回报推送"""
        logger.info(f"委托回报: {order}")
        account_id = getattr(order, 'account_id', '')
        self._manager._dispatch_callback(
            TradingCallbackType.ORDER,
            account_id=account_id,
            data=OrderCallback(
                account_id=account_id,
                order_id=str(getattr(order, 'order_id', '')),
                order_sysid=getattr(order, 'order_sysid', None),
                stock_code=getattr(order, 'stock_code', ''),
                stock_name=getattr(order, 'stock_name', None),
                side=str(getattr(order, 'order_type', '')),
                order_type=str(getattr(order, 'price_type', '')),
                volume=getattr(order, 'order_volume', 0),
                price=getattr(order, 'price', 0.0),
                status=str(getattr(order, 'order_status', '')),
                status_msg=getattr(order, 'order_status_msg', None),
                filled_volume=getattr(order, 'traded_volume', 0),
                filled_amount=getattr(order, 'traded_amount', 0.0),
                order_time=None
            ).model_dump()
        )

    def on_stock_trade(self, trade):
        """成交回报推送"""
        logger.info(f"成交回报: {trade}")
        account_id = getattr(trade, 'account_id', '')
        self._manager._dispatch_callback(
            TradingCallbackType.TRADE,
            account_id=account_id,
            data=TradeCallback(
                account_id=account_id,
                trade_id=str(getattr(trade, 'traded_id', '')),
                order_id=str(getattr(trade, 'order_id', '')),
                order_sysid=getattr(trade, 'order_sysid', None),
                stock_code=getattr(trade, 'stock_code', ''),
                stock_name=getattr(trade, 'stock_name', None),
                side=str(getattr(trade, 'order_type', '')),
                volume=getattr(trade, 'traded_volume', 0),
                price=getattr(trade, 'traded_price', 0.0),
                amount=getattr(trade, 'traded_amount', 0.0),
                trade_time=datetime.now(),
                commission=getattr(trade, 'commission', 0.0)
            ).model_dump()
        )

    def on_stock_position(self, position):
        """持仓变动推送"""
        logger.debug(f"持仓变动: {position}")
        account_id = getattr(position, 'account_id', '')
        self._manager._dispatch_callback(
            TradingCallbackType.POSITION,
            account_id=account_id,
            data=PositionCallback(
                account_id=account_id,
                stock_code=getattr(position, 'stock_code', ''),
                stock_name=getattr(position, 'stock_name', None),
                volume=getattr(position, 'volume', 0),
                available_volume=getattr(position, 'can_use_volume', 0),
                frozen_volume=getattr(position, 'frozen_volume', 0),
                cost_price=getattr(position, 'open_price', 0.0),
                market_price=getattr(position, 'market_value', 0.0) / max(getattr(position, 'volume', 1), 1),
                market_value=getattr(position, 'market_value', 0.0),
                profit_loss=getattr(position, 'profit', 0.0)
            ).model_dump()
        )

    def on_order_error(self, order_error):
        """委托失败推送"""
        logger.error(f"委托失败: {order_error}")
        self._manager._dispatch_callback(
            TradingCallbackType.ORDER_ERROR,
            account_id=getattr(order_error, 'account_id', ''),
            data=self._convert_to_dict(order_error)
        )

    def on_cancel_error(self, cancel_error):
        """撤单失败推送"""
        logger.error(f"撤单失败: {cancel_error}")
        self._manager._dispatch_callback(
            TradingCallbackType.CANCEL_ERROR,
            account_id=getattr(cancel_error, 'account_id', ''),
            data=self._convert_to_dict(cancel_error)
        )

    def on_order_stock_async_response(self, response):
        """异步下单回报推送"""
        logger.info(f"异步下单回报: {response}")
        self._manager._dispatch_callback(
            TradingCallbackType.ASYNC_ORDER,
            account_id=getattr(response, 'account_id', ''),
            data=self._convert_to_dict(response),
            seq=getattr(response, 'seq', None)
        )

    def on_cancel_order_stock_async_response(self, response):
        """异步撤单回报推送"""
        logger.info(f"异步撤单回报: {response}")
        self._manager._dispatch_callback(
            TradingCallbackType.ASYNC_CANCEL,
            account_id=getattr(response, 'account_id', ''),
            data=self._convert_to_dict(response),
            seq=getattr(response, 'seq', None)
        )

    def _convert_to_dict(self, obj) -> Dict[str, Any]:
        """将 xtquant 对象转换为字典"""
        if obj is None:
            return {}
        if isinstance(obj, dict):
            return obj
        # 尝试获取所有属性
        result = {}
        for attr in dir(obj):
            if not attr.startswith('_'):
                try:
                    value = getattr(obj, attr)
                    if not callable(value):
                        # 处理日期时间
                        if isinstance(value, datetime):
                            result[attr] = value.isoformat()
                        else:
                            result[attr] = value
                except Exception:
                    pass
        return result


class TradingCallbackManager:
    """
    交易回调管理器

    管理交易回调的接收和分发
    """

    _instance: Optional["TradingCallbackManager"] = None
    _lock = threading.Lock()

    def __new__(cls, settings: Settings = None):
        """单例模式"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, settings: Settings = None):
        if self._initialized:
            return

        self.settings = settings
        self._callback_handler: Optional[TradingCallbackHandler] = None
        self._xt_trader: Optional["XtQuantTrader"] = None
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None

        # WebSocket 客户端管理
        # account_id -> Set[asyncio.Queue]
        self._ws_queues: Dict[str, Set[asyncio.Queue]] = {}
        self._ws_lock = threading.Lock()

        # 全局订阅者（接收所有账户的回调）
        self._global_queues: Set[asyncio.Queue] = set()

        # 回调历史（用于新连接时发送最近的回调）
        self._callback_history: List[TradingCallback] = []
        self._max_history = 100

        self._initialized = True
        logger.info("交易回调管理器已初始化")

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        """设置事件循环（在 FastAPI lifespan 中调用）"""
        self._event_loop = loop
        logger.info("交易回调管理器事件循环已设置")

    def start(self, xt_trader: "XtQuantTrader" = None):
        """
        启动回调管理器

        Args:
            xt_trader: XtQuantTrader 实例，如果为 None 则创建新实例
        """
        if not XTQUANT_AVAILABLE:
            logger.warning("xtquant 不可用，交易回调功能禁用")
            return

        if self.settings and self.settings.xtquant.mode == XTQuantMode.MOCK:
            logger.info("Mock 模式，跳过交易回调初始化")
            return

        try:
            # 创建回调处理器
            self._callback_handler = TradingCallbackHandler(self)

            # 注册回调
            if xt_trader:
                self._xt_trader = xt_trader
                xt_trader.register_callback(self._callback_handler)
                logger.info("已注册交易回调处理器")

        except Exception as e:
            logger.error(f"启动交易回调管理器失败: {e}")

    def stop(self):
        """停止回调管理器"""
        # 清空所有队列
        with self._ws_lock:
            self._ws_queues.clear()
            self._global_queues.clear()

        self._xt_trader = None
        self._callback_handler = None
        logger.info("交易回调管理器已停止")

    def subscribe(self, account_id: str = None) -> asyncio.Queue:
        """
        订阅交易回调

        Args:
            account_id: 账户ID，如果为 None 则订阅所有账户的回调

        Returns:
            asyncio.Queue: 用于接收回调的队列
        """
        queue = asyncio.Queue(maxsize=1000)

        with self._ws_lock:
            if account_id:
                if account_id not in self._ws_queues:
                    self._ws_queues[account_id] = set()
                self._ws_queues[account_id].add(queue)
                logger.info(f"新订阅: account_id={account_id}")
            else:
                self._global_queues.add(queue)
                logger.info("新全局订阅")

        return queue

    def unsubscribe(self, queue: asyncio.Queue, account_id: str = None):
        """
        取消订阅

        Args:
            queue: 要取消的队列
            account_id: 账户ID
        """
        with self._ws_lock:
            if account_id and account_id in self._ws_queues:
                self._ws_queues[account_id].discard(queue)
                if not self._ws_queues[account_id]:
                    del self._ws_queues[account_id]
            else:
                self._global_queues.discard(queue)

        logger.info(f"取消订阅: account_id={account_id}")

    def _dispatch_callback(
        self,
        callback_type: TradingCallbackType,
        account_id: str,
        data: Dict[str, Any],
        seq: int = None
    ):
        """
        分发回调到所有订阅者

        在 xtquant 回调线程中调用，需要线程安全地将消息放入队列
        """
        callback = TradingCallback(
            callback_type=callback_type,
            account_id=account_id,
            timestamp=datetime.now(),
            data=data,
            seq=seq
        )

        # 保存到历史
        self._callback_history.append(callback)
        if len(self._callback_history) > self._max_history:
            self._callback_history = self._callback_history[-self._max_history:]

        # 分发到订阅者
        callback_dict = callback.model_dump()
        # 转换 datetime 为 ISO 格式字符串
        callback_dict['timestamp'] = callback.timestamp.isoformat()
        callback_dict['callback_type'] = callback_type.value

        with self._ws_lock:
            # 分发到账户特定订阅者
            if account_id and account_id in self._ws_queues:
                for queue in self._ws_queues[account_id]:
                    self._put_to_queue(queue, callback_dict)

            # 分发到全局订阅者
            for queue in self._global_queues:
                self._put_to_queue(queue, callback_dict)

    def _put_to_queue(self, queue: asyncio.Queue, data: Dict[str, Any]):
        """线程安全地将数据放入队列"""
        if self._event_loop and not self._event_loop.is_closed():
            try:
                asyncio.run_coroutine_threadsafe(
                    self._async_put(queue, data),
                    self._event_loop
                )
            except Exception as e:
                logger.error(f"放入队列失败: {e}")

    async def _async_put(self, queue: asyncio.Queue, data: Dict[str, Any]):
        """异步放入队列"""
        try:
            queue.put_nowait(data)
        except asyncio.QueueFull:
            # 队列满时丢弃旧数据
            try:
                queue.get_nowait()
                queue.put_nowait(data)
            except Exception:
                pass

    async def stream_callbacks(
        self,
        account_id: str = None
    ):
        """
        流式获取交易回调

        Args:
            account_id: 账户ID，如果为 None 则获取所有账户的回调

        Yields:
            Dict: 回调数据
        """
        queue = self.subscribe(account_id)

        try:
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield data
                except asyncio.TimeoutError:
                    # 发送心跳
                    yield {
                        "callback_type": "heartbeat",
                        "timestamp": datetime.now().isoformat()
                    }
        finally:
            self.unsubscribe(queue, account_id)

    def get_recent_callbacks(self, account_id: str = None, limit: int = 20) -> List[Dict]:
        """
        获取最近的回调历史

        Args:
            account_id: 账户ID过滤
            limit: 返回数量限制

        Returns:
            最近的回调列表
        """
        callbacks = self._callback_history

        if account_id:
            callbacks = [c for c in callbacks if c.account_id == account_id]

        result = []
        for c in callbacks[-limit:]:
            d = c.model_dump()
            d['timestamp'] = c.timestamp.isoformat()
            d['callback_type'] = c.callback_type.value
            result.append(d)

        return result

    # ==================== Mock 模式支持 ====================

    def mock_callback(
        self,
        callback_type: TradingCallbackType,
        account_id: str,
        data: Dict[str, Any],
        seq: int = None
    ):
        """
        发送模拟回调（用于测试和 Mock 模式）
        """
        self._dispatch_callback(callback_type, account_id, data, seq)


# 全局单例获取函数
_trading_callback_manager: Optional[TradingCallbackManager] = None


def get_trading_callback_manager(settings: Settings = None) -> TradingCallbackManager:
    """获取交易回调管理器单例"""
    global _trading_callback_manager
    if _trading_callback_manager is None:
        _trading_callback_manager = TradingCallbackManager(settings)
    return _trading_callback_manager
