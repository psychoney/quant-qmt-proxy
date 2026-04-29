from __future__ import annotations

import os
import sys

import uvicorn

sys.path.insert(0, os.path.dirname(__file__))

from app.config import Settings, _normalize_app_servers, get_settings
from app.grpc_server import create_grpc_server, serve as serve_grpc
from app.utils.logger import configure_logging_from_settings, logger


def run_rest_server(settings: Settings, reload_enabled: bool | None = None) -> None:
    if reload_enabled is None:
        reload_enabled = settings.app.debug and _normalize_app_servers(settings.app_servers) == "rest"
    uvicorn.run(
        "app.main:app",
        host=settings.app.host,
        port=settings.app.port,
        reload=reload_enabled,
        reload_includes=["*.py"] if reload_enabled else None,
        log_level=settings.logging.level.lower(),
        access_log=True,
        timeout_keep_alive=settings.uvicorn.timeout_keep_alive,
    )


def print_banner(settings: Settings) -> None:
    servers = _normalize_app_servers(settings.app_servers)
    account_profiles = len(settings.xtquant.trading.accounts)
    print("\n" + "=" * 72)
    print(f"{settings.app.name} {settings.app.version}")
    print("=" * 72)
    print(f"mode         : {settings.xtquant.mode.value}")
    print(f"servers      : {servers}")
    print(f"rest         : http://{settings.app.host}:{settings.app.port}")
    print(f"grpc         : {settings.grpc_host}:{settings.grpc_port}")
    print(f"accounts     : {account_profiles}")
    print(f"preload      : {'enabled' if settings.xtquant.data.preload.enabled else 'disabled'}")
    print(f"debug        : {settings.app.debug}")
    print("=" * 72 + "\n")


def main() -> None:
    settings = get_settings()
    settings.app_servers = _normalize_app_servers(settings.app_servers)
    configure_logging_from_settings(settings)
    print_banner(settings)

    if settings.xtquant.data.preload.enabled and settings.xtquant.mode.value != "mock":
        from app.services.data_preloader import start_preload_sync
        logger.info("启动数据预下载...")
        start_preload_sync()

    if settings.app_servers == "grpc":
        serve_grpc(settings)
        return

    if settings.app_servers == "rest":
        run_rest_server(settings)
        return

    if settings.app.debug:
        logger.warning("reload is disabled in all-in-one mode; use APP_SERVERS=rest for live reload")

    grpc_server = create_grpc_server(settings)
    grpc_server.start()
    bound_port = getattr(grpc_server, "_bound_port", settings.grpc_port)
    logger.info(f"gRPC server started on {settings.grpc_host}:{bound_port}")
    try:
        run_rest_server(settings, reload_enabled=False)
    finally:
        logger.info("stopping gRPC server")
        grpc_server.stop(grace=5)


if __name__ == "__main__":
    main()
