# Pitch (about 5 minutes)

## 0:00 The loss
"During a flash sale our bank can do one of two bad things. Tighten the rules, and Rahul's card dies at checkout while he is buying a laptop that 4,000 other people are also buying. Loosen the rules, and a bot ring drains accounts in the same minute, because the spike hides them. Static thresholds make us pick a loss."

## 0:40 The data, said honestly
"The file we were given is 199,364 payments, 344 frauds, two days, PCA components, amount, and time. There is no user id and no merchant id. Approving everyone is 99.83% accurate and saves nobody. Fraud is twenty times higher around 2am, and the fraudulent tickets are smaller than normal ones, not larger. So 'big amount at a busy hour' is the wrong rule."

## Micro versus macro
A sale and a drain can post the same volume. The difference is the mix.

| Signal | Genuine sale | Attack | Source |
| --- | --- | --- | --- |
| Merchant concentration | One store, many buyers | Mule: two cash-out stores, and the vectors match | Live tokens |
| Round amounts | Sale prices, not neat thousands | ₹1,000, ₹10,000, ₹49,999 | Amount |
| Arrival cadence | Uneven, people hesitate | Fixed gap | Timestamps |
| Geography and device | Clustered cities, many phones | Scattered cities, three devices | Simulated telemetry |
| Session, clicks, typing, mouse | Browse then pay | Direct call, uniform gaps | Simulated telemetry |

Simulated rows are badged in the drawer. They are not in the training file, and they never block by themselves. A bot-like session becomes an OTP step-up. The champion still produces the score. The 0–100 dial is that probability, not a second formula.

## Where the brief's features live

| Brief | What you see | Simulated? |
| --- | --- | --- |
| 1.1–1.4 stream, latency, amount, velocity | Decision feed, p99 tile, drawer amount ratio, fan-out | No |
| 1.5–1.7 round amounts, near-cap, cadence | Surge verdict gauges | No |
| 2.1–2.7 surge vs attack, gini, geography, ramp, flash sale, devices, amount shape | Regime banner, surge verdict, merchant flash-sale chip | Geography and device are simulated |
| 3.1–3.7 spending, familiarity, category, hour, region, new user, personal pace | Decision drawer | Region is simulated |
| 4.1–4.5 merchant baseline, surge ratio, category risk, unique buyers, ticket size | Drawer and flash-sale chip | Category is simulated in the demo |
| 5.1–5.5 session, actions, typing, mouse, interval | Human score. Under 35 becomes an OTP, never a block | Yes, badged |
| 6.1–6.6 moving thresholds, three decisions, 0–100 dial, reasons, false declines, review offsets | Command KPIs, Model page | No |
| 7.1–7.7 feed, surge-vs-attack chart, dial, city tiles, merchant donut, decision donut, threshold panel | Command and Model | City tiles use simulated region |
| 8.1–8.5 `/api/analyze`, `/api/surge-status`, WebSocket, `/score/batch`, `/score/csv`, rate limit | API | No |
| 9.1–9.2 silent approve, OTP step-up | Decision | No |
| 10.1–10.5 confusion, false declines, rupees stopped, latency, incident filing | Analytics, Command, Incidents | No |

## 1:20 The idea
"Volume is not the signal. The shape of the volume is. A real sale gets louder but stays diverse, and the risk scores do not jump. An attack is a tight knot of look-alike payments, often a few rupees first and then the drain. We approve, or we ask for OTP, or we block. We do not decline a grey-zone customer."

## Jury mode
Press J, or the Jury mode button. Space advances, Backspace goes back, Esc exits. Nine chapters: normal, flash sale, bot ring, attack inside the sale, the new shapes, Big Billion Days in the War Room, a customer case, tamper and kill switch, then the before/after scorecard. If the API is down, the overlay plays the backup video.

## 1:50 Live
Run `scripts/reset_demo.sh` before this, or Governance Verify shows the chain that was tampered in testing. Read the numbers on screen. Do not quote a latency, a percentage, or a decision count from memory.

1. Overview. Point at p50 and p99, and at the share of payments with zero friction.
2. Sale War Room. Press B. The sale goes to SURGE, then its own attack phases latch ATTACK on that segment only. There is no inject button.
3. Investigate. Click Run the model. It reads each stored history and writes Status and Why. Open cases were repeatedly flagged, so expect declines there, not a quiet approval.
4. Analytics. Click Replay scenarios. About 10 seconds. The live stream is not reset, and the five-seed report is unchanged.
5. Sale War Room. Boundary probe. The feed shows how far the risk sits under the block line. The decision stays a step-up.
6. Governance. Verify, tamper one record, verify again, flip the kill switch. Payments keep flowing. The switch selects the fallback rule. It does not pause the queue, and nothing in the product times that click at 200 ms.

## Detection matrix
Five seeds each. "Latch" is the share of runs that entered ATTACK. Baseline is the old geometry-only detector. After is density, graph, sequence, and diversity together. A latch of 0 on the flash sale is the result we want.

| Shape | Signal | Baseline latch | After | Rupees leaked before latch |
| --- | --- | --- | --- | --- |
| Flash sale | Diversity stays high, so this stays SURGE | 0 | 0 | 0 |
| Classic bot ring | Tight cluster plus probe-drain | 1.0 | 1.0 | 0 |
| Noisy ring (noise 0.08) | kNN density versus that segment's own spread | 1.0 | 1.0 | 0 |
| Split across two segments | Same, on whichever cohort is tighter | 1.0 | 1.0 | 0 |
| Hidden inside a sale | Geometry inside the busy window | 0.8 | 1.0 | ₹1,254 → ₹216 |
| Low and slow (~4 min) | 300s window plus CUSUM ramp | 0 | 1.0 | 0 |
| Card testing (sub-₹2, many merchants) | Tiny-amount burst | 0 | 1.0 | 0 |
| Account takeover (one user, 18 merchants) | Fan-out on the token | 0 | 0.8 | 0 (rows already blocked) |
| Mule fan-in (many cards, 2 merchants) | Fan-in plus tightness | 0 | 1.0 | 0 |
| Distributed drain (many merchants, round amounts) | Tight clones, plus a suspicious-surge verdict | not in the old set | 1.0 | ₹12,960 before the latch |

