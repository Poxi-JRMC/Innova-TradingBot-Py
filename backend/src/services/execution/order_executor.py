from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Optional

from src.infrastructure.deriv.deriv_ws_client import DerivWSClient


JsonDict = Dict[str, Any]


@dataclass(frozen=True)
class ExecutedTrade:
    contract_id: int
    profit: float
    buy_price: float
    payout: float
    is_win: bool


class OrderExecutor:
    def __init__(self, client: DerivWSClient, *, symbol: str, currency: str = "USD") -> None:
        self.client = client
        self.symbol = symbol
        self.currency = currency

    async def execute_rise_fall(
        self,
        *,
        side: str,  # "CALL" or "PUT"
        stake: float,
        duration: int = 1,
        duration_unit: str = "m",
        symbol: Optional[str] = None,
        poll_sec: float = 1.0,
        timeout_sec: float = 180.0,
    ) -> ExecutedTrade:
        sym = symbol or self.symbol
        # 1) proposal
        proposal_req: JsonDict = {
            "proposal": 1,
            "amount": float(stake),
            "basis": "stake",
            "contract_type": side,  # CALL/PUT
            "currency": self.currency,
            "duration": int(duration),
            "duration_unit": duration_unit,
            "symbol": sym,
        }
        proposal = await self.client.request(proposal_req)
        if proposal.get("error"):
            raise RuntimeError(f"proposal_error: {proposal['error']}")

        proposal_id = (proposal.get("proposal") or {}).get("id")
        if not proposal_id:
            raise RuntimeError("proposal_missing_id")

        # 2) buy
        buy = await self.client.request({"buy": proposal_id, "price": float(stake)})
        if buy.get("error"):
            raise RuntimeError(f"buy_error: {buy['error']}")

        buy_info = buy.get("buy") or {}
        contract_id = buy_info.get("contract_id")
        if contract_id is None:
            raise RuntimeError("buy_missing_contract_id")

        buy_price = float(buy_info.get("buy_price") or stake)

        # 3) wait until sold
        elapsed = 0.0
        while elapsed < timeout_sec:
            poc = await self.client.request({"proposal_open_contract": 1, "contract_id": int(contract_id)})
            if poc.get("error"):
                raise RuntimeError(f"poc_error: {poc['error']}")

            poc_data = poc.get("proposal_open_contract") or {}
            is_sold = bool(poc_data.get("is_sold"))
            if is_sold:
                profit = float(poc_data.get("profit") or 0.0)
                payout = float(poc_data.get("payout") or 0.0)
                return ExecutedTrade(
                    contract_id=int(contract_id),
                    profit=profit,
                    buy_price=buy_price,
                    payout=payout,
                    is_win=(profit > 0),
                )

            await asyncio.sleep(poll_sec)
            elapsed += poll_sec

        raise TimeoutError("contract_wait_timeout")

    async def execute_multiplier(
        self,
        *,
        side: str,  # "CALL" or "PUT"
        stake: float,
        take_profit_usd: float,
        stop_loss_usd: float,
        duration: int,
        duration_unit: str = "s",
        multiplier: int = 10,
        symbol: Optional[str] = None,
        poll_sec: float = 1.0,
        timeout_sec: float = 86400.0,
    ) -> ExecutedTrade:
        """Buy multiplier contract with TP/SL. CALL -> MULTUP, PUT -> MULTDOWN."""
        sym = symbol or self.symbol
        contract_type = "MULTUP" if side.upper() == "CALL" else "MULTDOWN"
        limit_order: JsonDict = {
            "take_profit": int(round(max(0.01, take_profit_usd))),
            "stop_loss": int(round(max(0.01, stop_loss_usd))),
        }

        # Deriv multiplier contracts often require duration in seconds (e.g. 900 for 15 min)
        dur_sec = int(duration)
        dur_unit = duration_unit
        if duration_unit == "m":
            dur_sec = int(duration) * 60
            dur_unit = "s"
        elif duration_unit == "h":
            dur_sec = int(duration) * 3600
            dur_unit = "s"

        proposal_req: JsonDict = {
            "proposal": 1,
            "amount": float(stake),
            "basis": "stake",
            "contract_type": contract_type,
            "currency": self.currency,
            "duration": dur_sec,
            "duration_unit": dur_unit,
            "multiplier": int(multiplier),
            "symbol": sym,
        }
        proposal = await self.client.request(proposal_req)
        if proposal.get("error"):
            raise RuntimeError(f"proposal_error: {proposal['error']}")

        proposal_id = (proposal.get("proposal") or {}).get("id")
        if not proposal_id:
            raise RuntimeError("proposal_missing_id")

        buy_payload: JsonDict = {"buy": proposal_id, "price": float(stake), "limit_order": limit_order}
        buy = await self.client.request(buy_payload)
        if buy.get("error"):
            raise RuntimeError(f"buy_error: {buy['error']}")

        buy_info = buy.get("buy") or {}
        contract_id = buy_info.get("contract_id")
        if contract_id is None:
            raise RuntimeError("buy_missing_contract_id")

        buy_price = float(buy_info.get("buy_price") or stake)

        elapsed = 0.0
        while elapsed < timeout_sec:
            poc = await self.client.request({"proposal_open_contract": 1, "contract_id": int(contract_id)})
            if poc.get("error"):
                raise RuntimeError(f"poc_error: {poc['error']}")

            poc_data = poc.get("proposal_open_contract") or {}
            is_sold = bool(poc_data.get("is_sold"))
            if is_sold:
                profit = float(poc_data.get("profit") or 0.0)
                payout = float(poc_data.get("payout") or 0.0)
                return ExecutedTrade(
                    contract_id=int(contract_id),
                    profit=profit,
                    buy_price=buy_price,
                    payout=payout,
                    is_win=(profit > 0),
                )

            await asyncio.sleep(poll_sec)
            elapsed += poll_sec

        raise TimeoutError("contract_wait_timeout")
