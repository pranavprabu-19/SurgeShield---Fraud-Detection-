"""Volume is not the signal. The shape of the volume is."""

from __future__ import annotations


class RegimeDetector:
    """NORMAL -> SURGE or ATTACK, then RECOVERY. Switches need a short dwell."""

    def __init__(self, dwell: int = 8):
        self.state = "NORMAL"
        self.dwell = dwell
        self._pending = None
        self._pending_hits = 0
        self._recovery_left = 0
        self.attacked_segment = None
        self.history = []

    def reset(self) -> None:
        self.state = "NORMAL"
        self._pending = None
        self._pending_hits = 0
        self._recovery_left = 0
        self.attacked_segment = None
        self.history = []

    def desired(self, snap: dict) -> str:
        attack = snap.get("attacked_segment") is not None or (
            snap.get("tightness", 0) >= 0.62
            and snap.get("dominance", 0) >= 0.45
            and snap.get("count_60", 0) >= 12
            and (snap.get("probe", 0) >= 0.45 or snap.get("mean_risk", 0) >= 0.3)
        )
        if attack:
            return "ATTACK"
        # A genuine surge is loud, diverse, and still low-risk. PSI can rise just
        # because almost every score is tiny, so mean risk is the check that matters.
        diverse = snap.get("diversity", 1.0) >= 0.45
        genuine = (snap.get("surge") or {}).get("genuine_score")
        genuine_ok = genuine is None or float(genuine) >= 0.5
        if (
            snap.get("vol_z", 0) >= 2.5
            and snap.get("mean_risk", 1) < 0.08
            and snap.get("tightness", 1) < 0.55
            and diverse
            and genuine_ok
        ):
            return "SURGE"
        return "NORMAL"

    def update(self, snap: dict) -> str:
        want = self.desired(snap)
        if self._recovery_left > 0 and want != "ATTACK":
            self._recovery_left -= 1
            self.state = "RECOVERY" if self._recovery_left else "NORMAL"
            self._remember(snap)
            return self.state

        if want == self.state or (want == "NORMAL" and self.state == "RECOVERY"):
            self._pending = None
            self._pending_hits = 0
            self._remember(snap)
            return self.state

        if want != self._pending:
            self._pending = want
            self._pending_hits = 1
        else:
            self._pending_hits += 1

        if self._pending_hits >= self.dwell:
            if self.state == "ATTACK" and want != "ATTACK":
                self.state = "RECOVERY"
                self._recovery_left = 20
                self.attacked_segment = None
            else:
                self.state = want
                if want == "ATTACK":
                    self.attacked_segment = snap.get("attacked_segment")
                else:
                    self.attacked_segment = None
            self._pending = None
            self._pending_hits = 0
        self._remember(snap)
        return self.state

    def _remember(self, snap: dict) -> None:
        self.history.append({"state": self.state, "vol_z": snap.get("vol_z", 0), "psi": snap.get("psi", 0)})
        if len(self.history) > 300:
            self.history = self.history[-300:]
