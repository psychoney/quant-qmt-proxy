#!/usr/bin/env python3
"""
远程服务API完整测试脚本

用法:
    python scripts/test_remote_api.py                    # 使用默认配置
    python scripts/test_remote_api.py --host 101.43.116.10  # 指定服务器IP
    python scripts/test_remote_api.py --api-key your-key    # 指定API密钥
    python scripts/test_remote_api.py --grpc                # 同时测试gRPC
"""

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

try:
    import httpx
except ImportError:
    print("❌ 请先安装 httpx: pip install httpx")
    sys.exit(1)


@dataclass
class TestResult:
    """测试结果"""
    name: str
    success: bool
    status_code: Optional[int] = None
    response_time: float = 0.0
    error: Optional[str] = None
    response_data: Optional[Dict] = None


@dataclass
class TestStats:
    """测试统计"""
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    results: List[TestResult] = field(default_factory=list)
    
    @property
    def success_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.passed / self.total) * 100


class APITester:
    """API测试器"""
    
    def __init__(self, host: str, port: int, api_key: str, timeout: int = 30):
        self.base_url = f"http://{host}:{port}"
        self.api_key = api_key
        self.timeout = timeout
        self.stats = TestStats()
        self.client = httpx.Client(timeout=timeout)
        
    def __del__(self):
        if hasattr(self, 'client'):
            self.client.close()
    
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
    
    def _print_result(self, result: TestResult):
        """打印测试结果"""
        status = "✅" if result.success else "❌"
        time_str = f"({result.response_time:.0f}ms)"
        
        if result.success:
            print(f"  {status} {result.name} {time_str}")
        else:
            print(f"  {status} {result.name} {time_str}")
            if result.error:
                print(f"      错误: {result.error}")
    
    def test_endpoint(
        self,
        name: str,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        require_auth: bool = True,
        expected_status: int = 200
    ) -> TestResult:
        """测试单个端点"""
        self.stats.total += 1
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers() if require_auth else {"Content-Type": "application/json"}
        
        start_time = time.time()
        
        try:
            if method.upper() == "GET":
                response = self.client.get(url, headers=headers)
            elif method.upper() == "POST":
                response = self.client.post(url, json=data, headers=headers)
            elif method.upper() == "DELETE":
                response = self.client.delete(url, headers=headers)
            else:
                raise ValueError(f"不支持的HTTP方法: {method}")
            
            response_time = (time.time() - start_time) * 1000
            
            if response.status_code == expected_status:
                self.stats.passed += 1
                result = TestResult(
                    name=name,
                    success=True,
                    status_code=response.status_code,
                    response_time=response_time,
                    response_data=response.json() if response.text else None
                )
            else:
                self.stats.failed += 1
                error_msg = response.text[:200] if response.text else "无响应内容"
                result = TestResult(
                    name=name,
                    success=False,
                    status_code=response.status_code,
                    response_time=response_time,
                    error=f"HTTP {response.status_code}: {error_msg}"
                )
                
        except httpx.ConnectError:
            self.stats.failed += 1
            result = TestResult(
                name=name,
                success=False,
                response_time=(time.time() - start_time) * 1000,
                error=f"连接失败: 无法连接到 {url}"
            )
        except httpx.TimeoutException:
            self.stats.failed += 1
            result = TestResult(
                name=name,
                success=False,
                response_time=(time.time() - start_time) * 1000,
                error=f"请求超时 ({self.timeout}s)"
            )
        except Exception as e:
            self.stats.failed += 1
            result = TestResult(
                name=name,
                success=False,
                response_time=(time.time() - start_time) * 1000,
                error=str(e)
            )
        
        self.stats.results.append(result)
        self._print_result(result)
        return result
    
    def run_health_tests(self):
        """运行健康检查测试"""
        print("\n" + "=" * 60)
        print("📋 1. 健康检查接口")
        print("=" * 60)
        
        # 健康检查接口不需要认证
        self.test_endpoint("根路径", "GET", "/", require_auth=False)
        self.test_endpoint("应用信息", "GET", "/info", require_auth=False)
        self.test_endpoint("健康检查", "GET", "/health/", require_auth=False)
        self.test_endpoint("就绪检查", "GET", "/health/ready", require_auth=False)
        self.test_endpoint("存活检查", "GET", "/health/live", require_auth=False)
    
    def run_data_api_tests(self):
        """运行数据服务API测试"""
        print("\n" + "=" * 60)
        print("📋 2. 数据服务接口")
        print("=" * 60)
        
        # 2.1 基础信息接口
        print("\n  📁 基础信息")
        self.test_endpoint("获取可用周期列表", "GET", "/api/v1/data/period-list")
        self.test_endpoint("获取本地数据路径", "GET", "/api/v1/data/data-dir")
        self.test_endpoint("获取节假日列表", "GET", "/api/v1/data/holidays")
        self.test_endpoint("获取合约类型", "GET", "/api/v1/data/instrument-type/600519.SH")
        self.test_endpoint("获取合约信息", "GET", "/api/v1/data/instrument/600519.SH")
        self.test_endpoint("获取交易日历", "GET", "/api/v1/data/trading-calendar/2025")
        
        # 2.2 行情数据接口
        print("\n  📁 行情数据")
        end_date = datetime.now()
        start_date = end_date - timedelta(days=10)
        
        market_request = {
            "stock_codes": ["600519.SH", "000001.SZ"],
            "start_date": start_date.strftime("%Y%m%d"),
            "end_date": end_date.strftime("%Y%m%d"),
            "period": "1d"
        }
        self.test_endpoint("获取市场数据(日线)", "POST", "/api/v1/data/market", market_request)
        
        # 分钟线数据
        minute_request = {
            "stock_codes": ["600519.SH"],
            "start_date": (end_date - timedelta(days=1)).strftime("%Y%m%d"),
            "end_date": end_date.strftime("%Y%m%d"),
            "period": "5m"
        }
        self.test_endpoint("获取市场数据(5分钟)", "POST", "/api/v1/data/market", minute_request)
        
        # 本地数据
        local_request = {
            "stock_codes": ["600519.SH"],
            "start_date": start_date.strftime("%Y%m%d"),
            "end_date": end_date.strftime("%Y%m%d"),
            "period": "1d"
        }
        self.test_endpoint("获取本地行情数据", "POST", "/api/v1/data/local-data", local_request)
        
        # Tick数据
        tick_request = {
            "stock_codes": ["600519.SH"]
        }
        self.test_endpoint("获取完整Tick数据", "POST", "/api/v1/data/full-tick", tick_request)
        
        # 除权除息数据
        divid_request = {
            "stock_code": "600519.SH"
        }
        self.test_endpoint("获取除权除息数据", "POST", "/api/v1/data/divid-factors", divid_request)
        
        # K线数据
        kline_request = {
            "stock_codes": ["600519.SH"],
            "start_date": start_date.strftime("%Y%m%d"),
            "end_date": end_date.strftime("%Y%m%d"),
            "period": "1d"
        }
        self.test_endpoint("获取完整K线数据", "POST", "/api/v1/data/full-kline", kline_request)
        
        # 2.3 板块数据接口
        print("\n  📁 板块数据")
        self.test_endpoint("获取板块列表", "GET", "/api/v1/data/sectors")
        
        sector_request = {"sector_name": "沪深300"}
        self.test_endpoint("获取板块股票", "POST", "/api/v1/data/sector", sector_request)
        
        # 指数权重
        index_request = {
            "index_code": "000300.SH"
        }
        self.test_endpoint("获取指数权重", "POST", "/api/v1/data/index-weight", index_request)
        
        # 2.4 财务数据接口
        print("\n  📁 财务数据")
        financial_request = {
            "stock_codes": ["600519.SH"],
            "table_list": ["Capital"],
            "start_date": "20240101",
            "end_date": "20241231"
        }
        self.test_endpoint("获取财务数据", "POST", "/api/v1/data/financial", financial_request)
        
        # 2.5 其他数据接口
        print("\n  📁 其他数据")
        self.test_endpoint("获取可转债信息", "GET", "/api/v1/data/convertible-bonds")
        self.test_endpoint("获取新股申购信息", "GET", "/api/v1/data/ipo-info")
        self.test_endpoint("获取ETF信息", "GET", "/api/v1/data/etf/510050.SH")
        
        # 2.6 Level2数据接口
        print("\n  📁 Level2数据")
        l2_request = {"stock_codes": ["600519.SH"]}
        self.test_endpoint("获取L2快照数据", "POST", "/api/v1/data/l2/quote", l2_request)
        self.test_endpoint("获取L2逐笔委托", "POST", "/api/v1/data/l2/order", l2_request)
        self.test_endpoint("获取L2逐笔成交", "POST", "/api/v1/data/l2/transaction", l2_request)
    
    def run_trading_api_tests(self):
        """运行交易服务API测试"""
        print("\n" + "=" * 60)
        print("📋 3. 交易服务接口")
        print("=" * 60)
        
        # 3.1 连接账户
        connect_request = {
            "account_id": "test_account_001",
            "password": "test_password",
            "account_type": "SECURITY"
        }
        result = self.test_endpoint("连接交易账户", "POST", "/api/v1/trading/connect", connect_request)
        
        if not result.success:
            print("  ⚠️  连接失败，跳过后续交易接口测试")
            return
        
        # 提取session_id
        session_id = "test_session"
        if result.response_data and "session_id" in result.response_data:
            session_id = result.response_data["session_id"]
            print(f"  📝 获取到 session_id: {session_id}")
        
        # 3.2 账户信息
        self.test_endpoint("获取账户信息", "GET", f"/api/v1/trading/account/{session_id}")
        self.test_endpoint("获取持仓信息", "GET", f"/api/v1/trading/positions/{session_id}")
        self.test_endpoint("获取资产信息", "GET", f"/api/v1/trading/asset/{session_id}")
        self.test_endpoint("获取风险信息", "GET", f"/api/v1/trading/risk/{session_id}")
        self.test_endpoint("获取连接状态", "GET", f"/api/v1/trading/status/{session_id}")
        
        # 3.3 订单相关
        self.test_endpoint("获取订单列表", "GET", f"/api/v1/trading/orders/{session_id}")
        self.test_endpoint("获取成交记录", "GET", f"/api/v1/trading/trades/{session_id}")
        self.test_endpoint("获取策略列表", "GET", f"/api/v1/trading/strategies/{session_id}")
        
        # 3.4 下单测试（模拟模式下不会真实下单）
        print("\n  ⚠️  下单测试（模拟模式，不会真实下单）")
        order_request = {
            "stock_code": "000001.SZ",
            "side": "BUY",
            "volume": 100,
            "price": 13.50,
            "order_type": "LIMIT"
        }
        self.test_endpoint("提交订单", "POST", f"/api/v1/trading/order/{session_id}", order_request)
        
        # 撤单测试
        cancel_request = {"order_id": "mock_order_001"}
        self.test_endpoint("撤销订单", "POST", f"/api/v1/trading/cancel/{session_id}", cancel_request)
        
        # 3.5 断开连接
        self.test_endpoint("断开账户连接", "POST", f"/api/v1/trading/disconnect/{session_id}")
    
    def run_subscription_tests(self):
        """运行订阅接口测试"""
        print("\n" + "=" * 60)
        print("📋 4. 行情订阅接口")
        print("=" * 60)
        
        # 创建订阅
        subscribe_request = {
            "symbols": ["600519.SH", "000001.SZ"],
            "period": "1d",
            "subscription_type": "quote"
        }
        result = self.test_endpoint("创建行情订阅", "POST", "/api/v1/data/subscription", subscribe_request)
        
        # 列出订阅
        self.test_endpoint("列出所有订阅", "GET", "/api/v1/data/subscriptions")
        
        # 如果创建成功，获取订阅信息并取消
        if result.success and result.response_data:
            subscription_id = result.response_data.get("subscription_id", "")
            if subscription_id:
                print(f"  📝 获取到 subscription_id: {subscription_id}")
                self.test_endpoint("获取订阅信息", "GET", f"/api/v1/data/subscription/{subscription_id}")
                self.test_endpoint("取消订阅", "DELETE", f"/api/v1/data/subscription/{subscription_id}")
    
    def print_summary(self):
        """打印测试摘要"""
        print("\n" + "=" * 60)
        print("📊 测试结果摘要")
        print("=" * 60)
        
        print(f"\n  总测试数:   {self.stats.total}")
        print(f"  ✅ 通过:    {self.stats.passed}")
        print(f"  ❌ 失败:    {self.stats.failed}")
        print(f"  成功率:     {self.stats.success_rate:.1f}%")
        
        # 失败的测试详情
        failed_tests = [r for r in self.stats.results if not r.success]
        if failed_tests:
            print("\n  失败的测试:")
            for i, result in enumerate(failed_tests, 1):
                print(f"    {i}. {result.name}")
                if result.error:
                    print(f"       {result.error[:80]}")
        
        # 响应时间统计
        successful_tests = [r for r in self.stats.results if r.success]
        if successful_tests:
            avg_time = sum(r.response_time for r in successful_tests) / len(successful_tests)
            max_time = max(r.response_time for r in successful_tests)
            min_time = min(r.response_time for r in successful_tests)
            print(f"\n  响应时间统计:")
            print(f"    平均: {avg_time:.0f}ms")
            print(f"    最快: {min_time:.0f}ms")
            print(f"    最慢: {max_time:.0f}ms")
        
        print("\n" + "=" * 60)


