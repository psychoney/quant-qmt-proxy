"""
gRPC 交易服务实现
"""
from datetime import datetime
from typing import Iterator

import grpc

from app.models.trading_models import AccountType as RestAccountType
from app.models.trading_models import AsyncCancelRequest as RestAsyncCancelRequest
from app.models.trading_models import AsyncOrderRequest as RestAsyncOrderRequest
from app.models.trading_models import CancelOrderRequest as RestCancelOrderRequest
from app.models.trading_models import ConnectRequest as RestConnectRequest
from app.models.trading_models import OrderRequest as RestOrderRequest
from app.models.trading_models import OrderSide as RestOrderSide
from app.models.trading_models import OrderType as RestOrderType

# 导入现有服务
from app.services.trading_service import TradingService
from app.services.trading_callback_manager import get_trading_callback_manager
from app.utils.exceptions import TradingServiceException
from app.utils.logger import logger

# 导入生成的 protobuf 代码
from generated import common_pb2, trading_pb2, trading_pb2_grpc


class TradingGrpcService(trading_pb2_grpc.TradingServiceServicer):
    """gRPC 交易服务实现"""
    
    def __init__(self, trading_service: TradingService):
        self.trading_service = trading_service
    
    def Connect(
        self, 
        request: trading_pb2.ConnectRequest, 
        context: grpc.ServicerContext
    ) -> trading_pb2.ConnectResponse:
        """连接账户"""
        try:
            # 转换请求
            rest_request = RestConnectRequest(
                account_id=request.account_id,
                password=request.password if request.password else None,
                client_id=request.client_id if request.client_id else None
            )
            
            # 调用服务
            result = self.trading_service.connect_account(rest_request)
            
            # 转换响应
            account_info = None
            if result.account_info:
                account_info = self._convert_account_info(result.account_info)
            
            return trading_pb2.ConnectResponse(
                success=result.success,
                message=result.message,
                session_id=result.session_id or "",
                account_info=account_info,
                status=common_pb2.Status(code=0 if result.success else 400, message=result.message)
            )
            
        except TradingServiceException as e:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return trading_pb2.ConnectResponse(
                success=False,
                message=str(e),
                status=common_pb2.Status(code=400, message=str(e))
            )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return trading_pb2.ConnectResponse(
                success=False,
                message=str(e),
                status=common_pb2.Status(code=500, message=str(e))
            )
    
    def Disconnect(
        self, 
        request: trading_pb2.DisconnectRequest, 
        context: grpc.ServicerContext
    ) -> trading_pb2.DisconnectResponse:
        """断开账户"""
        try:
            # 调用服务
            success = self.trading_service.disconnect_account(request.session_id)
            
            return trading_pb2.DisconnectResponse(
                success=success,
                message="断开账户成功" if success else "断开账户失败",
                status=common_pb2.Status(code=0 if success else 400, message="success" if success else "failed")
            )
            
        except TradingServiceException as e:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return trading_pb2.DisconnectResponse(
                success=False,
                message=str(e),
                status=common_pb2.Status(code=400, message=str(e))
            )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return trading_pb2.DisconnectResponse(
                success=False,
                message=str(e),
                status=common_pb2.Status(code=500, message=str(e))
            )
    
    def GetAccountInfo(
        self, 
        request: trading_pb2.DisconnectRequest, 
        context: grpc.ServicerContext
    ) -> trading_pb2.ConnectResponse:
        """获取账户信息"""
        try:
            # 调用服务
            result = self.trading_service.get_account_info(request.session_id)
            
            # 转换响应
            account_info = self._convert_account_info(result)
            
            return trading_pb2.ConnectResponse(
                success=True,
                message="获取账户信息成功",
                session_id=request.session_id,
                account_info=account_info,
                status=common_pb2.Status(code=0, message="success")
            )
            
        except TradingServiceException as e:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return trading_pb2.ConnectResponse(
                success=False,
                message=str(e),
                status=common_pb2.Status(code=400, message=str(e))
            )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return trading_pb2.ConnectResponse(
                success=False,
                message=str(e),
                status=common_pb2.Status(code=500, message=str(e))
            )
    
    def GetPositions(
        self, 
        request: trading_pb2.PositionRequest, 
        context: grpc.ServicerContext
    ) -> trading_pb2.PositionListResponse:
        """获取持仓列表"""
        try:
            # 调用服务
            results = self.trading_service.get_positions(request.session_id)
            
            # 转换响应
            positions = []
            for result in results:
                position = trading_pb2.PositionInfo(
                    stock_code=result.stock_code,
                    stock_name=result.stock_name,
                    volume=result.volume,
                    available_volume=result.available_volume,
                    frozen_volume=result.frozen_volume,
                    cost_price=result.cost_price,
                    market_price=result.market_price,
                    market_value=result.market_value,
                    profit_loss=result.profit_loss,
                    profit_loss_ratio=result.profit_loss_ratio
                )
                positions.append(position)
            
            return trading_pb2.PositionListResponse(
                positions=positions,
                status=common_pb2.Status(code=0, message="success")
            )
            
        except TradingServiceException as e:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return trading_pb2.PositionListResponse(
                status=common_pb2.Status(code=400, message=str(e))
            )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return trading_pb2.PositionListResponse(
                status=common_pb2.Status(code=500, message=str(e))
            )
    
    def SubmitOrder(
        self, 
        request: trading_pb2.OrderRequest, 
        context: grpc.ServicerContext
    ) -> trading_pb2.OrderResponse:
        """提交订单"""
        try:
            # 转换请求
            rest_request = self._convert_order_request(request)
            
            # 调用服务
            result = self.trading_service.submit_order(request.session_id, rest_request)
            
            # 转换响应
            order_info = self._convert_order_info(result)
            
            return trading_pb2.OrderResponse(
                order=order_info,
                status=common_pb2.Status(code=0, message="success")
            )
            
        except TradingServiceException as e:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return trading_pb2.OrderResponse(
                status=common_pb2.Status(code=400, message=str(e))
            )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return trading_pb2.OrderResponse(
                status=common_pb2.Status(code=500, message=str(e))
            )
    
    def CancelOrder(
        self, 
        request: trading_pb2.CancelOrderRequest, 
        context: grpc.ServicerContext
    ) -> trading_pb2.CancelOrderResponse:
        """撤销订单"""
        try:
            # 转换请求
            rest_request = RestCancelOrderRequest(order_id=request.order_id)
            
            # 调用服务
            success = self.trading_service.cancel_order(request.session_id, rest_request)
            
            return trading_pb2.CancelOrderResponse(
                success=success,
                message="撤销订单成功" if success else "撤销订单失败",
                status=common_pb2.Status(code=0 if success else 400, message="success" if success else "failed")
            )
            
        except TradingServiceException as e:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return trading_pb2.CancelOrderResponse(
                success=False,
                message=str(e),
                status=common_pb2.Status(code=400, message=str(e))
            )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return trading_pb2.CancelOrderResponse(
                success=False,
                message=str(e),
                status=common_pb2.Status(code=500, message=str(e))
            )
    
    def GetOrders(
        self, 
        request: trading_pb2.OrderListRequest, 
        context: grpc.ServicerContext
    ) -> trading_pb2.OrderListResponse:
        """获取订单列表"""
        try:
            # 调用服务
            results = self.trading_service.get_orders(request.session_id)
            
            # 转换响应
            orders = []
            for result in results:
                order_info = self._convert_order_info(result)
                orders.append(order_info)
            
            return trading_pb2.OrderListResponse(
                orders=orders,
                status=common_pb2.Status(code=0, message="success")
            )
            
        except TradingServiceException as e:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return trading_pb2.OrderListResponse(
                status=common_pb2.Status(code=400, message=str(e))
            )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return trading_pb2.OrderListResponse(
                status=common_pb2.Status(code=500, message=str(e))
            )
    
    def GetTrades(
        self, 
        request: trading_pb2.TradeListRequest, 
        context: grpc.ServicerContext
    ) -> trading_pb2.TradeListResponse:
        """获取成交记录"""
        try:
            # 调用服务
            results = self.trading_service.get_trades(request.session_id)
            
            # 转换响应
            trades = []
            for result in results:
                side_map = {
                    "BUY": trading_pb2.ORDER_SIDE_BUY,
                    "SELL": trading_pb2.ORDER_SIDE_SELL
                }
                
                trade = trading_pb2.TradeInfo(
                    trade_id=result.trade_id,
                    order_id=result.order_id,
                    stock_code=result.stock_code,
                    side=side_map.get(result.side, trading_pb2.ORDER_SIDE_UNSPECIFIED),
                    volume=result.volume,
                    price=result.price,
                    amount=result.amount,
                    trade_time=result.trade_time.isoformat() if isinstance(result.trade_time, datetime) else str(result.trade_time),
                    commission=result.commission
                )
                trades.append(trade)
            
            return trading_pb2.TradeListResponse(
                trades=trades,
                status=common_pb2.Status(code=0, message="success")
            )
            
        except TradingServiceException as e:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return trading_pb2.TradeListResponse(
                status=common_pb2.Status(code=400, message=str(e))
            )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return trading_pb2.TradeListResponse(
                status=common_pb2.Status(code=500, message=str(e))
            )
    
    def GetAsset(
        self, 
        request: trading_pb2.AssetRequest, 
        context: grpc.ServicerContext
    ) -> trading_pb2.AssetResponse:
        """获取资产信息"""
        try:
            # 调用服务
            result = self.trading_service.get_asset_info(request.session_id)
            
            # 转换响应
            asset = trading_pb2.AssetInfo(
                total_asset=result.total_asset,
                market_value=result.market_value,
                cash=result.cash,
                frozen_cash=result.frozen_cash,
                available_cash=result.available_cash,
                profit_loss=result.profit_loss,
                profit_loss_ratio=result.profit_loss_ratio
            )
            
            return trading_pb2.AssetResponse(
                asset=asset,
                status=common_pb2.Status(code=0, message="success")
            )
            
        except TradingServiceException as e:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return trading_pb2.AssetResponse(
                status=common_pb2.Status(code=400, message=str(e))
            )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return trading_pb2.AssetResponse(
                status=common_pb2.Status(code=500, message=str(e))
            )
    
    def GetRiskInfo(
        self, 
        request: trading_pb2.RiskInfoRequest, 
        context: grpc.ServicerContext
    ) -> trading_pb2.RiskInfoResponse:
        """获取风险信息"""
        try:
            # 调用服务
            result = self.trading_service.get_risk_info(request.session_id)
            
            return trading_pb2.RiskInfoResponse(
                position_ratio=result.position_ratio,
                cash_ratio=result.cash_ratio,
                max_drawdown=result.max_drawdown,
                var_95=result.var_95,
                var_99=result.var_99,
                status=common_pb2.Status(code=0, message="success")
            )
            
        except TradingServiceException as e:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return trading_pb2.RiskInfoResponse(
                status=common_pb2.Status(code=400, message=str(e))
            )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return trading_pb2.RiskInfoResponse(
                status=common_pb2.Status(code=500, message=str(e))
            )
    
    def GetStrategies(
        self, 
        request: trading_pb2.StrategyListRequest, 
        context: grpc.ServicerContext
    ) -> trading_pb2.StrategyListResponse:
        """获取策略列表"""
        try:
            # 调用服务
            results = self.trading_service.get_strategies(request.session_id)
            
            # 转换响应
            strategies = []
            for result in results:
                # 将parameters字典转换为map<string, string>
                parameters = {k: str(v) for k, v in result.parameters.items()}
                
                strategy = trading_pb2.StrategyInfo(
                    strategy_name=result.strategy_name,
                    strategy_type=result.strategy_type,
                    status=result.status,
                    created_time=result.created_time.isoformat() if isinstance(result.created_time, datetime) else str(result.created_time),
                    last_update_time=result.last_update_time.isoformat() if isinstance(result.last_update_time, datetime) else str(result.last_update_time),
                    parameters=parameters
                )
                strategies.append(strategy)
            
            return trading_pb2.StrategyListResponse(
                strategies=strategies,
                status=common_pb2.Status(code=0, message="success")
            )
            
        except TradingServiceException as e:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return trading_pb2.StrategyListResponse(
                status=common_pb2.Status(code=400, message=str(e))
            )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return trading_pb2.StrategyListResponse(
                status=common_pb2.Status(code=500, message=str(e))
            )
    
    # 辅助转换方法
    
    def _convert_account_info(self, account_info):
        """转换账户信息"""
        account_type_map = {
            RestAccountType.FUTURE: trading_pb2.ACCOUNT_TYPE_FUTURE,
            RestAccountType.SECURITY: trading_pb2.ACCOUNT_TYPE_SECURITY,
            RestAccountType.CREDIT: trading_pb2.ACCOUNT_TYPE_CREDIT,
            RestAccountType.FUTURE_OPTION: trading_pb2.ACCOUNT_TYPE_FUTURE_OPTION,
            RestAccountType.STOCK_OPTION: trading_pb2.ACCOUNT_TYPE_STOCK_OPTION
        }
        
        return trading_pb2.AccountInfo(
            account_id=account_info.account_id,
            account_type=account_type_map.get(account_info.account_type, trading_pb2.ACCOUNT_TYPE_UNSPECIFIED),
            account_name=account_info.account_name,
            status=account_info.status,
            balance=account_info.balance,
            available_balance=account_info.available_balance,
            frozen_balance=account_info.frozen_balance,
            market_value=account_info.market_value,
            total_asset=account_info.total_asset
        )
    
    def _convert_order_request(self, pb_request: trading_pb2.OrderRequest) -> RestOrderRequest:
        """转换订单请求"""
        side_map = {
            trading_pb2.ORDER_SIDE_BUY: RestOrderSide.BUY,
            trading_pb2.ORDER_SIDE_SELL: RestOrderSide.SELL
        }
        
        type_map = {
            trading_pb2.ORDER_TYPE_MARKET: RestOrderType.MARKET,
            trading_pb2.ORDER_TYPE_LIMIT: RestOrderType.LIMIT,
            trading_pb2.ORDER_TYPE_STOP: RestOrderType.STOP,
            trading_pb2.ORDER_TYPE_STOP_LIMIT: RestOrderType.STOP_LIMIT
        }
        
        return RestOrderRequest(
            stock_code=pb_request.stock_code,
            side=side_map.get(pb_request.side, RestOrderSide.BUY),
            order_type=type_map.get(pb_request.order_type, RestOrderType.LIMIT),
            volume=int(pb_request.volume),
            price=pb_request.price if pb_request.price else None,
            strategy_name=pb_request.strategy_name if pb_request.strategy_name else None
        )
    
    def _convert_order_info(self, order_response):
        """转换订单信息"""
        side_map = {
            "BUY": trading_pb2.ORDER_SIDE_BUY,
            "SELL": trading_pb2.ORDER_SIDE_SELL
        }
        
        type_map = {
            "MARKET": trading_pb2.ORDER_TYPE_MARKET,
            "LIMIT": trading_pb2.ORDER_TYPE_LIMIT,
            "STOP": trading_pb2.ORDER_TYPE_STOP,
            "STOP_LIMIT": trading_pb2.ORDER_TYPE_STOP_LIMIT
        }
        
        status_map = {
            "PENDING": trading_pb2.ORDER_STATUS_PENDING,
            "SUBMITTED": trading_pb2.ORDER_STATUS_SUBMITTED,
            "PARTIAL_FILLED": trading_pb2.ORDER_STATUS_PARTIAL_FILLED,
            "FILLED": trading_pb2.ORDER_STATUS_FILLED,
            "CANCELLED": trading_pb2.ORDER_STATUS_CANCELLED,
            "REJECTED": trading_pb2.ORDER_STATUS_REJECTED
        }
        
        return trading_pb2.OrderInfo(
            order_id=order_response.order_id,
            stock_code=order_response.stock_code,
            side=side_map.get(order_response.side, trading_pb2.ORDER_SIDE_UNSPECIFIED),
            order_type=type_map.get(order_response.order_type, trading_pb2.ORDER_TYPE_UNSPECIFIED),
            volume=order_response.volume,
            price=order_response.price if order_response.price else 0.0,
            status=status_map.get(order_response.status, trading_pb2.ORDER_STATUS_UNSPECIFIED),
            submitted_time=order_response.submitted_time.isoformat() if isinstance(order_response.submitted_time, datetime) else str(order_response.submitted_time),
            filled_volume=order_response.filled_volume,
            filled_amount=order_response.filled_amount,
            average_price=order_response.average_price if order_response.average_price else 0.0
        )

    # ==================== 异步交易接口 ====================

    def SubmitOrderAsync(
        self,
        request: trading_pb2.AsyncOrderRequest,
        context: grpc.ServicerContext
    ) -> trading_pb2.AsyncOrderResponse:
        """异步提交订单"""
        try:
            # 转换请求
            side_map = {
                trading_pb2.ORDER_SIDE_BUY: RestOrderSide.BUY,
                trading_pb2.ORDER_SIDE_SELL: RestOrderSide.SELL
            }

            type_map = {
                trading_pb2.ORDER_TYPE_MARKET: RestOrderType.MARKET,
                trading_pb2.ORDER_TYPE_LIMIT: RestOrderType.LIMIT,
                trading_pb2.ORDER_TYPE_STOP: RestOrderType.STOP,
                trading_pb2.ORDER_TYPE_STOP_LIMIT: RestOrderType.STOP_LIMIT
            }

            rest_request = RestAsyncOrderRequest(
                stock_code=request.stock_code,
                side=side_map.get(request.side, RestOrderSide.BUY),
                order_type=type_map.get(request.order_type, RestOrderType.LIMIT),
                volume=int(request.volume),
                price=request.price if request.price else None,
                strategy_name=request.strategy_name if request.strategy_name else None
            )

            # 调用服务
            result = self.trading_service.submit_order_async(request.session_id, rest_request)

            return trading_pb2.AsyncOrderResponse(
                success=result.success,
                message=result.message,
                seq=result.seq or 0,
                stock_code=result.stock_code or "",
                side=result.side or "",
                volume=result.volume or 0,
                price=result.price or 0.0,
                status=common_pb2.Status(code=0 if result.success else 400, message=result.message)
            )

        except TradingServiceException as e:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return trading_pb2.AsyncOrderResponse(
                success=False,
                message=str(e),
                status=common_pb2.Status(code=400, message=str(e))
            )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return trading_pb2.AsyncOrderResponse(
                success=False,
                message=str(e),
                status=common_pb2.Status(code=500, message=str(e))
            )

    def CancelOrderAsync(
        self,
        request: trading_pb2.AsyncCancelRequest,
        context: grpc.ServicerContext
    ) -> trading_pb2.AsyncCancelResponse:
        """异步撤销订单"""
        try:
            # 转换请求
            rest_request = RestAsyncCancelRequest(
                order_id=request.order_id if request.order_id else None,
                order_sysid=request.order_sysid if request.order_sysid else None
            )

            # 调用服务
            result = self.trading_service.cancel_order_async(request.session_id, rest_request)

            return trading_pb2.AsyncCancelResponse(
                success=result.success,
                message=result.message,
                seq=result.seq or 0,
                order_id=result.order_id or "",
                status=common_pb2.Status(code=0 if result.success else 400, message=result.message)
            )

        except TradingServiceException as e:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return trading_pb2.AsyncCancelResponse(
                success=False,
                message=str(e),
                status=common_pb2.Status(code=400, message=str(e))
            )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return trading_pb2.AsyncCancelResponse(
                success=False,
                message=str(e),
                status=common_pb2.Status(code=500, message=str(e))
            )

    def StreamTradingCallbacks(
        self,
        request: trading_pb2.TradingCallbackRequest,
        context: grpc.ServicerContext
    ) -> Iterator[trading_pb2.TradingCallbackMessage]:
        """
        订阅交易回调流（服务端流）

        注意：gRPC 流是同步的，需要特殊处理来桥接异步回调
        """
        try:
            from app.config import get_settings
            import asyncio
            import threading
            import queue

            settings = get_settings()
            callback_manager = get_trading_callback_manager(settings)
            account_id = request.account_id if request.account_id else None

            # 使用队列在异步回调和同步 gRPC 流之间传递数据
            sync_queue = queue.Queue(maxsize=1000)
            stop_event = threading.Event()

            # 回调类型映射
            callback_type_map = {
                "connected": trading_pb2.CALLBACK_TYPE_CONNECTED,
                "disconnected": trading_pb2.CALLBACK_TYPE_DISCONNECTED,
                "account_status": trading_pb2.CALLBACK_TYPE_ACCOUNT_STATUS,
                "asset": trading_pb2.CALLBACK_TYPE_ASSET,
                "order": trading_pb2.CALLBACK_TYPE_ORDER,
                "trade": trading_pb2.CALLBACK_TYPE_TRADE,
                "position": trading_pb2.CALLBACK_TYPE_POSITION,
                "order_error": trading_pb2.CALLBACK_TYPE_ORDER_ERROR,
                "cancel_error": trading_pb2.CALLBACK_TYPE_CANCEL_ERROR,
                "async_order": trading_pb2.CALLBACK_TYPE_ASYNC_ORDER,
                "async_cancel": trading_pb2.CALLBACK_TYPE_ASYNC_CANCEL,
                "heartbeat": trading_pb2.CALLBACK_TYPE_HEARTBEAT,
            }

            async def async_consumer():
                """异步消费回调并放入同步队列"""
                try:
                    async for callback_data in callback_manager.stream_callbacks(account_id):
                        if stop_event.is_set():
                            break
                        try:
                            sync_queue.put_nowait(callback_data)
                        except queue.Full:
                            # 队列满时丢弃旧数据
                            try:
                                sync_queue.get_nowait()
                                sync_queue.put_nowait(callback_data)
                            except Exception:
                                pass
                except Exception as e:
                    logger.error(f"gRPC 回调流异步消费异常: {e}")
                finally:
                    sync_queue.put(None)  # 发送结束信号

            def run_async_consumer():
                """在新线程中运行异步消费者"""
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(async_consumer())
                finally:
                    loop.close()

            # 启动异步消费者线程
            consumer_thread = threading.Thread(target=run_async_consumer, daemon=True)
            consumer_thread.start()

            logger.info(f"gRPC 交易回调流已启动: account_id={account_id}")

            # 从同步队列中读取并生成响应
            while not context.is_active() == False:
                try:
                    callback_data = sync_queue.get(timeout=30.0)

                    if callback_data is None:
                        break

                    # 心跳消息
                    if callback_data.get("callback_type") == "heartbeat":
                        yield trading_pb2.TradingCallbackMessage(
                            callback_type=trading_pb2.CALLBACK_TYPE_HEARTBEAT,
                            account_id="",
                            timestamp=callback_data.get("timestamp", datetime.now().isoformat()),
                            seq=0
                        )
                        continue

                    # 转换回调消息
                    cb_type_str = callback_data.get("callback_type", "")
                    cb_type = callback_type_map.get(cb_type_str, trading_pb2.CALLBACK_TYPE_UNSPECIFIED)

                    message = trading_pb2.TradingCallbackMessage(
                        callback_type=cb_type,
                        account_id=callback_data.get("account_id", ""),
                        timestamp=callback_data.get("timestamp", datetime.now().isoformat()),
                        seq=callback_data.get("seq", 0) or 0
                    )

                    # 根据回调类型设置对应的数据字段
                    data = callback_data.get("data", {})

                    if cb_type == trading_pb2.CALLBACK_TYPE_ORDER:
                        message.order_data.CopyFrom(trading_pb2.OrderCallbackData(
                            order_id=str(data.get("order_id", "")),
                            order_sysid=str(data.get("order_sysid", "") or ""),
                            stock_code=data.get("stock_code", ""),
                            stock_name=data.get("stock_name", "") or "",
                            side=data.get("side", ""),
                            order_type=data.get("order_type", ""),
                            volume=data.get("volume", 0),
                            price=data.get("price", 0.0),
                            status=data.get("status", ""),
                            status_msg=data.get("status_msg", "") or "",
                            filled_volume=data.get("filled_volume", 0),
                            filled_amount=data.get("filled_amount", 0.0),
                            order_time=str(data.get("order_time", "") or "")
                        ))
                    elif cb_type == trading_pb2.CALLBACK_TYPE_TRADE:
                        message.trade_data.CopyFrom(trading_pb2.TradeCallbackData(
                            trade_id=str(data.get("trade_id", "")),
                            order_id=str(data.get("order_id", "")),
                            order_sysid=str(data.get("order_sysid", "") or ""),
                            stock_code=data.get("stock_code", ""),
                            stock_name=data.get("stock_name", "") or "",
                            side=data.get("side", ""),
                            volume=data.get("volume", 0),
                            price=data.get("price", 0.0),
                            amount=data.get("amount", 0.0),
                            trade_time=str(data.get("trade_time", "") or ""),
                            commission=data.get("commission", 0.0)
                        ))
                    elif cb_type == trading_pb2.CALLBACK_TYPE_POSITION:
                        message.position_data.CopyFrom(trading_pb2.PositionCallbackData(
                            stock_code=data.get("stock_code", ""),
                            stock_name=data.get("stock_name", "") or "",
                            volume=data.get("volume", 0),
                            available_volume=data.get("available_volume", 0),
                            frozen_volume=data.get("frozen_volume", 0),
                            cost_price=data.get("cost_price", 0.0),
                            market_price=data.get("market_price", 0.0),
                            market_value=data.get("market_value", 0.0),
                            profit_loss=data.get("profit_loss", 0.0)
                        ))
                    elif cb_type == trading_pb2.CALLBACK_TYPE_ASSET:
                        message.asset_data.CopyFrom(trading_pb2.AssetCallbackData(
                            total_asset=data.get("total_asset", 0.0),
                            market_value=data.get("market_value", 0.0),
                            cash=data.get("cash", 0.0),
                            frozen_cash=data.get("frozen_cash", 0.0),
                            available_cash=data.get("available_cash", 0.0)
                        ))
                    elif cb_type in [trading_pb2.CALLBACK_TYPE_ORDER_ERROR, trading_pb2.CALLBACK_TYPE_CANCEL_ERROR]:
                        message.error_data.CopyFrom(trading_pb2.ErrorCallbackData(
                            error_code=str(data.get("error_code", "")),
                            error_msg=data.get("error_msg", "") or str(data),
                            order_id=str(data.get("order_id", "") or "")
                        ))
                    elif cb_type == trading_pb2.CALLBACK_TYPE_ASYNC_ORDER:
                        message.async_order_data.CopyFrom(trading_pb2.AsyncOrderCallbackData(
                            seq=data.get("seq", 0) or 0,
                            order_id=str(data.get("order_id", "") or ""),
                            error_msg=data.get("error_msg", "") or ""
                        ))
                    elif cb_type == trading_pb2.CALLBACK_TYPE_ASYNC_CANCEL:
                        message.async_cancel_data.CopyFrom(trading_pb2.AsyncCancelCallbackData(
                            seq=data.get("seq", 0) or 0,
                            order_id=str(data.get("order_id", "") or ""),
                            error_msg=data.get("error_msg", "") or ""
                        ))

                    yield message

                except queue.Empty:
                    # 超时，发送心跳
                    yield trading_pb2.TradingCallbackMessage(
                        callback_type=trading_pb2.CALLBACK_TYPE_HEARTBEAT,
                        account_id="",
                        timestamp=datetime.now().isoformat(),
                        seq=0
                    )

            # 清理
            stop_event.set()
            logger.info(f"gRPC 交易回调流已关闭: account_id={account_id}")

        except Exception as e:
            logger.error(f"gRPC 交易回调流异常: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
