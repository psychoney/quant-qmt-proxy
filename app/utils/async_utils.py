"""
异步工具函数

提供将同步调用安全地在异步上下文中执行的工具函数，
防止阻塞事件循环导致整个服务卡死。
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any, Callable, TypeVar

from fastapi import HTTPException, status

from app.utils.logger import logger

T = TypeVar("T")

# 全局线程池，用于执行阻塞操作
# 使用较大的线程池以支持并发请求
_executor: ThreadPoolExecutor | None = None


def get_executor() -> ThreadPoolExecutor:
    """获取全局线程池（懒加载）"""
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=50, thread_name_prefix="async-worker-")
    return _executor


def shutdown_executor():
    """关闭全局线程池"""
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=False)
        _executor = None


async def run_sync(
    func: Callable[..., T],
    *args,
    timeout: float = 30.0,
    **kwargs
) -> T:
    """
    在线程池中执行同步函数，带超时保护。

    这是核心工具函数，用于在 async 路由中安全调用同步的 xtdata API，
    不会阻塞 FastAPI 的事件循环。

    Args:
        func: 要执行的同步函数
        *args: 传递给函数的位置参数
        timeout: 超时时间（秒），默认30秒
        **kwargs: 传递给函数的关键字参数

    Returns:
        函数的返回值

    Raises:
        HTTPException: 超时或执行失败时抛出

    Example:
        # 在 async 路由中使用
        results = await run_sync(data_service.get_market_data, request, timeout=60.0)
    """
    loop = asyncio.get_running_loop()
    executor = get_executor()

    # 使用 partial 绑定参数
    if kwargs:
        func_with_args = partial(func, *args, **kwargs)
    else:
        func_with_args = partial(func, *args) if args else func

    try:
        # 在线程池中执行，带超时
        result = await asyncio.wait_for(
            loop.run_in_executor(executor, func_with_args),
            timeout=timeout
        )
        return result
    except asyncio.TimeoutError:
        func_name = getattr(func, "__name__", str(func))
        logger.error(f"调用 {func_name} 超时 ({timeout}秒)")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"message": f"请求超时，操作未能在 {timeout} 秒内完成"}
        )
    except HTTPException:
        # 直接重新抛出 HTTPException
        raise
    except Exception as e:
        func_name = getattr(func, "__name__", str(func))
        logger.error(f"调用 {func_name} 失败: {e}")
        raise


async def run_sync_no_timeout(
    func: Callable[..., T],
    *args,
    **kwargs
) -> T:
    """
    在线程池中执行同步函数，无超时限制。

    用于那些确实需要较长时间执行且不适合设置超时的操作，
    如大批量数据下载。

    Args:
        func: 要执行的同步函数
        *args: 传递给函数的位置参数
        **kwargs: 传递给函数的关键字参数

    Returns:
        函数的返回值
    """
    loop = asyncio.get_running_loop()
    executor = get_executor()

    if kwargs:
        func_with_args = partial(func, *args, **kwargs)
    else:
        func_with_args = partial(func, *args) if args else func

    return await loop.run_in_executor(executor, func_with_args)
