"""Reproducible local hardware E2E using the real worker and separate PostgreSQL."""

import hashlib
import json
import os
import platform
import subprocess
import time
from dataclasses import asdict, replace
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

import psutil
from alembic import command
from alembic.config import Config
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from local_transcriber.application.export import ExportFormat, ExportOptions, ExportService
from local_transcriber.application.pipeline import PipelineConfig
from local_transcriber.application.transcript import TranscriptService
from local_transcriber.infrastructure.benchmark_quality import NORMALIZATION, quality_metrics
from local_transcriber.infrastructure.benchmark_resources import ResourceSampler
from local_transcriber.infrastructure.database.export_store import PostgreSQLExportSource
from local_transcriber.infrastructure.database.models import ProcessingChunk, TranscriptSegment
from local_transcriber.infrastructure.database.pipeline_store import PostgreSQLPipelineStore
from local_transcriber.infrastructure.database.session import make_engine, session_factory
from local_transcriber.infrastructure.database.text_store import (
    PostgreSQLTranscriptStore,
    TermRepository,
)
from local_transcriber.infrastructure.diagnostics import DiagnosticLog
from local_transcriber.infrastructure.export_files import AtomicExportWriter
from local_transcriber.infrastructure.media import MediaInspector, media_fingerprint
from local_transcriber.infrastructure.privacy import child_environment, private_directory
from local_transcriber.infrastructure.settings import AppSettings
from local_transcriber.infrastructure.silero_segmenter import SegmentationConfig
from local_transcriber.infrastructure.transcription_task import prepare_task
from local_transcriber.infrastructure.worker_manager import WorkerManager


class BenchmarkCase(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,47}$")]
    path: str
    indices: Annotated[list[int], Field(min_length=1, max_length=16)] = [1]
    end_ms: Annotated[int, Field(gt=0)] | None = None
    crash_after_chunks: Annotated[int, Field(gt=0)] | None = None
    references: dict[str, str] = Field(default_factory=dict)
    normalization: str = NORMALIZATION
    # Human annotations, not inferred from ASR output or filename.
    profile: Annotated[str, Field(max_length=200)] = "UNREVIEWED"


class BenchmarkManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    cases: Annotated[list[BenchmarkCase], Field(min_length=1, max_length=32)]
    timeout_seconds: Annotated[int, Field(ge=30, le=86400)] = 14400


def load_manifest(path: Path) -> BenchmarkManifest:
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("Benchmark manifest exceeds 1 MiB")
    manifest = BenchmarkManifest.model_validate_json(path.read_bytes())
    if len({case.id for case in manifest.cases}) != len(manifest.cases):
        raise ValueError("Duplicate benchmark case id")
    for case in manifest.cases:
        if len(set(case.indices)) != len(case.indices) or any(i < 0 for i in case.indices):
            raise ValueError("Select unique nonnegative stream indices")
        if not Path(case.path).is_absolute():
            raise ValueError("Benchmark sources require absolute local paths")
        if case.normalization != NORMALIZATION:
            raise ValueError("Explicit normalization must match the documented protocol")
        if not set(case.references) <= {str(i) for i in case.indices}:
            raise ValueError("References must identify selected stream indices")
    return manifest


def _source_snapshot(root: Path) -> dict[str, str]:
    """Include untracked source modules: HEAD/diff alone cannot reproduce new code."""
    files = sorted(
        [
            *(root / "src/local_transcriber").rglob("*.py"),
            *(root / "scripts").glob("*.py"),
            *(root / name for name in ("pyproject.toml", "uv.lock") if (root / name).is_file()),
        ]
    )
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in files
    }


