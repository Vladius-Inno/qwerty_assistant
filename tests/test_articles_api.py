from __future__ import annotations


def test_articles_search_meta(client, monkeypatch):
    async def fake_combined_search(query: str, limit: int = 20, preselect: int = 200, alpha: float = 0.7):
        # Return minimal dicts with required keys for ArticleMeta model
        return [
            {"id": 10, "title": "T1", "date": "2020-01-01", "release_number": None, "keywords": [], "tags": []},
            {"id": 11, "title": "T2", "date": "2020-02-02", "release_number": None, "keywords": [], "tags": []},
        ][:limit]
    async def fake_get_article(article_id: int):
        from types import SimpleNamespace
        return SimpleNamespace(
            id=article_id,
            title=f"T{article_id}",
            date="2020-01-01",
            release_number=None,
            body="",
            source_link=None,
            article_link=None,
            keywords=[],
            tags=[],
            topic_name=None,
            summary=None,
            extra_links={},
        )

    # Patch where used in the router
    monkeypatch.setattr("app.api.articles.srch.combined_search", fake_combined_search)
    monkeypatch.setattr("app.api.articles.svc.get_article", fake_get_article)

    resp = client.get("/api/articles/search/meta?q=abc&limit=2")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list) and len(data) == 2
    assert {"id", "title", "date"}.issubset(data[0].keys())


def test_get_article_404_and_200(client, monkeypatch):
    from app.services import articles as art_mod

    async def fake_get_article_missing(article_id: int):
        return None

    async def fake_get_article_ok(article_id: int):
        return {
            "id": article_id,
            "title": "Sample",
            "date": "2020-01-01",
            "release_number": None,
            "body": "Body text",
            "source_link": None,
            "article_link": None,
            "keywords": [],
            "tags": [],
            "topic_name": None,
            "summary": None,
            "extra_links": {},
        }

    # 404 path
    monkeypatch.setattr(art_mod, "get_article", fake_get_article_missing)
    resp = client.get("/api/articles/12345")
    assert resp.status_code == 404

    # 200 path
    monkeypatch.setattr(art_mod, "get_article", fake_get_article_ok)
    resp2 = client.get("/api/articles/1")
    assert resp2.status_code == 200
    assert resp2.json()["id"] == 1


def test_articles_related(client, monkeypatch):
    from app.services import articles as art_mod

    async def fake_get_related_articles(article_id: int, method: str = "semantic", top_n: int = 10):
        return [
            {"id": 2, "title": "R1", "date": "2020-01-02", "release_number": None, "keywords": [], "tags": [], "summary": None, "score": 0.5},
        ]

    monkeypatch.setattr(art_mod, "get_related_articles", fake_get_related_articles)

    resp = client.get("/api/articles/1/related?method=semantic&top_n=1")
    assert resp.status_code == 200
    arr = resp.json()
    assert isinstance(arr, list) and arr[0]["id"] == 2
