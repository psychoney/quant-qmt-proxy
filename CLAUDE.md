# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

xtquant-proxy is a Python proxy service that wraps the 国金 QMT xtquant SDK, exposing quantitative trading data and trading functions through REST API, gRPC, and WebSocket interfaces. The project targets Windows (QMT requirement) with Python 3.12+.

## Common Commands

### Start the Service
```bash
# Set mode via APP_MODE environment variable (mock/dev/prod)
# Default is dev mode
python run.py

# PowerShell examples:
$env:APP_MODE="mock"; python run.py   # No QMT needed, mock data
$env:APP_MODE="dev"; python run.py    # Real data, trading blocked
$env:APP_MODE="prod"; python run.py   # Real data, real trading
```

### Run Tests
```bash
pytest tests/ -v              # All tests
pytest tests/rest/ -v         # REST API tests only
pytest tests/grpc/ -v         # gRPC tests only
pytest tests/ -k "market"     # Tests matching keyword
pytest tests/ -m grpc         # Tests with specific marker
pytest tests/rest/test_data_api.py::TestDataAPI::test_get_market_data -v  # Single test
```

### Generate Protobuf Code
```bash
python scripts/generate_proto.py
```
This generates Python stubs in `generated/` from `.proto` files in `proto/`.

### Install Dependencies
```bash
pip install -r requirements.txt
# Or with poetry:
poetry install
```

## Architecture

### Layered Design
```
REST Routers (app/routers/)     gRPC Services (app/grpc_services/)
           \                           /
            \                         /
             +-- Business Services --+    (app/services/)
                       |
              xtquant SDK (xtdata/xttrader)
```

REST and gRPC share the same business logic layer. The services are:
- `DataService` - Market data, financial data, sector data (wraps xtdata)
- `TradingService` - Orders, positions, account info (wraps xttrader)
- `SubscriptionManager` - Real-time quote subscriptions with async queues

### Key Components
- **app/config.py** - Singleton settings loaded from `config.yml`, mode-specific config via `APP_MODE`
- **app/dependencies.py** - FastAPI dependency injection, singleton service instances
- **app/main.py** - FastAPI app entry point
- **app/grpc_server.py** - gRPC server entry point
- **run.py** - Combined launcher (REST + gRPC in separate threads)

### Three Run Modes
| Mode | xtquant Connection | Real Trading | Use Case |
|------|-------------------|--------------|----------|
| mock | No | No | Frontend dev, testing without QMT |
| dev | Yes | No (intercepted) | Strategy development with real data |
| prod | Yes | Yes | Production trading |

### API Authentication
Requests require `X-API-Key` header. Valid keys are configured per-mode in `config.yml`.

### Proto Files
Located in `proto/`: `common.proto`, `data.proto`, `trading.proto`, `health.proto`. Run `python scripts/generate_proto.py` after modifying.

## Testing

Tests use pytest with fixtures in `conftest.py` files. Test markers:
- `rest` - REST API tests
- `grpc` - gRPC tests
- `integration` - Requires running service
- `slow` - Long-running tests

Set `SKIP_INTEGRATION_TESTS = False` in `tests/rest/config.py` or `tests/grpc/config.py` to run tests against live service.

## Ports
- REST API: 8000 (Swagger at /docs, ReDoc at /redoc)
- gRPC: 50051
- WebSocket: /ws/quote/{subscription_id}
