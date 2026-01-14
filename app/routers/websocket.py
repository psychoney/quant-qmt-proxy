"""
WebSocket路由 - 用于实时行情推送和交易回调推送
"""
import asyncio
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status

from app.config import Settings, get_settings
from app.dependencies import get_subscription_manager, get_trading_callback_manager
from app.utils.exceptions import DataServiceException
from app.utils.logger import logger

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/quote/{subscription_id}")
async def websocket_quote_stream(
    websocket: WebSocket,
    subscription_id: str,
    settings: Settings = Depends(get_settings)
):
    """
    WebSocket行情流式推送
    
    客户端连接后，持续接收订阅的行情数据
    支持心跳机制保持连接
    
    Args:
        subscription_id: 订阅ID
    """
    await websocket.accept()
    logger.info(f"WebSocket连接建立: subscription_id={subscription_id}, client={websocket.client}")
    
    try:
        # 获取订阅管理器
        subscription_manager = get_subscription_manager(settings)
        
        # 验证订阅是否存在
        info = subscription_manager.get_subscription_info(subscription_id)
        if not info:
            await websocket.send_json({
                "type": "error",
                "message": f"订阅不存在: {subscription_id}"
            })
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        # 发送连接确认
        await websocket.send_json({
            "type": "connected",
            "subscription_id": subscription_id,
            "message": "WebSocket连接成功",
            "timestamp": datetime.now().isoformat()
        })
        
        # 创建接收客户端消息的任务（用于心跳）
        async def receive_messages():
            try:
                while True:
                    data = await websocket.receive_text()
                    message = json.loads(data)
                    
                    # 处理心跳消息
                    if message.get("type") == "ping":
                        await websocket.send_json({
                            "type": "pong",
                            "timestamp": datetime.now().isoformat()
                        })
                        logger.debug(f"收到心跳: {subscription_id}")
            
            except WebSocketDisconnect:
                logger.info(f"客户端断开连接: {subscription_id}")
            except Exception as e:
                logger.error(f"接收消息异常: {e}")
        
        # 启动接收消息任务
        receive_task = asyncio.create_task(receive_messages())
        
        try:
            # 流式推送行情数据
            async for quote_data in subscription_manager.stream_quotes(subscription_id):
                try:
                    # 发送行情数据
                    await websocket.send_json({
                        "type": "quote",
                        "data": quote_data,
                        "timestamp": datetime.now().isoformat()
                    })
                
                except WebSocketDisconnect:
                    logger.info(f"客户端已断开: {subscription_id}")
                    break
                
                except Exception as e:
                    logger.error(f"发送数据异常: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "message": str(e)
                    })
        
        finally:
            # 取消接收任务
            receive_task.cancel()
            try:
                await receive_task
            except asyncio.CancelledError:
                pass
    
    except DataServiceException as e:
        logger.warning(f"订阅服务异常: {e}")
        await websocket.send_json({
            "type": "error",
            "message": str(e)
        })
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket断开: {subscription_id}")
    
    except Exception as e:
        logger.error(f"WebSocket异常: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "message": f"服务器内部错误: {str(e)}"
            })
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception:
            pass
    
    finally:
        logger.info(f"WebSocket连接关闭: {subscription_id}")


