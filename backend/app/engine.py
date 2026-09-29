"""Load artifacts and decide one transaction at a time."""

from __future__ import annotations

import hashlib
import json
import os
import queue
import threading
import time
import warnings
from collections import OrderedDict, deque
from pathlib import Path

warnings.filterwarnings("ignore", message="X does not have valid feature names")

import joblib
import numpy as np

from backend.app.context import ContextStore
from backend.app.coordination import analyze
from backend.app.copilot import explain as copilot_explain, summarize_case
from backend.app.governance.audit import AuditLog
from backend.app.governance.drift import histogram, population_stability
from backend.app.governance.explain import top_reasons
from backend.app.behavior import human_score
from backend.app.geo import locate
from backend.app.skills import judge_history, mark, mark_velocity, notes as skill_notes, step_up as skill_step_up
from backend.app.history import History
from backend.app.sales import SALE_EVENTS
from backend.app.governance.privacy import tokenize
from backend.app.profiles import ProfileStore
from backend.app.surge_context import compose
from backend.app.graph import analyze_graph
from backend.app.policy import friction_tier, safe_mode_decision, static_decision, surge_shield_decision
from backend.app.regime import RegimeDetector
from ml.schema import (
    ARTIFACT_PATH,
    FEATURE_NAMES,
    ROOT,
    STEP_UP_CATCH_RATE,
    STEP_UP_FRICTION,
    TIGHT_DIMS,
    V_COLS,
)


def _fresh_totals() -> dict:
    return {
        "seen": 0,
        "ss_approve": 0,
        "ss_step": 0,
        "ss_block": 0,
        "ss_fraud_caught_amt": 0.0,
        "ss_fraud_missed_amt": 0.0,
        "ss_legit_blocked_amt": 0.0,
        "ss_legit_blocked_n": 0,
        "st_block": 0,
        "st_approve": 0,
        "st_fraud_caught_amt": 0.0,
        "st_fraud_missed_amt": 0.0,
        "st_legit_blocked_amt": 0.0,
        "st_legit_blocked_n": 0,
        "latency_p50": 0.0,
        "latency_p99": 0.0,
        "ss_legit_step_n": 0,
        "ss_legit_approved_amt": 0.0,
        "ss_legit_approved_n": 0,
        "friction_none": 0,
        "friction_device": 0,
        "friction_push": 0,
        "friction_otp": 0,
        "friction_auth": 0,
        "friction_blocked": 0,
    }


_RECENT_KEYS = (
    "id",
    "decision",
    "score",
    "shadow_score",
    "anomaly",
    "regime",
    "mode",
    "amount",
    "segment",
    "latency_ms",
    "reasons",
    "static_decision",
    "scenario",
    "coordination",
    "tightness",
    "probe",
    "vol_z",
    "psi",
    "duplicate",
    "user_token",
    "merchant_token",
    "eval_label",
    "detectors",
    "evidence",
    "diversity",
    "surge",
    "profile",
    "human_score",
    "telemetry_simulated",
    "risk_100",
    "layers",
    "region",
    "phase",
    "lat",
    "lon",
    "geo_source",
    "device_token",
    "category",
)


