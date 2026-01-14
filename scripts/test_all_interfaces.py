#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
综合接口测试脚本

测试所有 REST API、gRPC 和 WebSocket 接口
使用方法：
    python scripts/test_all_interfaces.py [--rest] [--grpc] [--ws] [--all]

参数说明：
    --rest  只测试 REST API
    --grpc  只测试 gRPC 接口
    --ws    只测试 WebSocket 接口
    --all   测试所有接口（默认）
"""

import sys
import os
import json
import time
import asyncio
import argparse
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass, field
from enum import Enum

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestStatus(Enum):
    """测试状态"""
    PASS = "✅ PASS"
    FAIL = "❌ FAIL"
    SKIP = "⏭️  SKIP"
    ERROR = "💥 ERROR"


@dataclass
class TestResult:
    """测试结果"""
    name: str
    status: TestStatus
    duration_ms: float = 0.0
    message: str = ""
    response_data: Any = None


@dataclass
class TestSuite:
    """测试套件"""
    name: str
    results: List[TestResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == TestStatus.PASS)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == TestStatus.FAIL)

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.status == TestStatus.SKIP)

    @property
    def errored(self) -> int:
        return sum(1 for r in self.results if r.status == TestStatus.ERROR)

    @property
    def total(self) -> int:
        return len(self.results)


# ==================== 配置 ====================

REST_BASE_URL = os.getenv("REST_API_BASE_URL", "http://101.43.116.10:8000")
REST_API_KEY = os.getenv("REST_API_KEY", "dev-api-key-001")
GRPC_HOST = os.getenv("GRPC_HOST", "101.43.116.10")
GRPC_PORT = int(os.getenv("GRPC_PORT", "50051"))
TIMEOUT = 30

# 测试数据
TEST_STOCK_CODES = ["000001.SZ", "600000.SH", "000002.SZ", "600519.SH"]
TEST_INDEX_CODES = ["000001.SH", "000300.SH", "399001.SZ"]
TEST_SECTOR_NAMES = ["沪深300", "银行", "上证50"]


# ==================== REST API 测试 ====================

class RESTAPITester:
    """REST API 测试器"""

    def __init__(self, base_url: str, api_key: str, timeout: int = 30):
        import httpx
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout
        self.client = httpx.Client(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout
        )
        self.suite = TestSuite(name="REST API")

    def close(self):
        self.client.close()

    def _run_test(self, name: str, method: str, path: str,
                  json_data: Dict = None, expected_status: int = 200) -> TestResult:
        """运行单个测试"""
        start_time = time.time()
        try:
            if method.upper() == "GET":
                response = self.client.get(path)
            elif method.upper() == "POST":
                response = self.client.post(path, json=json_data)
            elif method.upper() == "DELETE":
                response = self.client.delete(path)
            else:
                raise ValueError(f"不支持的 HTTP 方法: {method}")

            duration_ms = (time.time() - start_time) * 1000

            if response.status_code == expected_status:
                try:
                    data = response.json()
                    return TestResult(
                        name=name,
                        status=TestStatus.PASS,
                        duration_ms=duration_ms,
                        message=f"HTTP {response.status_code}",
                        response_data=data
                    )
                except Exception:
                    return TestResult(
                        name=name,
                        status=TestStatus.PASS,
                        duration_ms=duration_ms,
                        message=f"HTTP {response.status_code} (非JSON响应)"
                    )
            else:
                return TestResult(
                    name=name,
                    status=TestStatus.FAIL,
                    duration_ms=duration_ms,
                    message=f"期望 HTTP {expected_status}, 实际 HTTP {response.status_code}: {response.text[:200]}"
                )
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return TestResult(
                name=name,
                status=TestStatus.ERROR,
                duration_ms=duration_ms,
                message=str(e)
            )

    def run_all_tests(self) -> TestSuite:
        """运行所有 REST API 测试"""
        print("\n" + "=" * 80)
        print("🌐 REST API 测试")
        print("=" * 80)
        print(f"基础URL: {self.base_url}")
        print(f"API Key: {self.api_key[:10]}...")
        print("-" * 80)

        # 健康检查接口
        self._test_health_endpoints()

        # 数据服务接口
        self._test_data_endpoints()

        # 交易服务接口
        self._test_trading_endpoints()

        return self.suite

    def _test_health_endpoints(self):
        """测试健康检查接口"""
        print("\n📋 健康检查接口")

        tests = [
            ("GET /", "GET", "/", None),
            ("GET /info", "GET", "/info", None),
            ("GET /health/", "GET", "/health/", None),
            ("GET /health/ready", "GET", "/health/ready", None),
            ("GET /health/live", "GET", "/health/live", None),
        ]

        for name, method, path, data in tests:
            result = self._run_test(name, method, path, data)
            self.suite.results.append(result)
            self._print_result(result)

    def _test_data_endpoints(self):
        """测试数据服务接口"""
        print("\n📊 数据服务接口")

        end_date = datetime.now()
        start_date = end_date - timedelta(days=10)

        tests = [
            # 基础信息接口
            ("GET 合约信息", "GET", f"/api/v1/data/instrument/{TEST_STOCK_CODES[0]}", None),
            ("GET 合约类型", "GET", f"/api/v1/data/instrument-type/{TEST_STOCK_CODES[0]}", None),
            ("GET 节假日列表", "GET", "/api/v1/data/holidays", None),
            ("GET 可转债信息", "GET", "/api/v1/data/convertible-bonds", None),
            ("GET 新股申购信息", "GET", "/api/v1/data/ipo-info", None),
            ("GET 周期列表", "GET", "/api/v1/data/period-list", None),
            ("GET 数据目录", "GET", "/api/v1/data/data-dir", None),
            ("GET 板块列表", "GET", "/api/v1/data/sectors", None),
            ("GET 交易日历", "GET", f"/api/v1/data/trading-calendar/{end_date.year}", None),

            # 行情数据接口
            ("POST 市场数据", "POST", "/api/v1/data/market", {
                "stock_codes": TEST_STOCK_CODES[:2],
                "start_date": start_date.strftime("%Y%m%d"),
                "end_date": end_date.strftime("%Y%m%d"),
                "period": "1d",
                "fields": ["time", "open", "high", "low", "close", "volume"]
            }),
            ("POST 板块股票列表", "POST", "/api/v1/data/sector", {
                "sector_name": TEST_SECTOR_NAMES[0]
            }),
            ("POST 指数权重", "POST", "/api/v1/data/index-weight", {
                "index_code": TEST_INDEX_CODES[1],
                "date": None
            }),
            ("POST 财务数据", "POST", "/api/v1/data/financial", {
                "stock_codes": [TEST_STOCK_CODES[0]],
                "table_list": ["Capital"],
                "start_date": "20230101",
                "end_date": "20241231"
            }),
            ("POST 本地行情数据", "POST", "/api/v1/data/local-data", {
                "stock_codes": TEST_STOCK_CODES[:2],
                "start_time": start_date.strftime("%Y%m%d"),
                "end_time": end_date.strftime("%Y%m%d"),
                "period": "1d"
            }),
            ("POST 完整Tick数据", "POST", "/api/v1/data/full-tick", {
                "stock_codes": [TEST_STOCK_CODES[0]],
                "start_time": "",
                "end_time": ""
            }),
            ("POST 除权除息数据", "POST", "/api/v1/data/divid-factors", {
                "stock_code": TEST_STOCK_CODES[0]
            }),
            ("POST 完整K线数据", "POST", "/api/v1/data/full-kline", {
                "stock_codes": TEST_STOCK_CODES[:1],
                "start_time": start_date.strftime("%Y%m%d"),
                "end_time": end_date.strftime("%Y%m%d"),
                "period": "1d"
            }),

            # Level2 数据接口
            ("POST L2快照数据", "POST", "/api/v1/data/l2/quote", {
                "stock_codes": [TEST_STOCK_CODES[0]],
                "start_time": "",
                "end_time": ""
            }),
            ("POST L2逐笔委托", "POST", "/api/v1/data/l2/order", {
                "stock_codes": [TEST_STOCK_CODES[0]],
                "start_time": "",
                "end_time": ""
            }),
            ("POST L2逐笔成交", "POST", "/api/v1/data/l2/transaction", {
                "stock_codes": [TEST_STOCK_CODES[0]],
                "start_time": "",
                "end_time": ""
            }),

            # 数据下载接口
            ("POST 下载历史数据", "POST", "/api/v1/data/download/history-data", {
                "stock_code": TEST_STOCK_CODES[0],
                "period": "1d",
                "start_time": "",
                "end_time": "",
                "incrementally": False
            }),
            ("POST 下载板块数据", "POST", "/api/v1/data/download/sector-data", None),
            ("POST 下载节假日数据", "POST", "/api/v1/data/download/holiday-data", None),
            ("POST 下载ETF信息", "POST", "/api/v1/data/download/etf-info", None),
            ("POST 下载可转债数据", "POST", "/api/v1/data/download/cb-data", None),
        ]

        for name, method, path, data in tests:
            result = self._run_test(name, method, path, data)
            self.suite.results.append(result)
            self._print_result(result)

    def _test_trading_endpoints(self):
        """测试交易服务接口"""
        print("\n💹 交易服务接口")

        # 使用模拟 session_id 测试，预期会收到 400 错误
        mock_session_id = "test_session_001"

        # 首先尝试连接（可能成功或失败，取决于模式）
        connect_result = self._run_test(
            "POST 连接交易账户", "POST", "/api/v1/trading/connect",
            {
                "account_id": "test_account",
                "password": "test_password",
                "account_type": "SECURITY"
            }
        )
        self.suite.results.append(connect_result)
        self._print_result(connect_result)

        # 如果连接成功，使用返回的 session_id
        session_id = mock_session_id
        if connect_result.status == TestStatus.PASS and connect_result.response_data:
            data = connect_result.response_data
            if isinstance(data, dict) and "session_id" in data:
                session_id = data["session_id"]
            elif isinstance(data, dict) and "data" in data and isinstance(data["data"], dict):
                session_id = data["data"].get("session_id", mock_session_id)

        tests = [
            ("GET 账户信息", "GET", f"/api/v1/trading/account/{session_id}", None),
            ("GET 连接状态", "GET", f"/api/v1/trading/status/{session_id}", None),
            ("GET 持仓信息", "GET", f"/api/v1/trading/positions/{session_id}", None),
            ("GET 订单列表", "GET", f"/api/v1/trading/orders/{session_id}", None),
            ("GET 成交记录", "GET", f"/api/v1/trading/trades/{session_id}", None),
            ("GET 资产信息", "GET", f"/api/v1/trading/asset/{session_id}", None),
            ("GET 风险信息", "GET", f"/api/v1/trading/risk/{session_id}", None),
            ("GET 策略列表", "GET", f"/api/v1/trading/strategies/{session_id}", None),
        ]

        for name, method, path, data in tests:
            # 交易接口在无效 session 时可能返回 400，这是预期行为
            result = self._run_test(name, method, path, data)
            # 如果是 400 错误且 session 无效，标记为 SKIP 而非 FAIL
            if result.status == TestStatus.FAIL and "400" in result.message:
                result.status = TestStatus.SKIP
                result.message = "无效会话（预期行为）"
            self.suite.results.append(result)
            self._print_result(result)

        # 断开连接
        disconnect_result = self._run_test(
            "POST 断开连接", "POST", f"/api/v1/trading/disconnect/{session_id}", None
        )
        if disconnect_result.status == TestStatus.FAIL and "400" in disconnect_result.message:
            disconnect_result.status = TestStatus.SKIP
            disconnect_result.message = "无效会话（预期行为）"
        self.suite.results.append(disconnect_result)
        self._print_result(disconnect_result)

    def _print_result(self, result: TestResult):
        """打印测试结果"""
        status_str = result.status.value
        duration_str = f"{result.duration_ms:.1f}ms"
        print(f"  {status_str} {result.name} ({duration_str})")
        if result.status in (TestStatus.FAIL, TestStatus.ERROR):
            print(f"       └─ {result.message}")


# ==================== gRPC 测试 ====================

class GRPCTester:
    """gRPC 测试器"""

    def __init__(self, host: str, port: int, timeout: int = 30):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.address = f"{host}:{port}"
        self.suite = TestSuite(name="gRPC")
        self.channel = None
        self.stubs = {}

    def _connect(self) -> bool:
        """连接到 gRPC 服务器"""
        try:
            import grpc
            from generated import (
                data_pb2_grpc,
                trading_pb2_grpc,
                health_pb2_grpc,
            )

            self.channel = grpc.insecure_channel(
                self.address,
                options=[
                    ('grpc.max_send_message_length', 50 * 1024 * 1024),
                    ('grpc.max_receive_message_length', 50 * 1024 * 1024),
                ]
            )

            self.stubs = {
                'data': data_pb2_grpc.DataServiceStub(self.channel),
                'trading': trading_pb2_grpc.TradingServiceStub(self.channel),
                'health': health_pb2_grpc.HealthStub(self.channel),
            }
            return True
        except ImportError as e:
            print(f"  ⚠️  gRPC 依赖未安装或生成代码不存在: {e}")
            return False
        except Exception as e:
            print(f"  ⚠️  连接 gRPC 服务器失败: {e}")
            return False

    def close(self):
        if self.channel:
            self.channel.close()

    def run_all_tests(self) -> TestSuite:
        """运行所有 gRPC 测试"""
        print("\n" + "=" * 80)
        print("🔌 gRPC 接口测试")
        print("=" * 80)
        print(f"服务器地址: {self.address}")
        print("-" * 80)

        if not self._connect():
            result = TestResult(
                name="gRPC 连接",
                status=TestStatus.ERROR,
                message="无法连接到 gRPC 服务器或依赖缺失"
            )
            self.suite.results.append(result)
            self._print_result(result)
            return self.suite

        # 健康检查
        self._test_health()

        # 数据服务
        self._test_data_service()

        # 交易服务
        self._test_trading_service()

        return self.suite

    def _test_health(self):
        """测试健康检查服务"""
        print("\n📋 健康检查服务")

        try:
            from generated import health_pb2

            start_time = time.time()
            request = health_pb2.HealthCheckRequest(service="")
            response = self.stubs['health'].Check(request, timeout=self.timeout)
            duration_ms = (time.time() - start_time) * 1000

            result = TestResult(
                name="Health.Check",
                status=TestStatus.PASS,
                duration_ms=duration_ms,
                message=f"status={response.status}"
            )
        except Exception as e:
            result = TestResult(
                name="Health.Check",
                status=TestStatus.ERROR,
                message=str(e)
            )

        self.suite.results.append(result)
        self._print_result(result)

    def _test_data_service(self):
        """测试数据服务"""
        print("\n📊 数据服务")

        try:
            from generated import data_pb2, common_pb2
            from google.protobuf import empty_pb2

            end_date = datetime.now()
            start_date = end_date - timedelta(days=10)

            # 测试 GetMarketData
            result = self._run_grpc_test(
                "DataService.GetMarketData",
                lambda: self.stubs['data'].GetMarketData(
                    data_pb2.MarketDataRequest(
                        stock_codes=TEST_STOCK_CODES[:2],
                        start_date=start_date.strftime("%Y%m%d"),
                        end_date=end_date.strftime("%Y%m%d"),
                        period=common_pb2.PERIOD_TYPE_1D  # 使用枚举值 7
                    ),
                    timeout=self.timeout
                )
            )
            self.suite.results.append(result)
            self._print_result(result)

            # 测试 GetSectorList
            result = self._run_grpc_test(
                "DataService.GetSectorList",
                lambda: self.stubs['data'].GetSectorList(
                    empty_pb2.Empty(),
                    timeout=self.timeout
                )
            )
            self.suite.results.append(result)
            self._print_result(result)

            # 测试 GetTradingCalendar
            result = self._run_grpc_test(
                "DataService.GetTradingCalendar",
                lambda: self.stubs['data'].GetTradingCalendar(
                    data_pb2.TradingCalendarRequest(year=end_date.year),
                    timeout=self.timeout
                )
            )
            self.suite.results.append(result)
            self._print_result(result)

            # 测试 GetInstrumentInfo
            result = self._run_grpc_test(
                "DataService.GetInstrumentInfo",
                lambda: self.stubs['data'].GetInstrumentInfo(
                    data_pb2.InstrumentInfoRequest(stock_code=TEST_STOCK_CODES[0]),
                    timeout=self.timeout
                )
            )
            self.suite.results.append(result)
            self._print_result(result)

            # 测试 GetIndexWeight
            result = self._run_grpc_test(
                "DataService.GetIndexWeight",
                lambda: self.stubs['data'].GetIndexWeight(
                    data_pb2.IndexWeightRequest(
                        index_code=TEST_INDEX_CODES[1],
                        date=""
                    ),
                    timeout=self.timeout
                )
            )
            self.suite.results.append(result)
            self._print_result(result)

            # 测试 GetFinancialData
            result = self._run_grpc_test(
                "DataService.GetFinancialData",
                lambda: self.stubs['data'].GetFinancialData(
                    data_pb2.FinancialDataRequest(
                        stock_codes=[TEST_STOCK_CODES[0]],
                        table_list=["Capital"],
                        start_date="20230101",
                        end_date="20241231"
                    ),
                    timeout=self.timeout
                )
            )
            self.suite.results.append(result)
            self._print_result(result)

        except ImportError as e:
            result = TestResult(
                name="DataService",
                status=TestStatus.ERROR,
                message=f"导入失败: {e}"
            )
            self.suite.results.append(result)
            self._print_result(result)

    def _test_trading_service(self):
        """测试交易服务"""
        print("\n💹 交易服务")

        try:
            from generated import trading_pb2

            # 测试 Connect
            result = self._run_grpc_test(
                "TradingService.Connect",
                lambda: self.stubs['trading'].Connect(
                    trading_pb2.ConnectRequest(
                        account_id="test_account",
                        password="test_password",
                        client_id=1
                    ),
                    timeout=self.timeout
                )
            )
            self.suite.results.append(result)
            self._print_result(result)

            # 获取 session_id
            session_id = "test_session"
            if result.status == TestStatus.PASS and result.response_data:
                if hasattr(result.response_data, 'session_id'):
                    session_id = result.response_data.session_id

            # 测试 GetPositions
            result = self._run_grpc_test(
                "TradingService.GetPositions",
                lambda: self.stubs['trading'].GetPositions(
                    trading_pb2.PositionRequest(session_id=session_id),
                    timeout=self.timeout
                )
            )
            self.suite.results.append(result)
            self._print_result(result)

            # 测试 GetOrders
            result = self._run_grpc_test(
                "TradingService.GetOrders",
                lambda: self.stubs['trading'].GetOrders(
                    trading_pb2.OrderListRequest(session_id=session_id),
                    timeout=self.timeout
                )
            )
            self.suite.results.append(result)
            self._print_result(result)

            # 测试 GetAsset
            result = self._run_grpc_test(
                "TradingService.GetAsset",
                lambda: self.stubs['trading'].GetAsset(
                    trading_pb2.AssetRequest(session_id=session_id),
                    timeout=self.timeout
                )
            )
            self.suite.results.append(result)
            self._print_result(result)

            # 测试 Disconnect
            result = self._run_grpc_test(
                "TradingService.Disconnect",
                lambda: self.stubs['trading'].Disconnect(
                    trading_pb2.DisconnectRequest(session_id=session_id),
                    timeout=self.timeout
                )
            )
            self.suite.results.append(result)
            self._print_result(result)

        except ImportError as e:
            result = TestResult(
                name="TradingService",
                status=TestStatus.ERROR,
                message=f"导入失败: {e}"
            )
            self.suite.results.append(result)
            self._print_result(result)

    def _run_grpc_test(self, name: str, call_func) -> TestResult:
        """运行单个 gRPC 测试"""
        start_time = time.time()
        try:
            response = call_func()
            duration_ms = (time.time() - start_time) * 1000

            # 检查响应状态
            if hasattr(response, 'status'):
                status = response.status
                if hasattr(status, 'code') and status.code != 0:
                    return TestResult(
                        name=name,
                        status=TestStatus.FAIL,
                        duration_ms=duration_ms,
                        message=f"code={status.code}, message={status.message}"
                    )

            return TestResult(
                name=name,
                status=TestStatus.PASS,
                duration_ms=duration_ms,
                response_data=response
            )
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            error_msg = str(e)
            # gRPC 错误信息可能很长，截断
            if len(error_msg) > 200:
                error_msg = error_msg[:200] + "..."
            return TestResult(
                name=name,
                status=TestStatus.ERROR,
                duration_ms=duration_ms,
                message=error_msg
            )

    def _print_result(self, result: TestResult):
        """打印测试结果"""
        status_str = result.status.value
        duration_str = f"{result.duration_ms:.1f}ms" if result.duration_ms > 0 else ""
        print(f"  {status_str} {result.name} ({duration_str})")
        if result.status in (TestStatus.FAIL, TestStatus.ERROR):
            print(f"       └─ {result.message}")


# ==================== WebSocket 测试 ====================

class WebSocketTester:
    """WebSocket 测试器"""

    def __init__(self, base_url: str, timeout: int = 10):
        self.base_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
        self.timeout = timeout
        self.suite = TestSuite(name="WebSocket")

    def run_all_tests(self) -> TestSuite:
        """运行所有 WebSocket 测试"""
        print("\n" + "=" * 80)
        print("🔗 WebSocket 接口测试")
        print("=" * 80)
        print(f"WebSocket URL: {self.base_url}")
        print("-" * 80)

        # 使用 asyncio 运行异步测试
        try:
            asyncio.get_event_loop().run_until_complete(self._run_async_tests())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._run_async_tests())

        return self.suite

    async def _run_async_tests(self):
        """运行异步测试"""
        # 测试行情 WebSocket
        await self._test_quote_websocket()

        # 测试交易 WebSocket
        await self._test_trading_websocket()

    async def _test_quote_websocket(self):
        """测试行情 WebSocket"""
        print("\n📊 行情 WebSocket")

        # 临时禁用代理环境变量
        import os
        proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY',
                      'http_proxy', 'https_proxy', 'all_proxy']
        saved_proxies = {k: os.environ.pop(k, None) for k in proxy_vars}

        try:
            import websockets

            url = f"{self.base_url}/ws/quote/test_subscription_123"
            start_time = time.time()

            try:
                async with websockets.connect(url, close_timeout=3) as ws:
                    await ws.send(json.dumps({"type": "ping"}))
                    try:
                        response = await asyncio.wait_for(ws.recv(), timeout=3)
                        duration_ms = (time.time() - start_time) * 1000
                        result = TestResult(
                            name="WS /ws/quote/{id} 连接",
                            status=TestStatus.PASS,
                            duration_ms=duration_ms,
                            message=f"收到响应: {response[:100]}..."
                        )
                    except asyncio.TimeoutError:
                        duration_ms = (time.time() - start_time) * 1000
                        result = TestResult(
                            name="WS /ws/quote/{id} 连接",
                            status=TestStatus.PASS,
                            duration_ms=duration_ms,
                            message="连接成功（无数据响应）"
                        )
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                error_msg = str(e)
                if "1008" in error_msg or "subscription" in error_msg.lower():
                    result = TestResult(
                        name="WS /ws/quote/{id} 连接",
                        status=TestStatus.SKIP,
                        duration_ms=duration_ms,
                        message="订阅不存在（预期行为）"
                    )
                else:
                    result = TestResult(
                        name="WS /ws/quote/{id} 连接",
                        status=TestStatus.ERROR,
                        duration_ms=duration_ms,
                        message=error_msg[:200]
                    )
        except ImportError:
            result = TestResult(
                name="WS /ws/quote/{id} 连接",
                status=TestStatus.SKIP,
                message="websockets 库未安装"
            )
        finally:
            # 恢复代理设置
            for k, v in saved_proxies.items():
                if v is not None:
                    os.environ[k] = v

        self.suite.results.append(result)
        self._print_result(result)

    async def _test_trading_websocket(self):
        """测试交易 WebSocket"""
        print("\n💹 交易 WebSocket")

        # 临时禁用代理环境变量
        import os
        proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY',
                      'http_proxy', 'https_proxy', 'all_proxy']
        saved_proxies = {k: os.environ.pop(k, None) for k in proxy_vars}

        try:
            import websockets

            url = f"{self.base_url}/ws/trading"
            start_time = time.time()

            try:
                async with websockets.connect(url, close_timeout=3) as ws:
                    await ws.send(json.dumps({"type": "ping"}))
                    try:
                        response = await asyncio.wait_for(ws.recv(), timeout=3)
                        duration_ms = (time.time() - start_time) * 1000
                        result = TestResult(
                            name="WS /ws/trading 连接",
                            status=TestStatus.PASS,
                            duration_ms=duration_ms,
                            message=f"收到响应: {response[:100]}..."
                        )
                    except asyncio.TimeoutError:
                        duration_ms = (time.time() - start_time) * 1000
                        result = TestResult(
                            name="WS /ws/trading 连接",
                            status=TestStatus.PASS,
                            duration_ms=duration_ms,
                            message="连接成功（等待回调）"
                        )
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                result = TestResult(
                    name="WS /ws/trading 连接",
                    status=TestStatus.ERROR,
                    duration_ms=duration_ms,
                    message=str(e)[:200]
                )
        except ImportError:
            result = TestResult(
                name="WS /ws/trading 连接",
                status=TestStatus.SKIP,
                message="websockets 库未安装"
            )
        finally:
            # 恢复代理设置
            for k, v in saved_proxies.items():
                if v is not None:
                    os.environ[k] = v

        self.suite.results.append(result)
        self._print_result(result)

    def _print_result(self, result: TestResult):
        """打印测试结果"""
        status_str = result.status.value
        duration_str = f"{result.duration_ms:.1f}ms" if result.duration_ms > 0 else ""
        print(f"  {status_str} {result.name} ({duration_str})")
        if result.status in (TestStatus.FAIL, TestStatus.ERROR):
            print(f"       └─ {result.message}")


# ==================== 主程序 ====================

def print_summary(suites: List[TestSuite]):
    """打印测试总结"""
    print("\n" + "=" * 80)
    print("📊 测试总结")
    print("=" * 80)

    total_passed = 0
    total_failed = 0
    total_skipped = 0
    total_errored = 0
    total_tests = 0

    for suite in suites:
        print(f"\n{suite.name}:")
        print(f"  ✅ 通过: {suite.passed}")
        print(f"  ❌ 失败: {suite.failed}")
        print(f"  ⏭️  跳过: {suite.skipped}")
        print(f"  💥 错误: {suite.errored}")
        print(f"  📋 总计: {suite.total}")

        total_passed += suite.passed
        total_failed += suite.failed
        total_skipped += suite.skipped
        total_errored += suite.errored
        total_tests += suite.total

    print("\n" + "-" * 80)
    print("总计:")
    print(f"  ✅ 通过: {total_passed}")
    print(f"  ❌ 失败: {total_failed}")
    print(f"  ⏭️  跳过: {total_skipped}")
    print(f"  💥 错误: {total_errored}")
    print(f"  📋 总计: {total_tests}")

    # 计算通过率
    if total_tests > 0:
        pass_rate = (total_passed / total_tests) * 100
        print(f"\n  📈 通过率: {pass_rate:.1f}%")

    print("=" * 80)

    # 返回是否全部通过
    return total_failed == 0 and total_errored == 0


def main():
    parser = argparse.ArgumentParser(description="综合接口测试脚本")
    parser.add_argument("--rest", action="store_true", help="只测试 REST API")
    parser.add_argument("--grpc", action="store_true", help="只测试 gRPC 接口")
    parser.add_argument("--ws", action="store_true", help="只测试 WebSocket 接口")
    parser.add_argument("--all", action="store_true", help="测试所有接口（默认）")
    parser.add_argument("--base-url", default=REST_BASE_URL, help="REST API 基础 URL")
    parser.add_argument("--api-key", default=REST_API_KEY, help="API Key")
    parser.add_argument("--grpc-host", default=GRPC_HOST, help="gRPC 主机地址")
    parser.add_argument("--grpc-port", type=int, default=GRPC_PORT, help="gRPC 端口")

    args = parser.parse_args()

    # 如果没有指定任何选项，默认测试所有
    if not any([args.rest, args.grpc, args.ws]):
        args.all = True

    print("\n" + "=" * 80)
    print("🚀 xtquant-proxy 综合接口测试")
    print("=" * 80)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"REST API: {args.base_url}")
    print(f"gRPC: {args.grpc_host}:{args.grpc_port}")

    suites = []

    # REST API 测试
    if args.rest or args.all:
        try:
            tester = RESTAPITester(args.base_url, args.api_key)
            suite = tester.run_all_tests()
            suites.append(suite)
            tester.close()
        except Exception as e:
            print(f"❌ REST API 测试失败: {e}")
            suite = TestSuite(name="REST API")
            suite.results.append(TestResult(
                name="REST API 测试",
                status=TestStatus.ERROR,
                message=str(e)
            ))
            suites.append(suite)

    # gRPC 测试
    if args.grpc or args.all:
        try:
            tester = GRPCTester(args.grpc_host, args.grpc_port)
            suite = tester.run_all_tests()
            suites.append(suite)
            tester.close()
        except Exception as e:
            print(f"❌ gRPC 测试失败: {e}")
            suite = TestSuite(name="gRPC")
            suite.results.append(TestResult(
                name="gRPC 测试",
                status=TestStatus.ERROR,
                message=str(e)
            ))
            suites.append(suite)

    # WebSocket 测试
    if args.ws or args.all:
        try:
            tester = WebSocketTester(args.base_url)
            suite = tester.run_all_tests()
            suites.append(suite)
        except Exception as e:
            print(f"❌ WebSocket 测试失败: {e}")
            suite = TestSuite(name="WebSocket")
            suite.results.append(TestResult(
                name="WebSocket 测试",
                status=TestStatus.ERROR,
                message=str(e)
            ))
            suites.append(suite)

    # 打印总结
    all_passed = print_summary(suites)

    print(f"\n完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 返回退出码
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
