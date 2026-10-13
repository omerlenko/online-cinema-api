from pytest import MonkeyPatch

from src.accounts.tasks import purge_expired_tokens
from tests.helpers import FakeTaskSession


def test_purge_expired_tokens(monkeypatch: MonkeyPatch):
    fake_session = FakeTaskSession()
    captured_sessions = []

    async def fake_delete_expired_tokens(db: FakeTaskSession) -> int:
        captured_sessions.append(db)
        return 3

    monkeypatch.setattr("src.accounts.tasks.TaskSession", lambda: fake_session)
    monkeypatch.setattr(
        "src.accounts.tasks.delete_expired_tokens", fake_delete_expired_tokens
    )

    result = purge_expired_tokens()

    assert result == 3, "The task did not return the deleted count"
    assert captured_sessions == [
        fake_session
    ], "The crud function did not get the correct session"
    assert fake_session.committed, "The task did not commit"
