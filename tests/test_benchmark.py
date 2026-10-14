"""Benchmark unit and real local sampler tests; these do not claim GPU acceptance."""

import json
import time
from pathlib import Path

import pytest

from local_transcriber.infrastructure.benchmark import load_manifest
from local_transcriber.infrastructure.benchmark_quality import (
    edit_distance,
    normalize,
    quality_metrics,
)
from local_transcriber.infrastructure.benchmark_resources import ResourceSampler


def test_quality_raw_normalization_and_insertions():
    assert normalize("  Ёж\nПривет\tМИР. ") == "ёж привет мир."
    assert quality_metrics("привет мир", "ПРИВЕТ\nмир")["wer"] == 0
    values = quality_metrics("кот", "код лишнее")
    assert values["wer"] == 2  # Ratios may exceed one; do not clamp quality failures.
    assert values["word_errors"] == 2
    assert quality_metrics("абв", "абг")["cer"] == pytest.approx(1 / 3)
    assert quality_metrics("а б", "")["wer"] == 1
    assert edit_distance("", "два") == 3
    assert edit_distance("equal prefix AAA suffix", "equal prefix ABA suffix") == 1
    with pytest.raises(ValueError, match="nonempty"):
        quality_metrics(" \n ", "hallucination")
    with pytest.raises(ValueError, match="budget"):
        edit_distance("aaaa", "bbbb", max_cells=10)


@pytest.mark.parametrize(
    "change",
    [
        {"indices": [1, 1]},
        {"indices": [-1]},
        {"path": "relative.mp4"},
        {"references": {"2": "private.txt"}},
        {"normalization": "strip-all"},
        {"id": "../escape"},
        {"end_ms": 0},
        {"indices": []},
        {"unknown": True},
    ],
)
def test_invalid_manifest_rejected_before_database(tmp_path, change):
    case = {"id": "case", "path": str(tmp_path / "source.mp4"), **change}
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"cases": [case]}))
    with pytest.raises(ValueError):
        load_manifest(manifest)


def test_manifest_duplicate_ids_and_size(tmp_path):
    manifest = tmp_path / "manifest.json"
    case = {"id": "case", "path": str(tmp_path / "source.mp4")}
    manifest.write_text(json.dumps({"cases": [case, case]}))
    with pytest.raises(ValueError, match="Duplicate"):
        load_manifest(manifest)
    manifest.write_bytes(b" " * (1024 * 1024 + 1))
    with pytest.raises(ValueError, match="1 MiB"):
        load_manifest(manifest)


def test_resource_sampler_real_rss_missing_smi_no_fake_vram(tmp_path):
    output = tmp_path / "samples.jsonl"
    sampler = ResourceSampler(output, str(tmp_path / "missing-smi.exe"), 0, interval=0.01)
    sampler.start()
    deadline = time.monotonic() + 3
    while not sampler.samples and time.monotonic() < deadline:
        time.sleep(0.01)
    sampler.stop()
    summary = sampler.summary()
    assert summary["peak_rss_bytes"] > 0
    assert summary["peak_vram_bytes"] is None
    assert summary["vram_errors"] >= 1
    row = json.loads(output.read_text().splitlines()[0])
    assert set(row) == {"seconds", "rss_bytes", "device_vram_bytes"}
    assert "source" not in output.read_text()
    with pytest.raises(ValueError):
        ResourceSampler(output, "nvidia-smi", 0, interval=0)


def test_missing_source_case_preserves_source_and_has_metrics(tmp_path):
    from local_transcriber.infrastructure.benchmark import BenchmarkCase, run_case
    from local_transcriber.infrastructure.settings import AppSettings

    source = tmp_path / "untouched.txt"
    source.write_bytes(b"keep")
    case = BenchmarkCase(id="missing", path=str(tmp_path / "absent.mp4"))
    result = run_case(case, AppSettings(_env_file=None), None, tmp_path, 30)
    assert result["status"] == "FAIL"
    assert result["errors"] == ["MediaInspectionError"]
    assert result["peak_vram_bytes"] is None
    assert source.read_bytes() == b"keep"
    assert "absent.mp4" not in json.dumps(result)
    assert Path(tmp_path / "missing/metrics.json").is_file()


def test_reproducibility_includes_new_untracked_code(tmp_path):
    import hashlib

    from local_transcriber.infrastructure.benchmark import _source_snapshot

    source = tmp_path / "src/local_transcriber/untracked.py"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"print('first')")
    secret = tmp_path / ".env"
    secret.write_bytes(b"DO_NOT_CAPTURE")
    before = _source_snapshot(tmp_path)
    assert before == {
        "src/local_transcriber/untracked.py": hashlib.sha256(source.read_bytes()).hexdigest()
    }
    source.write_bytes(b"print('changed')")
    assert _source_snapshot(tmp_path) != before
    assert secret.read_bytes() == b"DO_NOT_CAPTURE"


def test_sampler_output_failure_is_reported_without_overwrite(tmp_path):
    output = tmp_path / "existing.jsonl"
    output.write_bytes(b"keep")
    sampler = ResourceSampler(output, "nvidia-smi", 0, interval=0.01)
    sampler.start()
    with pytest.raises(RuntimeError, match="Resource sampler failed"):
        sampler.stop()
    assert sampler.failure == "FileExistsError"
    assert output.read_bytes() == b"keep"
    assert sampler.summary()["peak_vram_bytes"] is None
