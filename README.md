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
pip install 'uvicorn[standard]'
# --loop asyncio avoids a uvloop crash seen with LightGBM on this laptop.
uvicorn backend.app.main:app --port 8010 --loop asyncio --http h11
```

The champion is already in `ml/artifacts/surgeshield.joblib` (about 3 MB), so a clone can score without retraining. `train/train.csv` and `train/test.csv` stay out of git because the training file is over GitHub's 100 MB limit. To rebuild the model, put the organiser credit-card files at those two paths (Time, V1–V28, Amount, Class), then:

```bash
python -m ml.eda
python -m ml.train
python -m ml.evaluate
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

The API image needs `libgomp` (installed in the Dockerfile) and `ml/artifacts/surgeshield.joblib`, which is already in the repo. The dashboard talks to `http://localhost:8000` from the browser, which is the port mapped by Compose. The local demo in this README uses 8010 and 3010.

## What the jury should click

1. **Overview.** Flash sale: the regime banner goes to SURGE and legitimate buyers stay approved. Bot attack: the banner goes to ATTACK and those payments are blocked, with reasons. Attack inside a sale: thresholds tighten only for the attacked segment.
2. **Sale War Room.** Press B for Big Billion Days or G for the Great Indian Festival. The phase strip, map, and attack feed follow the rush.
3. **Investigate.** After a scenario has opened cases, click **Run the model**. It reads each stored customer and merchant history, blocks a pattern that stays challenged, and approves a history that is mostly quiet. The Cases table status and Why column update from that judgment.
4. **Upload and Data.** Upload scores a transaction CSV. Data shows which features run on real columns and which are simulated for an imported file.
5. **Governance.** Verify the audit chain, tamper one record, verify again, flip the kill switch.

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
