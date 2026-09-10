import pytest

from st_music_agent.transport import JsonRequest, TransportError, UrllibJsonTransport


def test_transport_rejects_non_http_urls_before_io() -> None:
    transport = UrllibJsonTransport()

    with pytest.raises(TransportError, match="http/https"):
        transport.request(JsonRequest(method="GET", url="file:///etc/passwd"))


def test_transport_rejects_relative_urls_before_io() -> None:
    transport = UrllibJsonTransport()

    with pytest.raises(TransportError, match="http/https"):
        transport.request(JsonRequest(method="GET", url="/api/conversations"))
