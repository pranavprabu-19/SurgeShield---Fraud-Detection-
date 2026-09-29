# Model card

## Model
- Champion: class-weighted logistic regression on standardized features, then Platt scaling. On the time holdout it beat LightGBM, which is the honest result for this PCA file: the fraud is close to linearly separable, and a huge class weight makes the trees worse.
- Shadow: LightGBM, 400 trees, `scale_pos_weight=1`. Logged on every decision, never used to decide. On the random test file its raw PR-AUC is 0.799, against the champion's 0.765. We did not promote it, because the time slice disagreed.
- Novelty: IsolationForest on legitimate rows. It runs when a score enters the grey zone. Obvious approvals skip it so checkout stays under a millisecond.
- Fusion: a stacker is kept only if it improves the time holdout. On this training run it did not, so the decision score is the calibrated champion probability.
- Held-out `test.csv`: PR-AUC 0.765, ROC-AUC 0.934, recall 0.833 at a 0.1% false-positive rate. At the block cut: precision 0.776, recall 0.819, false-positive rate 0.04%.
- Reasons for the linear champion are the closed form of SHAP against the training mean: coefficient times the standardized feature. TreeSHAP is the fallback if a tree model is champion.

## Data
- `train/train.csv` and `train/test.csv` from the hackathon bundle.
- Default dataset is the PCA credit-card file: `Time`, `V1`–`V28`, `Amount`, `Class`. Set `SURGESHIELD_DATASET` to `ieee_cis`, `paysim`, or `sparkov` and `SURGESHIELD_DATA_PATH` to that file. The adapter renames columns. It does not put age, gender, or geography into the model.
- On the default file, `user_velocity_60` and `merchant_fan_in_300` are 0 offline. On a file that has ids, those windows are computed from earlier rows only. `device_share` is added only when a device column exists.
- Duplicates dropped. No nulls.
- No raw identifiers exist, so none are stored.

## Split
- Inside the training file, ordered by `Time`: 80% fit, 10% calibration, 10% threshold selection.
- `test.csv` is scored once, after thresholds are frozen.
- Rolling features use only earlier rows.

## Decision policy
- `STEP_UP` below the block cut, `BLOCK` above it.
- Cuts minimize missed-fraud amount plus false-decline cost, not F1.
- In SURGE the cuts loosen for segments that are not under attack. SURGE also requires segment diversity of at least 0.45. High volume with low diversity is a suspicious surge: step-up on that cohort, not a block of the whole sale.
- In ATTACK the cuts tighten for the attacked segment, and for a merchant token that accounts for at least 30% of that segment's recent events.
- Attack evidence is geometry (kNN tightness versus the segment's training spread), fan-in, fan-out, a CUSUM amount ramp, and a card-testing burst. Any of those can latch ATTACK. Fan-in alone cannot, so a one-merchant sale stays a sale.
- Analyst Uphold and Release write a feedback row. With at least four labels on a segment, its thresholds move by at most ±0.03. The change is audited and the kill switch ignores it.
- A challenger logistic model can be fit on earlier feedback and scored on the later labels. Promotion is a separate human action and does not swap the live champion.
- Kill switch: rule-only safe mode (large amount, or a tight overnight burst).

## Limits
- 344 fraud labels in the raw training file, 332 after duplicates. The model can overfit a rare pattern; the time split and the single test evaluation are the guard.
- Fairness by age, gender, or geography cannot be measured. Those fields are not in the file. We can only watch amount and hour.
- `user_velocity_60` and `merchant_fan_in_300` are stream features. Training rows have no ids, so both are 0 in the fit and in the offline metrics. They are filled from HMAC tokens only at serve time.
- Merchant concentration, round-amount share, and arrival regularity are live regime inputs. They are not model features on the PCA file.
- `merchant_familiarity` and `user_amount_ratio` are computed from earlier rows only when the dataset has ids. They are absent from the credit-card artifact.
- Checkout may send session, click, typing, and mouse fields. Only `human_score` is kept, and a score under 35 can step a payment up. It cannot block one. The simulator marks its telemetry as simulated.
- `risk_100` is the champion probability times 100. The `layers` object (model, surge, context, behavior) explains that number. None of those layers can block a payment on its own.
- Behavioral segments are still PCA cohorts. The merchant and user counts are a second, live-only signal. They are not in the held-out PR-AUC.
- The attack scenario replays real fraud vectors from `test.csv` with small noise. It is a demonstration of coordination, not a claim that every future ring will look like this.
- OTP is assumed to stop 70% of challenged fraud. That assumption is shown in the UI and is not hidden inside the model.

## Owners
- Decisions: the model and the policy.
- Explanations: linear SHAP equivalent for the current champion, TreeSHAP if a tree wins, or a z-score fallback if either fails.
- The copilot may rephrase reason codes. It cannot change a decision, and it never receives a raw row.
