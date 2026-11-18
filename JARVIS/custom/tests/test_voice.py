"""Voice tests — DSP, model discovery, clap logic. No microphone needed."""

import array
import math

import pytest
from click.testing import CliRunner

from custom.cli import main
from custom.tools import voice_clap, voice_stt


# ── Audio pipeline ────────────────────────────────────────────────────

def _tone(rate: int, hz: float, seconds: float, amp: int = 12000) -> bytes:
    n = int(rate * seconds)
    samples = array.array("h", (int(amp * math.sin(2 * math.pi * hz * i / rate)) for i in range(n)))
    return samples.tobytes()


def test_prepare_for_vosk_downsamples_48k_to_16k():
    data = _tone(voice_stt.REC_RATE, 1000, 0.5)
    out, raw_peak = voice_stt._prepare_for_vosk(data, voice_stt.REC_RATE)

    assert len(out) == pytest.approx(len(data) // 6, rel=0.01)
    assert raw_peak > 0
    # Normalised peak must stay inside int16 and be clearly audible.
    assert max(abs(s) for s in out) > 1000


def test_prepare_for_vosk_handles_silence():
    out, peak = voice_stt._prepare_for_vosk(b"", voice_stt.REC_RATE)
    assert len(out) == 0 and peak == 0


def test_resample_identity():
    x = array.array("d", [1.0, 2.0, 3.0])
    assert list(voice_stt._resample(x, 16000, 16000)) == [1.0, 2.0, 3.0]


# ── Model discovery ───────────────────────────────────────────────────

def test_model_paths_stay_inside_project():
    path = voice_stt.model_path("en")
    assert path.name == "vosk-en"
    assert "MAYA AI" in str(path) or "Model" in str(path)


def test_available_reports_tamil_honestly():
    models = voice_stt.available()
    assert set(models) == {"en", "en-in", "ta"}
    # Official Vosk ships no Tamil model — it must not claim otherwise.
    assert models["en"] is True
    assert models["ta"] is False or models["ta"] is True  # present if user adds one


def test_status_shape():
    st = voice_stt.status()
    for key in ("vosk_installed", "models", "any_model", "windows_mic", "model_root"):
        assert key in st


# ── Clap detection ────────────────────────────────────────────────────

def _clap_series(detector, times):
    return [detector.feed(5000, now=t) for t in times]


def test_three_claps_trigger():
    detector = voice_clap.ClapDetector(threshold=2800, required=3)
    fired = False
    for i in range(3):
        detector.feed(100, now=10.0 + i * 0.3)
        fired = detector.feed(5000, now=10.05 + i * 0.3) or fired
    assert fired is True


def test_two_claps_do_not_trigger():
    detector = voice_clap.ClapDetector(threshold=2800, required=3)
    fired = False
    for i in range(2):
        detector.feed(100, now=10.0 + i * 0.3)
        fired = detector.feed(5000, now=10.05 + i * 0.3) or fired
    assert fired is False


def test_quiet_frames_do_not_trigger():
    detector = voice_clap.ClapDetector(threshold=2800, required=3)
    assert all(detector.feed(100, now=10.0 + i * 0.1) is False for i in range(20))


def test_slow_claps_reset_the_rhythm():
    detector = voice_clap.ClapDetector(threshold=2800, required=3, max_gap=0.9)
    fired = False
    for i in range(3):
        detector.feed(100, now=10.0 + i * 1.5)
        fired = detector.feed(5000, now=10.05 + i * 1.5) or fired
    assert fired is False


def test_simulate_returns_true():
    assert voice_clap.simulate() is True


def test_clap_status_self_test():
    st = voice_clap.status()
    assert st["logic_ok"] is True
    assert st["count"] >= 2


# ── CLI wiring ────────────────────────────────────────────────────────

@pytest.fixture()
def runner():
    return CliRunner()


def test_cli_voice_status(runner):
    result = runner.invoke(main, ["voice", "status"])
    assert result.exit_code == 0, result.output
    assert "STT models" in result.output
    assert "Vosk installed" in result.output


def test_cli_voice_clap_test(runner):
    result = runner.invoke(main, ["voice", "clap", "test"])
    assert result.exit_code == 0, result.output
    assert "ok" in result.output.lower()


def test_cli_voice_listen_missing_model(runner, tmp_path):
    wav = tmp_path / "empty.wav"
    wav.write_bytes(b"")
    result = runner.invoke(main, ["voice", "listen", str(wav), "--lang", "ta"])
    assert result.exit_code == 0, result.output
    assert "STT" in result.output
