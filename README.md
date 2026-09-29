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

Run `scripts/reset_demo.sh` first, then start the API. It deletes the audit database so Verify starts on an intact chain. Starting a scenario resets the live stream and the in-memory cases, so run Investigate before Boundary probe.

1. **Overview.** Read the p50 and p99 latency and the share of payments with zero friction. Both are on the page.
2. **Sale War Room.** Press B. Big Billion Days goes to SURGE, then its own attack phases latch ATTACK on the attacked segment only. Press G for the Great Indian Festival. There is no separate inject button.
3. **Investigate.** After the sale has opened cases, click **Run the model**. It reads each stored customer and merchant history and writes the decision into Status and Why.
4. **Analytics.** Click **Replay scenarios**. The recorded scenarios run once, in about 10 seconds, on a side engine. The live stream and the five-seed report stay as they are.
5. **Sale War Room again.** Choose **Boundary probe**. A row in the attack feed says how far the risk sits under the block line, and the decision stays a step-up.
6. **Governance.** Verify the chain, tamper one record, verify again, then flip the kill switch. Payments keep flowing under the fallback rules.

## Import your own data

Card files the importer already recognises (credit-card, Sparkov, IEEE-CIS, PaySim):

```bash
PYTHONPATH=. .venv/bin/python -m ml.import_dataset \
  --path fraudTrain.csv --test fraudTest.csv
```

A file with different column names, for example a UPI extract:

```bash
PYTHONPATH=. .venv/bin/python -m ml.import_dataset \
  --path upi.csv --name upi_bank \
  --map time=txn_ts,amount=amt,label=fraud,\
        user=payer_vpa,merchant=payee_vpa,\
        city=city,device=device_id
```

Train on that named dataset:

```bash
SURGESHIELD_DATASET=upi_bank PYTHONPATH=. .venv/bin/python -m ml.train
```

Leave `SURGESHIELD_DATASET` unset to score with the committed credit-card champion.

## Privacy

- Names, streets, jobs, emails, phone numbers, and transaction numbers are dropped on import by column name.
- Card numbers and VPAs are kept only as keys and HMAC-tokenized when a payment is scored. The raw id is not stored.
- Any column whose solo AUC is above 0.98 is dropped as a label leak.

## Architecture rule

The champion model is the only component that can `BLOCK` while it is in charge. Detectors and the boundary probe can only escalate a payment to `STEP_UP`. The step-up channel is device check, push, OTP, or strong auth; the decision is still one of `APPROVE`, `STEP_UP`, or `BLOCK`.

The kill switch does not pause the queue. It hands the payment to a small fallback rule, which blocks an amount of ₹2,000 or more and otherwise approves or steps up.

## Decisions

Every transaction is `APPROVE`, `STEP_UP`, or `BLOCK`. A static threshold is scored beside SurgeShield so the rupee difference is visible.

## Bank integration

`sdk/surgeshield_sdk.py` uses only the Python standard library. A gateway calls the existing score route. `BLOCK` declines, `STEP_UP` sends the friction channel the API already chose, and anything else is approved.

```python
from sdk.surgeshield_sdk import SurgeShieldClient, transaction_from_row

client = SurgeShieldClient("http://localhost:8010", "surgeshield-demo")

def payment_gateway_hook(row):
    result = client.score(transaction_from_row(row))
    if result.blocked:
        return decline(result.reasons)
    if result.step_up:
        return challenge(result.friction)
    return approve()
```

## Layout

- `ml/` training, features, evaluation
- `backend/` FastAPI scoring, regime, governance
- `frontend/` live command center
- `simulator/replay.py` scenario driver
- `sdk/` bank client for `POST /score`
- `docs/` model card, datasheet, governance, pitch

## Metrics that matter

Accuracy does not. A model that approves everything scores about 99.83%. We report PR-AUC, recall at 0.1% false-positive rate, rupees saved against a static threshold, and p50/p99 latency.