The noisy ring did not slip past the old tightness cut on this file. We do not claim it did. The real gaps were slow pacing, card testing, fan-out, and mule fan-in. Shadow LightGBM blocks the classic rings, and on account takeover its block rate is 0.83 against the champion's row recall of 1.0, so the tree is still not the decision.

## Big Billion Days and Great Indian Festival
Press B or G, then open the Sale War Room. The sale plays as phases: warm-up, the midnight open, then attacks riding the rush.

| Phase | What the attacker does | What catches it |
| --- | --- | --- |
| Midnight open | Nothing. Genuine buyers pile onto flagship merchants | Stays SURGE. Thresholds relax for the calm segments |
| Scalper bots | One device, many accounts, near-cap tickets on mobiles | Device farm chip (four or more accounts on one device in five minutes) plus the champion score |
| Card testing | Sub-₹2 probes across many merchants | Card-test detector latches ATTACK |
| Account takeover | One token, a far city, many merchants | Impossible travel (300 km or more, faster than 900 km/h) plus fan-out |
| Mule cash-out | Many cards into two merchants | Fan-in plus tightness |
| Distributed drain (Festival) | Round amounts, fixed cadence | Suspicious-surge verdict and cloned-vector tightness |

Device farm and impossible travel only ever raise a payment to an OTP. They never block on their own. The block still comes from the champion probability.

Red team, five seeds each, on the held-out file: every sale latched ATTACK, fraud row recall 1.0, false-decline rate 0.15% of genuine buyers. Rupees paid before the latch averaged ₹2,650 on Big Billion Days and ₹3,058 on the Festival, mostly the uncaught share of OTP step-ups. The static threshold has no latch at all.

Every flagged customer opens a case in Investigate: profile, map of flagged cities, timeline, AI insights, notes, and Approve, Decline and flag, Escalate, or Request verification. Approve and Decline release or uphold that customer's open review, and every action is in the audit chain. Search takes a raw customer or merchant id, tokenizes it on the server, and never stores it.

## 3:30 The numbers
PR-AUC 0.765 on the held-out file. Recall 0.83 at a 0.1% false-positive rate. Precision 0.78 at the block cut. Shadow LightGBM is 0.80 raw and we still did not let it decide, because the time holdout preferred the linear model. With explanations off, p99 on the laptop is about 2 ms and the batch path clears 1,000 transactions a second. The live feed with reason codes is about 10 to 16 ms. Do not say accuracy.

## 4:10 Trust
"The model decides. The copilot only translates reason codes, and only if we give it a key. The audit log is encrypted, hash-chained, and retention-redacted. We cannot test gender or age bias because those columns were removed before we arrived, and we will not pretend otherwise."

## 4:40 Roadmap
Federated training across issuers. The live token graph already runs on HMAC ids the bank sends at checkout. The training file still has none, so those two features are neutral offline. Analyst Uphold and Release nudge a segment threshold by at most 0.03, and a challenger can be proposed from those labels. A person promotes it. It does not replace the champion by itself.

## If they ask
- **No raw ids in the model.** Checkout can send a user and a merchant. We HMAC them and count fan-in and fan-out. The training CSV has neither column, so `user_velocity_60` and `merchant_fan_in_300` are 0 offline and only matter live.
- **Only 332 frauds after duplicates (344 in the raw file).** Time split, one test pass, class weights instead of synthetic fraud.
- **Model fails.** Kill switch. Rules only. The queue does not stop.
- **Is the attack fake?** The vectors are real fraud rows from `test.csv`, which the model never trained on, plus tiny noise, sent as a probe-then-drain burst.
- **Can it run on our data?** `python -m ml.import_dataset --path file.csv` detects IEEE-CIS, PaySim, and Sparkov, or takes `--map` for a custom file. It drops PII and label leaks, splits by time, and the Data page shows which features run on real columns and which are simulated.
- **Why can only the champion block?** Detectors escalate to step-up. Only the trained model has seen enough data to block without wrecking the false-positive rate. The exception is the kill switch: the fallback rule blocks an amount of ₹2,000 or more, and payments keep flowing.
- **What happens in a real flash sale?** The regime goes to SURGE and the block cut relaxes for the sale segment. Big Billion Days and the Great Indian Festival are that proof. The attack phases inside those sales tighten only the attacked segment.
- **How do you handle a new attack?** Replay runs the recorded scenarios. Boundary probe walks the decision edge and stays a step-up. A payment that matches no signal is not blocked by a detector.
- **Privacy?** Names, streets, jobs, emails, and phone numbers are dropped on import. Cards and VPAs are HMAC-tokenized at scoring and the raw id is not stored. A column with solo AUC above 0.98 is dropped as a leak.
- **Can a bank integrate this tomorrow?** Copy `sdk/surgeshield_sdk.py`. There is no package to install. Point `SurgeShieldClient` at the API and call `score()`. The README has the gateway hook.
- **Why are some skills unused?** Those fields are not on a payment row. They stay named so the catalog shows where they would plug in. They are not simulated.
