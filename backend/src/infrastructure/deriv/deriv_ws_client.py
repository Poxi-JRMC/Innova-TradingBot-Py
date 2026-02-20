"""Deriv WebSocket client (robust) using asyncio + websockets.

Features:
- Authenticate with API token
- Heartbeat (ping) task
- Reconnection with exponential backoff + jitter
- MessageRouter: correlate req_id -> response Future
- Subscription resubscribe after reconnect
"""

from __future__ import annotations

import asyncio
import json
import random
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

import websockets
from websockets.client import WebSocketClientProtocol
from websockets.exceptions import ConnectionClosed
from src.infrastructure.logging.logging import get_logger

JsonDict = Dict[str, Any]


class DerivWSError(RuntimeError):
    pass


@dataclass(frozen=True)
class Subscription:
    name: str
    request: JsonDict
    on_message: Callable[[JsonDict], Awaitable[None]]


class MessageRouter:
    def __init__(self) -> None:
        self._futures: Dict[int, asyncio.Future[JsonDict]] = {}
        self._lock = asyncio.Lock()

    async def register(self, req_id: int) -> asyncio.Future[JsonDict]:
        async with self._lock:
            fut: asyncio.Future[JsonDict] = asyncio.get_running_loop().create_future()
            self._futures[req_id] = fut
            return fut

    async def resolve(self, req_id: int, msg: JsonDict) -> None:
        async with self._lock:
            fut = self._futures.pop(req_id, None)
            if fut and not fut.done():
                fut.set_result(msg)

    async def reject_all(self, exc: BaseException) -> None:
        async with self._lock:
            for fut in self._futures.values():
                if not fut.done():
                    fut.set_exception(exc)
            self._futures.clear()


