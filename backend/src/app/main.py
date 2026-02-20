"""Entrypoint.

Usage:
  python -m src.app.main engine    # run trading engine
  python -m src.app.main api      # run FastAPI server
  python -m src.app.main backtest  # backtest con historial Deriv (o: python -m src.app.backtest)
"""

from __future__ import annotations

import argparse
import asyncio

import uvicorn

from src.app.engine import run_engine


def main() -> None:
    parser = argparse.ArgumentParser("deriv-trading-bot")
    parser.add_argument("command", choices=["engine", "api", "backtest"], help="What to run")
    args = parser.parse_args()

    if args.command == "engine":
        asyncio.run(run_engine())
        return

    if args.command == "api":
        uvicorn.run("src.controllers.api_controller:app", host="0.0.0.0", port=8000, reload=False)
        return

    if args.command == "backtest":
        from src.app.backtest import run_backtest
        asyncio.run(run_backtest())
        return


if __name__ == "__main__":
    main()
