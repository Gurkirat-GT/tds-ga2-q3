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

The only allowed browser origin is `https://dash-u3q2xa.example.com`.
Every HTTP response includes `X-Request-ID` and `X-Process-Time`.

## Deploy on Vercel

Import this GitHub repository into Vercel or run `npx vercel --prod` from the
project root. Vercel detects the FastAPI `app` in `main.py` and installs the
dependencies from `requirements.txt`.
