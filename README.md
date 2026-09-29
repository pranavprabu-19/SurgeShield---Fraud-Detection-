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

Open <http://localhost:3010>. The demo API key is `surgeshield-demo` (header `X-API-Key`).

Port 8000 on this machine is already taken by another service, so the local demo uses 8010 and 3010. `docker compose` still publishes 8000 and 3000 when those ports are free. Before a jury run, `scripts/reset_demo.sh` restarts the API so the audit chain starts intact.

Or, once the model artifact exists:

```bash
docker compose up --build
```

The API image needs `libgomp` (installed in the Dockerfile) and `ml/artifacts/surgeshield.joblib`, which is already in the repo. The dashboard talks to `http://localhost:8000` from the browser, which is the port mapped by Compose. The local demo in this README uses 8010 and 3010.

## What the jury should click

Run `scripts/reset_demo.sh` first. It restarts the API so Verify starts on an intact chain. Read the numbers on screen. Do not quote a latency, a percentage, or a decision count from memory. Press B and Boundary probe before Upload. Starting a scenario resets the live stream and the cases an upload just opened.

1. **Overview.** Read the p50 and p99 latency and the share of payments with zero friction. Both are on the page.
2. **Sale War Room.** Press B. Big Billion Days goes to SURGE, then its own attack phases latch ATTACK on the attacked segment only. There is no separate inject button. Then choose **Boundary probe**. The feed says how far that row's risk sits under the block line, and the decision stays a step-up. The gap is that row's gap.
3. **Analytics.** The logistic, LightGBM, and XGBoost comparison is already on screen. XGBoost does not score checkout. Click **Replay scenarios**. The recorded scenarios run once on a side engine. The live stream and the held-out precision-recall curve stay as they are.
4. **Upload.** Drop a CSV. The first 2,000 rows are scored. **File report** appears above the charts: decision counts, each feature that fired, and the columns the file does not have. **Export this report** prints that text. A step-up or block makes the Customer cell a case link. A file with no customer id uses `csv-row-1`, `csv-row-2`, and so on.
5. **Investigate.** Open that case. The payment Reason column is the anomaly name. Do not click the review button. It already says **Model running** and reviews stored histories about every 5 seconds. Status and Why update on their own. A history that stays challenged is declined. A quiet one is approved.
6. **Analytics again.** **Morph this payment.** Change the amount or V14. The new rows are marked synthesized. They are not passed off as live checkout traffic.
7. **Governance.** Verify the chain, tamper one record, verify again, then flip the kill switch. Payments keep flowing under the fallback rules. **Jury mode** is the separate button in the top bar.
8. **Data.** **Reports** lists the upload next to the installed creditcard test slice, with PR-AUC. **Export report** prints both.

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

If several files are already in `data/`, `scripts/import_all.sh` imports each one that is present and skips the rest. `scripts/train_all.sh` then trains a champion only where `data/<name>/train.csv` exists and no model file does yet. It does not retrain the credit-card champion. The Data page is where a trained champion is activated. `POST /models/route` only names which champion a raw row matches. It does not score, and `POST /score` still uses the champion that is loaded.

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
