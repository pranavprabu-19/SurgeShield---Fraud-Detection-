# Governance

SurgeShield treats governance as endpoints, not as a slide.

## 1. AI governance
- One versioned artifact (`ml/artifacts/surgeshield.joblib`) plus this model card.
- Champion decides (class-weighted logistic regression on this training run). LightGBM is the shadow score on every response. The time holdout, not the fancier algorithm, picked the champion.
- Kill switch (`POST /killswitch`) falls back to rules. Payments still flow.
- Human review queue for `STEP_UP` and `BLOCK`. An override is written into the audit log.
- Drift: population stability index on recent scores (`GET /drift`), alert at 0.2.

## 2. Responsible development
- Time-ordered split. Test labels are never used to fit, calibrate, or pick a threshold.
- Seed 42. Metrics are PR-AUC and recall at a fixed false-positive rate, because accuracy is meaningless at 0.17% fraud.
- Limits are written in the model card. Age, gender, and geography are never model inputs. If a dataset contains them, `GET /fairness` reports false-decline and step-up rates by group. The default PCA file has none.
- Unit tests cover leakage, the audit chain, the regime detector, the copilot fallback, and live scenarios.

## 3. Privacy
- Data minimization: the audit record stores the decision, score, segment, amount, and tokens. It does not store `V1`–`V28`.
- `user_id` and `merchant_id`, when a channel sends them, are HMAC-SHA256 tokenized with a secret salt. The raw value is not logged.
- Session length, click count, typing speed, and mouse movement are optional and are not written to the audit log. The log keeps `human_score` and a flag that says the telemetry was simulated.
- Investigate search sends a raw customer or merchant id to `POST /entity/lookup`. The server HMAC-tokenizes it with the stream key and returns only the token. The raw id is not stored, logged, or put in a URL.
- Customer and merchant history is in memory only, bounded (5,000 customers by 40 payments, 1,000 merchants by 200) and evicted least recently used. It holds tokens, amounts, decisions, reason names, city, and coordinates. It is cleared on reset.
- Case actions (Approve, Decline, Escalate, Request verification, notes) are written to the audit chain with the analyst note.
- Map tiles come from OpenStreetMap. The browser fetches tiles by area only. No payment, token, or coordinate is sent to the tile server.
- Audit payloads are AES-256-GCM at rest.
- Retention redacts old payloads and rebuilds the chain (`POST /audit/retention`).
- Aligned with the direction of India's DPDP Act 2023 (purpose limitation, minimization) and RBI expectations for digital payment security (authentication step-up, audit, incident control via the kill switch).

## 4. Data principles
- Pydantic rejects a negative amount, a short vector, or a wild timestamp before the model sees it.
- Duplicates inside 30 seconds cannot be approved twice; the retry becomes `STEP_UP`.
- Windows are strictly causal.
- Every artifact carries lineage: seed, hashes of both CSVs, timestamp, model name.
- Imported datasets (`python -m ml.import_dataset`) go through a fixed policy before training. Names, street, job, date of birth, transaction numbers, and similar columns are dropped as PII. Known leaks (`isFlaggedFraud`) and any single column whose AUC against the label is above 0.98 are dropped as leakage. Row ids and monotonic counters are dropped as identifiers. Free text is dropped. Every drop is listed in `report.json` and on the Data page.
- Imported files are split by time, 70/30, when no test file is given. Each dataset gets its own artifact and metrics. Switching the live model is `POST /datasets/activate`, which is audited.
- Fields a file does not have are shown as simulated or unavailable. Nothing is invented for real rows.

## 5. Transparency and encryption
- Top-3 reason codes on flagged decisions. The linear champion uses the closed form of SHAP (coefficient times the standardized feature). TreeSHAP is used if a tree model is champion.
- SHA-256 hash chain. `GET /audit/verify` walks it. `POST /audit/tamper` is a demo hook that breaks one record so the jury can see detection.
- API key on every route except `/health` and the docs. A per-host request budget of 5,000 requests per second returns HTTP 429.
- TLS belongs in front of the container in any real deployment. The demo binds localhost.

## 6. Prompt principles
- The copilot receives decision, regime, and reason codes. Never a raw transaction.
- The system prompt forbids changing the decision or inventing features.
- Temperature 0. If `SURGESHIELD_LLM_KEY` is unset, a fixed template is used. The response always says the model owns the decision.

## 7. Documents
- `README.md` one-command run.
- `docs/MODEL_CARD.md`, `docs/DATASHEET.md`, `docs/THREAT_MODEL.md`, `docs/PITCH.md`.
- OpenAPI at `http://localhost:8000/docs`.
- Diagrams in `docs/diagrams/` and PNG exports in `docs/img/`.
