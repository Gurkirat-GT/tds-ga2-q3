from time import perf_counter
from uuid import uuid4

import jwt
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
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
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class VerifyRequest(BaseModel):
    token: str


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
