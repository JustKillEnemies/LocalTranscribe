"""Pinned public FLEURS subset preparation and RAW corpus scoring; no uploads."""

import hashlib
import json
import re
import shutil
import tarfile
import unicodedata
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any

from local_transcriber.infrastructure.benchmark_quality import NORMALIZATION, quality_metrics
from local_transcriber.infrastructure.privacy import private_directory

FLEURS_REVISION = "70bb2e84b976b7e960aa89f1c648e09c59f894dd"
FLEURS_BASE = f"https://huggingface.co/datasets/google/fleurs/resolve/{FLEURS_REVISION}/data/ru_ru/"
LEXICAL_NORMALIZATION = "nfc-casefold-punctuation-space-v1"


def parse_metadata(content: str) -> dict[str, dict[str, Any]]:
    """Read the seven-field official TSV without evaluating remote dataset code."""
    result = {}
    for line in content.splitlines():
        fields = line.split("\t")
        if len(fields) != 7:
            raise ValueError("Expected seven FLEURS TSV fields")
        identity, name, raw, _, _, samples, gender = fields
        if (
            not re.fullmatch(r"[0-9]+\.wav", name)
            or name in result
            or not raw.strip()
            or int(samples) <= 0
        ):
            raise ValueError("Unsafe/duplicate FLEURS filename or empty reference")
        result[name] = {
            "id": int(identity),
            "raw_transcription": raw,
            "num_samples": int(samples),
            "gender": gender,
        }
    if not result:
        raise ValueError("Empty FLEURS metadata")
    return result


def lexical_text(text: str) -> str:
    """Secondary metric only: replace Unicode punctuation with spaces on BOTH sides."""
    return " ".join(
        "".join(
            " " if unicodedata.category(c).startswith("P") else c
            for c in unicodedata.normalize("NFC", text).casefold()
        ).split()
    )