@router.get("/ws/test")
async def websocket_test_page():
    """返回WebSocket测试页面的简单HTML"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>WebSocket Test</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            #messages { height: 400px; overflow-y: scroll; border: 1px solid #ccc; padding: 10px; }
            input, button { margin: 5px; padding: 5px; }
        </style>
    </head>
    <body>
        <h1>WebSocket行情推送测试</h1>
        <div>
            <input type="text" id="subscriptionId" placeholder="输入subscription_id" style="width: 300px;">
            <button onclick="connect()">连接</button>
            <button onclick="disconnect()">断开</button>
            <button onclick="sendPing()">发送心跳</button>
        </div>
        <div id="messages"></div>
        
        <script>
            let ws = null;
            
            function connect() {
                const subId = document.getElementById('subscriptionId').value;
                if (!subId) {
                    alert('请输入subscription_id');
                    return;
                }
                
                const wsUrl = `ws://${window.location.host}/ws/quote/${subId}`;
                ws = new WebSocket(wsUrl);
                
                ws.onopen = () => {
                    addMessage('WebSocket已连接');
                };
                
                ws.onmessage = (event) => {
                    const data = JSON.parse(event.data);
                    addMessage('收到消息: ' + JSON.stringify(data, null, 2));
                };
                
                ws.onerror = (error) => {
                    addMessage('WebSocket错误: ' + error);
                };
                
                ws.onclose = () => {
                    addMessage('WebSocket已关闭');
                };
            }
            
            function disconnect() {
                if (ws) {
                    ws.close();
                    ws = null;
                }
            }
            
            function sendPing() {
                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({ type: 'ping' }));
                    addMessage('已发送心跳');
                }
            }
            
            function addMessage(msg) {
                const messagesDiv = document.getElementById('messages');
                const time = new Date().toLocaleTimeString();
                messagesDiv.innerHTML += `[${time}] ${msg}<br>`;
                messagesDiv.scrollTop = messagesDiv.scrollHeight;
            }
        </script>
    </body>
    </html>
    """
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html_content)


# ==================== 交易回调 WebSocket ====================

@router.websocket("/ws/trading")
async def websocket_trading_stream(
    websocket: WebSocket,
    account_id: Optional[str] = Query(None, description="账户ID，不传则订阅所有账户"),
    settings: Settings = Depends(get_settings)
):
    """
    WebSocket 交易回调推送

    订阅后接收交易回调：
    - connected: 连接成功
    - disconnected: 连接断开
    - order: 委托回报
    - trade: 成交回报
    - position: 持仓变动
    - asset: 资金变动
    - order_error: 委托失败
    - cancel_error: 撤单失败
    - async_order: 异步下单回报
    - async_cancel: 异步撤单回报

    Args:
        account_id: 账户ID（可选），不传则订阅所有账户的回调
    """
    await websocket.accept()
    logger.info(f"交易WebSocket连接建立: account_id={account_id}, client={websocket.client}")

    try:
        # 获取交易回调管理器
        callback_manager = get_trading_callback_manager(settings)

        # 发送连接确认
        await websocket.send_json({
            "type": "connected",
            "account_id": account_id,
            "message": "交易WebSocket连接成功",
            "timestamp": datetime.now().isoformat()
        })

        # 发送最近的回调历史
        recent_callbacks = callback_manager.get_recent_callbacks(account_id, limit=10)
        if recent_callbacks:
            await websocket.send_json({
                "type": "history",
                "data": recent_callbacks,
                "timestamp": datetime.now().isoformat()
            })

        # 创建接收客户端消息的任务（用于心跳）
        async def receive_messages():
            try:
                while True:
                    data = await websocket.receive_text()
                    message = json.loads(data)

                    # 处理心跳消息
                    if message.get("type") == "ping":
                        await websocket.send_json({
                            "type": "pong",
                            "timestamp": datetime.now().isoformat()
                        })
                        logger.debug(f"收到交易心跳: account_id={account_id}")

            except WebSocketDisconnect:
                logger.info(f"交易客户端断开连接: account_id={account_id}")
            except Exception as e:
                logger.error(f"接收交易消息异常: {e}")

        # 启动接收消息任务
        receive_task = asyncio.create_task(receive_messages())

        try:
            # 流式推送交易回调
            async for callback_data in callback_manager.stream_callbacks(account_id):
                try:
                    # 发送交易回调
                    await websocket.send_json({
                        "type": "callback",
                        "data": callback_data,
                        "timestamp": datetime.now().isoformat()
                    })

                except WebSocketDisconnect:
                    logger.info(f"交易客户端已断开: account_id={account_id}")
                    break

                except Exception as e:
                    logger.error(f"发送交易回调异常: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "message": str(e)
                    })

        finally:
            # 取消接收任务
            receive_task.cancel()
            try:
                await receive_task
            except asyncio.CancelledError:
                pass

    except WebSocketDisconnect:
        logger.info(f"交易WebSocket断开: account_id={account_id}")

    except Exception as e:
        logger.error(f"交易WebSocket异常: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "message": f"服务器内部错误: {str(e)}"
            })
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception:
            pass

    finally:
        logger.info(f"交易WebSocket连接关闭: account_id={account_id}")


