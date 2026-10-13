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

The only allowed browser origin is `https://dash-u3q2xa.example.com`.
Every HTTP response includes `X-Request-ID` and `X-Process-Time`.

## Deploy on Render

Create a new Render Blueprint deployment from this repository and use
`render.yaml`. Render will install `requirements.txt` and launch the ASGI app.