class Engine:
    def __init__(self, artifact_path=ARTIFACT_PATH, audit_path=None):
        self.art = joblib.load(artifact_path)
        iforest = self.art.get("iforest")
        if iforest is not None:
            iforest.n_jobs = 1
        self.ctx = ContextStore()
        self.profiles = ProfileStore()
        self.history = History()
        self.phase_stats: dict = {}
        self.flash_merchants = []
        self.regime = RegimeDetector()
        secret = hashlib.sha256(os.environ.get("SURGESHIELD_SECRET", "surgeshield-demo-secret").encode()).digest()
        self.secret = secret
        data_dir = ROOT / "backend" / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        own_audit = audit_path is not None
        if audit_path is None:
            audit_path = os.environ.get("SURGESHIELD_AUDIT_PATH", str(data_dir / "audit.db"))
        self.audit = AuditLog(str(audit_path), secret)
        self.controls_path = data_dir / "controls.json"
        self.safe_mode = False
        if not own_audit and self.controls_path.exists():
            self.safe_mode = bool(json.loads(self.controls_path.read_text()).get("safe_mode", False))
        self.recent_scores: deque = deque(maxlen=400)
        self.latencies: deque = deque(maxlen=800)
        self.recent: deque = deque(maxlen=200)
        self.fingerprints: deque = deque(maxlen=4000)
        self.probe_ring: OrderedDict = OrderedDict()
        self.totals = _fresh_totals()
        self._seq = 0
        self.buckets: deque = deque(maxlen=180)
        self._open_bucket = None
        self.samples: deque = deque(maxlen=4000)
        self.psi_history: deque = deque(maxlen=180)
        self.incidents: list = []
        self._incident_seq = 0
        self._open_incident = None
        self.scenario_runs: dict = {}
        self.threshold_offsets: dict = {}
        self._review_meta: dict = {}
        self._pending_features: dict = {}
        self.challenger = {"status": "idle"}
        self.story_events: list = []
        self._story_seq = 0
        self._saw_fraud = False
        self._latched = False
        self._leak_before = 0.0
        self._blocks_before = 0
        self._blocks_after = 0
        self.group_stats: dict = {}
        self.feature_names = list(self.art.get("feature_names") or FEATURE_NAMES)
        self._name_at = {name: i for i, name in enumerate(self.feature_names)}
        self.artifact_sha256 = hashlib.sha256(Path(artifact_path).read_bytes()).hexdigest()
        self.lock = threading.Lock()
        self._explainer = None
        self.scenario = "idle"
        self._audit_queue = queue.Queue(maxsize=20000)
        self._audit_thread = threading.Thread(target=self._audit_loop, daemon=True)
        self._audit_thread.start()

    def load_artifact(self, artifact_path) -> dict:
        art = joblib.load(artifact_path)
        iforest = art.get("iforest")
        if iforest is not None:
            iforest.n_jobs = 1
        digest = hashlib.sha256(Path(artifact_path).read_bytes()).hexdigest()
        with self.lock:
            self.art = art
            self.feature_names = list(art.get("feature_names") or FEATURE_NAMES)
            self._name_at = {name: i for i, name in enumerate(self.feature_names)}
            self.artifact_sha256 = digest
            self._explainer = None
            self.threshold_offsets = {}
        self.reset()
        return {"dataset": art.get("dataset"), "model": art.get("lineage", {}).get("model"), "artifact_sha256": digest}

    def _audit_loop(self) -> None:
        while True:
            payload = self._audit_queue.get()
            try:
                self.audit.append(payload)
            except Exception:
                continue

    def reset(self) -> None:
        with self.lock:
            if self.scenario not in {"", "idle"} and self.totals["seen"]:
                self.scenario_runs[self.scenario] = {
                    "scenario": self.scenario,
                    "totals": dict(self.totals),
                    "regime": self.regime.state,
                }
            self._finalize_bucket()
            self.ctx.reset()
            self.profiles.reset()
            self.history.reset()
            self.phase_stats = {}
            self.flash_merchants = []
            self.regime.reset()
            self.recent_scores.clear()
            self.latencies.clear()
            self.recent.clear()
            self.fingerprints.clear()
            self.probe_ring.clear()
            self.totals = _fresh_totals()
            self.samples.clear()
            self.buckets.clear()
            self._open_bucket = None
            self.psi_history.clear()
            self.incidents.clear()
            self._open_incident = None
            self.story_events = []
            self._story_seq = 0
            self._saw_fraud = False
            self._latched = False
            self._leak_before = 0.0
            self._blocks_before = 0
            self._blocks_after = 0
            self.group_stats = {}
            self.scenario = "idle"

    def set_safe_mode(self, enabled: bool, reason: str = "") -> dict:
        with self.lock:
            self.safe_mode = enabled
            self.controls_path.write_text(json.dumps({"safe_mode": enabled, "reason": reason[:500]}))
        self.audit.append({"type": "kill_switch", "safe_mode": enabled, "reason": reason[:500]})
        return {"safe_mode": enabled, "reason": reason[:500]}

    def note_feedback(self, review_id: int, action: str) -> dict:
        meta = self._review_meta.pop(int(review_id), {})
        segment = int(meta.get("segment") or 0)
        score = float(meta.get("score") or 0.0)
        self.audit.save_feedback(int(review_id), action, segment, score, meta.get("features"))
        self._recompute_offsets()
        self.audit.append({"type": "threshold_adapt", "segment": segment, "action": action, "offset": self.threshold_offsets.get(segment, 0.0)})
        return self.adapt_status()

    def _recompute_offsets(self) -> None:
        grouped: dict = {}
        for row in self.audit.list_feedback(80):
            grouped.setdefault(int(row["segment"]), []).append(int(row["label"]))
        offsets = {}
        for segment, labels in grouped.items():
            if len(labels) < 4:
                continue
            release_rate = 1.0 - (sum(labels) / len(labels))
            offsets[segment] = float(np.clip((release_rate - 0.5) * 0.06, -0.03, 0.03))
        self.threshold_offsets = offsets

    def adapt_status(self) -> dict:
        return {
            "offsets": {str(key): round(value, 4) for key, value in self.threshold_offsets.items()},
            "feedback": len(self.audit.list_feedback(200)),
            "cap": 0.03,
            "challenger": self.challenger,
        }

    def train_challenger(self) -> dict:
        from ml.challenger import propose

        self.challenger = propose(self.audit.list_feedback(500))
        return self.challenger

    def promote_challenger(self) -> dict:
        if not self.challenger.get("recommend"):
            return {"ok": False, "reason": "challenger is not recommended"}
        self.challenger = {**self.challenger, "promoted": True, "status": "promoted"}
        self.audit.append({"type": "challenger_promoted", "n": self.challenger.get("n")})
        return {"ok": True, "challenger": self.challenger}

    def _push_story(self, kind: str, label: str, when: float) -> None:
        self._story_seq += 1
        self.story_events.append({"seq": self._story_seq, "kind": kind, "label": label, "t": round(float(when), 3)})

    def _note_story(self, when: float, decision: str, prev: str, regime: str, amount: float, label) -> None:
        if not self.story_events:
            self._push_story("start", "First event", when)
        if regime != prev:
            self._push_story("regime", f"Regime {prev} to {regime}", when)
        if label == 1 and not self._saw_fraud:
            self._saw_fraud = True
            self._push_story("fraud", "First fraud row", when)
        if regime == "ATTACK" and not self._latched:
            self._latched = True
            self._push_story("latch", "ATTACK latched", when)
        if decision == "BLOCK":
            if self._latched:
                self._blocks_after += 1
            else:
                self._blocks_before += 1
        if label == 1 and decision != "BLOCK" and not self._latched:
            self._leak_before += float(amount)

    def story(self) -> dict:
        with self.lock:
            return {
                "scenario": self.scenario,
                "milestones": list(self.story_events),
                "blocks_before_latch": self._blocks_before,
                "blocks_after_latch": self._blocks_after,
                "rupees_leaked_before_latch": round(self._leak_before, 2),
                "totals": dict(self.totals),
            }

    def _note_fairness(self, txn: dict, decision: str) -> None:
        groups = txn.get("groups") or {}
        label = txn.get("eval_label")
        for key, value in groups.items():
            slot = self.group_stats.setdefault(str(key), {})
            row = slot.setdefault(str(value), {"seen": 0, "legit": 0, "legit_blocked": 0, "step": 0})
            row["seen"] += 1
            if decision == "STEP_UP":
                row["step"] += 1
            if label == 0:
                row["legit"] += 1
                if decision == "BLOCK":
                    row["legit_blocked"] += 1

    def fairness(self) -> dict:
        with self.lock:
            groups = {}
            for key, values in self.group_stats.items():
                rates = []
                rows = []
                for name, row in values.items():
                    legit = row["legit"] or 0
                    decline = (row["legit_blocked"] / legit) if legit else 0.0
                    step = (row["step"] / row["seen"]) if row["seen"] else 0.0
                    if row["seen"] >= 5:
                        rates.append(decline)
                    rows.append({
                        "value": name,
                        "seen": row["seen"],
                        "false_decline_rate": round(decline, 4),
                        "step_up_rate": round(step, 4),
                    })
                ratio = None
                if len(rates) >= 2 and min(rates) > 0:
                    ratio = round(max(rates) / min(rates), 3)
                elif len(rates) >= 2:
                    ratio = None
                groups[key] = {"rows": rows, "disparity_ratio": ratio}
            return {
                "available": bool(groups),
                "groups": groups,
                "note": "Sensitive columns are counted here and are not model inputs.",
            }

    def score(self, txn: dict, explain: bool = True) -> dict:
        started = time.perf_counter()
        with self.lock:
            result = self._score_locked(txn, explain, started)
        if result["decision"] in {"BLOCK", "STEP_UP"} and not result["duplicate"]:
            review_id = self.audit.enqueue_review(
                result["decision"], result["score"], result["amount"], result["reasons"]
            )
            result["review_id"] = review_id
            self._review_meta[review_id] = {
                "segment": result["segment"],
                "score": result["score"],
                "features": self._pending_features.pop(result["id"], None),
            }
        self.history.record(result)
        try:
            self._audit_queue.put_nowait(self._audit_payload(result))
        except queue.Full:
            pass
        return result

    def _score_locked(self, txn: dict, explain: bool, started: float) -> dict:
        vector_in = np.asarray(txn["v"], dtype=float)
        amount = float(txn["amount"])
        now = float(txn["time"])
        distances = np.linalg.norm(self.art["kmeans"].cluster_centers_ - vector_in, axis=1)
        segment = int(distances.argmin())
        dist = float(distances[segment])
        amt_z = float((amount - self.art["seg_mean"][segment]) / self.art["seg_std"][segment])
        counts = self.ctx.window_counts(now, segment)
        user_token = tokenize(txn.get("user_id"), self.secret)
        merchant_token = tokenize(txn.get("merchant_id"), self.secret)
        recent = self.ctx.tail(96)
        graph = analyze_graph(recent, now, user_token, merchant_token)
        device = txn.get("device") or ""
        device_token = tokenize(device, self.secret) if device else ""
        lat, lon, geo_source = locate(txn.get("region") or "", txn.get("lat"), txn.get("lon"), user_token or "")
        hour = int((now // 3600.0) % 24)
        velocity = 1
        sharing = {user_token} if device_token else None
        for row in recent:
            age = now - row["time"]
            if age < 0 or age > 300.0:
                continue
            if age <= 60.0 and row.get("user") == user_token:
                velocity += 1
            if sharing is not None and row.get("device") == device_token:
                sharing.add(row.get("user"))
        profile = self.profiles.signals(
            user_token,
            merchant_token,
            amount,
            hour,
            txn.get("category") or "",
            txn.get("region") or "",
            device_token,
            now,
            velocity,
            lat,
            lon,
        )
        if sharing is not None:
            sharing.discard("")
            sharing.discard(None)
            profile["device_users"] = len(sharing)
            profile["device_farm"] = len(sharing) >= 4
        mark(profile, txn)
        mark_velocity(profile, velocity)
        features = self._vector(txn, segment, dist, amt_z, counts, graph, profile)
        duplicate = self._seen_recently(vector_in, amount, now)

        try:
            score, shadow, anomaly = self._fuse(features, explain=explain)
            failed = False
        except Exception:
            score, shadow, anomaly = 0.0, 0.0, 0.0
            failed = True

        snapshot_event = ContextStore.snapshot(txn, segment, user_token, merchant_token)
        snapshot_event["risk"] = float(score)
        snapshot_event["device"] = device_token
        self.ctx.add(snapshot_event)
        tail = self.ctx.tail(96)
        ramp = counts[0] * 6.0 / max(counts[1], 1)
        surge = compose(tail, ramp=ramp)
        human = human_score(txn.get("telemetry"))
        profile["flash_sale"] = bool(
            profile.get("merchant_n", 0) >= 20
            and profile.get("merchant_surge_ratio", 0) >= 5
            and profile.get("unique_share", 0) >= 0.8
            and (human is None or human >= 35)
        )
        if profile["flash_sale"] and merchant_token and merchant_token not in self.flash_merchants:
            self.flash_merchants.append(merchant_token)
            self.flash_merchants = self.flash_merchants[-20:]
        self.profiles.update(
            user_token,
            merchant_token,
            amount,
            hour,
            txn.get("category") or "",
            txn.get("region") or "",
            device_token,
            now,
            velocity,
            lat,
            lon,
        )
        snap = analyze(
            tail,
            now,
            self.art["cnt60_mean"],
            self.art["cnt60_std"],
            spreads=self.art.get("segment_spread"),
            graph=graph,
            count_60=counts[1],
            surge=surge,
            profile=profile,
        )
        self.recent_scores.append(float(score))
        snap["psi"] = self._psi()
        prev_regime = self.regime.state
        regime = self.regime.update(snap)
        cfg = self.art["thresholds"]
        profile["model_probe"] = self._note_probe(user_token, now, amount, float(score), float(cfg["t_block"]))
        merchant_hot = False
        if self.safe_mode or failed:
            decision = safe_mode_decision(amount, features[self._name_at["night"]], snap["tightness"], snap["count_60"])
            mode = "SAFE_MODE"
        else:
            offset = float(self.threshold_offsets.get(segment, 0.0))
            merchant_hot = self._merchant_hot(merchant_token, snap, recent)
            decision = surge_shield_decision(
                score,
                regime,
                segment,
                self.regime.attacked_segment,
                cfg,
                suspicious=bool(snap.get("suspicious")),
                merchant_hot=merchant_hot,
                threshold_offset=offset,
                human_score=human,
                context_step_up=bool(
                    profile.get("device_farm") or profile.get("impossible_travel") or profile.get("model_probe") or skill_step_up(profile)
                ),
            )
            mode = "MODEL"
        if duplicate and decision == "APPROVE":
            decision = "STEP_UP"
        self._note_story(now, decision, prev_regime, regime, amount, txn.get("eval_label"))
        self._note_fairness(txn, decision)

        static = static_decision(score, cfg["t_static"])
        attacked = self.regime.attacked_segment
        attack_hot = regime == "ATTACK" and (attacked is None or segment == attacked or merchant_hot)
        friction = friction_tier(decision, score, cfg, profile, amount, regime, attack_hot=attack_hot)
        snap["profile"] = profile
        reasons = self._detector_reasons(snap)
        if explain and decision != "APPROVE":
            reasons = reasons + self._reasons(features)

        latency_ms = (time.perf_counter() - started) * 1000
        self.latencies.append(latency_ms)
        self._account(decision, static, txn.get("eval_label"), amount, friction)
        self._latency_stats()
        self._seq += 1
        self._pending_features[self._seq] = [round(float(v), 5) for v in features]
        result = {
            "id": self._seq,
            "decision": decision,
            "friction": friction,
            "static_decision": static,
            "score": round(float(score), 5),
            "shadow_score": round(float(shadow), 5),
            "anomaly": round(float(anomaly), 5),
            "regime": regime,
            "mode": mode,
            "segment": segment,
            "attacked_segment": self.regime.attacked_segment,
            "coordination": round(float(snap["coordination"]), 4),
            "tightness": round(float(snap["tightness"]), 4),
            "probe": round(float(snap["probe"]), 4),
            "vol_z": round(float(snap["vol_z"]), 3),
            "psi": round(float(snap["psi"]), 4),
            "amount": amount,
            "reasons": reasons,
            "duplicate": duplicate,
            "user_token": user_token,
            "merchant_token": merchant_token,
            "detectors": snap.get("detectors") or {},
            "evidence": snap.get("evidence", 0.0),
            "diversity": snap.get("diversity", 0.0),
            "surge": snap.get("surge") or {},
            "profile": snap.get("profile") or {},
            "human_score": human,
            "telemetry_simulated": bool((txn.get("telemetry") or {}).get("simulated")),
            "risk_100": int(round(float(score) * 100)),
            "layers": self._layers(score, surge, profile, human),
            "region": txn.get("region") or "",
            "phase": txn.get("phase") or "",
            "lat": lat,
            "lon": lon,
            "geo_source": geo_source,
            "device_token": device_token,
            "category": txn.get("category") or "",
            "latency_ms": round(latency_ms, 3),
            "eval_label": txn.get("eval_label"),
            "scenario": self.scenario,
            "safe_mode": self.safe_mode or failed,
            "totals": self.totals,
        }
        if profile.get("model_probe"):
            block_line = int(round(float(cfg["t_block"]) * 100))
            result["boundary_probe"] = {
                "risk_100": result["risk_100"],
                "block_line_100": block_line,
                "gap": block_line - result["risk_100"],
            }
        compact = {k: result[k] for k in _RECENT_KEYS}
        if "boundary_probe" in result:
            compact["boundary_probe"] = result["boundary_probe"]
        self.recent.appendleft(compact)
        self._note_sample(compact, latency_ms)
        self._note_bucket(compact, latency_ms)
        self._note_incident(compact, prev_regime, regime, snap)
        self._note_phase(compact, reasons, now)
        return result

    def skill_review(self) -> dict:
        """Judge each stored customer and merchant from their full history. Called only from Investigate."""
        summary = {"APPROVE": 0, "BLOCK": 0}
        blocked = []
        with self.history._lock:
            pairs = [
                (kind, token)
                for kind, store in self.history.stores.items()
                for token, row in store.items()
                if row["n"] >= 2 or f"{kind}-{token}" in self.history.cases
            ]
        for kind, token in pairs:
            view = self.history.entity(kind, token)
            if view is None:
                continue
            decision, why = judge_history(view["history"], view["summary"])
            summary[decision] += 1
            case = view.get("case")
            if case and case.get("status") == "OPEN":
                self.case_action(case["id"], "DECLINE" if decision == "BLOCK" else "APPROVE", why)
            elif decision == "BLOCK":
                self.case_action(f"{kind}-{token}", "DECLINE", why)
            if decision == "BLOCK":
                blocked.append(
                    {
                        "id": f"{kind}-{token}",
                        "kind": kind,
                        "token": token,
                        "decision": decision,
                        "risk_100": max((event.get("risk_100") or 0) for event in view["history"]) if view["history"] else 0,
                        "payments": view["summary"]["payments"],
                        "flags": view["summary"]["flags"],
                        "amount": view["summary"]["amount"],
                        "why": why,
                    }
                )
        self.audit.append({"type": "case_model_run", "entities": summary["APPROVE"] + summary["BLOCK"], "decisions": summary})
        blocked.sort(key=lambda row: (-row["flags"], -row["risk_100"]))
        return {"payments": summary["APPROVE"] + summary["BLOCK"], "summary": summary, "rows": blocked[:80]}

    def _note_phase(self, compact: dict, reasons: list, now: float) -> None:
        name = compact.get("phase") or "live"
        row = self.phase_stats.get(name)
        if row is None:
            row = {
                "phase": name,
                "n": 0,
                "gmv": 0.0,
                "blocked_amount": 0.0,
                "decisions": {"APPROVE": 0, "STEP_UP": 0, "BLOCK": 0},
                "legit_n": 0,
                "legit_blocked": 0,
                "legit_stepped": 0,
                "fraud_n": 0,
                "fraud_caught": 0,
                "fraud_leaked": 0.0,
                "regimes": {},
                "signals": {},
                "first_t": now,
                "last_t": now,
            }
            self.phase_stats[name] = row
        decision = compact["decision"]
        amount = float(compact["amount"])
        row["n"] += 1
        row["last_t"] = now
        row["decisions"][decision] = row["decisions"].get(decision, 0) + 1
        row["regimes"][compact["regime"]] = row["regimes"].get(compact["regime"], 0) + 1
        if decision == "APPROVE":
            row["gmv"] += amount
        elif decision == "BLOCK":
            row["blocked_amount"] += amount
        label = compact.get("eval_label")
        if label == 0:
            row["legit_n"] += 1
            row["legit_blocked"] += decision == "BLOCK"
            row["legit_stepped"] += decision == "STEP_UP"
        elif label == 1:
            row["fraud_n"] += 1
            if decision == "APPROVE":
                row["fraud_leaked"] += amount
            else:
                row["fraud_caught"] += 1
        if decision != "APPROVE":
            for note in reasons:
                feature = note.get("feature")
                if feature:
                    row["signals"][feature] = row["signals"].get(feature, 0) + 1

    def sale_report(self) -> dict:
        with self.lock:
            rows = [dict(row) for row in self.phase_stats.values()]
            scenario = self.scenario
            totals = dict(self.totals)
        order = [phase["id"] for phase in SALE_EVENTS.get(scenario, {}).get("phases", [])]
        rows.sort(key=lambda row: (order.index(row["phase"]) if row["phase"] in order else 99, row["first_t"]))
        phases = []
        for row in rows:
            seconds = max(row["last_t"] - row["first_t"], 1.0)
            regimes = row.pop("regimes")
            signals = row.pop("signals")
            phases.append(
                {
                    **row,
                    "gmv": round(row["gmv"], 2),
                    "blocked_amount": round(row["blocked_amount"], 2),
                    "fraud_leaked": round(row["fraud_leaked"], 2),
                    "tps": round(row["n"] / seconds, 2),
                    "regime": max(regimes.items(), key=lambda item: item[1])[0] if regimes else "NORMAL",
                    "regimes": regimes,
                    "false_decline_rate": round(row["legit_blocked"] / row["legit_n"], 4) if row["legit_n"] else None,
                    "catch_rate": round(row["fraud_caught"] / row["fraud_n"], 4) if row["fraud_n"] else None,
                    "top_signals": [name for name, _ in sorted(signals.items(), key=lambda item: item[1], reverse=True)[:3]],
                }
            )
        event = SALE_EVENTS.get(scenario)
        names = {tokenize(merchant, self.secret): merchant for sale in SALE_EVENTS.values() for merchant in sale["merchants"]}
        merchants = self.history.top_merchants(10)
        for row in merchants:
            row["name"] = names.get(row["token"])
        return {
            "scenario": scenario,
            "sale": {"id": scenario, "name": event["name"]} if event else None,
            "phases": phases,
            "merchants": merchants,
            "totals": {
                "seen": totals.get("seen", 0),
                "gmv": round(sum(row["gmv"] for row in phases), 2),
                "blocked_amount": round(sum(row["blocked_amount"] for row in phases), 2),
                "fraud_leaked": round(sum(row["fraud_leaked"] for row in phases), 2),
                "legit_blocked": sum(row["legit_blocked"] for row in phases),
                "legit_n": sum(row["legit_n"] for row in phases),
                "fraud_n": sum(row["fraud_n"] for row in phases),
                "fraud_caught": sum(row["fraud_caught"] for row in phases),
            },
        }

    def cases(self) -> list:
        with self.lock:
            incidents = [dict(inc) for inc in self.incidents]
        return self.history.list_cases(incidents)

    def entity_view(self, kind: str, token: str) -> dict | None:
        view = self.history.entity(kind, token)
        if view is None:
            return None
        with self.lock:
            profile = self.profiles.summary(kind, token)
            field = "user_token" if kind == "user" else "merchant_token"
            incidents = []
            for inc in self.incidents:
                hit = token in (inc.get("mules") or []) if kind == "user" else any(
                    member.get("id") in {event["id"] for event in view["history"]} for member in inc.get("members") or []
                )
                if hit:
                    incidents.append({key: inc[key] for key in ("id", "status", "severity", "started_at", "ended_at", "tx_count", "rupees_blocked")})
        review_ids = {event["review_id"] for event in view["history"] if event.get("review_id")}
        reviews = [row for row in self.audit.list_reviews(1000) if row["id"] in review_ids][:20] if review_ids else []
        view["profile"] = profile
        view["incidents"] = incidents
        view["reviews"] = reviews
        view["timeline"] = self._entity_timeline(view)
        view["insights"] = self._entity_insights(kind, view, profile or {})
        view["field"] = field
        return view

    @staticmethod
    def _entity_timeline(view: dict) -> list:
        items = []
        events = list(reversed(view["history"]))
        if events:
            first = events[0]
            items.append({"t": first["t"], "kind": "seen", "label": f"First seen, {first['region'] or 'region unavailable'}"})
        for event in events:
            if event["decision"] != "APPROVE":
                why = event["reasons"][0] if event["reasons"] else "model score"
                items.append({"t": event["t"], "kind": event["decision"].lower(), "label": f"{event['decision']} ₹{event['amount']:.0f}: {why}"})
        for inc in view.get("incidents") or []:
            items.append({"t": inc["started_at"], "kind": "incident", "label": f"Linked to {inc['id']}"})
        case = view.get("case") or {}
        for entry in case.get("actions") or []:
            items.append({"t": entry["t"], "kind": "action", "label": f"Analyst {entry['action'].lower()}" + (f": {entry['note']}" if entry["note"] else "")})
        for entry in case.get("notes") or []:
            items.append({"t": entry["t"], "kind": "note", "label": f"Note: {entry['note']}"})
        items.sort(key=lambda item: item["t"])
        return items[-40:]

    @staticmethod
    def _entity_insights(kind: str, view: dict, profile: dict) -> list:
        notes = []
        summary = view["summary"]
        history = view["history"]
        if summary["payments"]:
            share = summary["flags"] / summary["payments"]
            notes.append(f"{summary['flags']} of {summary['payments']} payments were challenged or blocked ({share:.0%}).")
        regions = {event["region"] for event in history if event["region"]}
        if kind == "user" and len(regions) >= 3:
            notes.append(f"Paid from {len(regions)} cities in its recent history: {', '.join(sorted(regions)[:4])}.")
        devices = {event["device_token"] for event in history if event["device_token"]}
        if kind == "user" and len(devices) >= 3:
            notes.append(f"Used {len(devices)} different devices.")
        signals = [item["name"] for item in summary["signals"][:3]]
        labels = {
            "device_farm": "shares a device with several other accounts",
            "impossible_travel": "moved faster than a plane between payments",
            "fan_out": "one account spread across many merchants",
            "fan_in": "many cards converging on one merchant",
            "card_test": "tiny probe amounts before larger ones",
            "sequence": "amounts ramp from probes into drains",
            "geometry": "payments cloned from one template",
            "surge": "loud traffic that does not look like a genuine sale",
            "context": "unfamiliar merchant, place, device, or hour",
        }
        for name in signals:
            if name in labels:
                notes.append(f"Most frequent signal: {labels[name]}.")
        if kind == "merchant" and profile.get("unique_buyers"):
            notes.append(f"{profile['unique_buyers']} distinct buyers, average ticket ₹{profile.get('avg_amount', 0):.0f}.")
        if view.get("incidents"):
            notes.append(f"Appears in {len(view['incidents'])} coordinated-attack incident(s).")
        geo_sources = {point["source"] for point in view["geo"]}
        if geo_sources == {"simulated"}:
            notes.append("Locations are simulated city centroids, not device GPS.")
        if not notes:
            notes.append("Nothing unusual yet.")
        return notes

    def case_action(self, case_id: str, action: str, note: str = "") -> dict:
        kind, _, token = case_id.partition("-")
        status_for = {"APPROVE": "APPROVED", "DECLINE": "DECLINED", "ESCALATE": "ESCALATED", "VERIFY": "VERIFY_REQUESTED", "NOTE": None}
        if action not in status_for:
            raise ValueError("action must be APPROVE, DECLINE, ESCALATE, VERIFY, or NOTE")
        review = None
        incident = None
        if action in {"APPROVE", "DECLINE"}:
            open_ids = {row["id"] for row in self.audit.list_reviews(1000) if row["status"] == "OPEN"}
            review_id = self.history.latest_open_review(kind, token, open_ids)
            if review_id is not None:
                verdict = "RELEASE" if action == "APPROVE" else "UPHOLD"
                review = self.audit.override(review_id, verdict, note or f"case {action.lower()}")
                self.note_feedback(review_id, verdict)
        if action == "ESCALATE":
            incident = self._escalate(kind, token)
        case = self.history.act(case_id, action, note, status_for[action])
        if case is None:
            raise KeyError(case_id)
        self.audit.append({"type": "case_action", "case": case_id, "action": action, "note": note[:500], "review_id": (review or {}).get("review_id"), "incident": incident})
        return {"case": case, "review": review, "incident": incident}

    def _escalate(self, kind: str, token: str) -> str:
        with self.lock:
            self._incident_seq += 1
            inc = {
                "id": f"INC-{self._incident_seq:04d}",
                "status": "OPEN",
                "severity": "HIGH",
                "started_at": time.time(),
                "ended_at": None,
                "segment": None,
                "tx_count": 0,
                "rupees_at_risk": 0.0,
                "rupees_blocked": 0.0,
                "mules": [token] if kind == "user" else [],
                "peak": {"tightness": 0.0, "probe": 0.0, "vol_z": 0.0, "coordination": 0.0, "psi": 0.0},
                "signals": [],
                "amounts": [],
                "members": [],
                "source": f"escalated {kind} case",
            }
            self.incidents.append(inc)
            return inc["id"]

    def _merchant_hot(self, merchant: str, snap: dict, recent: list) -> bool:
        attacked = snap.get("attacked_segment")
        if not merchant or attacked is None:
            return False
        group = [event for event in recent if event.get("segment") == attacked]
        if len(group) < 8:
            return False
        share = sum(1 for event in group if event.get("merchant") == merchant) / len(group)
        return share >= 0.3

    def _vector(self, txn, segment, dist, amt_z, counts, graph=None, profile=None) -> np.ndarray:
        values_v = np.asarray(txn["v"], dtype=float)
        amount = float(txn["amount"])
        hour = (float(txn["time"]) // 3600.0) % 24.0
        c10, cnt60, c300, sum60, sumsq, sum300, same = counts
        seg_share = same / cnt60 if cnt60 else 0.0
        mean60 = sum60 / cnt60 if cnt60 else 0.0
        var60 = (sumsq / cnt60 - mean60 * mean60) if cnt60 else 0.0
        row = {name: float(values_v[i]) for i, name in enumerate(V_COLS)}
        row.update(
            {
                "log_amount": float(np.log1p(amount)),
                "hour": hour / 24.0,
                "night": 1.0 if hour <= 5 or hour >= 23 else 0.0,
                "cnt_10": float(c10),
                "cnt_60": float(cnt60),
                "cnt_300": float(c300),
                "amt_mean_60": float(mean60),
                "amt_std_60": float(var60 ** 0.5) if var60 > 0 else 0.0,
                "amt_mean_300": float(sum300 / c300) if c300 else 0.0,
                "seg_share_60": float(seg_share),
                "amt_z": float(amt_z),
                "dist_centroid": float(dist),
                "segment": float(segment),
                "coord_proxy": float(seg_share * (cnt60 / (cnt60 + 20.0))),
                "user_velocity_60": float((graph or {}).get("user_velocity_60") or 0.0),
                "merchant_fan_in_300": float((graph or {}).get("merchant_fan_in") or 0.0),
            }
        )
        profile = profile or {}
        row["merchant_familiarity"] = float(profile.get("merchant_familiarity") or 0.0)
        row["user_amount_ratio"] = float(profile.get("amount_ratio") or 1.0)
        row["accounts_per_device_300"] = float(profile.get("device_users") or 0.0)
        row["travel_kmh"] = float(min(profile.get("travel_kmh") or 0.0, 20000.0))
        row["merchant_ticket_ratio"] = float(profile.get("ticket_ratio") or 1.0)
        return np.array([row.get(name, 0.0) for name in self.feature_names], dtype=float)

    def _fuse(self, features: np.ndarray, explain: bool = False):
        row = features.reshape(1, -1)
        raw = self._champion_proba(features)
        calibrated = self._sigmoid_model(self.art["platt"], raw)
        # The forest is the expensive model. Obvious approvals do not need it.
        needs_anomaly = self.art["thresholds"].get("use_stacker") or calibrated >= self.art["thresholds"]["t_step"] * 0.5
        if needs_anomaly:
            iforest_names = self.art.get("iforest_features")
            if iforest_names:
                iforest_x = np.array([features[self._name_at[name]] for name in iforest_names], dtype=float)
            else:
                iforest_x = np.concatenate([
                    features[:28],
                    features[self._name_at["log_amount"]: self._name_at["log_amount"] + 1],
                ])
            anomaly_raw = float(-self.art["iforest"].decision_function(iforest_x.reshape(1, -1))[0])
            span = max(self.art["anomaly_hi"] - self.art["anomaly_lo"], 1e-6)
            anomaly = float(np.clip((anomaly_raw - self.art["anomaly_lo"]) / span, 0.0, 1.0))
        else:
            anomaly = 0.0
        coord = float(features[self._name_at["coord_proxy"]])
        stacker = self.art["stacker"]
        if self.art["thresholds"].get("use_stacker") and stacker is not None:
            score = float(stacker.predict_proba(np.array([[calibrated, anomaly, coord]]))[0, 1])
        else:
            score = float(np.clip(calibrated + 0.12 * max(0.0, coord - 0.75), 0.0, 1.0))
        shadow = self._shadow_proba(row) if explain else 0.0
        return score, shadow, anomaly

    def _sigmoid_model(self, model, value: float) -> float:
        logit = float(model.coef_.ravel()[0] * value + model.intercept_.ravel()[0])
        if logit >= 0:
            return float(1.0 / (1.0 + np.exp(-logit)))
        ez = np.exp(logit)
        return float(ez / (1.0 + ez))

    def _champion_proba(self, features: np.ndarray) -> float:
        if self.art.get("champion_kind") == "linear":
            scaler = self.art["champion"].named_steps["standardscaler"]
            clf = self.art["champion"].named_steps["logisticregression"]
            scaled = (features - scaler.mean_) / scaler.scale_
            logit = float(scaled.dot(clf.coef_.ravel()) + clf.intercept_.ravel()[0])
            if logit >= 0:
                return float(1.0 / (1.0 + np.exp(-logit)))
            ez = np.exp(logit)
            return float(ez / (1.0 + ez))
        return float(self.art["champion"].predict_proba(features.reshape(1, -1))[0, 1])

    def _shadow_proba(self, row: np.ndarray) -> float:
        model = self.art["shadow"]
        booster = getattr(model, "booster_", None)
        if booster is not None:
            return float(booster.predict(row)[0])
        return float(model.predict_proba(row)[0, 1])

    def _reasons(self, features: np.ndarray) -> list:
        try:
            if self.art.get("champion_kind") == "linear":
                scaler = self.art["champion"].named_steps["standardscaler"]
                coef = self.art["champion"].named_steps["logisticregression"].coef_.ravel()
                scaled = scaler.transform(features.reshape(1, -1)).ravel()
                # For a linear model, SHAP vs the training mean is coef * scaled_x.
                return top_reasons(coef * scaled, self.feature_names)
            if self._explainer is None:
                import shap

                self._explainer = shap.TreeExplainer(self.art["champion"])
            values = self._explainer.shap_values(features.reshape(1, -1))
            if isinstance(values, list):
                values = values[-1]
            return top_reasons(np.asarray(values).reshape(-1), self.feature_names)
        except Exception:
            mean = self.art["feature_mean"]
            std = self.art["feature_std"]
            z = (features - mean) / std
            order = np.argsort(-np.abs(z))[:3]
            return [
                {
                    "feature": self.feature_names[i],
                    "shap": round(float(z[i]), 4),
                    "direction": "up" if z[i] > 0 else "down",
                    "text": f"{self.feature_names[i]} is {abs(float(z[i])):.1f} standard deviations from normal",
                }
                for i in order
            ]

    def _detector_reasons(self, snap: dict) -> list:
        detectors = snap.get("detectors") or {}
        notes = []
        if detectors.get("geometry", 0) >= 0.55:
            notes.append({
                "feature": "geometry",
                "shap": detectors["geometry"],
                "direction": "up",
                "text": "payments in this cohort are unusually alike",
            })
        if detectors.get("fan_out", 0) >= 0.5:
            notes.append({
                "feature": "fan_out",
                "shap": detectors["fan_out"],
                "direction": "up",
                "text": f"{snap.get('fan_out', 0)} merchants for one account in 60s",
            })
        if detectors.get("fan_in", 0) >= 0.45:
            notes.append({
                "feature": "fan_in",
                "shap": detectors["fan_in"],
                "direction": "up",
                "text": f"{snap.get('fan_in', 0)} cards into one merchant, and they look alike",
            })
        if detectors.get("card_test", 0) >= 0.5:
            notes.append({
                "feature": "card_test",
                "shap": detectors["card_test"],
                "direction": "up",
                "text": "burst of tiny amounts across many merchants",
            })
        if detectors.get("sequence", 0) >= 0.45:
            notes.append({
                "feature": "sequence",
                "shap": detectors["sequence"],
                "direction": "up",
                "text": "amounts ramp from probes into larger drains",
            })
        profile = snap.get("profile") or {}
        context = self._context_note(profile)
        if context:
            notes.append(context)
        if profile.get("flash_sale"):
            notes.append({
                "feature": "flash_sale",
                "shap": profile.get("merchant_surge_ratio") or 0,
                "direction": "down",
                "text": "this merchant's volume looks like a flash sale: many new buyers, human pace",
            })
        if profile.get("device_farm"):
            notes.append({
                "feature": "device_farm",
                "shap": profile.get("device_users") or 0,
                "direction": "up",
                "text": f"{profile.get('device_users')} accounts on one device in 5 minutes",
            })
        if profile.get("impossible_travel"):
            notes.append({
                "feature": "impossible_travel",
                "shap": profile.get("travel_kmh") or 0,
                "direction": "up",
                "text": f"{int(profile.get('travel_km') or 0)} km from the last payment in {profile.get('travel_minutes')} min",
            })
        notes.extend(skill_notes(profile))
        if float(profile.get("ticket_ratio") or 1) >= 3 and profile.get("merchant_n", 0) >= 3:
            notes.append({
                "feature": "ticket",
                "shap": profile.get("ticket_ratio") or 0,
                "direction": "up",
                "text": f"amount is {profile.get('ticket_ratio')}x this merchant's usual ticket",
            })
        if float(profile.get("category_risk") or 0) >= 0.7 and profile.get("category"):
            notes.append({
                "feature": "category",
                "shap": profile.get("category_risk") or 0,
                "direction": "up",
                "text": f"{profile.get('category')} is a higher-risk category",
            })
        surge = snap.get("surge") or {}
        if surge.get("verdict") == "SUSPICIOUS":
            notes.append({
                "feature": "surge",
                "shap": surge.get("genuine_score") or 0,
                "direction": "up",
                "text": "volume is loud but the mix looks distributed, round, or metronomic",
            })
        return notes

    @staticmethod
    def _context_note(profile: dict) -> dict | None:
        if profile.get("new_user") and float(profile.get("merchant_familiarity") or 1) < 0.25:
            return {
                "feature": "context",
                "shap": 0.1,
                "direction": "up",
                "text": f"first payment at this merchant, {profile.get('amount_ratio', 1)}x the user's usual amount",
            }
        if profile.get("region_new"):
            place = profile.get("region") or "a new region"
            return {"feature": "context", "shap": 0.1, "direction": "up", "text": f"first payment from {place} for this user"}
        if profile.get("device_new"):
            return {"feature": "context", "shap": 0.1, "direction": "up", "text": "new device for this user"}
        if profile.get("category_new"):
            return {"feature": "context", "shap": 0.1, "direction": "up", "text": "first payment in this category for this user"}
        if profile.get("hour_unusual"):
            return {"feature": "context", "shap": 0.1, "direction": "up", "text": "unusual hour for this user"}
        if float(profile.get("velocity_vs_max") or 0) >= 2 and not profile.get("new_user"):
            return {"feature": "context", "shap": 0.1, "direction": "up", "text": "paying faster than this user's own peak"}
        return None

    @staticmethod
    def _layers(score: float, surge: dict, profile: dict, human) -> dict:
        genuine = surge.get("genuine_score")
        surge_value = 0.0 if genuine is None else round(max(0.0, min(1.0, 1.0 - float(genuine))), 3)
        flags = [
            profile.get("new_user") and float(profile.get("merchant_familiarity") or 1) < 0.25,
            profile.get("region_new"),
            profile.get("device_new"),
            profile.get("category_new"),
            profile.get("hour_unusual"),
            float(profile.get("velocity_vs_max") or 0) >= 2,
            profile.get("device_farm"),
            profile.get("impossible_travel"),
            profile.get("amount_spike"),
            profile.get("velocity_burst"),
            profile.get("suspicious_syntax"),
            profile.get("model_probe"),
        ]
        context_value = round(sum(1 for flag in flags if flag) / len(flags), 3)
        if human is None:
            behavior_value = None
        else:
            behavior_value = round(max(0.0, min(1.0, (100.0 - float(human)) / 100.0)), 3)
        return {
            "model": {"value": round(float(score), 3), "label": "champion probability"},
            "surge": {"value": surge_value, "label": "how unlike a genuine sale this window is"},
            "context": {"value": context_value, "label": "unfamiliar user, place, device, hour, pace, shared device, or impossible travel"},
            "behavior": {"value": behavior_value, "label": "bot-like checkout telemetry, if any was sent"},
        }

    def _psi(self) -> float:
        if len(self.recent_scores) < 40:
            return 0.0
        actual = histogram(list(self.recent_scores), self.art["psi_edges"])
        return min(5.0, float(population_stability(self.art["psi_expected"], actual)))

    def _seen_recently(self, values, amount, now) -> bool:
        fingerprint = hashlib.sha1(np.round(values, 3).tobytes() + f"{amount:.2f}".encode()).hexdigest()
        while self.fingerprints and now - self.fingerprints[0][1] > 30:
            self.fingerprints.popleft()
        for seen, _seen_at in self.fingerprints:
            if seen == fingerprint:
                self.fingerprints.append((fingerprint, now))
                return True
        self.fingerprints.append((fingerprint, now))
        return False

    def _note_probe(self, user_token: str, now: float, amount: float, score: float, t_block: float) -> bool:
        """True when one customer walks amounts up through the band just under the block cut."""
        if not user_token:
            return False
        ring = self.probe_ring.get(user_token)
        if ring is None:
            if len(self.probe_ring) >= 5_000:
                self.probe_ring.popitem(last=False)
            ring = deque(maxlen=6)
            self.probe_ring[user_token] = ring
        else:
            self.probe_ring.move_to_end(user_token)
        ring.append((now, float(amount), float(score)))
        window = [row for row in ring if now - row[0] <= 600]
        if len(window) < 5:
            return False
        amounts = [row[1] for row in window]
        scores = [row[2] for row in window]
        rising = all(amounts[i] < amounts[i + 1] for i in range(len(amounts) - 1))
        floor = t_block * 0.75
        grey = all(floor <= value < t_block for value in scores)
        return bool(rising and grey)

    def case_summary(self, case_id: str) -> dict:
        kind, _, token = case_id.partition("-")
        view = self.entity_view(kind, token)
        if view is None:
            raise KeyError(case_id)
        judgment = judge_history(view["history"], view["summary"])
        summary = summarize_case(view, judgment)
        summary["verdict"] = judgment[0]
        return summary

    def _account(self, decision: str, static: str, label, amount: float, friction: str = "NONE") -> None:
        totals = self.totals
        totals["seen"] += 1
        totals[{"APPROVE": "ss_approve", "STEP_UP": "ss_step", "BLOCK": "ss_block"}[decision]] += 1
        totals[{
            "NONE": "friction_none",
            "DEVICE_CHECK": "friction_device",
            "PUSH": "friction_push",
            "OTP": "friction_otp",
            "STEP_UP_AUTH": "friction_auth",
            "BLOCKED": "friction_blocked",
        }[friction]] += 1
        if static == "BLOCK":
            totals["st_block"] += 1
        else:
            totals["st_approve"] += 1
        if label is None:
            return
        label = int(label)
        if label == 1:
            if decision == "BLOCK":
                totals["ss_fraud_caught_amt"] += amount
            elif decision == "STEP_UP":
                totals["ss_fraud_caught_amt"] += STEP_UP_CATCH_RATE * amount
                totals["ss_fraud_missed_amt"] += (1 - STEP_UP_CATCH_RATE) * amount
            else:
                totals["ss_fraud_missed_amt"] += amount
            if static == "BLOCK":
                totals["st_fraud_caught_amt"] += amount
            else:
                totals["st_fraud_missed_amt"] += amount
        else:
            if decision == "APPROVE":
                totals["ss_legit_approved_amt"] += amount
                totals["ss_legit_approved_n"] += 1
            if decision == "STEP_UP":
                totals["ss_legit_step_n"] += 1
            if decision == "BLOCK":
                totals["ss_legit_blocked_amt"] += amount
                totals["ss_legit_blocked_n"] += 1
            if static == "BLOCK":
                totals["st_legit_blocked_amt"] += amount
                totals["st_legit_blocked_n"] += 1

    def _latency_stats(self) -> None:
        if not self.latencies or (len(self.latencies) > 32 and self._seq % 8):
            return
        arr = np.asarray(self.latencies)
        self.totals["latency_p50"] = round(float(np.percentile(arr, 50)), 3)
        self.totals["latency_p99"] = round(float(np.percentile(arr, 99)), 3)

    def _audit_payload(self, result: dict) -> dict:
        return {
            "type": "decision",
            "decision": result["decision"],
            "regime": result["regime"],
            "score": result["score"],
            "segment": result["segment"],
            "amount": result["amount"],
            "user_token": result["user_token"],
            "merchant_token": result["merchant_token"],
            "reason_features": [r["feature"] for r in result["reasons"]],
            "mode": result["mode"],
            "human_score": result.get("human_score"),
            "telemetry_simulated": bool(result.get("telemetry_simulated")),
        }

    def _note_sample(self, compact: dict, latency_ms: float) -> None:
        self.samples.append(
            {
                "decision": compact["decision"],
                "static": compact["static_decision"],
                "label": compact["eval_label"],
                "score": compact["score"],
                "segment": int(compact["segment"]),
                "amount": compact["amount"],
                "latency_ms": latency_ms,
            }
        )

    def _bucket_row(self, bucket: dict) -> dict:
        n = bucket["n"] or 1
        lats = bucket["lats"] or [0.0]
        return {
            "t": bucket["t"],
            "tps": bucket["n"],
            "approve": bucket["approve"],
            "step": bucket["step"],
            "block": bucket["block"],
            "ss_caught": round(bucket["ss_caught"], 2),
            "st_caught": round(bucket["st_caught"], 2),
            "p99_ms": round(float(np.percentile(lats, 99)), 3),
            "regime": bucket["regime"],
            "vol_z": round(bucket["vol_z"] / n, 3),
            "tightness": round(bucket["tightness"] / n, 4),
            "probe": round(bucket["probe"] / n, 4),
            "psi": round(bucket["psi"] / n, 4),
            "legit_n": int(bucket.get("legit_n") or 0),
            "flagged_n": int(bucket.get("flagged_n") or 0),
            "regions": dict(bucket.get("regions") or {}),
            "merchants": dict(bucket.get("merchants") or {}),
        }

    def _note_bucket(self, compact: dict, latency_ms: float) -> None:
        sec = int(time.time())
        bucket = self._open_bucket
        if bucket is None or bucket["t"] != sec:
            self._finalize_bucket()
            bucket = {
                "t": sec,
                "approve": 0,
                "step": 0,
                "block": 0,
                "ss_caught": 0.0,
                "st_caught": 0.0,
                "lats": [],
                "vol_z": 0.0,
                "tightness": 0.0,
                "probe": 0.0,
                "psi": 0.0,
                "n": 0,
                "regime": compact["regime"],
                "legit_n": 0,
                "flagged_n": 0,
                "regions": {},
                "merchants": {},
            }
            self._open_bucket = bucket
        bucket[{"APPROVE": "approve", "STEP_UP": "step", "BLOCK": "block"}[compact["decision"]]] += 1
        bucket["n"] += 1
        bucket["lats"].append(latency_ms)
        bucket["vol_z"] += compact["vol_z"]
        bucket["tightness"] += compact["tightness"]
        bucket["probe"] += compact["probe"]
        bucket["psi"] += compact["psi"]
        bucket["regime"] = compact["regime"]
        if compact.get("eval_label") == 0:
            bucket["legit_n"] += 1
        if compact["decision"] in {"STEP_UP", "BLOCK"}:
            bucket["flagged_n"] += 1
        region = compact.get("region") or ""
        if region:
            bucket["regions"][region] = bucket["regions"].get(region, 0) + 1
        merchant = compact.get("merchant_token") or ""
        if merchant:
            bucket["merchants"][merchant] = bucket["merchants"].get(merchant, 0) + 1
        label = compact["eval_label"]
        if label == 1:
            if compact["decision"] == "BLOCK":
                bucket["ss_caught"] += compact["amount"]
            elif compact["decision"] == "STEP_UP":
                bucket["ss_caught"] += STEP_UP_CATCH_RATE * compact["amount"]
            if compact["static_decision"] == "BLOCK":
                bucket["st_caught"] += compact["amount"]

    def _finalize_bucket(self) -> None:
        bucket = self._open_bucket
        self._open_bucket = None
        if not bucket or not bucket["n"]:
            return
        row = self._bucket_row(bucket)
        self.buckets.append(row)
        self.psi_history.append({"t": row["t"], "psi": row["psi"], "alert": row["psi"] >= 0.2})

    def _note_incident(self, compact: dict, prev: str, regime: str, snap: dict) -> None:
        if regime == "ATTACK" and prev != "ATTACK":
            self._incident_seq += 1
            self._open_incident = {
                "id": f"INC-{self._incident_seq:04d}",
                "status": "OPEN",
                "severity": "CRITICAL",
                "started_at": time.time(),
                "ended_at": None,
                "segment": snap.get("attacked_segment") if snap.get("attacked_segment") is not None else compact["segment"],
                "tx_count": 0,
                "rupees_at_risk": 0.0,
                "rupees_blocked": 0.0,
                "mules": [],
                "peak": {"tightness": 0.0, "probe": 0.0, "vol_z": 0.0, "coordination": 0.0, "psi": 0.0},
                "signals": [],
                "amounts": [],
                "members": [],
            }
            self.incidents.append(self._open_incident)
        inc = self._open_incident
        if inc is not None and regime == "ATTACK":
            inc["tx_count"] += 1
            if compact["eval_label"] == 1:
                inc["rupees_at_risk"] = round(inc["rupees_at_risk"] + compact["amount"], 2)
            if compact["decision"] == "BLOCK":
                inc["rupees_blocked"] = round(inc["rupees_blocked"] + compact["amount"], 2)
            elif compact["decision"] == "STEP_UP" and compact["eval_label"] == 1:
                inc["rupees_blocked"] = round(inc["rupees_blocked"] + STEP_UP_CATCH_RATE * compact["amount"], 2)
            token = compact["user_token"]
            if token and token not in inc["mules"] and len(inc["mules"]) < 40:
                inc["mules"].append(token)
            for key in inc["peak"]:
                inc["peak"][key] = round(max(inc["peak"][key], float(compact[key])), 4)
            if len(inc["signals"]) < 160:
                inc["signals"].append(
                    {
                        "id": compact["id"],
                        "tightness": compact["tightness"],
                        "probe": compact["probe"],
                        "vol_z": compact["vol_z"],
                        "coordination": compact["coordination"],
                        "psi": compact["psi"],
                    }
                )
            if len(inc["amounts"]) < 240:
                inc["amounts"].append(
                    {"id": compact["id"], "amount": compact["amount"], "decision": compact["decision"]}
                )
            if len(inc["members"]) < 80:
                inc["members"].append(
                    {
                        "id": compact["id"],
                        "decision": compact["decision"],
                        "score": compact["score"],
                        "amount": compact["amount"],
                        "user_token": compact["user_token"],
                        "segment": compact["segment"],
                    }
                )
            if snap.get("attacked_segment") is not None:
                inc["segment"] = snap.get("attacked_segment")
        if prev == "ATTACK" and regime != "ATTACK" and inc is not None:
            inc["ended_at"] = time.time()
            inc["status"] = "RESOLVED"
            self._open_incident = None

    def timeseries(self, seconds: int = 120) -> list:
        with self.lock:
            rows = list(self.buckets)
            if self._open_bucket and self._open_bucket["n"]:
                rows.append(self._bucket_row(self._open_bucket))
        return rows[-max(1, min(seconds, 180)) :]

    def list_incidents(self) -> list:
        with self.lock:
            return [dict(item) for item in reversed(self.incidents)]

    def set_incident_status(self, incident_id: str, status: str) -> dict | None:
        with self.lock:
            for inc in self.incidents:
                if inc["id"] != incident_id:
                    continue
                if status == "ACK" and inc["status"] == "OPEN":
                    inc["status"] = "ACK"
                elif status == "RESOLVED":
                    inc["status"] = "RESOLVED"
                    inc["ended_at"] = inc["ended_at"] or time.time()
                    if self._open_incident and self._open_incident["id"] == incident_id:
                        self._open_incident = None
                return dict(inc)
        return None

    def analytics(self) -> dict:
        with self.lock:
            rows = list(self.samples)
            totals = dict(self.totals)
            runs = list(self.scenario_runs.values())
            live_scenario = self.scenario
            latencies = [round(float(v), 3) for v in self.latencies]
            region_counts: dict = {}
            merchant_counts: dict = {}
            for bucket in self.buckets:
                for name, count in (bucket.get("regions") or {}).items():
                    region_counts[name] = region_counts.get(name, 0) + count
                for name, count in (bucket.get("merchants") or {}).items():
                    merchant_counts[name] = merchant_counts.get(name, 0) + count
            top_merchants = sorted(merchant_counts.items(), key=lambda item: item[1], reverse=True)[:8]

        def matrix(positive) -> dict:
            tp = fp = tn = fn = 0
            for row in rows:
                if row["label"] is None:
                    continue
                hit = positive(row)
                if row["label"] == 1 and hit:
                    tp += 1
                elif row["label"] == 0 and hit:
                    fp += 1
                elif row["label"] == 1:
                    fn += 1
                else:
                    tn += 1
            return {"tp": tp, "fp": fp, "tn": tn, "fn": fn}

        histogram = [0] * 40
        segments = [{"segment": i, "n": 0, "mean_risk": 0.0, "_sum": 0.0} for i in range(8)]
        mix = {"APPROVE": 0, "STEP_UP": 0, "BLOCK": 0}
        for row in rows:
            mix[row["decision"]] = mix.get(row["decision"], 0) + 1
            histogram[min(39, int(float(row["score"]) * 40))] += 1
            seg = segments[int(row["segment"]) % 8]
            seg["n"] += 1
            seg["_sum"] += float(row["score"])
        for seg in segments:
            seg["mean_risk"] = round(seg["_sum"] / seg["n"], 4) if seg["n"] else 0.0
            del seg["_sum"]
        legit = [row for row in rows if row["label"] == 0]
        declined = sum(1 for row in legit if row["decision"] == "BLOCK")
        lat_hist = [0] * 20
        for value in latencies:
            lat_hist[min(19, int(value))] += 1
        return {
            "confusion_surgeshield": matrix(lambda row: row["decision"] in {"BLOCK", "STEP_UP"}),
            "confusion_static": matrix(lambda row: row["static"] == "BLOCK"),
            "score_histogram": histogram,
            "segments": segments,
            "decision_mix": mix,
            "false_decline_rate": round(declined / len(legit), 4) if legit else 0.0,
            "latency_histogram": lat_hist,
            "latencies_ms": latencies[-240:],
            "totals": totals,
            "friction_rupees": round(totals.get("ss_legit_step_n", 0) * STEP_UP_FRICTION, 2),
            "scenario_runs": runs,
            "live_scenario": live_scenario,
            "samples": len(rows),
            "regions": region_counts,
            "merchants": [{"token": token, "n": count} for token, count in top_merchants],
        }

    def live_config(self) -> dict:
        lineage = self.art.get("lineage", {})
        return {
            "thresholds": self.art["thresholds"],
            "regime_rules": {
                "vol_z_surge": 2.5,
                "tightness_attack": 0.62,
                "tightness_surge_max": 0.55,
                "micro_cluster": 12,
                "probe": 0.45,
                "mean_risk_attack": 0.3,
                "mean_risk_surge_max": 0.08,
                "psi_alert": 0.2,
                "dwell": self.regime.dwell,
                "recovery_events": 20,
            },
            "lineage": lineage,
            "artifact_sha256": self.artifact_sha256,
            "model_version": lineage.get("model", "unknown"),
            "trained_at": lineage.get("trained_at"),
            "slo_p99_ms": 25,
            "step_up_catch_rate": STEP_UP_CATCH_RATE,
            "step_up_friction": STEP_UP_FRICTION,
        }

    def _training_mean(self) -> float:
        edges = np.asarray(self.art["psi_edges"], dtype=float)
        expected = np.asarray(self.art["psi_expected"], dtype=float)
        total = float(expected.sum()) or 1.0
        centers = (edges[:-1] + edges[1:]) / 2.0
        return float(np.sum((expected / total) * centers))

    def drift(self) -> dict:
        psi = self._psi()
        samples = list(self.recent_scores)
        current = float(np.mean(samples)) if samples else 0.0
        baseline = self._training_mean()
        history = list(self.psi_history)
        sustained = len(history) >= 3 and all(row.get("alert") for row in history[-3:])
        regime = self.regime.state
        if sustained and regime == "ATTACK":
            suggestion = "Scores moved because the stream is in ATTACK. That shift is expected. The kill switch stays manual."
        elif sustained:
            suggestion = "Score drift has stayed above 0.2 for three buckets. Consider the kill switch. It does not flip by itself."
        else:
            suggestion = ""
        return {
            "psi": round(psi, 4),
            "alert": psi >= 0.2,
            "sustained": sustained,
            "samples": len(samples),
            "current_mean": round(current, 4),
            "baseline_mean": round(baseline, 4),
            "mean_shift": round(current - baseline, 4),
            "regime": regime,
            "threshold": 0.2,
            "suggestion": suggestion,
            "history": history,
        }

    def copilot(self, decision: str, regime: str, reasons: list) -> dict:
        return copilot_explain(decision, regime, reasons)

    def metrics(self) -> dict:
        stored = dict(self.art["metrics"])
        stored["live"] = {
            "regime": self.regime.state,
            "safe_mode": self.safe_mode,
            "scenario": self.scenario,
            "totals": self.totals,
            "drift": self.drift(),
            "lineage": self.art["lineage"],
            "thresholds": self.art["thresholds"],
        }
        return stored
