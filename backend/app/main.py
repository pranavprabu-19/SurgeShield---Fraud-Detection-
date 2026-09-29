"""Scoring API. The decision is synchronous. Audit and explain stay off the hot path when asked."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import threading
import time
from collections import Counter
from typing import Optional

from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.app.engine import Engine
from backend.app.governance.privacy import tokenize
from backend.app.sales import public_events
from backend.app.skills import coverage as skill_coverage
from backend.app.scenarios import build_scenario
from ml.datasets import active_name, artifact_path, field_sources, installed

API_KEY = os.environ.get("SURGESHIELD_API_KEY", "surgeshield-demo")
OPEN_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}

@asynccontextmanager
async def lifespan(application: FastAPI):
    global engine, loop
    path = artifact_path()
    if not path.exists():
        raise RuntimeError(f"missing model artifact at {path}. Run python -m ml.train")
    engine = Engine(path)
    loop = asyncio.get_running_loop()
    yield


app = FastAPI(
    title="SurgeShield",
    version="1.0.0",
    description="Real-time surge vs coordinated account-draining attack decisions.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = None
subscribers = set()
sim_thread = None
sim_stop = threading.Event()
loop = None
rate_buckets: dict[str, list] = {}


class Transaction(BaseModel):
    time: float = Field(ge=0, le=300_000)
    amount: float = Field(ge=0, le=1_000_000)
    v: list[float] = Field(min_length=28, max_length=28)
    user_id: Optional[str] = Field(default=None, max_length=64)
    merchant_id: Optional[str] = Field(default=None, max_length=64)
    eval_label: Optional[int] = Field(default=None, ge=0, le=1)
    region: Optional[str] = Field(default=None, max_length=64)
    device: Optional[str] = Field(default=None, max_length=64)
    category: Optional[str] = Field(default=None, max_length=64)
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lon: Optional[float] = Field(default=None, ge=-180, le=180)
    telemetry: Optional[dict] = None


class LookupRequest(BaseModel):
    kind: str = Field(pattern="^(user|merchant)$")
    raw_id: str = Field(min_length=1, max_length=64)


class ActivateRequest(BaseModel):
    name: str = Field(pattern="^[a-z0-9_]{1,40}$")
    note: str = Field(default="", max_length=500)


class CaseAction(BaseModel):
    action: str = Field(pattern="^(APPROVE|DECLINE|ESCALATE|VERIFY|NOTE)$")
    note: str = Field(default="", max_length=500)


class Batch(BaseModel):
    transactions: list[Transaction] = Field(min_length=1, max_length=2000)
    explain: bool = False


class SimulateRequest(BaseModel):
    scenario: str = Field(
        pattern="^(normal|flash_sale|bot_attack|mixed|noisy_ring|low_and_slow|card_testing|account_takeover|split_ring|mule_fan_in|distributed_drain|big_billion_day|great_indian_festival|replay_real|real_peak)$"
    )
    events_per_second: float = Field(default=25, ge=1, le=500)


class ReviewAction(BaseModel):
    action: str = Field(pattern="^(UPHOLD|RELEASE)$")
    note: str = Field(default="", max_length=500)


class CopilotRequest(BaseModel):
    decision: str
    regime: str
    reasons: list[dict] = []


def _rate_limit(host: str) -> None:
    now = time.time()
    bucket = [stamp for stamp in rate_buckets.get(host, []) if now - stamp < 1]
    if len(bucket) > 5000:
        raise HTTPException(status_code=429, detail="rate limit")
    bucket.append(now)
    rate_buckets[host] = bucket


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.url.path in OPEN_PATHS or request.method == "OPTIONS":
        return await call_next(request)
    if request.headers.get("x-api-key") != API_KEY:
        return JSONResponse(status_code=401, content={"detail": "invalid api key"})
    try:
        _rate_limit(request.client.host if request.client else "unknown")
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return await call_next(request)


@app.get("/health")
def health():
    return {"ok": True, "model": artifact_path().exists(), "safe_mode": bool(engine and engine.safe_mode), "dataset": active_name()}


@app.post("/score")
def score(txn: Transaction, explain: bool = True):
    return engine.score(txn.model_dump(), explain=explain)


@app.post("/score/batch")
def score_batch(batch: Batch):
    started = time.perf_counter()
    decisions = [engine.score(txn.model_dump(), explain=batch.explain) for txn in batch.transactions]
    elapsed = time.perf_counter() - started
    return {
        "count": len(decisions),
        "elapsed_s": round(elapsed, 4),
        "tps": round(len(decisions) / max(elapsed, 1e-6), 1),
        "decisions": decisions,
    }


@app.post("/api/analyze")
def analyze(txn: Transaction, explain: bool = True):
    return score(txn, explain=explain)


@app.get("/api/surge-status")
def surge_status():
    latest = engine.recent[0] if engine.recent else {}
    surge = latest.get("surge") or {}
    return {
        "regime": engine.regime.state,
        "surge": surge,
        "vol_z": latest.get("vol_z"),
        "flash_sale_merchants": list(engine.flash_merchants),
        "genuine_score": surge.get("genuine_score"),
    }


def _csv_float(row: dict, *keys, default=0.0):
    for key in keys:
        raw = row.get(key)
        if raw in (None, ""):
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return default


@app.post("/score/csv")
async def score_csv(file: UploadFile = File(...)):
    raw = await file.read()
    if len(raw) > 8_000_000:
        raise HTTPException(status_code=413, detail="file is larger than 8 MB")
    text = raw.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="the file has no header row")
    decisions = []
    skipped = 0
    scored = 0
    summary = Counter()
    histogram = [0] * 20
    reasons = Counter()
    regimes = Counter()
    labelled = {"fraud": 0, "fraud_caught": 0, "legit": 0, "legit_blocked": 0}
    amounts = Counter()
    last_index = -1
    for index, row in enumerate(reader):
        last_index = index
        if index >= 2000:
            break
        vector = [_csv_float(row, f"V{key}") for key in range(1, 29)]
        label_raw = row.get("Class", row.get("is_fraud", row.get("label", row.get("eval_label"))))
        label = None
        if label_raw not in (None, ""):
            try:
                label = int(float(label_raw))
            except (TypeError, ValueError):
                label = None
        lat = row.get("lat")
        lon = row.get("lon") or row.get("long")
        txn = {
            "time": _csv_float(row, "Time", "time", default=float(index)),
            "amount": _csv_float(row, "Amount", "amount", "amt"),
            "v": vector,
            "user_id": row.get("user_id") or row.get("cc_num") or None,
            "merchant_id": row.get("merchant_id") or row.get("merchant") or None,
            "region": row.get("region") or row.get("city") or None,
            "device": row.get("device") or row.get("device_id") or None,
            "category": row.get("category") or None,
            "eval_label": label,
        }
        try:
            txn["lat"] = float(lat) if lat not in (None, "") else None
            txn["lon"] = float(lon) if lon not in (None, "") else None
            result = engine.score(txn, explain=False)
        except (TypeError, ValueError):
            skipped += 1
            continue
        scored += 1
        decision = result["decision"]
        summary[decision] += 1
        amounts[decision] += float(result["amount"])
        regimes[result["regime"]] += 1
        histogram[min(19, int(float(result["score"]) * 20))] += 1
        for note in result.get("reasons") or []:
            if note.get("feature"):
                reasons[note["feature"]] += 1
        if label == 1:
            labelled["fraud"] += 1
            labelled["fraud_caught"] += decision != "APPROVE"
        elif label == 0:
            labelled["legit"] += 1
            labelled["legit_blocked"] += decision == "BLOCK"
        if len(decisions) < 200:
            decisions.append(
                {
                    "id": result["id"],
                    "decision": decision,
                    "score": result["score"],
                    "risk_100": result["risk_100"],
                    "amount": result["amount"],
                    "regime": result["regime"],
                    "user_token": result.get("user_token"),
                    "merchant_token": result.get("merchant_token"),
                    "region": result.get("region"),
                    "reason": (result.get("reasons") or [{}])[0].get("text"),
                }
            )
    return {
        "count": scored,
        "skipped": skipped,
        "truncated": last_index >= 1999,
        "summary": dict(summary),
        "decisions": decisions,
        "histogram": [{"bin": index, "count": count} for index, count in enumerate(histogram)],
        "amounts": {key: round(value, 2) for key, value in amounts.items()},
        "regimes": dict(regimes),
        "reasons": [{"feature": name, "count": count} for name, count in reasons.most_common(8)],
        "labels": labelled,
        "columns": list(reader.fieldnames or []),
    }


@app.get("/regime")
def regime():
    return {
        "regime": engine.regime.state,
        "attacked_segment": engine.regime.attacked_segment,
        "safe_mode": engine.safe_mode,
        "scenario": engine.scenario,
        "history": engine.regime.history[-60:],
    }


@app.get("/metrics")
def metrics():
    return engine.metrics()


@app.get("/recent")
def recent():
    return {"transactions": list(engine.recent), "totals": engine.totals}


@app.post("/killswitch")
def killswitch(enabled: bool, reason: str = ""):
    return engine.set_safe_mode(enabled, reason)


@app.get("/timeseries")
def timeseries(seconds: int = 120):
    return {"buckets": engine.timeseries(seconds)}


@app.get("/incidents")
def incidents():
    return {"items": engine.list_incidents(), "open": sum(1 for item in engine.list_incidents() if item["status"] != "RESOLVED")}


@app.post("/incidents/{incident_id}/ack")
def incident_ack(incident_id: str):
    found = engine.set_incident_status(incident_id, "ACK")
    if found is None:
        raise HTTPException(status_code=404, detail="unknown incident")
    return found


@app.post("/incidents/{incident_id}/resolve")
def incident_resolve(incident_id: str):
    found = engine.set_incident_status(incident_id, "RESOLVED")
    if found is None:
        raise HTTPException(status_code=404, detail="unknown incident")
    return found


@app.get("/analytics")
def analytics():
    return engine.analytics()


@app.get("/config")
def live_config():
    return engine.live_config()


@app.get("/adapt")
def adapt():
    return engine.adapt_status()


@app.post("/challenger/train")
def challenger_train():
    return engine.train_challenger()


@app.post("/challenger/promote")
def challenger_promote():
    return engine.promote_challenger()


@app.get("/story")
def story():
    return engine.story()


@app.get("/skills")
def skills():
    return skill_coverage()


@app.post("/investigate/run")
def investigate_run():
    return engine.skill_review()


@app.get("/sales")
def sales():
    return {"events": public_events(lambda merchant: tokenize(merchant, engine.secret))}


@app.get("/sale/report")
def sale_report():
    return engine.sale_report()


@app.get("/cases")
def cases():
    return {"cases": engine.cases(), "watchlist": engine.history.watchlist()}


@app.get("/entity/{kind}/{token}")
def entity(kind: str, token: str):
    if kind not in {"user", "merchant"}:
        raise HTTPException(status_code=404, detail="unknown kind")
    view = engine.entity_view(kind, token[:64])
    if view is None:
        raise HTTPException(status_code=404, detail="no history for this token")
    view["sources"] = field_sources()
    return view


@app.post("/entity/lookup")
def entity_lookup(body: LookupRequest):
    token = tokenize(body.raw_id.strip(), engine.secret)
    return {"kind": body.kind, "token": token, "found": engine.history.known(body.kind, token)}


@app.post("/cases/{case_id}/action")
def case_action(case_id: str, body: CaseAction):
    try:
        return engine.case_action(case_id[:80], body.action, body.note)
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown case")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/fairness")
def fairness():
    return engine.fairness()


@app.get("/redteam")
def redteam_report():
    from ml.schema import ARTIFACT_DIR

    summary = ARTIFACT_DIR / "redteam.json"
    sweep = ARTIFACT_DIR / "redteam_sweep.json"
    payload = {"summary": [], "sweep": []}
    if summary.exists():
        payload["summary"] = json.loads(summary.read_text()).get("summary", [])
    if sweep.exists():
        payload["sweep"] = json.loads(sweep.read_text())
    return payload


@app.get("/drift")
def drift():
    return engine.drift()


@app.get("/audit/verify")
def audit_verify():
    return engine.audit.verify()


@app.post("/audit/tamper")
def audit_tamper():
    """Demo control. Flips one stored byte so the verifier can show the break."""
    return engine.audit.tamper_latest()


@app.post("/audit/retention")
def audit_retention(ttl_seconds: int = 1):
    return engine.audit.enforce_retention(ttl_seconds)


@app.get("/review")
def review_list():
    return {"items": engine.audit.list_reviews()}


@app.post("/review/{review_id}")
def review_override(review_id: int, body: ReviewAction):
    try:
        result = engine.audit.override(review_id, body.action, body.note)
        engine.note_feedback(review_id, body.action)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/privacy")
def privacy():
    return {
        "minimized_fields": ["V1-V28", "amount", "time", "segment"],
        "tokenized": ["user_id", "merchant_id"],
        "not_stored": [
            "raw user id",
            "raw merchant id",
            "full feature vector",
            "session duration",
            "clicks",
            "typing speed",
            "mouse path",
        ],
        "telemetry_kept": ["human_score", "telemetry_simulated"],
        "encryption": "AES-256-GCM at rest on the audit log",
        "integrity": "SHA-256 hash chain",
        "retention": "payloads older than the TTL are redacted and the chain is rebuilt",
        "statutes": ["India DPDP Act 2023", "RBI digital payment security controls"],
        "audit": engine.audit.stats(),
    }


@app.post("/copilot")
def copilot(body: CopilotRequest):
    return engine.copilot(body.decision, body.regime, body.reasons)


@app.get("/datasets")
def datasets():
    return {"active": active_name(), "loaded": engine.art.get("dataset", "creditcard"), "datasets": installed()}


@app.post("/datasets/activate")
def datasets_activate(body: ActivateRequest):
    global sim_thread
    rows = {row["name"]: row for row in installed()}
    row = rows.get(body.name)
    if row is None:
        raise HTTPException(status_code=404, detail="dataset is not installed")
    if not row["has_model"]:
        raise HTTPException(status_code=409, detail=f"train it first: SURGESHIELD_DATASET={body.name} python -m ml.train")
    sim_stop.set()
    if sim_thread and sim_thread.is_alive():
        sim_thread.join(timeout=2)
    previous = active_name()
    os.environ["SURGESHIELD_DATASET"] = body.name
    try:
        loaded = engine.load_artifact(artifact_path(body.name))
    except Exception as exc:
        os.environ["SURGESHIELD_DATASET"] = previous
        raise HTTPException(status_code=500, detail=f"could not load artifact: {exc}")
    engine.audit.append({"type": "dataset_activated", "from": previous, "to": body.name, "note": body.note[:500], **loaded})
    return {"ok": True, "active": body.name, **loaded}


@app.post("/simulate/reset")
def simulate_reset():
    global sim_thread
    sim_stop.set()
    if sim_thread and sim_thread.is_alive():
        sim_thread.join(timeout=2)
    engine.reset()
    return {"ok": True, "regime": engine.regime.state}


@app.post("/simulate")
def simulate(body: SimulateRequest):
    global sim_thread
    sim_stop.set()
    if sim_thread and sim_thread.is_alive():
        sim_thread.join(timeout=2)
    sim_stop.clear()
    engine.reset()
    engine.scenario = body.scenario
    events = build_scenario(body.scenario)

    def _run():
        delay = 1.0 / body.events_per_second
        for event in events:
            if sim_stop.is_set():
                break
            result = engine.score(event, explain=True)
            if loop is not None:
                asyncio.run_coroutine_threadsafe(_broadcast(result), loop)
            time.sleep(delay)

    sim_thread = threading.Thread(target=_run, daemon=True)
    sim_thread.start()
    return {"ok": True, "scenario": body.scenario, "events": len(events)}


@app.get("/benchmark")
def benchmark(n: int = 300):
    events = build_scenario("normal")[: max(1, min(n, 220))]
    engine.reset()
    started = time.perf_counter()
    for event in events:
        engine.score(event, explain=False)
    elapsed = time.perf_counter() - started
    return {
        "n": len(events),
        "elapsed_s": round(elapsed, 4),
        "tps": round(len(events) / max(elapsed, 1e-6), 1),
        "p50_ms": engine.totals["latency_p50"],
        "p99_ms": engine.totals["latency_p99"],
        "latencies_ms": [round(float(value), 3) for value in list(engine.latencies)[-240:]],
    }


async def _broadcast(message: dict) -> None:
    dead = []
    for socket in list(subscribers):
        try:
            await socket.send_json(message)
        except Exception:
            dead.append(socket)
    for socket in dead:
        subscribers.discard(socket)


@app.websocket("/ws/stream")
async def stream(socket: WebSocket, api_key: str = ""):
    if api_key != API_KEY:
        await socket.close(code=4401)
        return
    await socket.accept()
    subscribers.add(socket)
    try:
        while True:
            await socket.receive_text()
    except WebSocketDisconnect:
        subscribers.discard(socket)
