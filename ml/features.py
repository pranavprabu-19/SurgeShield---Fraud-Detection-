"""Causal stream features. Every window looks strictly backward in time."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

from ml.schema import N_SEGMENTS, SEED, V_COLS


def load_transactions(path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["Class"] = df["Class"].astype(int)
    df["Amount"] = df["Amount"].astype(float)
    df["Time"] = df["Time"].astype(float)
    before = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    df.attrs["dropped_duplicates"] = before - len(df)
    return df


def fit_segments(train_df: pd.DataFrame, columns=None):
    """Behavioral cohorts stand in for merchant context the dataset does not contain."""
    columns = list(columns or V_COLS)
    sample = train_df.sample(n=min(40_000, len(train_df)), random_state=SEED)
    clusters = min(N_SEGMENTS, max(1, len(sample)))
    km = KMeans(n_clusters=clusters, random_state=SEED, n_init=10)
    km.fit(sample[columns].to_numpy())
    seg = km.predict(train_df[columns].to_numpy())
    means = np.ones(N_SEGMENTS)
    stds = np.ones(N_SEGMENTS)
    for s in range(clusters):
        amounts = train_df.loc[seg == s, "Amount"].to_numpy()
        if len(amounts) == 0:
            continue
        means[s] = float(amounts.mean())
        std = float(amounts.std())
        stds[s] = std if std > 1e-6 else 1.0
    return km, means, stds


def _window_start(times: np.ndarray, seconds: float) -> np.ndarray:
    return np.searchsorted(times, times - seconds, side="left")


def _window_sum(prefix: np.ndarray, start: np.ndarray) -> np.ndarray:
    idx = np.arange(len(start))
    return prefix[idx] - prefix[start]


def _entity_window(times, keys, partners, seconds: float) -> np.ndarray:
    """Distinct partners per key inside a backward window, including the current row."""
    from collections import defaultdict, deque

    counts = np.zeros(len(times))
    queues = defaultdict(deque)
    tallies = defaultdict(lambda: defaultdict(int))
    for index, (when, key, partner) in enumerate(zip(times, keys, partners)):
        queue = queues[key]
        tally = tallies[key]
        while queue and when - queue[0][0] > seconds:
            _, old = queue.popleft()
            tally[old] -= 1
            if tally[old] <= 0:
                del tally[old]
        queue.append((when, partner))
        tally[partner] += 1
        counts[index] = len(tally)
    return counts


def _device_share(times, devices) -> np.ndarray:
    from collections import deque

    share = np.zeros(len(times))
    window = deque()
    tally = {}
    for index, (when, device) in enumerate(zip(times, devices)):
        window.append((when, device))
        tally[device] = tally.get(device, 0) + 1
        while window and when - window[0][0] > 60.0:
            _, old = window.popleft()
            tally[old] -= 1
        share[index] = tally.get(device, 0) / max(len(window), 1)
    return share


def _familiarity(users, merchants, amounts) -> tuple:
    """Prior visits and amount ratio. The current row is not counted as history."""
    from collections import defaultdict

    familiarity = np.zeros(len(users))
    ratio = np.ones(len(users))
    visits = defaultdict(lambda: defaultdict(int))
    count = defaultdict(int)
    average = defaultdict(float)
    for index, (user, merchant, amount) in enumerate(zip(users, merchants, amounts)):
        seen = visits[user][merchant]
        familiarity[index] = min(1.0, seen / 4.0)
        if count[user] >= 3 and average[user] > 0:
            ratio[index] = float(amount) / average[user]
        visits[user][merchant] += 1
        count[user] += 1
        average[user] += (float(amount) - average[user]) / count[user]
    return familiarity, ratio


def _travel_kmh(times, users, lats, lons) -> np.ndarray:
    """Speed implied by the user's previous located payment. Zero for a first sighting."""
    from backend.app.geo import haversine_km

    speed = np.zeros(len(times))
    last = {}
    for index, (when, user, lat, lon) in enumerate(zip(times, users, lats, lons)):
        if np.isnan(lat) or np.isnan(lon):
            continue
        previous = last.get(user)
        if previous is not None:
            km = haversine_km(previous[0], previous[1], lat, lon)
            seconds = max(float(when) - previous[2], 1.0)
            speed[index] = min(km / (seconds / 3600.0), 20000.0)
        last[user] = (float(lat), float(lon), float(when))
    return speed


def _ticket_ratio(merchants, amounts) -> np.ndarray:
    """Amount over the merchant's running average ticket, once it has three prior payments."""
    from collections import defaultdict

    ratio = np.ones(len(merchants))
    count = defaultdict(int)
    average = defaultdict(float)
    for index, (merchant, amount) in enumerate(zip(merchants, amounts)):
        if count[merchant] >= 3 and average[merchant] > 0:
            ratio[index] = float(amount) / average[merchant]
        count[merchant] += 1
        average[merchant] += (float(amount) - average[merchant]) / count[merchant]
    return ratio


