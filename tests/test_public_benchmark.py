"""Public benchmark safety and quality protocol tests; no network needed."""

import io
import json
import tarfile

import pytest

from local_transcriber.infrastructure.benchmark_quality import quality_metrics
from local_transcriber.infrastructure.public_benchmark import (
    aggregate_quality,
    extract_subset,
    lexical_text,
    parse_metadata,
    score_fleurs,
)


def test_micro_average_uses_counts_not_average_percentages():
    one = quality_metrics("a", "b")
    nine = quality_metrics("a b c d e f g h i", "a b c d e f g h i")
    assert aggregate_quality([one, nine])["wer"] == pytest.approx(0.1)
    with pytest.raises(ValueError):
        aggregate_quality([])
    nine["normalization"] = "different"
    with pytest.raises(ValueError):
        aggregate_quality([one, nine])


def test_secondary_normalization_preserves_primary_digits_and_yo():
    assert lexical_text("Ёж, PYTHON-3.14!") == "ёж python 3 14"
    assert quality_metrics("word", "word.")["wer"] == 1
    assert quality_metrics(lexical_text("word"), lexical_text("word."))["wer"] == 0


@pytest.mark.parametrize(
    "text",
    [
        "bad",
        "1\t../1.wav\traw\tnorm\tx\t16000\tMALE",
        "1\t1.wav\t \tnorm\tx\t16000\tMALE",
        "1\t1.wav\traw\tnorm\tx\t0\tMALE",
    ],
)
def test_invalid_metadata_rejected(text):
    with pytest.raises(ValueError):
        parse_metadata(text)


def archive_bytes(names):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name in names:
            member = tarfile.TarInfo(name)
            member.size = 4
            archive.addfile(member, io.BytesIO(b"test"))
    buffer.seek(0)
    return buffer


def test_archive_order_and_path_safety(tmp_path):
    metadata = parse_metadata(
        "1\t1.wav\traw\tnorm\tx\t16000\tMALE\n2\t2.wav\tother\tnorm\tx\t16000\tFEMALE"
    )
    with tarfile.open(fileobj=archive_bytes(["test/2.wav", "test/1.wav"]), mode="r|") as archive:
        selected = extract_subset(archive, metadata, tmp_path, 1)
    assert selected[0]["filename"] == "2.wav"
    assert (tmp_path / "fleurs-000.txt").read_text() == "other"
    assert not (tmp_path / "1.wav").exists()
    with tarfile.open(fileobj=archive_bytes(["../1.wav"]), mode="r|") as archive:
        with pytest.raises(ValueError):
            extract_subset(archive, metadata, tmp_path, 1)
    assert not (tmp_path / "1.wav").exists()


def test_failed_utterance_cannot_disappear_from_corpus_score(tmp_path):
    (tmp_path / "provenance.json").write_text(json.dumps({"samples": [{"case": "sample"}]}))
    report = tmp_path / "benchmark.json"
    report.write_text(json.dumps({"cases": [{"case": "sample", "status": "FAIL"}]}))
    with pytest.raises(ValueError, match="Incomplete"):
        score_fleurs(tmp_path, report)
    assert not (tmp_path / "quality-summary.json").exists()
