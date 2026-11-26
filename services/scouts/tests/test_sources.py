from src.sources import parse_github, parse_hn, parse_reddit, parse_yc, run_source


HN = {"hits": [{"objectID": "1", "title": "Show HN: Foo – a faster CSV viewer",
                "story_text": "Export is slow in Excel", "created_at_i": 1700000000, "author": "a"}]}


def test_parse_hn():
    c = parse_hn(HN)[0]
    assert c["name"] == "Foo" and c["source"] == "hackernews" and c["id"].startswith("card_")
    assert c["published_at"] == "2023-11-14"


def test_parse_github():
    c = parse_github({"items": [{"html_url": "https://github.com/a/b", "name": "b",
                                 "description": "d", "topics": ["devtools"], "created_at": "2024-01-02T00:00:00Z",
                                 "owner": {"login": "a"}, "stargazers_count": 50}]})[0]
    assert c["niche_tags"] == ["devtools"] and c["published_at"] == "2024-01-02"


def test_parse_yc_and_reddit():
    assert parse_yc([{"name": "X", "one_liner": "y", "slug": "x", "tags": ["B2B"]}])[0]["niche_tags"] == ["b2b"]
    r = parse_reddit({"data": {"children": [{"data": {"title": "t", "permalink": "/r/a/1", "subreddit": "SaaS"}}]}})
    assert r[0]["url"] == "https://www.reddit.com/r/a/1"


def test_empty_source_is_not_an_error():  # "empty source" behaviour case
    res = run_source("hn", lambda url: {"json": {"hits": []}}, pages=2)
    assert res["cards"] == [] and res["errors"] == []


def test_failing_page_is_recorded_and_skipped():
    calls = {"n": 0}

    def flaky(url):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("tool timeout")
        return {"json": HN}
    res = run_source("hn", flaky, pages=2)
    assert len(res["errors"]) == 1 and len(res["cards"]) == 1
