from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Protocol

import httpx


class StreamError(RuntimeError):
    """Raised when Redis Streams cannot complete a required operation."""


@dataclass(frozen=True)
class StreamEntry:
    stream_id: str
    fields: dict[str, str]


class StreamBus(Protocol):
    def ensure_group(self, group: str) -> None: ...

    def append(self, fields: dict[str, str]) -> str: ...

    def read_new(self, group: str, consumer: str, count: int) -> list[StreamEntry]: ...

    def reclaim_idle(self, group: str, consumer: str, minimum_idle_ms: int, count: int) -> list[StreamEntry]: ...

    def acknowledge(self, group: str, stream_ids: list[str]) -> int: ...

    def pending_count(self, group: str) -> int: ...

    def stream_length(self) -> int: ...

    def delete_stream(self) -> int: ...


def _decode_entries(result: Any) -> list[StreamEntry]:
    if not result:
        return []

    entries: list[StreamEntry] = []
    for _, raw_entries in result:
        for stream_id, raw_fields in raw_entries:
            if isinstance(raw_fields, dict):
                fields = {str(key): str(value) for key, value in raw_fields.items()}
            else:
                fields = {
                    str(raw_fields[index]): str(raw_fields[index + 1])
                    for index in range(0, len(raw_fields), 2)
                }
            entries.append(StreamEntry(str(stream_id), fields))
    return entries


class UpstashRedisStream:
    """A small REST adapter for the Redis Streams commands MetricThread needs."""

    def __init__(
        self,
        rest_url: str,
        rest_token: str,
        *,
        stream_name: str = "metricthread:events",
        retention: int = 2_000,
        timeout_seconds: float = 5.0,
    ) -> None:
        if retention < 600:
            raise ValueError("stream retention must preserve the 600-event reliability test")
        self._rest_url = rest_url.rstrip("/")
        self._stream_name = stream_name
        self._retention = retention
        self._client = httpx.Client(
            base_url=self._rest_url,
            headers={"Authorization": f"Bearer {rest_token}"},
            timeout=timeout_seconds,
        )

    def _command(self, arguments: list[str | int]) -> Any:
        try:
            response = self._client.post("/", json=arguments)
        except httpx.HTTPError as error:
            raise StreamError(f"Upstash request failed: {error}") from error
        try:
            payload = response.json()
        except ValueError as error:
            try:
                response.raise_for_status()
            except httpx.HTTPError as request_error:
                raise StreamError(f"Upstash request failed: {request_error}") from request_error
            raise StreamError("Upstash returned a non-JSON response") from error
        if "error" in payload:
            raise StreamError(str(payload["error"]))
        try:
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise StreamError(f"Upstash request failed: {error}") from error
        return payload.get("result")

    def ensure_group(self, group: str) -> None:
        try:
            self._command(["XGROUP", "CREATE", self._stream_name, group, "0-0", "MKSTREAM"])
        except StreamError as error:
            if "BUSYGROUP" not in str(error):
                raise

    def append(self, fields: dict[str, str]) -> str:
        arguments: list[str | int] = ["XADD", self._stream_name, "MAXLEN", "~", self._retention, "*"]
        for key, value in fields.items():
            arguments.extend((key, value))
        result = self._command(arguments)
        if not isinstance(result, str):
            raise StreamError("XADD did not return a stream entry ID")
        return result

    def read_new(self, group: str, consumer: str, count: int) -> list[StreamEntry]:
        result = self._command(
            ["XREADGROUP", "GROUP", group, consumer, "COUNT", count, "STREAMS", self._stream_name, ">"]
        )
        return _decode_entries(result)

    def reclaim_idle(self, group: str, consumer: str, minimum_idle_ms: int, count: int) -> list[StreamEntry]:
        result = self._command(
            ["XAUTOCLAIM", self._stream_name, group, consumer, minimum_idle_ms, "0-0", "COUNT", count]
        )
        if not result:
            return []
        _, raw_entries, _ = result
        return _decode_entries([[self._stream_name, raw_entries]])

    def acknowledge(self, group: str, stream_ids: list[str]) -> int:
        if not stream_ids:
            return 0
        result = self._command(["XACK", self._stream_name, group, *stream_ids])
        return int(result)

    def pending_count(self, group: str) -> int:
        result = self._command(["XPENDING", self._stream_name, group])
        return int(result[0]) if result else 0

    def stream_length(self) -> int:
        return int(self._command(["XLEN", self._stream_name]))

    def delete_stream(self) -> int:
        return int(self._command(["DEL", self._stream_name]))

    def close(self) -> None:
        self._client.close()


class InMemoryStream:
    """Deterministic Redis Streams substitute used only by unit tests."""

    def __init__(self, *, retention: int = 2_000) -> None:
        self._retention = retention
        self._entries: list[StreamEntry] = []
        self._next_index: dict[str, int] = {}
        self._pending: dict[str, dict[str, StreamEntry]] = defaultdict(dict)
        self._sequence = 0
        self._claimed_at: dict[tuple[str, str], float] = {}

    def ensure_group(self, group: str) -> None:
        self._next_index.setdefault(group, 0)

    def append(self, fields: dict[str, str]) -> str:
        self._sequence += 1
        entry = StreamEntry(f"{self._sequence}-0", dict(fields))
        self._entries.append(entry)
        if len(self._entries) > self._retention:
            self._entries.pop(0)
            for group in self._next_index:
                self._next_index[group] = max(0, self._next_index[group] - 1)
        return entry.stream_id

    def read_new(self, group: str, consumer: str, count: int) -> list[StreamEntry]:
        self.ensure_group(group)
        start = self._next_index[group]
        entries = self._entries[start : start + count]
        self._next_index[group] = start + len(entries)
        for entry in entries:
            self._pending[group][entry.stream_id] = entry
            self._claimed_at[(group, entry.stream_id)] = time.monotonic()
        return entries

    def reclaim_idle(self, group: str, consumer: str, minimum_idle_ms: int, count: int) -> list[StreamEntry]:
        minimum_age = minimum_idle_ms / 1_000
        now = time.monotonic()
        entries = [
            entry
            for stream_id, entry in self._pending[group].items()
            if now - self._claimed_at[(group, stream_id)] >= minimum_age
        ][:count]
        for entry in entries:
            self._claimed_at[(group, entry.stream_id)] = now
        return entries

    def acknowledge(self, group: str, stream_ids: list[str]) -> int:
        acknowledged = 0
        for stream_id in stream_ids:
            if self._pending[group].pop(stream_id, None) is not None:
                acknowledged += 1
                self._claimed_at.pop((group, stream_id), None)
        return acknowledged

    def pending_count(self, group: str) -> int:
        return len(self._pending[group])

    def stream_length(self) -> int:
        return len(self._entries)

    def delete_stream(self) -> int:
        deleted = int(bool(self._entries))
        self._entries.clear()
        self._next_index.clear()
        self._pending.clear()
        self._claimed_at.clear()
        return deleted
