from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from metricthread.live_pipeline import LivePipeline, cold_store_from_environment
from metricthread.streams import UpstashRedisStream


class AgentRuntime:
    def __init__(self, pipeline: LivePipeline, interval_seconds: float = 5.0) -> None:
        self.pipeline = pipeline
        self._interval_seconds = interval_seconds
        self._simulation_task: asyncio.Task[None] | None = None
        self._worker_task: asyncio.Task[None] | None = None

    async def start_simulation(self) -> bool:
        if self._simulation_task and not self._simulation_task.done():
            return False
        self.pipeline.start()
        self._worker_task = asyncio.create_task(self._process_stream(), name="metricthread-stream-worker")
        self._simulation_task = asyncio.create_task(self._simulate(), name="metricthread-simulator")
        return True

    async def _simulate(self) -> None:
        while True:
            emitted = await asyncio.to_thread(self.pipeline.emit_next_day)
            if emitted == 0:
                return
            await asyncio.sleep(self._interval_seconds)

    async def _process_stream(self) -> None:
        while True:
            await asyncio.to_thread(self.pipeline.process_once)
            await asyncio.sleep(1)

    async def stop(self) -> None:
        for task in (self._simulation_task, self._worker_task):
            if task:
                task.cancel()
        for task in (self._simulation_task, self._worker_task):
            if not task:
                continue
            try:
                await task
            except asyncio.CancelledError:
                pass


def runtime_from_environment() -> AgentRuntime:
    rest_url = os.environ.get("UPSTASH_REDIS_REST_URL")
    rest_token = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    if not rest_url or not rest_token:
        raise RuntimeError("UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN are required")
    stream = UpstashRedisStream(rest_url, rest_token)
    return AgentRuntime(LivePipeline(stream, cold_store_from_environment()))


def create_app(runtime: AgentRuntime | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.runtime = runtime or runtime_from_environment()
        yield
        await app.state.runtime.stop()

    app = FastAPI(title="MetricThread", version="0.2.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.get("/agent/status")
    def agent_status() -> dict[str, object]:
        status = asdict(app.state.runtime.pipeline.status())
        return {
            **status,
            "anomaly_state": "watching",
            "signal_state": "pending deterministic analysis in Phase 3",
            "simulation_label": "synthetic live simulation",
        }

    @app.get("/metrics/live")
    def live_metrics() -> dict[str, object]:
        return {
            "simulation_label": "synthetic live simulation",
            "metrics": app.state.runtime.pipeline.latest_metrics(),
        }

    @app.post("/simulation/start")
    async def start_simulation() -> dict[str, object]:
        started = await app.state.runtime.start_simulation()
        return {
            "started": started,
            "simulation_label": "synthetic live simulation",
            "status": asdict(app.state.runtime.pipeline.status()),
        }

    @app.get("/insights")
    def insights_placeholder() -> None:
        raise HTTPException(status_code=501, detail="Insights begin in Phase 3 after deterministic evidence is available")

    return app


app = create_app()
