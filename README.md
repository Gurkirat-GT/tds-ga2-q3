# CORS-Aware Metrics API

FastAPI service for computing descriptive statistics over integer query values.

## Run locally

```powershell
py -m pip install -r requirements.txt
py -m uvicorn main:app --reload
```

Request example:

```text
GET http://127.0.0.1:8000/stats?values=1,2,3
```

Verify an RS256 token issued by the configured identity provider:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/verify `
  -Method Post -ContentType 'application/json' `
  -Body '{"token":"<JWT>"}'
```

`POST /verify` checks the signature, issuer, exact audience, and expiration.
Invalid tokens receive HTTP 401 with `{"detail":{"valid":false}}`.

`GET /effective-config` merges defaults, `config.<APP_ENV>.yaml`, `.env`, and
`APP_*` process environment variables, then applies repeated `set=key=value`
query overrides. The `api_key` value is always masked in its response.

Browser requests to the API are allowed from any origin. Every HTTP response
includes `X-Request-ID` and `X-Process-Time`.

## Run the API and Redis with Docker Compose

```powershell
docker compose up --build -d
```

The API is available on `http://localhost:8000`; Redis is only exposed on the
internal Compose network. Increment counters with `POST /hit/{key}`, inspect
them with `GET /count/{key}`, and check Redis with `GET /healthz`.

Expose the API publicly with Cloudflare Tunnel:

```powershell
cloudflared tunnel --url http://localhost:8000
```
