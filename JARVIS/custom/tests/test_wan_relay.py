"""WAN relay framing + TLS skeleton tests."""

from __future__ import annotations

import pytest

from custom.server import wan_relay


def test_frame_roundtrip() -> None:
    payload = b'{"type":"screen"}'
    frame = wan_relay.encode_frame(payload)
    assert frame[:4] == b"MYWN"
    decoded = wan_relay.decode_frame(frame)
    assert decoded is not None
    result, remainder = decoded
    assert result == payload
    assert remainder == b""


def test_frame_partial_then_complete() -> None:
    frame = wan_relay.encode_frame(b"hello")
    assert wan_relay.decode_frame(frame[:5]) is None
    assert wan_relay.decode_frame(frame) == (b"hello", b"")


def test_bad_magic_raises() -> None:
    with pytest.raises(ValueError):
        wan_relay.decode_frame(b"XXXX\x00\x00\x00\x01a")


def test_client_receive_keeps_remainder_across_calls() -> None:
    """Two frames in one recv() must both be returned; none may be lost."""
    client = wan_relay.RelayClient()

    class _FakeSocket:
        def __init__(self) -> None:
            self._data = wan_relay.encode_frame(b"one") + wan_relay.encode_frame(b"two")

        def recv(self, _size: int) -> bytes:
            data, self._data = self._data, b""
            return data

    client._sock = _FakeSocket()  # type: ignore[assignment]
    assert client.receive() == b"one"
    assert client.receive() == b"two"
    assert client.receive() is None


def test_client_receive_handles_partial_frame() -> None:
    """A frame split across recv() calls is reassembled, not dropped."""
    client = wan_relay.RelayClient()
    frame = wan_relay.encode_frame(b"hello")

    class _ChunkedSocket:
        def __init__(self) -> None:
            self._chunks = [frame[:6], frame[6:]]

        def recv(self, _size: int) -> bytes:
            return self._chunks.pop(0) if self._chunks else b""

    client._sock = _ChunkedSocket()  # type: ignore[assignment]
    assert client.receive() == b"hello"


def test_split_host_port() -> None:
    assert wan_relay._split_host_port("relay.example.com:9443") == ("relay.example.com", 9443)
    assert wan_relay._split_host_port("ws://relay.example.com:9443/path") == ("relay.example.com", 9443)
    assert wan_relay._split_host_port("relay.example.com") == ("relay.example.com", 443)


def test_tls_lan_requires_paths() -> None:
    from custom.server import tls

    with pytest.raises(ValueError):
        tls.create_ssl_context(mode="lan")
    with pytest.raises(NotImplementedError):
        tls.create_ssl_context(mode="wan", cert_path="x", key_path="y")