def compute_features(df: pd.DataFrame, kmeans, seg_mean: np.ndarray, seg_std: np.ndarray, columns=None) -> pd.DataFrame:
    """Features for a time-ordered population. Row i never sees rows i..end."""
    columns = list(columns or V_COLS)
    ordered = df.sort_values(["Time"], kind="mergesort").reset_index(drop=True)
    times = ordered["Time"].to_numpy()
    amounts = ordered["Amount"].to_numpy(dtype=float)
    values = ordered[columns].to_numpy(dtype=float)
    n = len(ordered)
    seg = kmeans.predict(values).astype(int)

    start_10 = _window_start(times, 10.0)
    start_60 = _window_start(times, 60.0)
    start_300 = _window_start(times, 300.0)
    idx = np.arange(n)
    cnt_10 = idx - start_10
    cnt_60 = idx - start_60
    cnt_300 = idx - start_300

    amt_prefix = np.concatenate([[0.0], np.cumsum(amounts)])
    sq_prefix = np.concatenate([[0.0], np.cumsum(amounts ** 2)])
    sum_60 = amt_prefix[idx] - amt_prefix[start_60]
    sumsq_60 = sq_prefix[idx] - sq_prefix[start_60]
    sum_300 = amt_prefix[idx] - amt_prefix[start_300]

    with np.errstate(divide="ignore", invalid="ignore"):
        amt_mean_60 = np.divide(sum_60, cnt_60, out=np.zeros(n), where=cnt_60 > 0)
        mean_sq = np.divide(sumsq_60, cnt_60, out=np.zeros(n), where=cnt_60 > 0)
        var_60 = np.maximum(0.0, mean_sq - amt_mean_60 ** 2)
        amt_std_60 = np.sqrt(var_60)
        amt_mean_300 = np.divide(sum_300, cnt_300, out=np.zeros(n), where=cnt_300 > 0)

    onehot = np.zeros((n, N_SEGMENTS), dtype=np.int32)
    onehot[idx, seg] = 1
    seg_prefix = np.vstack([np.zeros((1, N_SEGMENTS), dtype=np.int32), np.cumsum(onehot, axis=0)])
    seg_in_60 = seg_prefix[idx] - seg_prefix[start_60]
    same_seg = seg_in_60[idx, seg]
    seg_share = np.divide(same_seg, cnt_60, out=np.zeros(n), where=cnt_60 > 0)

    amt_z = (amounts - seg_mean[seg]) / seg_std[seg]
    dist = np.linalg.norm(values - kmeans.cluster_centers_[seg], axis=1)
    coord_proxy = seg_share * (cnt_60 / (cnt_60 + 20.0))
    hour = (times // 3600.0) % 24.0

    out = pd.DataFrame(values, columns=columns)
    out["log_amount"] = np.log1p(amounts)
    out["hour"] = hour / 24.0
    out["night"] = ((hour <= 5) | (hour >= 23)).astype(float)
    out["cnt_10"] = cnt_10.astype(float)
    out["cnt_60"] = cnt_60.astype(float)
    out["cnt_300"] = cnt_300.astype(float)
    out["amt_mean_60"] = amt_mean_60
    out["amt_std_60"] = amt_std_60
    out["amt_mean_300"] = amt_mean_300
    out["seg_share_60"] = seg_share
    out["amt_z"] = amt_z
    out["dist_centroid"] = dist
    out["segment"] = seg.astype(float)
    out["coord_proxy"] = coord_proxy
    if "user_id" in ordered.columns and "merchant_id" in ordered.columns:
        users = ordered["user_id"].astype(str).to_numpy()
        merchants = ordered["merchant_id"].astype(str).to_numpy()
        out["user_velocity_60"] = _entity_window(times, users, merchants, 60.0)
        out["merchant_fan_in_300"] = _entity_window(times, merchants, users, 300.0)
    else:
        # The credit-card file has no ids. Live scoring fills these from HMAC tokens.
        out["user_velocity_60"] = 0.0
        out["merchant_fan_in_300"] = 0.0
    if "device" in ordered.columns:
        out["device_share"] = _device_share(times, ordered["device"].astype(str).to_numpy())
    if "user_id" in ordered.columns and "merchant_id" in ordered.columns:
        familiarity, ratio = _familiarity(
            ordered["user_id"].astype(str).to_numpy(),
            ordered["merchant_id"].astype(str).to_numpy(),
            amounts,
        )
        out["merchant_familiarity"] = familiarity
        out["user_amount_ratio"] = ratio
    device_is_id = df.attrs.get("device_is_id", True)
    if "device" in ordered.columns and "user_id" in ordered.columns and device_is_id:
        out["accounts_per_device_300"] = _entity_window(
            times, ordered["device"].astype(str).to_numpy(), ordered["user_id"].astype(str).to_numpy(), 300.0
        )
    if {"lat", "lon", "user_id"}.issubset(ordered.columns):
        out["travel_kmh"] = _travel_kmh(
            times,
            ordered["user_id"].astype(str).to_numpy(),
            pd.to_numeric(ordered["lat"], errors="coerce").to_numpy(dtype=float),
            pd.to_numeric(ordered["lon"], errors="coerce").to_numpy(dtype=float),
        )
    if "merchant_id" in ordered.columns:
        out["merchant_ticket_ratio"] = _ticket_ratio(ordered["merchant_id"].astype(str).to_numpy(), amounts)
    out["Time"] = times
    out["Amount"] = amounts
    out["Class"] = ordered["Class"].to_numpy()
    out["segment_id"] = seg
    return out
