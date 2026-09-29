# SurgeShield

SurgeShield tells a genuine flash-sale surge apart from a coordinated account-draining attack, and it does it per transaction in milliseconds.

The supplied data has `Time`, PCA components `V1`–`V28`, `Amount`, and `Class`. It does not have user, merchant, or location columns. The product says that out loud and builds context from the stream instead: rolling windows, behavioral segments, and a coordination detector.

## Run it

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# macOS only, if LightGBM cannot find OpenMP:
# brew install libomp
python -m ml.eda
python -m ml.train
python -m ml.evaluate
pip install 'uvicorn[standard]'
# --loop asyncio avoids a uvloop crash seen with LightGBM on this laptop.
uvicorn backend.app.main:app --port 8010 --loop asyncio --http h11
```

In another terminal:

```bash
cd frontend
npm install
# frontend/.env.local
# NEXT_PUBLIC_API_URL=http://localhost:8010
# NEXT_PUBLIC_API_KEY=surgeshield-demo
npx next dev -p 3010
```

Open http://localhost:3010. The demo API key is `surgeshield-demo` (header `X-API-Key`).

Port 8000 on this machine is already taken by another service, so the local demo uses 8010 and 3010. `docker compose` still publishes 8000 and 3000 when those ports are free. Before a jury run, `scripts/reset_demo.sh` deletes the audit database so the chain starts intact.

Or, once the model artifact exists:

```bash
docker compose up --build
```

The API image needs `libgomp` (installed in the Dockerfile) and `ml/artifacts/surgeshield.joblib` (created by `python -m ml.train`). The dashboard talks to `http://localhost:8000` from the browser, which is the port mapped by Compose.

## What the jury should click

1. **Flash sale.** The regime banner goes to SURGE. Legitimate buyers keep getting approved.
2. **Bot attack.** Cloned fraud vectors from `test.csv`, small probes then large drains. The banner goes to ATTACK and those payments are blocked, with reasons.
3. **Attack inside a sale.** Both happen together. Thresholds tighten only for the attacked segment.
4. **Governance.** Verify the audit chain, tamper one record, verify again, flip the kill switch.

## Decisions

Every transaction is `APPROVE`, `STEP_UP` (OTP), or `BLOCK`. A static threshold is scored beside SurgeShield so the rupee difference is visible.

## Layout

- `ml/` training, features, evaluation
- `backend/` FastAPI scoring, regime, governance
- `frontend/` live command center
- `simulator/replay.py` scenario driver
- `docs/` model card, datasheet, governance, pitch

## Metrics that matter

Accuracy does not. A model that approves everything scores about 99.83%. We report PR-AUC, recall at 0.1% false-positive rate, rupees saved against a static threshold, and p50/p99 latency.
