from src.core import BM25, Filters, InMemoryIndex, chunk, dedupe, freshness_report, normalise_url, rrf
from common.embedding import hashing_embed


def card(i, **kw):
    c = {"id": f"card_{i}", "name": f"App {i}", "summary": "s", "source": "github",
         "url": f"https://github.com/a/{i}", "text": "word " * 300, "niche_tags": ["devtools"],
         "published_at": "2026-05-01"}
    c.update(kw)
    return c


def test_normalise_url():
    assert normalise_url("http://www.GitHub.com/a/b/") == "https://github.com/a/b"


def test_dedupe_by_url_and_content_and_repeatable():
    urls, keys = set(), set()
    a, d1 = dedupe([card(1), card(2, url="https://www.github.com/a/1/")], urls, keys)
    assert len(a) == 1 and d1 == 1
    b, d2 = dedupe([card(1)], urls, keys)  # re-running ingestion adds nothing
    assert b == [] and d2 == 1
    c, _ = dedupe([card(3, name="App 1", url="https://x.org/z")], urls, keys)  # same name+summary
    assert c == []


def test_chunks_keep_card_id():
    chs = chunk(card(7))
    assert len(chs) > 1
    assert all(ch["card_id"] == "card_7" and ch["chunk_id"].startswith("card_7#c") for ch in chs)


def test_bm25_ranks_matching_doc_first():
    b = BM25()
    for t in ["slow csv export", "fast image resize", "csv csv viewer"]:
        b.add(t)
    s = b.scores("csv viewer")
    assert s.argmax() == 2


def test_rrf_combines():
    assert rrf([[1, 2, 3], [3, 1]])[0][0] == 1


def test_filters_and_search():
    idx = InMemoryIndex(embed=hashing_embed)
    idx.add_cards([card(1, text="csv export slow", source="reddit"), card(2, text="csv export slow")])
    res = idx.search("csv export", filters=Filters(source=["reddit"]))
    assert [r["card_id"] for r in res] == ["card_1"]
    assert res[0]["evidence_id"].startswith("card_1#c")
    assert idx.search("csv", filters=Filters(date_from="2027-01-01")) == []


def test_freshness_report():
    r = freshness_report([card(1, fetched_at="2026-11-01"), card(2, fetched_at="2026-11-10")], "2026-11-20")
    assert r["sources"]["github"]["age_days"] == 10 and r["n_niches"] == 1
