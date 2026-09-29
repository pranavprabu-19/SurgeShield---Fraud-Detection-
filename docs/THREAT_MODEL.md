# Threat model

## What we protect
- Cardholder funds during a traffic spike.
- Legitimate buyers from a false decline.
- The integrity of the decision log.
- The absence of raw identifiers in that log.

## Assumptions
- The scoring API is on a private network. The demo key is not a production secret.
- `V1`–`V28` are already anonymized. We do not try to invert PCA.
- The model file and `SURGESHIELD_SECRET` are deployed together and rotated together.

## Abuse we designed for
- A bot ring of look-alike vectors, probes then drains, including one hidden inside a sale. Answer: per-segment kNN density, compared with that segment's training spread, plus regime-aware thresholds.
- The same ring stretched over about four minutes. Answer: a 300-second window and a CUSUM on log amount, so the ramp does not have to jump from under ₹8 to over ₹40.
- Card testing: many sub-₹2 payments across many merchants, no drain. Answer: the card-test detector latches ATTACK when tiny amounts dominate and touch at least eight merchants.
- Account takeover: one token across many merchants in a minute. Answer: fan-out on the HMAC user token.
- Mule fan-in: many tokens paying two cash-out merchants. Answer: fan-in, and it only counts when those payments are also unusually alike. A genuine sale into one merchant stays diverse and is not an attack.
- Distributed drain: many users, many merchants, round amounts, a fixed cadence, and a handful of devices. Answer: the surge verdict goes SUSPICIOUS, and the cloned vectors still latch ATTACK through tightness. Merchant count alone is not the rule, because a real sale is also many buyers into one store.
- Scalper bots during a sale open: many accounts on one device buying near-cap mobiles. Answer: the device farm chip fires at four or more accounts on one device token in five minutes, and the payment steps up to OTP. It does not block by itself. On files where the device column is a model name (IEEE-CIS `DeviceInfo`), the detector is off, because thousands of honest buyers share one phone model.
- A device farm that rotates a fresh device per account. Answer: the chip goes quiet. Tightness, cadence, and the champion score still apply.
- Account takeover from another city: a stolen token paying from a location it could not have reached. Answer: impossible travel fires at 300 km or more at faster than 900 km/h since the token's last payment, with a one-second floor on the gap. It steps up only. Simulated city centroids are jittered per token and badged as simulated; a missing location is unavailable, never guessed.
- A bot that sends no telemetry. Answer: nothing happens. Missing behavior is not evidence.
- A bot that copies human session timing. Answer: the behavior step-up does not fire. Geometry, fan-out, and the champion score still apply. We do not claim telemetry is unforgeable.
- A ring split across two PCA segments. Answer: each segment is scored on its own.
- A retry storm of the same payment. Answer: 30-second fingerprint, second copy cannot be a clean approve.
- An operator who edits the audit database. Answer: hash chain verification names the broken record.
- A bad model push, or a threshold that drifted from review labels. Answer: kill switch to rules. Adaptive offsets are capped at ±0.03. LightGBM remains a shadow score. A challenger fit on review labels cannot promote itself.

## Abuse we do not claim to solve here
- Account takeover that looks exactly like the real customer, stays on their usual merchants, and spends like them. Fan-out needs many merchants. The training file has no device graph.
- A patient attacker who stays under eight look-alike events. On the measured grid (noise 0.01 to 0.15, spacing 0.22s to 6s) every cell still latched. That grid does not prove a wider or slower ring will.
- A VPN or GPS spoof that places the attacker in the victim's city. Impossible travel only sees where the payment claims to be.
- Theft of `SURGESHIELD_SECRET`. Anyone with it can mint tokens and decrypt the audit log. Production should use a KMS.

## Residual risk
- Thresholds were chosen on a few dozen holdout frauds. A shift in fraud mix moves the rupee-optimal cut. The PSI alert is the tripwire, not a promise that the cut stays optimal.
