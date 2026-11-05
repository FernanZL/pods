"""Job history cleanup and Apple Podcasts discovery (HTTP mocked)."""

import httpx
import respx
from sqlmodel import Session

from app.models import Job, Podcast
from app.services import discover


def _jobs(session: Session) -> dict[str, int]:
    ids = {}
    for status in ("done", "failed", "cancelled", "queued"):
        job = Job(kind="process", status=status)
        session.add(job)
        session.commit()
        ids[status] = job.id
    return ids


def test_delete_single_finished_job_and_refuse_active(client, session) -> None:
    ids = _jobs(session)
    assert client.delete(f"/api/jobs/{ids['done']}").status_code == 204
    assert client.get(f"/api/jobs/{ids['done']}").status_code == 404
    assert client.delete(f"/api/jobs/{ids['queued']}").status_code == 409


def test_clear_finished_keeps_active(client, session) -> None:
    _jobs(session)
    res = client.delete("/api/jobs")
    assert res.json() == {"deleted": 3}
    assert {j["status"] for j in client.get("/api/jobs").json()} <= {"queued", "running"}
    assert client.delete("/api/jobs?status=queued").status_code == 422


SEARCH_PAYLOAD = {
    "resultCount": 2,
    "results": [
        {
            "collectionId": 1545953110,
            "collectionName": "Huberman Lab",
            "artistName": "Scicomm Media",
            "feedUrl": "https://feeds.megaphone.fm/hubermanlab",
            "artworkUrl600": "https://img/600.jpg",
            "primaryGenreName": "Health & Fitness",
            "trackCount": 456,
        },
        {"collectionId": 2, "collectionName": "No Feed Show", "artistName": "X"},
    ],
}


@respx.mock
def test_search_marks_already_added_feeds(client, session) -> None:
    session.add(Podcast(title="HL", rss_url="https://feeds.megaphone.fm/hubermanlab", slug="hl"))
    session.commit()
    respx.get(discover.SEARCH_URL).mock(return_value=httpx.Response(200, json=SEARCH_PAYLOAD))
    body = client.get("/api/discover/search?q=huberman").json()
    assert body[0]["title"] == "Huberman Lab"
    assert body[0]["podcast_id"] is not None
    assert body[1]["feed_url"] is None and body[1]["podcast_id"] is None


@respx.mock
def test_top_resolves_chart_ids_to_feeds_in_order(client) -> None:
    discover._chart_cache.clear()
    chart = {
        "feed": {
            "entry": [
                {"id": {"attributes": {"im:id": "2"}}},
                {"id": {"attributes": {"im:id": "1545953110"}}},
            ]
        }
    }
    respx.get(url__regex=r"https://itunes\.apple\.com/us/rss/toppodcasts/.*").mock(
        return_value=httpx.Response(200, json=chart)
    )
    respx.get(discover.LOOKUP_URL).mock(return_value=httpx.Response(200, json=SEARCH_PAYLOAD))
    body = client.get("/api/discover/top?genre_id=1533&limit=2").json()
    assert [r["itunes_id"] for r in body] == [2, 1545953110]


@respx.mock
def test_directory_down_returns_502(client) -> None:
    respx.get(discover.SEARCH_URL).mock(return_value=httpx.Response(503))
    assert client.get("/api/discover/search?q=x").status_code == 502