@router.get("/ws/trading-test")
async def websocket_trading_test_page():
    """返回交易 WebSocket 测试页面的简单 HTML"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Trading WebSocket Test</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            #messages { height: 400px; overflow-y: scroll; border: 1px solid #ccc; padding: 10px; background: #f9f9f9; }
            input, button { margin: 5px; padding: 8px; }
            .callback-order { color: blue; }
            .callback-trade { color: green; }
            .callback-position { color: purple; }
            .callback-asset { color: orange; }
            .callback-error { color: red; }
            .heartbeat { color: gray; }
        </style>
    </head>
    <body>
        <h1>交易回调 WebSocket 测试</h1>
        <div>
            <input type="text" id="accountId" placeholder="账户ID（可选）" style="width: 200px;">
            <button onclick="connect()">连接</button>
            <button onclick="disconnect()">断开</button>
            <button onclick="sendPing()">发送心跳</button>
            <button onclick="clearMessages()">清空消息</button>
        </div>
        <div id="messages"></div>

        <script>
            let ws = null;

            function connect() {
                const accountId = document.getElementById('accountId').value;
                let wsUrl = `ws://${window.location.host}/ws/trading`;
                if (accountId) {
                    wsUrl += `?account_id=${encodeURIComponent(accountId)}`;
                }

                ws = new WebSocket(wsUrl);

                ws.onopen = () => {
                    addMessage('WebSocket已连接', 'heartbeat');
                };

                ws.onmessage = (event) => {
                    const data = JSON.parse(event.data);
                    let cssClass = '';

                    if (data.type === 'callback') {
                        const callbackType = data.data?.callback_type || '';
                        if (callbackType.includes('order')) cssClass = 'callback-order';
                        else if (callbackType.includes('trade')) cssClass = 'callback-trade';
                        else if (callbackType.includes('position')) cssClass = 'callback-position';
                        else if (callbackType.includes('asset')) cssClass = 'callback-asset';
                        else if (callbackType.includes('error')) cssClass = 'callback-error';
                    } else if (data.type === 'pong' || data.type === 'heartbeat') {
                        cssClass = 'heartbeat';
                    } else if (data.type === 'error') {
                        cssClass = 'callback-error';
                    }

                    addMessage('收到: ' + JSON.stringify(data, null, 2), cssClass);
                };

                ws.onerror = (error) => {
                    addMessage('WebSocket错误: ' + error, 'callback-error');
                };

                ws.onclose = () => {
                    addMessage('WebSocket已关闭', 'heartbeat');
                };
            }

            function disconnect() {
                if (ws) {
                    ws.close();
                    ws = null;
                }
            }

            function sendPing() {
                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({ type: 'ping' }));
                    addMessage('已发送心跳', 'heartbeat');
                }
            }

            function clearMessages() {
                document.getElementById('messages').innerHTML = '';
            }

            function addMessage(msg, cssClass) {
                const messagesDiv = document.getElementById('messages');
                const time = new Date().toLocaleTimeString();
                const className = cssClass ? `class="${cssClass}"` : '';
                messagesDiv.innerHTML += `<pre ${className}>[${time}] ${msg}</pre>`;
                messagesDiv.scrollTop = messagesDiv.scrollHeight;
            }
        </script>
    </body>
    </html>
    """
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html_content)
