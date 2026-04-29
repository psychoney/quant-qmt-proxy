"""
数据预加载服务
在项目启动时预下载常用数据到本地，减少 API 调用时的延迟

参考官方盘前数据准备示例：
- 静态数据更新：板块数据
- K线数据更新：历史行情增量下载
"""
import hashlib
import json
import os
import threading
import time
from typing import List, Optional

from loguru import logger

from app.config import PreloadConfig, XTQuantMode, get_settings


class DataPreloader:
    """数据预加载器"""

    # 进度打印间隔（秒）
    PROGRESS_INTERVAL = 10
    # 单个下载任务超时时间（秒）
    DOWNLOAD_TIMEOUT = 60
    BATCH_SIZE = 50
    INTRADAY_BATCH_SIZE = 20
    HISTORY_BATCH_TIMEOUT = 120
    HISTORY_SPLIT_MAX_DEPTH = 3
    HISTORY_SPLIT_RETRY_COOLDOWN = 2

    def __init__(self, config: PreloadConfig, mode: XTQuantMode):
        self.config = config
        self.mode = mode
        self._is_running = False
        self._thread: Optional[threading.Thread] = None
        self._progress_thread: Optional[threading.Thread] = None
        self._start_time: Optional[float] = None
        self._current_stage = ""  # 当前阶段
        self._current_progress = ""  # 当前进度详情
        self._total_stocks = 0  # 总股票数
        self._processed_stocks = 0  # 已处理股票数
        self._stats = {
            "sector_data": {"status": "pending", "message": ""},
            "history_data": {"status": "pending", "message": "", "count": 0},
            "financial_data": {"status": "pending", "message": "", "count": 0}
        }
    
    def should_preload(self) -> bool:
        """判断是否应该执行预下载"""
        if not self.config.enabled:
            logger.info("数据预下载未启用")
            return False

        return True

    # --- 配置指纹：检测预下载配置是否变更 ---

    FINGERPRINT_FILE = ".preload_fingerprint.json"

    def _get_config_fingerprint(self, stock_list: List[str]) -> dict:
        """生成当前预下载配置的指纹"""
        return {
            "start_date": self.config.start_date,
            "end_date": self.config.end_date,
            "periods": sorted(self.config.periods),
            "stock_list_hash": hashlib.md5(
                ",".join(sorted(stock_list)).encode()
            ).hexdigest(),
            "stock_count": len(stock_list),
        }

    def _get_fingerprint_path(self) -> str:
        settings = get_settings()
        data_path = settings.xtquant.data.path
        return os.path.join(data_path, self.FINGERPRINT_FILE)

    def _load_saved_fingerprint(self) -> Optional[dict]:
        path = self._get_fingerprint_path()
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def _save_fingerprint(self, fingerprint: dict):
        path = self._get_fingerprint_path()
        try:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(fingerprint, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"[预下载] 保存配置指纹失败: {e}")

    def _config_changed(self, stock_list: List[str]) -> bool:
        """检查预下载配置是否与上次不同"""
        current = self._get_config_fingerprint(stock_list)
        saved = self._load_saved_fingerprint()
        if saved is None:
            logger.info("[预下载] 未找到历史配置指纹，需要下载")
            return True
        changed_keys = [k for k in current if current.get(k) != saved.get(k)]
        if changed_keys:
            logger.info(f"[预下载] 配置已变更 ({', '.join(changed_keys)})，需要重新下载")
            return True
        return False
    
    def start(self):
        """启动预下载（根据配置决定同步或异步）"""
        if not self.should_preload():
            return
        
        if self.config.async_mode:
            self._start_async()
        else:
            self._run_preload()
    
    def _start_async(self):
        """异步启动预下载（不阻塞主线程）"""
        # 启动进度监控线程
        self._progress_thread = threading.Thread(
            target=self._progress_monitor,
            daemon=True,
            name="PreloadProgressMonitor"
        )
        self._progress_thread.start()
        
        # 启动预下载线程
        self._thread = threading.Thread(
            target=self._run_preload,
            daemon=True,
            name="DataPreloader"
        )
        self._thread.start()
        logger.info("数据预下载已在后台启动")
    
    def _progress_monitor(self):
        """进度监控线程，定期打印下载进度"""
        last_print_time = time.time()
        
        while self._is_running or self._start_time is None:
            time.sleep(1)  # 每秒检查一次
            
            # 等待预下载开始
            if self._start_time is None:
                continue
            
            # 检查是否需要打印进度
            current_time = time.time()
            if current_time - last_print_time >= self.PROGRESS_INTERVAL:
                self._print_progress()
                last_print_time = current_time
            
            # 如果预下载结束，退出监控
            if not self._is_running:
                break
    
    def _print_progress(self):
        """打印当前进度"""
        if self._start_time is None:
            return

        elapsed = time.time() - self._start_time
        elapsed_str = self._format_time(elapsed)

        # 构建进度信息
        progress_parts = [f"[预下载进度] 已运行: {elapsed_str}"]

        if self._current_stage:
            progress_parts.append(f"当前阶段: {self._current_stage}")

        if self._current_progress:
            progress_parts.append(self._current_progress)

        if self._total_stocks > 0:
            percent = (self._processed_stocks / self._total_stocks) * 100
            progress_parts.append(f"进度: {self._processed_stocks}/{self._total_stocks} ({percent:.1f}%)")
        elif self._current_stage:
            # 还没收到回调数据时显示等待中
            progress_parts.append("进度: 等待中...")

        # 打印已完成的阶段
        completed = []
        for key, value in self._stats.items():
            status = value.get("status")
            if status == "success":
                completed.append(f"{key}(✓)")
            elif status == "skipped":
                completed.append(f"{key}(跳过)")
        if completed:
            progress_parts.append(f"已完成: {', '.join(completed)}")

        logger.info(" | ".join(progress_parts))
    
    def _format_time(self, seconds: float) -> str:
        """格式化时间"""
        if seconds < 60:
            return f"{seconds:.0f}秒"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}分{secs}秒"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}时{minutes}分"
    
    def _run_preload(self):
        """执行预下载任务"""
        self._is_running = True
        self._start_time = time.time()
        
        logger.info("=" * 60)
        logger.info("开始数据预下载...")
        logger.info("=" * 60)
        
        try:
            # 导入 xtdata（仅在非 mock 模式下）
            from xtquant import xtdata
            
            # 1. 下载板块数据
            if self.config.sector_data:
                self._download_sector_data(xtdata)
            
            # 2. 展开股票列表（处理板块代码）
            stock_list = self._expand_stock_list(xtdata, self.config.stock_list)
            
            # 3. 下载历史行情数据
            if stock_list and self.config.periods:
                self._download_history_data(xtdata, stock_list)

            # 4. 下载财务数据
            if stock_list and self.config.financial_tables:
                self._download_financial_data(xtdata, stock_list)
            
            elapsed = time.time() - self._start_time
            logger.info("=" * 60)
            logger.info(f"数据预下载完成，耗时: {elapsed:.2f} 秒")
            logger.info(f"统计: {self._format_stats()}")
            logger.info("=" * 60)
            
        except ImportError as e:
            logger.warning(f"无法导入 xtquant，跳过预下载: {e}")
        except Exception as e:
            logger.error(f"数据预下载失败: {e}")
        finally:
            self._is_running = False
    
    def _download_with_timeout(self, func, timeout: int = None, description: str = "下载") -> tuple:
        """带超时的下载执行器

        Args:
            func: 要执行的下载函数
            timeout: 超时时间（秒），默认使用 DOWNLOAD_TIMEOUT
            description: 描述信息，用于日志

        Returns:
            (success: bool, error: Exception or None)
        """
        if timeout is None:
            timeout = self.DOWNLOAD_TIMEOUT

        result = {"success": False, "error": None}

        def do_task():
            try:
                func()
                result["success"] = True
            except Exception as e:
                result["error"] = e

        thread = threading.Thread(target=do_task, daemon=True)
        thread.start()

        start = time.time()
        last_heartbeat = start
        while thread.is_alive():
            thread.join(timeout=1)
            if not thread.is_alive():
                break

            now = time.time()
            if now - start >= timeout:
                logger.warning(f"[预下载] {description}超时({timeout}秒)")
                return False, TimeoutError(f"{description}超时")

            if now - last_heartbeat >= 10:
                logger.info(f"[预下载] {description}进行中，已等待 {int(now - start)} 秒")
                last_heartbeat = now

        return result["success"], result["error"]

    @staticmethod
    def _is_intraday_period(period: str) -> bool:
        """Whether period is intraday (minute/hour level)."""
        if not period:
            return False
        period = period.lower()
        return period.endswith("m") or period.endswith("h")

    def _resolve_history_batch_size(self, period: str) -> int:
        """Resolve batch size by period."""
        if self._is_intraday_period(period):
            return max(self.BATCH_SIZE, self.INTRADAY_BATCH_SIZE)
        return self.BATCH_SIZE

    def _download_history_batch_with_split_retry(
        self,
        xtdata,
        batch: List[str],
        period: str,
        start_time_str: str,
        end_time_str: str,
        batch_label: str,
        split_level: int = 0,
    ) -> tuple:
        """Download one history batch; on timeout, split and retry recursively."""
        if not batch:
            return 0, 0, False

        if self._check_timeout():
            logger.warning(f"[预下载] {period} 批次 {batch_label} 前检测到全局超时，停止当前周期")
            return 0, len(batch), True

        self._current_progress = (
            f"周期: {period} | 批次 {batch_label} 下载中..."
            f" (n={len(batch)}, split={split_level})"
        )
        batch_begin = time.time()
        success, error = self._download_with_timeout(
            lambda b=batch: xtdata.download_history_data2(
                stock_list=b,
                period=period,
                start_time=start_time_str,
                end_time=end_time_str,
                incrementally=True,
            ),
            timeout=self.HISTORY_BATCH_TIMEOUT,
            description=f"{period} 批次 {batch_label} (n={len(batch)}, split={split_level})",
        )

        if success:
            duration = time.time() - batch_begin
            if duration > self.DOWNLOAD_TIMEOUT:
                logger.warning(
                    f"[预下载] {period} 批次 {batch_label} 耗时较长: {duration:.1f}秒"
                )
            return len(batch), 0, False

        if isinstance(error, TimeoutError):
            if len(batch) == 1:
                logger.warning(f"[预下载] {period} 批次 {batch_label} 单股超时: {batch[0]}")
                return 0, 1, False

            if split_level >= self.HISTORY_SPLIT_MAX_DEPTH:
                logger.warning(
                    f"[预下载] {period} 批次 {batch_label} 达到最大二分层级({self.HISTORY_SPLIT_MAX_DEPTH})，标记失败 {len(batch)} 只"
                )
                return 0, len(batch), False

            mid = len(batch) // 2
            left_batch = batch[:mid]
            right_batch = batch[mid:]
            logger.warning(
                f"[预下载] {period} 批次 {batch_label} 超时，二分重试: {len(left_batch)} + {len(right_batch)}"
            )
            if self.HISTORY_SPLIT_RETRY_COOLDOWN > 0:
                time.sleep(self.HISTORY_SPLIT_RETRY_COOLDOWN)

            left_success, left_fail, left_abort = self._download_history_batch_with_split_retry(
                xtdata=xtdata,
                batch=left_batch,
                period=period,
                start_time_str=start_time_str,
                end_time_str=end_time_str,
                batch_label=f"{batch_label}.L",
                split_level=split_level + 1,
            )
            if left_abort:
                # 右半批次未尝试，按失败统计，避免进度和统计不一致
                return left_success, left_fail + len(right_batch), True

            right_success, right_fail, right_abort = self._download_history_batch_with_split_retry(
                xtdata=xtdata,
                batch=right_batch,
                period=period,
                start_time_str=start_time_str,
                end_time_str=end_time_str,
                batch_label=f"{batch_label}.R",
                split_level=split_level + 1,
            )
            return left_success + right_success, left_fail + right_fail, right_abort

        logger.warning(f"[预下载] {period} 批次 {batch_label} 失败: {error}")
        return 0, len(batch), False

    def _init_vip_datacenter(self):
        """初始化VIP数据中心（tick数据需要VIP权限）"""
        if not self.config.vip_token:
            logger.warning("[预下载] 未配置vip_token，tick数据下载可能失败")
            return

        try:
            from xtquant import xtdatacenter as xtdc
            logger.info("[预下载] 初始化VIP数据中心...")
            xtdc.set_token(self.config.vip_token)
            xtdc.init()
            logger.info("[预下载] VIP数据中心初始化完成")
        except Exception as e:
            logger.error(f"[预下载] VIP数据中心初始化失败: {e}")

    def _download_sector_data(self, xtdata):
        """下载板块数据（每次都更新）"""
        self._current_stage = "板块数据"
        self._current_progress = "下载中..."

        try:
            logger.info("[预下载] 正在下载板块数据...")

            success, error = self._download_with_timeout(
                xtdata.download_sector_data,
                description="板块数据下载"
            )

            if success:
                # 验证下载结果
                new_sectors = xtdata.get_sector_list()
                count = len(new_sectors) if new_sectors else 0
                self._stats["sector_data"] = {"status": "success", "message": f"下载完成，{count} 个板块"}
                logger.info(f"[预下载] 板块数据下载完成，共 {count} 个板块")
            elif isinstance(error, TimeoutError):
                self._stats["sector_data"] = {"status": "skipped", "message": "下载超时"}
            else:
                raise error if error else Exception("未知错误")

        except Exception as e:
            self._stats["sector_data"] = {"status": "failed", "message": str(e)}
            logger.error(f"[预下载] 板块数据下载失败: {e}")
    
    def _expand_stock_list(self, xtdata, stock_list: List[str]) -> List[str]:
        """展开股票列表，将板块代码转换为成分股"""
        if not stock_list:
            return []
        
        expanded = []
        for item in stock_list:
            # 检查是否是板块代码（不包含 .SZ/.SH 等后缀）
            if "." not in item:
                try:
                    # 尝试获取板块成分股
                    sector_stocks = xtdata.get_stock_list_in_sector(item)
                    if sector_stocks:
                        logger.info(f"[预下载] 展开板块 '{item}': {len(sector_stocks)} 只股票")
                        expanded.extend(sector_stocks)
                    else:
                        logger.warning(f"[预下载] 板块 '{item}' 无成分股或不存在")
                except Exception as e:
                    logger.warning(f"[预下载] 获取板块 '{item}' 成分股失败: {e}")
            else:
                expanded.append(item)
        
        # 去重
        expanded = list(set(expanded))
        logger.info(f"[预下载] 股票列表展开完成，共 {len(expanded)} 只股票")
        return expanded
    
    def _check_local_history_data(self, xtdata, stock_list: List[str], period: str, sample_size: int = 5) -> bool:
        """检查本地是否已有足够新的历史数据

        通过抽样检查几只股票的本地数据来判断是否需要下载。
        注意：配置变更检测由 _config_changed() 负责，此方法只检查数据新鲜度。

        Args:
            xtdata: xtdata 模块
            stock_list: 股票列表
            period: K线周期
            sample_size: 抽样数量

        Returns:
            True 如果本地数据足够新，可以跳过下载
        """
        import random
        from datetime import datetime, timedelta

        if not stock_list:
            return False

        # 抽样检查
        sample_stocks = random.sample(stock_list, min(sample_size, len(stock_list)))

        # 获取最近的交易日（简单处理：如果是周末则往前推）
        today = datetime.now()
        # 计算一个合理的检查日期范围（最近3个交易日）
        check_start = (today - timedelta(days=7)).strftime("%Y%m%d")

        stocks_with_recent_data = 0

        for stock_code in sample_stocks:
            try:
                # 尝试获取本地数据，不触发网络请求
                data = xtdata.get_local_data(
                    field_list=['close'],
                    stock_list=[stock_code],
                    period=period,
                    start_time=check_start,
                    end_time='',
                    count=-1,
                    fill_data=False
                )

                if data and stock_code in data:
                    df = data[stock_code]
                    if df is not None and len(df) > 0:
                        latest_time = df.index[-1] if hasattr(df, 'index') else None
                        if latest_time is not None:
                            stocks_with_recent_data += 1
            except Exception:
                pass

        # 如果大部分抽样股票都有最近数据，认为本地数据足够新
        has_recent_data = stocks_with_recent_data >= len(sample_stocks) * 0.8

        if has_recent_data:
            logger.info(f"[预下载] {period} 周期本地数据检测: {stocks_with_recent_data}/{len(sample_stocks)} 只股票有最近数据，跳过下载")
        else:
            logger.info(f"[预下载] {period} 周期本地数据检测: {stocks_with_recent_data}/{len(sample_stocks)} 只股票有最近数据，需要下载")

        return has_recent_data
    
    def _download_history_data(self, xtdata, stock_list: List[str]):
        """下载历史行情数据（逐个股票下载）"""
        from datetime import datetime

        self._current_stage = "历史行情数据"

        logger.info(f"[预下载] 正在检查/下载历史行情数据: {len(stock_list)} 只股票, 周期: {self.config.periods}")

        start_time_str = self.config.start_date
        end_time_str = self.config.end_date or datetime.now().strftime("%Y%m%d")
        logger.info(f"[预下载] 下载时间范围: {start_time_str} ~ {end_time_str}")

        # 检查配置是否变更，变更则跳过本地数据检测直接下载
        config_changed = self._config_changed(stock_list)

        success_count = 0
        fail_count = 0
        skipped_count = 0

        for period_idx, period in enumerate(self.config.periods):
            total = len(stock_list)
            self._total_stocks = total
            self._processed_stocks = 0
            self._current_progress = f"周期: {period} ({period_idx + 1}/{len(self.config.periods)}) | 检查本地数据..."

            # 配置未变更时，才检查本地数据是否可以跳过
            if not config_changed and self._check_local_history_data(xtdata, stock_list, period):
                skipped_count += total
                self._processed_stocks = total
                self._current_progress = f"周期: {period} | 已跳过(本地已有数据)"
                continue

            logger.info(f"[预下载] 逐个下载 {period} 周期数据，共 {total} 只股票...")

            for idx, stock_code in enumerate(stock_list):
                self._processed_stocks = idx + 1
                self._current_progress = f"周期: {period} | 下载: {idx + 1}/{total} ({stock_code})"

                try:
                    success, error = self._download_with_timeout(
                        lambda sc=stock_code: xtdata.download_history_data(
                            sc,
                            period=period,
                            start_time=start_time_str,
                            end_time=end_time_str,
                            incrementally=True
                        ),
                        description=f"{stock_code} {period}"
                    )
                    if success:
                        success_count += 1
                    elif isinstance(error, TimeoutError):
                        fail_count += 1
                        logger.warning(f"[预下载] {stock_code} {period} 超时，跳过")
                    else:
                        fail_count += 1
                        logger.debug(f"[预下载] 下载 {stock_code} {period} 失败: {error}")
                except Exception as e:
                    fail_count += 1
                    logger.debug(f"[预下载] 下载 {stock_code} {period} 失败: {e}")

                # 每100只股票打印一次进度
                if (idx + 1) % 100 == 0:
                    logger.info(f"[预下载] {period} 进度: {idx + 1}/{total}")

                # 检查超时
                if self._check_timeout():
                    logger.warning("[预下载] 历史数据下载超时，提前结束")
                    break

            self._processed_stocks = total
            self._current_progress = f"周期: {period} | 下载完成"
            logger.info(f"[预下载] {period} 周期数据下载完成")

            if self._check_timeout():
                break

        self._stats["history_data"] = {
            "status": "success" if fail_count == 0 else "partial",
            "message": f"成功: {success_count}, 跳过: {skipped_count}, 失败: {fail_count}",
            "count": success_count
        }
        logger.info(f"[预下载] 历史行情数据下载完成 - 成功: {success_count}, 跳过(已有数据): {skipped_count}, 失败: {fail_count}")

        # 下载完成后保存配置指纹
        if success_count > 0 or skipped_count > 0:
            self._save_fingerprint(self._get_config_fingerprint(stock_list))

    def _check_local_financial_data(self, xtdata, stock_list: List[str], table_list: List[str], sample_size: int = 5) -> bool:
        """检查本地是否已有财务数据
        
        通过抽样检查几只股票的财务数据来判断是否需要下载
        
        Args:
            xtdata: xtdata 模块
            stock_list: 股票列表
            table_list: 财务表列表
            sample_size: 抽样数量
            
        Returns:
            True 如果本地数据存在，可以跳过下载
        """
        import random
        
        if not stock_list or not table_list:
            return False
        
        # 抽样检查
        sample_stocks = random.sample(stock_list, min(sample_size, len(stock_list)))
        
        stocks_with_data = 0
        
        for stock_code in sample_stocks:
            try:
                # 尝试获取本地财务数据
                data = xtdata.get_financial_data(
                    [stock_code],
                    table_list=table_list[:1],  # 只检查第一张表
                    start_time='',
                    end_time=''
                )
                
                if data and stock_code in data:
                    table_data = data[stock_code]
                    # 检查是否有数据
                    if table_data and len(table_data) > 0:
                        # 检查第一张表是否有数据
                        first_table = table_list[0]
                        if first_table in table_data:
                            df = table_data[first_table]
                            if df is not None and len(df) > 0:
                                stocks_with_data += 1
            except Exception:
                pass
        
        # 如果大部分抽样股票都有财务数据，认为本地数据存在
        has_data = stocks_with_data >= len(sample_stocks) * 0.8
        
        if has_data:
            logger.info(f"[预下载] 财务数据本地检测: {stocks_with_data}/{len(sample_stocks)} 只股票有数据，跳过下载")
        else:
            logger.info(f"[预下载] 财务数据本地检测: {stocks_with_data}/{len(sample_stocks)} 只股票有数据，需要下载")
        
        return has_data
    
    def _download_financial_data(self, xtdata, stock_list: List[str]):
        """下载财务数据（使用带进度回调的批量接口）"""
        self._current_stage = "财务数据"
        self._total_stocks = len(stock_list)
        self._processed_stocks = 0
        self._current_progress = f"检查本地数据..."

        logger.info(f"[预下载] 正在检查/下载财务数据: {len(stock_list)} 只股票, 表: {self.config.financial_tables}")

        # 先检查本地是否已有财务数据
        if self._check_local_financial_data(xtdata, stock_list, self.config.financial_tables):
            self._stats["financial_data"] = {
                "status": "skipped",
                "message": f"本地已有数据，跳过下载",
                "count": 0
            }
            self._processed_stocks = len(stock_list)
            self._current_progress = "已跳过(本地已有数据)"
            return

        try:
            # 设置下载中进度显示
            self._current_progress = f"下载中..."

            # 进度回调函数
            def progress_callback(data):
                if isinstance(data, dict):
                    finished = data.get('finished', 0)
                    total = data.get('total', 0)
                    stockcode = data.get('stockcode', '')
                    if total > 0:
                        self._total_stocks = total
                        self._processed_stocks = finished
                        self._current_progress = f"下载: {finished}/{total} ({stockcode})"

            # 使用批量下载接口（同步执行，callback 用于进度显示）
            xtdata.download_financial_data2(
                stock_list=stock_list,
                table_list=self.config.financial_tables,
                start_time='',
                end_time='',
                callback=progress_callback
            )
            self._processed_stocks = len(stock_list)
            self._current_progress = f"下载完成"
            self._stats["financial_data"] = {
                "status": "success",
                "message": f"{len(stock_list)} 只股票, {len(self.config.financial_tables)} 张表",
                "count": len(stock_list) * len(self.config.financial_tables)
            }
            logger.info("[预下载] 财务数据下载完成")
        except Exception as e:
            self._stats["financial_data"] = {"status": "failed", "message": str(e), "count": 0}
            logger.error(f"[预下载] 财务数据下载失败: {e}")
    
    def _check_timeout(self) -> bool:
        """检查是否超时"""
        if self._start_time is None:
            return False
        elapsed = time.time() - self._start_time
        return elapsed > self.config.timeout
    
    def _format_stats(self) -> str:
        """格式化统计信息"""
        parts = []
        status_icons = {
            "success": "✓",
            "partial": "△",
            "skipped": "○",
            "failed": "✗",
        }
        for key, value in self._stats.items():
            status = value.get("status", "unknown")
            if status == "pending":
                continue
            icon = status_icons.get(status, "?")
            parts.append(f"{key}: {icon}")
        return ", ".join(parts) if parts else "无"
    
    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self._is_running
    
    @property
    def stats(self) -> dict:
        """获取统计信息"""
        return self._stats.copy()