def aggregate_quality(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Corpus micro-average; never average per-utterance percentages."""
    if not rows:
        raise ValueError("No scored utterances")
    normalizations = {row["normalization"] for row in rows}
    if len(normalizations) != 1:
        raise ValueError("Cannot mix normalization protocols")
    result = {
        key: sum(row[key] for row in rows)
        for key in ("reference_words", "reference_characters", "word_errors", "character_errors")
    }
    if result["reference_words"] <= 0 or result["reference_characters"] <= 0:
        raise ValueError("Empty corpus reference")
    result.update(
        utterances=len(rows),
        normalization=next(iter(normalizations)),
        wer=result["word_errors"] / result["reference_words"],
        cer=result["character_errors"] / result["reference_characters"],
    )
    return result


def extract_subset(
    archive: tarfile.TarFile, metadata: dict[str, dict[str, Any]], output: Path, count: int
) -> list[dict[str, Any]]:
    """First N regular audio members in archive order, independent of ASR outcomes."""
    selected = []
    seen = set()
    for member in archive:
        name = PurePosixPath(member.name)
        if not member.isfile() or name.name not in metadata:
            continue
        if name.is_absolute() or ".." in name.parts or member.size > 16 * 1024 * 1024:
            raise ValueError("Unsafe archive member")
        if name.name in seen:
            raise ValueError("Duplicate archive audio")
        seen.add(name.name)
        entry = metadata[name.name]
        case = "fleurs-" + str(len(selected)).zfill(3)
        destination = output / name.name
        source = archive.extractfile(member)
        if source is None:
            raise ValueError("Archive member has no content")
        with source, destination.open("xb") as target:
            shutil.copyfileobj(source, target, length=64 * 1024)
        reference = output / (case + ".txt")
        reference.write_text(entry["raw_transcription"], encoding="utf-8")
        selected.append(
            {
                "case": case,
                "dataset_id": entry["id"],
                "filename": name.name,
                "num_samples": entry["num_samples"],
                "gender": entry["gender"],
                "audio_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                "reference_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
            }
        )
        if len(selected) == count:
            return selected
    raise ValueError("Archive contains too few matching audio files")


def prepare_fleurs(output: Path, *, count: int = 32) -> Path:
    """Download only public data, stream archive and retain at most N bounded clips."""
    if not 1 <= count <= 32 or output.exists():
        raise ValueError("Use count 1..32 and a new output directory")
    output = private_directory(output.resolve())
    with urllib.request.urlopen(FLEURS_BASE + "test.tsv", timeout=60) as response:
        content = response.read(2 * 1024 * 1024 + 1)
    if len(content) > 2 * 1024 * 1024:
        raise ValueError("Oversized test metadata")
    (output / "test.tsv").write_bytes(content)
    metadata = parse_metadata(content.decode("utf-8"))
    # tarfile reads an archive stream; no extractall, links or remote code execution.
    with urllib.request.urlopen(FLEURS_BASE + "audio/test.tar.gz", timeout=60) as response:
        with tarfile.open(fileobj=response, mode="r|gz") as archive:
            selected = extract_subset(archive, metadata, output, count)
    provenance = {
        "dataset": "google/fleurs",
        "revision": FLEURS_REVISION,
        "config": "ru_ru",
        "split": "test",
        "license": "CC-BY-4.0",
        "attribution": "Conneau et al., FLEURS (2022), https://arxiv.org/abs/2205.12446",
        "source": "https://huggingface.co/datasets/google/fleurs",
        "selection": "first N matching regular WAV members in pinned test archive order",
        "count": count,
        "reference_field": "raw_transcription",
        "normalizations_declared_before_inference": [NORMALIZATION, LEXICAL_NORMALIZATION],
        "metadata_sha256": hashlib.sha256(content).hexdigest(),
        "samples": selected,
    }
    (output / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    manifest = {
        "cases": [
            {
                "id": row["case"],
                "path": str(output / row["filename"]),
                "indices": [0],
                "references": {"0": str(output / (row["case"] + ".txt"))},
                "profile": "FLEURS ru_ru test read speech; dataset reference; not manually re-audited",
            }
            for row in selected
        ],
        "timeout_seconds": 300,
    }
    path = output / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def score_fleurs(dataset: Path, report: Path) -> dict[str, Any]:
    """Score every selected case; fail rather than silently drop failed recognition."""
    provenance = json.loads((dataset / "provenance.json").read_text(encoding="utf-8"))
    benchmark = json.loads(report.read_text(encoding="utf-8"))
    selected = {row["case"]: row for row in provenance["samples"]}
    cases = benchmark["cases"]
    if (
        len(cases) != len(selected)
        or {c["case"] for c in cases} != set(selected)
        or any(c["status"] != "PASS" for c in cases)
    ):
        raise ValueError("Incomplete benchmark: all selected utterances must succeed")
    strict, lexical = [], []
    for case in cases:
        identity = case["case"]
        row = selected[identity]
        reference = dataset / (identity + ".txt")
        if hashlib.sha256(reference.read_bytes()).hexdigest() != row["reference_sha256"]:
            raise ValueError("Reference changed after selection")
        if (
            hashlib.sha256((dataset / row["filename"]).read_bytes()).hexdigest()
            != row["audio_sha256"]
        ):
            raise ValueError("Audio changed after selection")
        exported = json.loads(
            (report.parent / identity / "transcript.json").read_text(encoding="utf-8")
        )
        hypothesis = " ".join(s["raw_text"] for s in exported["segments"] if s["stream_index"] == 0)
        text = reference.read_text(encoding="utf-8")
        original = quality_metrics(text, hypothesis)
        if original != case["quality"]["0"]:
            raise ValueError("Exported RAW differs from in-pipeline scoring")
        strict.append(original)
        secondary = quality_metrics(lexical_text(text), lexical_text(hypothesis))
        secondary["normalization"] = LEXICAL_NORMALIZATION
        lexical.append(secondary)
    result = {
        "dataset": provenance["dataset"],
        "revision": provenance["revision"],
        "count": len(cases),
        "audio_seconds": sum(c["audio_duration_ms"] for c in cases) / 1000,
        "wall_seconds": sum(c["wall_seconds"] for c in cases),
        "strict_primary": aggregate_quality(strict),
        "lexical_secondary": aggregate_quality(lexical),
        "provenance_sha256": hashlib.sha256((dataset / "provenance.json").read_bytes()).hexdigest(),
    }
    (report.parent / "quality-summary.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    return result
