from src.debate import Agents, debate

GAPS = [{"description": "exam clashes found late", "evidence_ids": ["card_a#c0"]}]


def make(ideas_per_round, skeptic_fatal_titles=(), critic_ok=True):
    calls = {"ideator": 0}

    def ideator(profile, niches, gaps, prev):
        calls["ideator"] += 1
        return ideas_per_round
    agents = Agents(
        ideator=ideator,
        gap_analyst=lambda idea, ev: {"complaints": [{"text": "late", "evidence_ids": ["card_a#c0"]}]},
        skeptic=lambda idea, ev: ([{"text": "exact copy of X", "evidence_ids": ["card_x#c0"], "fatal": True}]
                                  if idea.title in skeptic_fatal_titles else []),
        critic=lambda objs: [critic_ok] * len(objs),
        search=lambda q: [],
    )
    return agents, calls


def test_idea_without_gap_evidence_dropped():
    a, _ = make([{"title": "A", "pitch": "p", "gap_evidence_ids": ["made_up#c0"]}])
    r = debate({}, [], GAPS, a)
    assert r["ideas"] == [] and "gap evidence" in r["dropped"][0].dropped_reason


def test_fatal_supported_objection_drops_idea():
    a, _ = make([{"title": "A", "pitch": "p", "gap_evidence_ids": ["card_a#c0"]},
                 {"title": "B", "pitch": "p", "gap_evidence_ids": ["card_a#c0"]}], skeptic_fatal_titles={"A"})
    r = debate({}, [], GAPS, a)
    assert [i.title for i in r["ideas"]] == ["B"] and r["dropped"][0].title == "A"


def test_unsupported_objection_does_not_drop():
    a, _ = make([{"title": "A", "pitch": "p", "gap_evidence_ids": ["card_a#c0"]}],
                skeptic_fatal_titles={"A"}, critic_ok=False)
    assert [i.title for i in debate({}, [], GAPS, a)["ideas"]] == ["A"]


def test_rounds_limited_to_3():
    a, calls = make([{"title": "A", "pitch": "p", "gap_evidence_ids": ["card_a#c0"]}], skeptic_fatal_titles={"A"})
    r = debate({}, [], GAPS, a)
    assert r["rounds"] == 3 and calls["ideator"] == 3