def _checkpoint_snapshot(factory, job: UUID) -> dict[str, str]:
    """Hash committed content and identities; keep transcript text out of artifacts."""
    with factory() as session:
        chunks = session.scalars(
            select(ProcessingChunk).where(
                ProcessingChunk.job_id == job, ProcessingChunk.status == "COMPLETED"
            )
        ).all()
        result = {}
        for chunk in chunks:
            rows = session.scalars(
                select(TranscriptSegment)
                .where(TranscriptSegment.chunk_id == chunk.id)
                .order_by(TranscriptSegment.segment_index)
            ).all()
            payload = [(str(r.id), r.segment_index, r.start_ms, r.end_ms, r.raw_text) for r in rows]
            result[str(chunk.id)] = hashlib.sha256(
                json.dumps(
                    [chunk.attempt_count, str(chunk.completed_at), payload], ensure_ascii=False
                ).encode()
            ).hexdigest()
        return result


def _verify_chunks(factory, job: UUID, end_ms: int, indices: tuple[int, ...]) -> dict:
    with factory() as session:
        rows = session.scalars(select(ProcessingChunk).where(ProcessingChunk.job_id == job)).all()
        segments = session.scalars(
            select(TranscriptSegment).where(TranscriptSegment.job_id == job)
        ).all()
        expected = len(indices) * ((end_ms + 299999) // 300000)
        keys = {(str(r.stream_id), r.chunk_index) for r in rows}
        covered = all(
            sorted((r.start_ms, r.end_ms) for r in rows if r.stream_id == stream)
            == [(i, min(i + 300000, end_ms)) for i in range(0, end_ms, 300000)]
            for stream in {r.stream_id for r in rows}
        )
        valid = (
            len(rows) == expected == len(keys)
            and covered
            and all(r.status == "COMPLETED" for r in rows)
            and all(0 <= s.start_ms < s.end_ms <= end_ms for s in segments)
        )
        if not valid:
            raise RuntimeError("Persisted chunk coverage/segment timeline validation failed")
        return {
            "chunks": len(rows),
            "segments": len(segments),
            "timeline_integrity": "PASS",
            "chunk_boundaries": "PASS",
            "last_segment_end_ms": max((s.end_ms for s in segments), default=None),
        }


def run_case(
    case: BenchmarkCase,
    settings: AppSettings,
    factory: sessionmaker[Session],
    work: Path,
    timeout: int,
) -> dict:
    directory = private_directory(work / case.id)
    result = {
        "case": case.id,
        "status": "FAIL",
        "errors": [],
        "profile": case.profile,
        "quality": "NOT RUN: no human reference",
        "wall_seconds": None,
    }
    sampler = ResourceSampler(
        directory / "resources.jsonl", settings.nvidia_smi_path, settings.gpu_index
    )
    start = time.perf_counter()
    job = None
    try:
        media = MediaInspector(settings.ffprobe_path, timeout=30).inspect(Path(case.path))
        if case.end_ms and case.end_ms > media.duration_ms:
            result.update(
                status="NOT TESTED",
                errors=["source_shorter_than_requested"],
                requested_duration_ms=case.end_ms,
                source_duration_ms=media.duration_ms,
            )
            return result
        end = case.end_ms or media.duration_ms
        result.update(
            source_fingerprint=media.fingerprint,
            source_size_bytes=media.size_bytes,
            source_duration_ms=media.duration_ms,
            audio_duration_ms=end,
            stream_audio_duration_ms=end * len(case.indices),
            indices=case.indices,
            container=media.container,
            full_source=case.end_ms is None,
            processing="cold worker; cuda; beam=5; word timestamps; VAD; chunk=300000/overlap=1000",
        )
        task = prepare_task(
            settings, media, tuple(case.indices), PipelineConfig(end_ms=case.end_ms)
        )
        # A benchmark never enables downloads or permits a silent alternate compute profile.
        task = replace(task, model_config={**task.model_config, "fallback_compute_type": None})
        task.parameters["model_config"]["fallback_compute_type"] = None
        frozen = {}
        killed = False
        sampler.start()
        with (directory / "events.jsonl").open("x", encoding="utf-8") as events:
            with WorkerManager(PostgreSQLPipelineStore(factory)) as manager:
                manager.submit(task)
                while True:
                    if time.perf_counter() - start > timeout:
                        raise TimeoutError("benchmark_timeout")
                    manager.wait(0.2)
                    for event in manager.poll():
                        if event.ticket != task.ticket:
                            continue
                        job = event.job_id or job
                        progress = event.payload if event.kind == "PROGRESS" else None
                        events.write(
                            json.dumps(
                                {
                                    "seconds": time.perf_counter() - start,
                                    "event": event.kind,
                                    "progress": progress,
                                }
                            )
                            + "\n"
                        )
                        events.flush()
                        if (
                            event.kind == "PROGRESS"
                            and case.crash_after_chunks
                            and not killed
                            and progress["completed"] >= case.crash_after_chunks
                        ):
                            if progress["completed"] >= progress["total"]:
                                raise ValueError("Crash must occur before all chunks complete")
                            frozen = _checkpoint_snapshot(factory, job)
                            result["crash_completed_chunks"] = len(frozen)
                            result["crash_at_seconds"] = time.perf_counter() - start
                            # Kill ONLY the current child created by this manager, never a user process.
                            psutil.Process(manager.pid).kill()
                            killed = True
                        if event.kind in {"INTERRUPTED", "IPC_ERROR", "ERROR", "CANCELLED"}:
                            if event.kind == "INTERRUPTED" and killed and task.resume is None:
                                manager.restart()
                                task = replace(task, ticket=uuid4(), resume=job)
                                manager.submit(task)
                                result["resumed"] = True
                            else:
                                raise RuntimeError("worker_" + event.kind)
                        if event.kind == "COMPLETED":
                            inference_seconds = time.perf_counter() - start
                            if case.crash_after_chunks and not killed:
                                raise RuntimeError("Requested crash point was not reached")
                            final = _checkpoint_snapshot(factory, job)
                            if any(final.get(key) != digest for key, digest in frozen.items()):
                                raise RuntimeError("Committed checkpoints changed after resume")
                            result.update(_verify_chunks(factory, job, end, tuple(case.indices)))
                            if killed:
                                result["crash_resume_integrity"] = "PASS"
                            service = TranscriptService(
                                PostgreSQLTranscriptStore(factory), TermRepository(factory)
                            )
                            raw = PostgreSQLTranscriptStore(factory).raw(job)
                            service.readable(job)
                            exporter = ExportService(
                                PostgreSQLExportSource(factory), AtomicExportWriter()
                            )
                            for format in ExportFormat:
                                exporter.export(
                                    job,
                                    directory / ("transcript." + format.value),
                                    ExportOptions(format),
                                )
                            result["text_and_exports"] = "PASS"
                            if case.references:
                                quality = {}
                                for index, path in case.references.items():
                                    reference = Path(path)
                                    if (
                                        not reference.is_absolute()
                                        or reference.stat().st_size > 1024 * 1024
                                    ):
                                        raise ValueError(
                                            "Reference requires absolute local path and <=1 MiB"
                                        )
                                    hypothesis = " ".join(
                                        s.raw_text
                                        for s in raw.segments
                                        if s.stream_index == int(index)
                                    )
                                    quality[index] = quality_metrics(
                                        reference.read_text(encoding="utf-8-sig"), hypothesis
                                    )
                                result["quality"] = quality
                            result.update(
                                status="PASS",
                                pipeline_seconds=inference_seconds,
                                pipeline_rtf=inference_seconds / (end / 1000),
                            )
                            return result
    except Exception as error:
        # Class/code only: SQL, private text, credentials, paths and traceback are excluded.
        result["errors"].append(type(error).__name__)
        return result
    finally:
        if sampler._thread.ident is not None:
            try:
                sampler.stop()
            except RuntimeError:
                result.update(status="FAIL")
                result["errors"].append("resource_sampler_failed")
        result.update(sampler.summary())
        result["wall_seconds"] = time.perf_counter() - start
        if result.get("audio_duration_ms"):
            result["rtf"] = result["wall_seconds"] / (result["audio_duration_ms"] / 1000)
        result["job_id"] = str(job) if job else None
        (directory / "metrics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")


def run_manifest(path: Path, settings: AppSettings, root: Path, output: Path) -> int:
    """Migrate a new random schema in the separate test DB; preserve private artifacts."""
    manifest = load_manifest(path)
    if settings.device != "cuda":
        raise ValueError("Hardware benchmark requires cuda; CPU cannot satisfy this gate")
    if output.exists():
        raise ValueError("Choose a new benchmark output directory; existing results are preserved")
    work = private_directory(output.resolve())
    diagnostics = None
    schema = "lt_test_" + uuid4().hex
    probe = make_engine(settings, test=True)
    engine = None
    try:
        diagnostics = DiagnosticLog(settings.logs_dir)
        with probe.begin() as connection:
            connection.execute(text('CREATE SCHEMA "' + schema + '"'))
        engine = make_engine(settings, test=True, test_schema=schema)
        config = Config(str(root / "alembic.ini"))
        config.attributes.update(settings=settings, test_database=True, test_schema=schema)
        with engine.connect() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        environment = {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "cpu": platform.processor(),
            "logical_cpus": psutil.cpu_count(),
            "physical_ram_bytes": psutil.virtual_memory().total,
            "packages": {
                name: version(name)
                for name in (
                    "faster-whisper",
                    "ctranslate2",
                    "onnxruntime",
                    "sqlalchemy",
                    "psycopg",
                    "psutil",
                    "PySide6",
                )
            },
            "model_files": {
                name: media_fingerprint(settings.model_path / name)
                for name in ("model.bin", "config.json", "tokenizer.json")
            },
            "device": settings.device,
            "gpu_index": settings.gpu_index,
            "model_name": settings.model_name,
            "compute_type": settings.compute_type,
            "beam_size": 5,
            "word_timestamps": True,
            "fallback_compute_type": None,
            "vad_config": asdict(SegmentationConfig.from_settings(settings)),
            "chunk_ms": 300000,
            "overlap_ms": 1000,
            "git_commit": subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=5
            ).stdout.strip(),
            "started_utc": datetime.now(UTC).isoformat(),
            "normalization": NORMALIZATION,
            "source_files_sha256": _source_snapshot(root),
        }
        for label, arguments in (
            (
                "gpu",
                [
                    settings.nvidia_smi_path,
                    f"--id={settings.gpu_index}",
                    "--query-gpu=name,driver_version,memory.total",
                    "--format=csv,noheader",
                ],
            ),
            ("ffmpeg", [settings.ffmpeg_path, "-version"]),
            ("ffprobe", [settings.ffprobe_path, "-version"]),
        ):
            info = subprocess.run(
                arguments,
                capture_output=True,
                text=True,
                timeout=5,
                env=child_environment(),
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            environment[label] = (
                info.stdout.splitlines()[0]
                if info.returncode == 0 and info.stdout
                else "NOT AVAILABLE"
            )
        diff = subprocess.run(
            ["git", "diff", "--binary", "HEAD"], cwd=root, capture_output=True, timeout=5
        )
        environment["working_tree_diff_sha256"] = hashlib.sha256(diff.stdout).hexdigest()
        environment["tracked_working_tree_dirty"] = bool(diff.stdout)
        with probe.connect() as connection:
            environment["postgresql"] = connection.scalar(text("SHOW server_version"))
        results = []
        for case in manifest.cases:
            print("BENCHMARK START:", case.id, flush=True)
            result = run_case(
                case, settings, session_factory(engine), work, manifest.timeout_seconds
            )
            results.append(result)
            (work / "benchmark.json").write_text(
                json.dumps({"environment": environment, "cases": results}, indent=2),
                encoding="utf-8",
            )
            print("BENCHMARK RESULT:", json.dumps(result), flush=True)
        return int(any(r["status"] == "FAIL" for r in results))
    finally:
        if engine is not None:
            engine.dispose()
        probe.dispose()
        if diagnostics is not None:
            diagnostics.close()
        # Do not drop a schema or private artifacts automatically; owned launcher stops its cluster.