# 全局预加载器实例
_preloader: Optional[DataPreloader] = None


def get_preloader() -> Optional[DataPreloader]:
    """获取预加载器实例"""
    return _preloader


def start_preload():
    """启动数据预下载（根据配置决定同步或异步）"""
    global _preloader
    
    settings = get_settings()
    preload_config = settings.xtquant.data.preload
    mode = settings.xtquant.mode
    
    _preloader = DataPreloader(preload_config, mode)
    _preloader.start()
    
    return _preloader


def start_preload_sync():
    """
    同步启动数据预下载（阻塞直到完成）

    无论配置中的 async_mode 如何设置，都会同步执行预下载，
    适用于需要确保数据准备完成后再启动服务的场景。
    """
    global _preloader

    settings = get_settings()
    preload_config = settings.xtquant.data.preload
    mode = settings.xtquant.mode

    _preloader = DataPreloader(preload_config, mode)

    if not _preloader.should_preload():
        return _preloader

    # 启动进度监控线程（后台运行）
    _preloader._progress_thread = threading.Thread(
        target=_preloader._progress_monitor,
        daemon=True,
        name="PreloadProgressMonitor"
    )
    _preloader._progress_thread.start()

    # 强制同步执行，直接调用 _run_preload（阻塞直到完成）
    _preloader._run_preload()

    return _preloader
