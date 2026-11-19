"""Tests for Maya AI Connection Manager."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from custom.tools.connection_manager import (
    ConnectionManager,
    ConnectionType,
    ConnectionStatus,
    ConnectionInfo,
    MockBackend,
)


def _connected_wifi():
    return ConnectionInfo(type=ConnectionType.WIFI,
                          status=ConnectionStatus.CONNECTED,
                          name="TestWiFi", ip="192.168.1.5", signal=80)


def test_initial_state():
    mb = MockBackend()
    cm = ConnectionManager(backend=mb, sleep_fn=lambda x: None)
    assert cm.active == ConnectionType.NONE
    s = cm.summary()
    assert s["active"] == "none"
    assert set(s["statuses"].keys()) == {"wifi", "hotspot", "bluetooth", "internet"}


def test_status_single():
    mb = MockBackend()
    mb.wifi = _connected_wifi()
    cm = ConnectionManager(backend=mb, sleep_fn=lambda x: None)
    info = cm.status(ConnectionType.WIFI)
    assert isinstance(info, ConnectionInfo)
    assert info.is_connected()
    assert info.name == "TestWiFi"


def test_status_all_dict():
    mb = MockBackend()
    cm = ConnectionManager(backend=mb, sleep_fn=lambda x: None)
    d = cm.status()
    assert isinstance(d, dict)
    assert "wifi" in d and "bluetooth" in d


def test_refresh_all():
    mb = MockBackend()
    mb.internet = ConnectionInfo(type=ConnectionType.INTERNET,
                                status=ConnectionStatus.CONNECTED, name="internet")
    cm = ConnectionManager(backend=mb, sleep_fn=lambda x: None)
    out = cm.refresh_all()
    assert out["internet"]["status"] == "connected"


def test_connect_success():
    mb = MockBackend()
    mb.wifi = _connected_wifi()
    cm = ConnectionManager(backend=mb, sleep_fn=lambda x: None, max_retries=2)
    info = cm.connect(ConnectionType.WIFI)
    assert info.is_connected()
    assert cm.active == ConnectionType.WIFI


def test_connect_failure():
    mb = MockBackend()
    mb.wifi = ConnectionInfo(type=ConnectionType.WIFI,
                             status=ConnectionStatus.DISCONNECTED)
    cm = ConnectionManager(backend=mb, sleep_fn=lambda x: None, max_retries=2)
    info = cm.connect(ConnectionType.WIFI)
    assert not info.is_connected()
    assert info.status == ConnectionStatus.FAILED


def test_connect_retry_sleeps():
    mb = MockBackend()
    mb.wifi = ConnectionInfo(type=ConnectionType.WIFI,
                             status=ConnectionStatus.DISCONNECTED)
    sleeps = []
    cm = ConnectionManager(backend=mb, sleep_fn=lambda s: sleeps.append(s),
                           max_retries=3, base_backoff=1.0)
    cm.connect(ConnectionType.WIFI)
    # 3 attempts -> 2 sleeps (backoff 1, 2)
    assert sleeps == [1.0, 2.0]


def test_disconnect():
    mb = MockBackend()
    mb.wifi = _connected_wifi()
    cm = ConnectionManager(backend=mb, sleep_fn=lambda x: None)
    cm.connect(ConnectionType.WIFI)
    info = cm.disconnect(ConnectionType.WIFI)
    assert info.status == ConnectionStatus.DISCONNECTED
    assert cm.active == ConnectionType.NONE


def test_switch_same_type():
    mb = MockBackend()
    mb.wifi = _connected_wifi()
    cm = ConnectionManager(backend=mb, sleep_fn=lambda x: None)
    cm.connect(ConnectionType.WIFI)
    res = cm.switch(ConnectionType.WIFI)
    assert res.ok is True
    assert res.from_type == ConnectionType.WIFI
    assert res.to_type == ConnectionType.WIFI


def test_switch_different_type():
    mb = MockBackend()
    mb.wifi = _connected_wifi()
    mb.bluetooth = ConnectionInfo(type=ConnectionType.BLUETOOTH,
                                 status=ConnectionStatus.CONNECTED, name="BT-Headset")
    cm = ConnectionManager(backend=mb, sleep_fn=lambda x: None)
    cm.connect(ConnectionType.WIFI)
    res = cm.switch(ConnectionType.BLUETOOTH)
    assert res.ok is True
    assert res.from_type == ConnectionType.WIFI
    assert res.to_type == ConnectionType.BLUETOOTH
    assert cm.active == ConnectionType.BLUETOOTH


def test_switch_failure():
    mb = MockBackend()
    mb.wifi = _connected_wifi()
    mb.bluetooth = ConnectionInfo(type=ConnectionType.BLUETOOTH,
                                 status=ConnectionStatus.DISCONNECTED)
    cm = ConnectionManager(backend=mb, sleep_fn=lambda x: None, max_retries=1)
    cm.connect(ConnectionType.WIFI)
    res = cm.switch(ConnectionType.BLUETOOTH)
    assert res.ok is False


def test_scan_wifi():
    mb = MockBackend()
    mb.wifi_ssids = ["HomeWiFi", "OfficeWiFi"]
    cm = ConnectionManager(backend=mb, sleep_fn=lambda x: None)
    ssids = cm.scan(ConnectionType.WIFI)
    assert ssids == ["HomeWiFi", "OfficeWiFi"]


def test_scan_bluetooth():
    mb = MockBackend()
    mb.bt_devices = ["Phone", "Speaker"]
    cm = ConnectionManager(backend=mb, sleep_fn=lambda x: None)
    devs = cm.scan(ConnectionType.BLUETOOTH)
    assert devs == ["Phone", "Speaker"]


def test_scan_other_returns_empty():
    mb = MockBackend()
    cm = ConnectionManager(backend=mb, sleep_fn=lambda x: None)
    assert cm.scan(ConnectionType.HOTSPOT) == []
    assert cm.scan(ConnectionType.INTERNET) == []


def test_detect_available():
    mb = MockBackend()
    mb.bluetooth = ConnectionInfo(type=ConnectionType.BLUETOOTH,
                                 status=ConnectionStatus.CONNECTED, name="bt")
    cm = ConnectionManager(backend=mb, sleep_fn=lambda x: None)
    avail = cm.detect_available()
    assert ConnectionType.WIFI in avail
    assert ConnectionType.HOTSPOT in avail
    assert ConnectionType.BLUETOOTH in avail
    assert ConnectionType.INTERNET in avail


def test_status_change_listener():
    mb = MockBackend()
    mb.wifi = _connected_wifi()
    cm = ConnectionManager(backend=mb, sleep_fn=lambda x: None)
    events = []
    cm.on_status_change(lambda info: events.append(info))
    cm.status(ConnectionType.WIFI)
    assert len(events) >= 1
    assert events[-1].is_connected()


def test_listener_exception_does_not_crash():
    mb = MockBackend()
    cm = ConnectionManager(backend=mb, sleep_fn=lambda x: None)
    cm.on_status_change(lambda info: (_ for _ in ()).throw(ValueError("boom")))
    # should not raise
    cm.status(ConnectionType.WIFI)


def test_backend_failure_marks_unknown_not_crash():
    mb = MockBackend()
    mb.raise_on = "wifi_status"
    cm = ConnectionManager(backend=mb, sleep_fn=lambda x: None, max_retries=1)
    # _status_one catches? connect calls _status_one which calls backend -> raises.
    # Manager.connect wraps in try/except per attempt, so should not propagate.
    info = cm.connect(ConnectionType.WIFI)
    assert info.status == ConnectionStatus.FAILED


def test_to_dict():
    info = _connected_wifi()
    d = info.to_dict()
    assert d["type"] == "wifi"
    assert d["status"] == "connected"
    assert d["name"] == "TestWiFi"
    assert d["signal"] == 80


def test_connection_info_is_connected():
    info = ConnectionInfo(type=ConnectionType.WIFI, status=ConnectionStatus.CONNECTED)
    assert info.is_connected()
    info2 = ConnectionInfo(type=ConnectionType.WIFI, status=ConnectionStatus.DISCONNECTED)
    assert not info2.is_connected()


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"✓ {t.__name__} passed")
    print(f"\nAll {len(tests)} connection manager tests passed!")
