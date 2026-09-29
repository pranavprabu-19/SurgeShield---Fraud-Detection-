"""City coordinates for simulated regions, and the distance between two points."""

from __future__ import annotations

import hashlib
import math

CITIES = {
    "Bengaluru": (12.9716, 77.5946),
    "Chennai": (13.0827, 80.2707),
    "Hyderabad": (17.3850, 78.4867),
    "Mumbai": (19.0760, 72.8777),
    "Delhi": (28.6139, 77.2090),
    "Kolkata": (22.5726, 88.3639),
    "Jaipur": (26.9124, 75.7873),
    "Guwahati": (26.1445, 91.7362),
    "Kochi": (9.9312, 76.2673),
    "Lucknow": (26.8467, 80.9462),
    "Pune": (18.5204, 73.8567),
    "Ahmedabad": (23.0225, 72.5714),
}


def locate(region: str, lat=None, lon=None, salt: str = "") -> tuple:
    """Real coordinates win. A named city gets a small, repeatable jitter so pins do not stack."""
    if lat is not None and lon is not None:
        try:
            return float(lat), float(lon), "real"
        except (TypeError, ValueError):
            pass
    base = CITIES.get(region or "")
    if base is None:
        return None, None, "unavailable"
    digest = hashlib.sha1(f"{region}|{salt}".encode()).digest()
    jitter_lat = (digest[0] / 255.0 - 0.5) * 0.12
    jitter_lon = (digest[1] / 255.0 - 0.5) * 0.12
    return round(base[0] + jitter_lat, 5), round(base[1] + jitter_lon, 5), "simulated"


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    radius = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return float(2 * radius * math.asin(min(1.0, math.sqrt(a))))
