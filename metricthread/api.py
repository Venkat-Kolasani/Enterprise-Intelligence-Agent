from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from metricthread.executive import (
    BriefingService,
    ExecutiveStore,
    GroundedChatService,
    ScenarioForecastService,
)
from metricthread.executive_repository import executive_store_from_environment
from metricthread.insight_repository import insight_store_from_environment
from metricthread.insights import (
    GroundedInsightService,
    InsightStore,
    NarrativeGenerator,
    narrative_generator_from_environment,
)
from metricthread.live_pipeline import LivePipeline, cold_store_from_environment
from metricthread.signal_repository import signal_repository_from_environment
from metricthread.signals import SignalRepository
from metricthread.streams import UpstashRedisStream


load_dotenv()


class RecommendationStatusRequest(BaseModel):
    status: Literal["proposed", "planned", "implemented"]


class OutcomeRequest(BaseModel):
    implemented_at: datetime
    outcome_metric: str = Field(min_length=1, max_length=120)
    outcome_value: float
    measured_at: datetime
    notes: str = Field(default="", max_length=2_000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1_000)
    prior_insight_ids: list[UUID] = Field(default_factory=list, max_length=5)


class ScenarioForecastRequest(BaseModel):
    input_metric: Literal["marketing_spend"]
    input_change_percent: float = Field(ge=-20, le=20)
    horizon_days: int = Field(ge=1, le=7)


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


def create_app(
    runtime: AgentRuntime | None = None,
    signal_repository: SignalRepository | None = None,
    insight_store: InsightStore | None = None,
    narrative_generator: NarrativeGenerator | None = None,
    executive_store: ExecutiveStore | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.runtime = runtime or runtime_from_environment()
        app.state.signal_repository = signal_repository
        app.state.insight_store = insight_store
        app.state.narrative_generator = narrative_generator
        app.state.executive_store = executive_store
        app.state.grounded_insight_service = None
        yield
        await app.state.runtime.stop()

    app = FastAPI(title="MetricThread", version="0.2.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.get("/agent/status")
    def agent_status() -> dict[str, object]:
        status = asdict(app.state.runtime.pipeline.status())
        return {
            **status,
            "anomaly_state": "watching",
            "signal_state": "deterministic analysis available",
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

    def repository() -> SignalRepository:
        configured_repository = app.state.signal_repository
        if configured_repository is None:
            configured_repository = signal_repository_from_environment()
            app.state.signal_repository = configured_repository
        return configured_repository

    def insights_store() -> InsightStore:
        configured_store = app.state.insight_store
        if configured_store is None:
            configured_store = insight_store_from_environment()
            app.state.insight_store = configured_store
        return configured_store

    def grounded_insight_service() -> GroundedInsightService:
        service = app.state.grounded_insight_service
        if service is None:
            generator = app.state.narrative_generator or narrative_generator_from_environment()
            service = GroundedInsightService(repository(), insights_store(), generator)
            app.state.grounded_insight_service = service
        return service

    def executive_store_instance() -> ExecutiveStore:
        configured_store = app.state.executive_store
        if configured_store is None:
            configured_store = executive_store_from_environment()
            app.state.executive_store = configured_store
        return configured_store

    @app.get("/signals")
    def signals() -> dict[str, object]:
        return {
            "simulation_label": "synthetic live simulation",
            "evidence_language": "Predictive lead-lag evidence; not proof of causation.",
            "signals": [signal.as_public_dict() for signal in repository().list_accepted()],
        }

    @app.post("/signals/run")
    async def run_signals() -> dict[str, object]:
        report = await asyncio.to_thread(repository().run_analysis)
        return {
            "simulation_label": "synthetic live simulation",
            "candidate_count": report.candidate_count,
            "accepted_count": len(report.accepted),
            "rejected_count": len(report.rejected),
            "signals": [signal.as_public_dict() for signal in report.accepted],
        }

    @app.get("/insights")
    def insights() -> dict[str, object]:
        recommendations_by_insight: dict[UUID, list[dict[str, object]]] = {}
        for recommendation in insights_store().list_recommendations():
            recommendations_by_insight.setdefault(recommendation.insight_id, []).append(
                recommendation.as_public_dict()
            )
        return {
            "simulation_label": "synthetic live simulation",
            "insights": [
                {
                    **insight.as_public_dict(),
                    "recommendations": recommendations_by_insight.get(insight.id, []),
                }
                for insight in insights_store().list_insights()
            ],
        }

    @app.get("/insights/{insight_id}")
    def insight_detail(insight_id: UUID) -> dict[str, object]:
        for insight in insights()["insights"]:
            if insight["id"] == str(insight_id):
                return {"simulation_label": "synthetic live simulation", "insight": insight}
        raise HTTPException(status_code=404, detail="Insight was not found")

    @app.post("/insights/generate")
    async def generate_insight() -> dict[str, object]:
        generated = await asyncio.to_thread(grounded_insight_service().generate_next)
        if generated is None:
            return {
                "generated": False,
                "reason": "No newly accepted or materially changed signal requires a configured-model narrative.",
            }
        return {
            "generated": True,
            "simulation_label": "synthetic live simulation",
            "insight": {
                **generated.insight.as_public_dict(),
                "recommendations": [generated.recommendation.as_public_dict()],
            },
            "source_signal_id": str(generated.source_signal.id),
        }

    @app.post("/recommendations/{recommendation_id}/status")
    def update_recommendation_status(
        recommendation_id: UUID, request: RecommendationStatusRequest
    ) -> dict[str, object]:
        try:
            recommendation = insights_store().update_recommendation_status(recommendation_id, request.status)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {"recommendation": recommendation.as_public_dict()}

    @app.post("/recommendations/{recommendation_id}/outcomes")
    def record_recommendation_outcome(
        recommendation_id: UUID, request: OutcomeRequest
    ) -> dict[str, object]:
        try:
            recommendation = insights_store().record_outcome(
                recommendation_id,
                implemented_at=request.implemented_at,
                outcome_metric=request.outcome_metric.strip(),
                outcome_value=request.outcome_value,
                measured_at=request.measured_at,
                notes=request.notes.strip(),
            )
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return {"recommendation": recommendation.as_public_dict()}

    @app.post("/briefings/generate")
    async def generate_briefing() -> dict[str, object]:
        briefing = await asyncio.to_thread(BriefingService(insights_store(), executive_store_instance()).generate)
        if briefing is None:
            return {
                "generated": False,
                "reason": "No newly generated insight is available for a briefing.",
                "simulation_label": "synthetic live simulation",
            }
        return {
            "generated": True,
            "simulation_label": "synthetic live simulation",
            "briefing": briefing.as_public_dict(),
        }

    @app.post("/chat")
    def chat(request: ChatRequest) -> dict[str, object]:
        result = GroundedChatService(insights_store(), repository()).answer(
            request.question,
            prior_insight_ids=tuple(str(insight_id) for insight_id in request.prior_insight_ids),
        )
        return {
            "simulation_label": "synthetic live simulation",
            **result.as_public_dict(),
        }

    @app.post("/scenarios/forecast")
    async def scenario_forecast(request: ScenarioForecastRequest) -> dict[str, object]:
        try:
            forecast = await asyncio.to_thread(
                ScenarioForecastService(repository(), executive_store_instance()).forecast,
                input_change_percent=request.input_change_percent,
                horizon_days=request.horizon_days,
            )
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return {
            "simulation_label": "synthetic live simulation",
            "forecast": forecast.as_public_dict(),
        }

    return app


app = create_app()