class DerivWSClient:
    def __init__(
        self,
        websocket_url: str,
        app_id: str,
        api_token: str,
        *,
        heartbeat_interval_sec: float = 15.0,
        request_timeout_sec: float = 10.0,
        max_reconnect_backoff_sec: float = 60.0,
    ) -> None:
        self._logger = get_logger("deriv_ws")
        self._url = f"{websocket_url}?app_id={app_id}"
        self._token = api_token
        self._heartbeat_interval = heartbeat_interval_sec
        self._request_timeout = request_timeout_sec
        self._max_backoff = max_reconnect_backoff_sec

        self._ws: Optional[WebSocketClientProtocol] = None
        self._router = MessageRouter()
        self._connected_evt = asyncio.Event()
        self._stop_evt = asyncio.Event()

        self._runner_task: Optional[asyncio.Task[None]] = None
        self._reader_task: Optional[asyncio.Task[None]] = None
        self._heartbeat_task: Optional[asyncio.Task[None]] = None

        self._req_id = 10_000
        self._subscriptions: Dict[str, Subscription] = {}
        self._sub_ids: Dict[str, str] = {}

    @property
    def is_connected(self) -> bool:
        return self._connected_evt.is_set()

    async def start(self) -> None:
        self._stop_evt.clear()
        self._runner_task = asyncio.create_task(self._run_forever())

    async def stop(self) -> None:
        self._stop_evt.set()
        if self._runner_task:
            self._runner_task.cancel()
        await self._disconnect()

    async def wait_until_connected(self, timeout: float = 30.0) -> None:
        await asyncio.wait_for(self._connected_evt.wait(), timeout=timeout)

    async def _run_forever(self) -> None:
        backoff = 1.0
        while not self._stop_evt.is_set():
            try:
                await self._connect_and_run()
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._logger.error("ws_loop_error", error=str(e))

            if self._stop_evt.is_set():
                break

            jitter = random.random() * 0.3 * backoff
            sleep_for = min(self._max_backoff, backoff + jitter)
            self._logger.warning("reconnect_backoff", seconds=sleep_for)
            await asyncio.sleep(sleep_for)
            backoff = min(self._max_backoff, backoff * 2)

    async def _connect_and_run(self) -> None:
        self._logger.info("ws_connect", url=self._url)

        async with websockets.connect(
            self._url,
            ping_interval=None,  # we manage ping manually
            close_timeout=5,
            max_queue=256,
        ) as ws:
            self._ws = ws
            self._connected_evt.clear()

            # ✅ Start reader FIRST so requests can be resolved (authorize needs it)
            self._reader_task = asyncio.create_task(self._reader_loop())

            try:
                # ✅ Authorize using raw_request (doesn't wait for connected event)
                auth_resp = await self._raw_request({"authorize": self._token})
                if auth_resp.get("error"):
                    raise DerivWSError(f"Auth error: {auth_resp['error']}")

                self._logger.info("ws_authorized")

                # ✅ Now we are fully connected for normal requests
                self._connected_evt.set()

                # Start heartbeat AFTER auth
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

                # Re-activate subscriptions after reconnect
                await self._resubscribe_all()

                # Keep running until one task fails
                done, pending = await asyncio.wait(
                    [self._reader_task, self._heartbeat_task],
                    return_when=asyncio.FIRST_EXCEPTION,
                )

                for t in done:
                    exc = t.exception()
                    if exc:
                        raise exc

                for t in pending:
                    t.cancel()

            except Exception:
                # Reject any pending requests so they don't hang
                await self._router.reject_all(DerivWSError("Disconnected during connect/auth"))
                raise
            finally:
                # Ensure connected flag is cleared if we leave the context
                self._connected_evt.clear()

    async def _disconnect(self) -> None:
        self._connected_evt.clear()

        # ✅ Reject pending futures to avoid hanging tasks
        await self._router.reject_all(DerivWSError("Disconnected"))

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

        if self._reader_task:
            self._reader_task.cancel()
            self._reader_task = None

        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    def _next_req_id(self) -> int:
        self._req_id += 1
        return self._req_id

    async def _raw_request(self, payload: JsonDict) -> JsonDict:
        """Send a request without waiting for the connected event.
        Use only during connect/auth phase, or internally.
        """
        if not self._ws:
            raise DerivWSError("WebSocket not open")

        req_id = self._next_req_id()
        payload = dict(payload)
        payload["req_id"] = req_id

        fut = await self._router.register(req_id)
        await self._ws.send(json.dumps(payload))

        try:
            resp = await asyncio.wait_for(fut, timeout=self._request_timeout)
        except asyncio.TimeoutError as e:
            raise DerivWSError(f"Request timeout req_id={req_id}") from e

        return resp

    async def request(self, payload: JsonDict) -> JsonDict:
        """Safe request used by other modules (waits until authorized/connected)."""
        await self.wait_until_connected()
        return await self._raw_request(payload)

    async def subscribe(
        self,
        name: str,
        request: JsonDict,
        on_message: Callable[[JsonDict], Awaitable[None]],
    ) -> None:
        self._subscriptions[name] = Subscription(name=name, request=request, on_message=on_message)
        if self.is_connected:
            await self._activate_subscription(name)

    async def unsubscribe(self, name: str) -> None:
        sub_id = self._sub_ids.get(name)
        self._subscriptions.pop(name, None)
        if not sub_id:
            return
        try:
            await self.request({"forget": sub_id})
        finally:
            self._sub_ids.pop(name, None)

    async def _activate_subscription(self, name: str) -> None:
        sub = self._subscriptions[name]
        resp = await self.request(sub.request)
        if resp.get("error"):
            raise DerivWSError(f"Subscribe error: {resp['error']}")
        sub_id = (resp.get("subscription") or {}).get("id")
        if sub_id:
            self._sub_ids[name] = sub_id
        self._logger.info("subscribed", name=name, sub_id=sub_id)

    async def _resubscribe_all(self) -> None:
        self._sub_ids.clear()
        for name in list(self._subscriptions.keys()):
            await self._activate_subscription(name)

    async def _reader_loop(self) -> None:
        assert self._ws is not None
        try:
            while True:
               raw = await self._ws.recv()
               msg = json.loads(raw)

               req_id = msg.get("req_id")
               if isinstance(req_id, int):
                 await self._router.resolve(req_id, msg)

               msg_type = msg.get("msg_type")
               if msg_type in {"tick", "ohlc", "proposal"}:
                sub_id = (msg.get("subscription") or {}).get("id")
                if sub_id:
                    for name, sid in self._sub_ids.items():
                        if sid == sub_id:
                            await self._subscriptions[name].on_message(msg)
                            break
        except ConnectionClosed:
         # cierre normal o reconexión -> lo dejamos salir limpio
          return
        except Exception as e:
         self._logger.error("reader_loop_error", error=str(e))
         raise
 
    async def _heartbeat_loop(self) -> None:
        assert self._ws is not None
        while True:
            await asyncio.sleep(self._heartbeat_interval)
            try:
                pong_waiter = await self._ws.ping()
                await asyncio.wait_for(pong_waiter, timeout=5.0)
                self._logger.debug("ws_ping_ok")
            except Exception as e:
                self._logger.warning("ws_ping_failed", error=str(e))
                raise
