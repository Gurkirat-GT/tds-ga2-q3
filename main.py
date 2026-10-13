from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from starlette.middleware.cors import CORSMiddleware
from starlette.types import Message, Receive, Scope, Send


ALLOWED_ORIGIN = "https://dash-u3q2xa.example.com"
EMAIL = "24f3002454@ds.study.iitm.ac.in"


class MetricsFastAPI(FastAPI):
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await super().__call__(scope, receive, send)
            return

        request_id = str(uuid4())
        started_at = perf_counter()

        async def send_with_metrics(message: Message) -> None:
            if message["type"] == "http.response.start":
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

        await super().__call__(scope, receive, send_with_metrics)


app = MetricsFastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


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
