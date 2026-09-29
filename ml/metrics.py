"""Metrics that stay meaningful when fraud is 0.17% of the stream."""

from __future__ import annotations

import numpy as np
from sklearn.metrics import average_precision_score, confusion_matrix, roc_auc_score

from ml.schema import FALSE_DECLINE_FLOOR, FALSE_DECLINE_RATE, STEP_UP_CATCH_RATE, STEP_UP_FRICTION


def recall_at_fpr(y, scores, target: float = 0.001) -> float:
    y = np.asarray(y).astype(int)
    scores = np.asarray(scores)
    n_pos = max(int((y == 1).sum()), 1)
    n_neg = max(int((y == 0).sum()), 1)
    order = np.argsort(-scores)
    tp = fp = 0
    best = 0.0
    for label in y[order]:
        if label == 1:
            tp += 1
        else:
            fp += 1
            if fp / n_neg > target:
                break
        best = tp / n_pos
    return float(best)


def binary_rates(y, scores, threshold: float) -> dict:
    pred = (np.asarray(scores) >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    legit = max(tn + fp, 1)
    fraud = max(tp + fn, 1)
    return {
        "tp": int(tp),
        "fp": int(fp),
        "tn": int(tn),
        "fn": int(fn),
        "precision": float(tp / max(tp + fp, 1)),
        "recall": float(tp / fraud),
        "fpr": float(fp / legit),
    }


def ranking_metrics(y, scores) -> dict:
    y = np.asarray(y).astype(int)
    scores = np.asarray(scores)
    return {
        "pr_auc": float(average_precision_score(y, scores)),
        "roc_auc": float(roc_auc_score(y, scores)) if y.min() != y.max() else None,
        "recall_at_0_1pct_fpr": recall_at_fpr(y, scores, 0.001),
        "always_legit_accuracy": float((y == 0).mean()),
    }


def stream_cost(y, amount, decisions: np.ndarray) -> dict:
    y = np.asarray(y).astype(int)
    amount = np.asarray(amount, dtype=float)
    decisions = np.asarray(decisions)
    fraud = y == 1
    legit = ~fraud
    blocked = decisions == "BLOCK"
    stepped = decisions == "STEP_UP"
    missed = float(amount[fraud & ~blocked & ~stepped].sum())
    missed += float((amount[fraud & stepped] * (1.0 - STEP_UP_CATCH_RATE)).sum())
    caught = float(amount[fraud].sum()) - missed
    false_decline = float(np.maximum(FALSE_DECLINE_FLOOR, FALSE_DECLINE_RATE * amount[legit & blocked]).sum())
    friction = float(np.full(int((legit & stepped).sum()), STEP_UP_FRICTION).sum())
    legit_declined_amount = float(amount[legit & blocked].sum())
    return {
        "fraud_caught_amount": caught,
        "fraud_missed_amount": missed,
        "false_decline_cost": false_decline,
        "step_up_friction": friction,
        "legit_declined_amount": legit_declined_amount,
        "legit_declined_n": int((legit & blocked).sum()),
        "total_cost": missed + false_decline + friction,
    }
