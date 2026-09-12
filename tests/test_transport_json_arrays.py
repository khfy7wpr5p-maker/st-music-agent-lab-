from __future__ import annotations

from st_music_agent import transport
from st_music_agent.transport import JsonRequest, UrllibJsonTransport


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return b'[{"id":1},{"id":2}]'


def test_transport_accepts_json_arrays(monkeypatch) -> None:
    monkeypatch.setattr(transport, "urlopen", lambda request, timeout: FakeResponse())

    response = UrllibJsonTransport().request(
        JsonRequest(method="GET", url="https://example.invalid/reviews")
    )

    assert response.status_code == 200
    assert response.payload == [{"id": 1}, {"id": 2}]
