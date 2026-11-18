"""Tests for Maya AI system monitor tools."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from custom.tools.monitor import get_full_report, get_cpu_usage, get_ram_usage, get_gpu_info, get_npu_info, get_temperature, get_battery, get_ssd_health


def test_get_full_report():
    """Full report should be a non-empty string."""
    report = get_full_report()
    assert isinstance(report, str), f"Expected string, got {type(report)}"
    assert len(report) > 0, "Expected non-empty report"


def test_get_cpu_usage():
    """CPU usage should return a dict."""
    cpu = get_cpu_usage()
    assert isinstance(cpu, dict), f"Expected dict, got {type(cpu)}"


def test_get_ram_usage():
    """RAM usage should return a dict."""
    ram = get_ram_usage()
    assert isinstance(ram, dict), f"Expected dict, got {type(ram)}"


def test_get_gpu_info():
    """GPU info should return a dict."""
    gpu = get_gpu_info()
    assert isinstance(gpu, dict), f"Expected dict, got {type(gpu)}"


def test_get_npu_info():
    """NPU info should return a dict."""
    npu = get_npu_info()
    assert isinstance(npu, dict), f"Expected dict, got {type(npu)}"


def test_get_temperature():
    """Temperature should return a dict."""
    temp = get_temperature()
    assert isinstance(temp, dict), f"Expected dict, got {type(temp)}"


def test_get_battery():
    """Battery should return a dict."""
    batt = get_battery()
    assert isinstance(batt, dict), f"Expected dict, got {type(batt)}"


def test_get_ssd_health():
    """SSD health should return a dict."""
    ssd = get_ssd_health()
    assert isinstance(ssd, dict), f"Expected dict, got {type(ssd)}"


if __name__ == "__main__":
    test_get_full_report()
    print("✓ test_get_full_report passed")
    test_get_cpu_usage()
    print("✓ test_get_cpu_usage passed")
    test_get_ram_usage()
    print("✓ test_get_ram_usage passed")
    test_get_gpu_info()
    print("✓ test_get_gpu_info passed")
    test_get_npu_info()
    print("✓ test_get_npu_info passed")
    test_get_temperature()
    print("✓ test_get_temperature passed")
    test_get_battery()
    print("✓ test_get_battery passed")
    test_get_ssd_health()
    print("✓ test_get_ssd_health passed")
    print("\nAll monitor tests passed!")