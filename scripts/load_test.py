"""Locust entry: POST /score/batch. Run with `locust -f scripts/load_test.py --headless -u 4 -r 4 -t 20s`."""

import os

from locust import HttpUser, between, task

KEY = os.environ.get("SURGESHIELD_API_KEY", "surgeshield-demo")
VECTOR = [0.1] * 28


class Checkout(HttpUser):
    wait_time = between(0.01, 0.05)

    @task
    def batch(self):
        payload = {
            "explain": False,
            "transactions": [
                {"time": 1000 + i, "amount": 20 + i, "v": VECTOR, "user_id": f"u{i}", "merchant_id": "m1"}
                for i in range(50)
            ],
        }
        self.client.post("/score/batch", json=payload, headers={"X-API-Key": KEY})
