"""Behaviour tests with recorded responses (no model needed)."""
from src.core import score, validate

IDS = {"card_a#c0", "card_b#c1"}
GOOD = '{"score": 3.5, "confidence": 0.7, "evidence_ids": ["card_a#c0"], "reason": "see card_a#c0"}'


def fixed(*answers):
    it = iter(answers)

    def f(system, user):
        a = next(it)
        if isinstance(a, Exception):
            raise a
        return a, {}
    return f


def test_valid_output_first_try():
    r = score("s", "u", IDS, fixed(GOOD), "ft", None, "")
    assert r.output.score == 3.5 and r.attempts == 1 and not r.fallback


def test_invalid_json_then_retry_succeeds():
    r = score("s", "u", IDS, fixed("not json", GOOD), "ft", None, "")
    assert r.output and r.attempts == 2 and len(r.errors) == 1


def test_invalid_twice_falls_back_to_hosted():
    r = score("s", "u", IDS, fixed("{}", "{bad"), "ft", fixed(GOOD), "hosted")
    assert r.fallback and r.model == "hosted" and r.output.score == 3.5


def test_model_timeout_falls_back():
    r = score("s", "u", IDS, fixed(TimeoutError(), TimeoutError()), "ft", fixed(GOOD), "hosted")
    assert r.fallback and r.output


def test_invented_evidence_id_rejected():
    bad = GOOD.replace("card_a#c0", "card_zzz#c9")
    r = score("s", "u", IDS, fixed(bad, bad), "ft", fixed(bad), "hosted")
    assert r.output is None and any("invented" in e for e in r.errors)


def test_abstain_is_none():
    assert validate('{"abstain": true}', IDS) is None


def test_score_out_of_range_rejected():
    r = score("s", "u", IDS, fixed(GOOD.replace("3.5", "7"), GOOD), "ft", None, "")
    assert r.attempts == 2
