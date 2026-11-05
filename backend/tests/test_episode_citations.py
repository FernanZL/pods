"""Back-links from an episode to the conversation answers that cited it."""

from sqlmodel import Session

from app.models import Conversation, Episode, Message, Podcast


def _seed(session: Session) -> int:
    pod = Podcast(title="Pod", rss_url="demo://x", slug="pod")
    session.add(pod)
    session.commit()
    ep = Episode(podcast_id=pod.id, guid="g1", number=1, title="Ep", slug="0001-ep", audio_url="x")
    other = Episode(
        podcast_id=pod.id, guid="g2", number=2, title="Other", slug="0002-o", audio_url="y"
    )
    session.add_all([ep, other])
    session.commit()
    conv = Conversation(title="Sleep questions")
    session.add(conv)
    session.commit()
    cits = [
        {
            "n": 1,
            "episode_id": ep.id,
            "start": 10.0,
            "end": 20.0,
            "speaker": "Host",
            "source": "transcript",
        },
        {
            "n": 2,
            "episode_id": other.id,
            "start": 5.0,
            "end": 9.0,
            "speaker": "Guest",
            "source": "transcript",
        },
        {"n": 3, "episode_id": ep.id, "start": 0.0, "end": 0.0, "speaker": "", "source": "summary"},
    ]
    session.add(Message(conversation_id=conv.id, role="user", content="q"))
    session.add(Message(conversation_id=conv.id, role="assistant", content="a [1]", citations=cits))
    session.commit()
    assert ep.id is not None
    return ep.id


def test_episode_citations_lists_only_this_episodes_transcript_cites(client, session) -> None:
    ep_id = _seed(session)
    res = client.get(f"/api/episodes/{ep_id}/citations")
    assert res.status_code == 200
    body = res.json()
    assert [(r["n"], r["start"], r["conversation_title"]) for r in body] == [
        (1, 10.0, "Sleep questions")
    ]


def test_episode_citations_404(client) -> None:
    assert client.get("/api/episodes/999/citations").status_code == 404
