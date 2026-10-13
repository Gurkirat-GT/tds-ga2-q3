import hmac
import json
import logging
import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from time import monotonic
from uuid import uuid4

import jwt
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest
from redis.asyncio import Redis
from redis.exceptions import RedisError
import yaml
from dotenv import dotenv_values
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware
from starlette.types import Message, Receive, Scope, Send


ALLOWED_ORIGIN = "https://dash-u3q2xa.example.com"
EMAIL = "24f3002454@ds.study.iitm.ac.in"
OIDC_ISSUER = "https://idp.exam.local"
OIDC_AUDIENCE = "tds-9brnjekr.apps.exam.local"
OIDC_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA2okOHspNjgA+2rTLbeuY
cxiP/hG8C6Sb9iwg3yiLAA4HCnpITcbWCSelbvbYGuc3EbNy4xFyf5Cbj5DHJMID
EkryOgyd2giIIIBOUBj8S63uGcnRpOBh9NFatfNwheKuzsPuVNldu6A9cNteNpXc
WyJjG2axVfmq7i6SuKr1JoWYG7xTTAvKPujSl4OtsQfO3h5NepzdfXpr28oNnzfW
ed+zclR6BcmNNo/WVfJ4xyCLSf0BCOgdTgW6PdaChd1l9VDetJZVEgC5tkyvXsfI
SI6iyrYbKR0NEBSqq4XkadEjsCs4F1RncsS4LlgniT7GlkL9Mce3b0wGLs9/7ZIX
dQIDAQAB
-----END PUBLIC KEY-----"""
DEFAULT_CONFIG: dict[str, object] = {
    "port": 8000,
    "workers": 1,
    "debug": False,
    "log_level": "info",
    "api_key": "default-secret-000",
}
TRUTHY_VALUES = {"true", "1", "yes", "on"}
STARTED_AT = monotonic()
HTTP_REQUESTS = Counter("http_requests_total", "Total HTTP requests")
REQUEST_LOGS: deque[dict[str, str | int]] = deque(maxlen=1000)
REQUEST_LOGGER = logging.getLogger("request_json")
REQUEST_LOGGER.setLevel(logging.INFO)
REQUEST_LOGGER.propagate = False
if not REQUEST_LOGGER.handlers:
    log_handler = logging.StreamHandler()
    log_handler.setFormatter(logging.Formatter("%(message)s"))
    REQUEST_LOGGER.addHandler(log_handler)


class MetricsFastAPI(FastAPI):
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await super().__call__(scope, receive, send)
            return

        request_id = str(uuid4())
        started_at = perf_counter()
        HTTP_REQUESTS.inc()
        status_code = 500

        async def send_with_metrics(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() not in (b"x-request-id", b"x-process-time")
                ]
                duration = max(0.0, perf_counter() - started_at)
                headers.extend(
                    [
                        (b"x-request-id", request_id.encode("ascii")),
                        (b"x-process-time", f"{duration:.6f}".encode("ascii")),
                    ]
                )
                message = {**message, "headers": headers}
            await send(message)

        app_call = super().__call__
        origin = (
            [ALLOWED_ORIGIN]
            if scope["path"] == "/stats"
            else ["*"]
        )
        cors_app = CORSMiddleware(
            app_call,
            allow_origins=origin,
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        )
        try:
            await cors_app(scope, receive, send_with_metrics)
        finally:
            log_entry: dict[str, str | int] = {
                "level": "info" if status_code < 500 else "error",
                "ts": datetime.now(timezone.utc).isoformat(),
                "path": scope["path"],
                "request_id": request_id,
                "method": scope["method"],
                "status": status_code,
            }
            REQUEST_LOGS.append(log_entry)
            REQUEST_LOGGER.info(json.dumps(log_entry, separators=(",", ":")))


app = MetricsFastAPI()
redis_client = Redis.from_url(
    os.environ.get("REDIS_URL", "redis://redis:6379/0"),
    decode_responses=True,
)
class VerifyRequest(BaseModel):
    token: str


class AnalyticsEvent(BaseModel):
    user: str
    amount: float
    ts: int | float


class AnalyticsRequest(BaseModel):
    events: list[AnalyticsEvent]


def normalize_config_key(key: object) -> str:
    normalized = str(key).strip().lower()
    if normalized.startswith("app_"):
        normalized = normalized[4:]
    if normalized == "num_workers":
        return "workers"
    return normalized


def coerce_config_value(key: str, value: object) -> object:
    if key in {"port", "workers"}:
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail=f"{key} must be an integer",
            ) from exc
    if key == "debug":
        return str(value).strip().lower() in TRUTHY_VALUES
    return str(value)


@app.get("/")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/healthz")
async def redis_health_check() -> dict[str, str | float]:
    try:
        redis_up = bool(await redis_client.ping())
    except RedisError:
        redis_up = False
    return {
        "status": "ok",
        "uptime_s": max(0.0, monotonic() - STARTED_AT),
        "redis": "up" if redis_up else "down",
    }


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/logs/tail")
async def tail_logs(limit: int = Query(default=100, ge=0, le=1000)) -> list[dict[str, str | int]]:
    if limit == 0:
        return []
    return list(REQUEST_LOGS)[-limit:]


@app.get("/work")
async def do_work(n: int = Query(..., ge=0)) -> dict[str, int | str]:
    for _ in range(n):
        pass
    return {"email": EMAIL, "done": n}


@app.post("/hit/{key}")
async def record_hit(key: str) -> dict[str, int | str]:
    count = await redis_client.incr(f"hit:{key}")
    return {"key": key, "count": count}


@app.get("/count/{key}")
async def get_hit_count(key: str) -> dict[str, int | str]:
    count = await redis_client.get(f"hit:{key}")
    return {"key": key, "count": int(count) if count is not None else 0}


@app.post("/analytics")
async def aggregate_analytics(
    request: AnalyticsRequest,
    api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, int | float | str]:
    assigned_key = os.environ.get("ANALYTICS_API_KEY")
    if (
        assigned_key is None
        or api_key is None
        or not hmac.compare_digest(api_key, assigned_key)
    ):
        raise HTTPException(status_code=401, detail="Unauthorized")

    user_totals: dict[str, float] = {}
    revenue = 0.0
    for event in request.events:
        if event.amount > 0:
            revenue += event.amount
            user_totals[event.user] = user_totals.get(event.user, 0.0) + event.amount

    return {
        "email": EMAIL,
        "total_events": len(request.events),
        "unique_users": len({event.user for event in request.events}),
        "revenue": revenue,
        "top_user": max(user_totals, key=user_totals.get) if user_totals else "",
    }


@app.get("/effective-config")
async def get_effective_config(
    set: list[str] = Query(default=[]),
) -> dict[str, object]:
    project_dir = Path(__file__).resolve().parent
    environment = os.environ.get("APP_ENV", "development")
    config_path = project_dir / f"config.{environment}.yaml"
    yaml_values = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(yaml_values, dict):
        raise HTTPException(
            status_code=500,
            detail=f"{config_path.name} must contain a YAML mapping",
        )

    config = DEFAULT_CONFIG.copy()
    for layer in (
        yaml_values,
        {
            normalize_config_key(key): value
            for key, value in dotenv_values(project_dir / ".env").items()
            if value is not None
        },
        {
            normalize_config_key(key): value
            for key, value in os.environ.items()
            if key.startswith("APP_") and key != "APP_ENV"
        },
    ):
        for key, value in layer.items():
            normalized_key = normalize_config_key(key)
            config[normalized_key] = coerce_config_value(normalized_key, value)

    for override in set:
        key, separator, value = override.partition("=")
        normalized_key = normalize_config_key(key)
        if not separator or not normalized_key:
            raise HTTPException(
                status_code=422,
                detail="each set parameter must use key=value format",
            )
        config[normalized_key] = coerce_config_value(normalized_key, value)

    config["api_key"] = "****"
    return config


@app.get("/stats")
async def get_stats(values: str = Query(...)) -> dict[str, int | float | str]:
    try:
        numbers = [int(value.strip()) for value in values.split(",")]
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="values must be a comma-separated list of integers",
        ) from exc

    if not numbers:
        raise HTTPException(status_code=422, detail="values must not be empty")

    return {
        "email": EMAIL,
        "count": len(numbers),
        "sum": sum(numbers),
        "min": min(numbers),
        "max": max(numbers),
        "mean": sum(numbers) / len(numbers),
    }


@app.post("/verify")
async def verify_token(request: VerifyRequest) -> JSONResponse:
    try:
        claims = jwt.decode(
            request.token,
            OIDC_PUBLIC_KEY,
            algorithms=["RS256"],
            issuer=OIDC_ISSUER,
            options={
                "verify_aud": False,
                "require": ["iss", "aud", "exp", "email", "sub"],
            },
        )
    except jwt.InvalidTokenError:
        return JSONResponse(status_code=401, content={"valid": False})

    if (
        claims.get("aud") != OIDC_AUDIENCE
        or not isinstance(claims.get("email"), str)
        or not isinstance(claims.get("sub"), str)
    ):
        return JSONResponse(status_code=401, content={"valid": False})

    return JSONResponse(
        content={
            "valid": True,
            "email": claims["email"],
            "sub": claims["sub"],
            "aud": claims["aud"],
        }
    )
