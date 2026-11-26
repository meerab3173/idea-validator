from src.security import LIMITS, MemoryCounter, allowed, hash_password, make_token, read_token, verify_password


def test_password_roundtrip():
    h = hash_password("correct horse")
    assert verify_password("correct horse", h) and not verify_password("wrong", h)


def test_token_roundtrip_and_tamper_and_expiry():
    t = make_token("u1", secret="s", now=1000)
    assert read_token(t, secret="s", now=1001) == "u1"
    assert read_token(t, secret="other", now=1001) is None
    assert read_token(t[:-2] + "xx", secret="s", now=1001) is None
    assert read_token(t, secret="s", now=1000 + 10 ** 7) is None


def test_rate_limit():
    c = MemoryCounter()
    n = LIMITS["runs"]
    results = [allowed(c, "u1", "runs", now=60) for _ in range(n + 1)]
    assert all(results[:n]) and not results[-1]
    assert allowed(c, "u2", "runs", now=60)          # other user unaffected
    assert allowed(c, "u1", "runs", now=125)         # next minute
