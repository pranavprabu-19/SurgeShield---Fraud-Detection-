from backend.app.profiles import ProfileStore


def test_familiarity_grows_and_lru_drops_the_oldest():
    store = ProfileStore(user_limit=2, merchant_limit=2)
    first = store.signals("u1", "m1", 100, 10)
    assert first["new_user"] is True
    assert first["merchant_familiarity"] == 0
    store.update("u1", "m1", 100, 10)
    store.update("u1", "m1", 100, 10)
    store.update("u1", "m1", 100, 10)
    store.update("u1", "m1", 100, 10)
    again = store.signals("u1", "m1", 400, 10)
    assert again["new_user"] is False
    assert again["merchant_familiarity"] == 1
    assert again["amount_ratio"] > 3
    store.update("u2", "m2", 10, 1)
    store.update("u3", "m3", 10, 1)
    assert "u1" not in store.users
    assert len(store.users) == 2


def test_burst_ratio_and_first_sighting_flags():
    store = ProfileStore()
    now = 1_000.0
    for index in range(50):
        store.update(f"buyer-{index}", "m-flash", 80, 12, "electronics", "Bengaluru", f"phone-{index}", now, 1)
        now += 0.05
    signal = store.signals("buyer-new", "m-flash", 90, 12, "electronics", "Bengaluru", "phone-x", now, 1)
    assert signal["merchant_n"] >= 20
    assert signal["merchant_surge_ratio"] >= 5
    assert signal["unique_share"] >= 0.8
    store.update("known", "m", 20, 11, "grocery", "Chennai", "phone-a", 10, 1)
    for _ in range(4):
        store.update("known", "m", 20, 11, "grocery", "Chennai", "phone-a", 11, 1)
    later = store.signals("known", "other", 20, 11, "electronics", "Delhi", "phone-b", 12, 1)
    assert later["region_new"] is True
    assert later["device_new"] is True
    assert later["category_new"] is True