def test_grpc(host: str, port: int = 50051):
    """测试gRPC接口"""
    print("\n" + "=" * 60)
    print("📋 5. gRPC接口测试")
    print("=" * 60)
    
    try:
        import grpc
        sys.path.insert(0, '.')
        from generated import health_pb2, health_pb2_grpc
        
        channel = grpc.insecure_channel(f'{host}:{port}')
        stub = health_pb2_grpc.HealthStub(channel)
        
        start_time = time.time()
        response = stub.Check(health_pb2.HealthCheckRequest(service=""))
        response_time = (time.time() - start_time) * 1000
        
        status_map = {0: "UNKNOWN", 1: "SERVING", 2: "NOT_SERVING"}
        status_name = status_map.get(response.status, "UNKNOWN")
        
        if response.status == 1:
            print(f"  ✅ gRPC健康检查: {status_name} ({response_time:.0f}ms)")
            return True
        else:
            print(f"  ❌ gRPC健康检查: {status_name} ({response_time:.0f}ms)")
            return False
            
    except ImportError:
        print("  ⚠️  未安装grpc或未生成proto代码，跳过gRPC测试")
        print("     安装: pip install grpcio grpcio-tools")
        print("     生成: python scripts/generate_proto.py")
        return False
    except Exception as e:
        print(f"  ❌ gRPC测试失败: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="远程服务API测试脚本")
    parser.add_argument("--host", default="101.43.116.10", help="服务器IP地址")
    parser.add_argument("--port", type=int, default=8000, help="REST API端口")
    parser.add_argument("--grpc-port", type=int, default=50051, help="gRPC端口")
    parser.add_argument("--api-key", default="dev-api-key-001", help="API密钥")
    parser.add_argument("--timeout", type=int, default=30, help="请求超时(秒)")
    parser.add_argument("--grpc", action="store_true", help="同时测试gRPC接口")
    parser.add_argument("--quick", action="store_true", help="快速模式(仅测试健康检查)")
    args = parser.parse_args()
    
    print("=" * 60)
    print("🚀 远程服务API完整测试")
    print("=" * 60)
    print(f"  服务器:    {args.host}:{args.port}")
    print(f"  API密钥:   {args.api_key[:10]}...")
    print(f"  超时设置:  {args.timeout}秒")
    print(f"  开始时间:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 创建测试器
    tester = APITester(args.host, args.port, args.api_key, args.timeout)
    
    # 运行测试
    tester.run_health_tests()
    
    if not args.quick:
        tester.run_data_api_tests()
        tester.run_trading_api_tests()
        tester.run_subscription_tests()
    
    # gRPC测试
    if args.grpc:
        test_grpc(args.host, args.grpc_port)
    
    # 打印摘要
    tester.print_summary()
    
    print(f"  结束时间:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 返回退出码
    return 0 if tester.stats.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
