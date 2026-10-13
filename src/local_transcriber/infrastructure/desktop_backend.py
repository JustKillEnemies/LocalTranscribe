"""Background desktop composition; Qt event loop never performs SQL/probe/inference."""

import json
import shutil
import time
from dataclasses import asdict, replace
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select

from local_transcriber.application.desktop import DesktopEvent, DesktopRecord, JobChoices
from local_transcriber.application.export import ExportService
from local_transcriber.application.media_import import ImportMedia
from local_transcriber.application.pipeline import PipelineConfig
from local_transcriber.application.transcript import TranscriptService
from local_transcriber.application.worker_protocol import WorkerCommand, WorkerTask
from local_transcriber.domain.audio import PCM_BYTES_PER_SECOND
from local_transcriber.domain.media import AudioStreamInfo, MediaInfo
from local_transcriber.infrastructure.database.export_store import PostgreSQLExportSource
from local_transcriber.infrastructure.database.models import (
    AudioStream,
    MediaFile,
    TranscriptionJob,
)
from local_transcriber.infrastructure.database.pipeline_store import PostgreSQLPipelineStore
from local_transcriber.infrastructure.database.repositories import MediaRepository
from local_transcriber.infrastructure.database.session import (
    make_engine,
    session_factory,
    transaction,
)
from local_transcriber.infrastructure.database.text_store import (
    PostgreSQLTranscriptStore,
    TermRepository,
)
from local_transcriber.infrastructure.export_files import AtomicExportWriter
from local_transcriber.infrastructure.faster_whisper_engine import FasterWhisperConfig
from local_transcriber.infrastructure.media import MediaInspector, media_fingerprint
from local_transcriber.infrastructure.settings import AppSettings, load_settings
from local_transcriber.infrastructure.silero_segmenter import SegmentationConfig
from local_transcriber.infrastructure.worker_manager import WorkerManager


class DesktopService:
    def __init__(
        self, env_file: Path | None = None, *, settings: AppSettings | None = None
    ) -> None:
        self.settings = settings or load_settings(env_file)
        self.engine = None
        self.factory = None
        self.manager = None
        self.records: dict[UUID, DesktopRecord] = {}
        self.tickets: dict[UUID, UUID] = {}
        self.started: dict[UUID, float] = {}

    def _connect(self) -> None:
        if self.engine is None:
            self.engine = make_engine(self.settings)
            self.factory = session_factory(self.engine)

    def _disk(self, required: int = 128 * 1024 * 1024) -> DesktopEvent:
        path = self.settings.temp_dir
        while not path.exists() and path != path.parent:
            path = path.parent
        free = shutil.disk_usage(path).free
        if free < required:
            raise ValueError("Недостаточно места в каталоге рабочих данных.")
        return DesktopEvent(
            "DISK", {"free": free, "required": required, "path": str(self.settings.temp_dir)}
        )

    def execute(self, command: str, payload: Any = None) -> list[DesktopEvent]:
        if command in {"result_load", "result_manual", "result_export"}:
            self._connect()
            source = PostgreSQLExportSource(self.factory)
            if command == "result_load":
                # Read-only snapshot; opening history never initializes the model/worker.
                value = source.load(payload.job_id)
                kind = "RESULT_LOADED"
            elif command == "result_manual":
                if payload.base_id is None:
                    raise ValueError("Не выбрана исходная версия правок.")
                service = TranscriptService(
                    PostgreSQLTranscriptStore(self.factory), TermRepository(self.factory)
                )
                value = service.manual(payload.job_id, payload.base_id, payload.content)
                kind = "MANUAL_SAVED"
            else:
                if payload.destination is None or payload.options is None:
                    raise ValueError("Не задан путь или формат экспорта.")
                value = ExportService(source, AtomicExportWriter()).export(
                    payload.job_id, payload.destination, payload.options, version_id=payload.base_id
                )
                kind = "RESULT_EXPORTED"
            return [DesktopEvent(kind, value, payload.request_id)]
        if command == "refresh":
            self._connect()
            with transaction(self.factory) as session:
                media_rows = session.scalars(
                    select(MediaFile).order_by(MediaFile.created_at.desc()).limit(500)
                ).all()
                records = []
                for row in media_rows:
                    streams = session.scalars(
                        select(AudioStream)
                        .where(AudioStream.media_file_id == row.id)
                        .order_by(AudioStream.stream_index)
                    ).all()
                    job = session.scalar(
                        select(TranscriptionJob)
                        .where(TranscriptionJob.media_file_id == row.id)
                        .order_by(TranscriptionJob.created_at.desc())
                        .limit(1)
                    )
                    info = MediaInfo(
                        Path(row.file_path),
                        row.filename,
                        row.file_size_bytes,
                        row.duration_ms,
                        row.container_format,
                        row.file_fingerprint,
                        tuple(
                            AudioStreamInfo(
                                s.stream_index,
                                s.codec,
                                s.sample_rate,
                                s.channels,
                                s.language_tag,
                                s.title,
                                s.start_time_ms,
                            )
                            for s in streams
                        ),
                    )
                    elapsed = 0
                    if job and job.started_at:
                        elapsed = int(
                            (
                                (job.finished_at or datetime.now(UTC)) - job.started_at
                            ).total_seconds()
                            * 1000
                        )
                    previous = self.records.get(row.id)
                    # Running/queued state is owned by the manager, not a refresh query.
                    record = (
                        previous
                        if row.id in self.tickets.values()
                        else DesktopRecord(
                            row.id,
                            info,
                            job.id if job else None,
                            job.status if job else "IMPORTED",
                            job.model_name if job else "",
                            float(job.progress_percent) if job else 0,
                            elapsed,
                            job.error_message or "" if job else "",
                            dict(job.parameters) if job else {},
                            tuple((s.stream_index, s.role_label or "") for s in streams),
                        )
                    )
                    self.records[row.id] = record
                    records.append(record)
            return [
                DesktopEvent("CONNECTED", self.settings),
                DesktopEvent("RECORDS", records),
                self._disk(),
            ]
        if command == "settings":
            if self.tickets:
                raise ValueError("Настройки подключения можно менять после остановки очереди.")
            self.close()
            self.settings = load_settings(payload)
            self.records.clear()
            return self.execute("refresh")
        self._connect()
        if command == "import":
            disk = self._disk()
            result = ImportMedia(
                MediaInspector(self.settings.ffprobe_path, timeout=self.settings.probe_timeout),
                MediaRepository(self.factory),
            ).execute(Path(payload))
            if result.media_id in self.records:
                record = self.records[result.media_id]
            else:
                record = DesktopRecord(result.media_id, result.media)
                self.records[record.id] = record
            return [DesktopEvent("RECORD", record), disk]
        if command == "start":
            identifier, choices = payload
            return self._start(identifier, choices)
        if command in {"pause", "resume", "cancel"}:
            identifier = payload
            ticket = next((t for t, key in self.tickets.items() if key == identifier), None)
            if ticket is not None:
                self.manager.command(
                    {
                        "pause": WorkerCommand.PAUSE,
                        "resume": WorkerCommand.RESUME,
                        "cancel": WorkerCommand.CANCEL,
                    }[command],
                    ticket,
                )
                return [
                    DesktopEvent(
                        "INFO", "Команда отправлена; ожидается подтверждение worker.", identifier
                    )
                ]
            record = self.records[identifier]
            if command == "resume" and record.status in {"FAILED", "INTERRUPTED", "PAUSED"}:
                return self._start(identifier, None, resume=True)
            if command == "cancel" and record.job_id:
                PostgreSQLPipelineStore(self.factory).cancel(record.job_id, None, None)
                record = replace(record, status="CANCELLED")
                self.records[identifier] = record
                return [DesktopEvent("RECORD", record)]
            raise ValueError("Нет активного задания для этой команды.")
        raise ValueError("Неизвестная команда интерфейса.")

    def _start(
        self, identifier: UUID, choices: JobChoices | None, *, resume: bool = False
    ) -> list[DesktopEvent]:
        record = self.records[identifier]
        if identifier in self.tickets.values():
            raise ValueError("Запись уже находится в очереди.")
        media = MediaInspector(
            self.settings.ffprobe_path, timeout=self.settings.probe_timeout
        ).inspect(record.media.path)
        if media.fingerprint != record.media.fingerprint:
            raise ValueError("Исходный файл изменился; импортируйте новую версию отдельно.")
        if resume:
            signature = record.parameters
            parameters = signature["parameters"]
            model_dict, vad_dict = parameters["model_config"], parameters["vad"]
            model_dict = {
                **model_dict,
                "model_path": Path(model_dict["model_path"]),
                "download_root": Path(model_dict["download_root"])
                if model_dict.get("download_root")
                else None,
            }
            config = PipelineConfig(**signature["pipeline"])
            indices = tuple(signature["stream_indices"])
        else:
            if not set(choices.indices) <= {s.stream_index for s in media.audio_streams}:
                raise ValueError("Выбранная дорожка отсутствует.")
            model_path = (
                self.settings.model_path
                if choices.model == self.settings.model_name
                else self.settings.models_dir / choices.model
            )
            if not model_path.is_dir() or not all(
                (model_path / name).is_file()
                for name in ("model.bin", "config.json", "tokenizer.json")
            ):
                raise ValueError(
                    "Локальная модель не найдена. Подготовьте модель в настроенном каталоге."
                )
            model = FasterWhisperConfig(
                model_name=choices.model,
                model_path=model_path,
                device=choices.device,
                device_index=self.settings.gpu_index,
                compute_type=choices.compute,
                fallback_compute_type="int8_float16"
                if choices.device == "cuda" and choices.compute != "int8_float16"
                else None,
                word_timestamps=True,
                download_root=self.settings.models_dir,
            )
            vad = replace(SegmentationConfig.from_settings(self.settings), enabled=choices.vad)
            model_dict, vad_dict = asdict(model), asdict(vad)
            parameters = {
                "model_config": json.loads(json.dumps(model_dict, default=str)),
                "vad": vad_dict,
                "model_files": {
                    name: media_fingerprint(model_path / name)
                    for name in ("model.bin", "config.json", "tokenizer.json")
                },
                "runtime": {name: version(name) for name in ("faster-whisper", "ctranslate2")},
                "roles": {str(i): role.strip() for i, role in choices.roles},
                "intermediate_audio": {
                    "enabled": choices.keep_audio,
                    "directory": str(self.settings.temp_dir / "intermediate"),
                },
            }
            config, indices = PipelineConfig(), choices.indices
        if not Path(model_dict["model_path"]).is_dir():
            raise ValueError("Локальная модель не найдена. Загрузка моделей из GUI отключена.")
        if (
            vad_dict["enabled"]
            and config.overlap_ms < vad_dict["min_silence_ms"] + vad_dict["padding_ms"]
        ):
            raise ValueError("Overlap недостаточен для выбранных параметров VAD.")
        audio = parameters.get("intermediate_audio", {})
        required = (
            max(
                128 * 1024 * 1024,
                int(media.duration_ms / 1000 * PCM_BYTES_PER_SECOND * len(indices) * 1.05),
            )
            if audio.get("enabled")
            else 128 * 1024 * 1024
        )
        disk = self._disk(required)
        if self.manager is None:
            self.manager = WorkerManager(PostgreSQLPipelineStore(self.factory))
        elif resume and not self.tickets:
            self.manager.restart()
        task = WorkerTask(
            uuid4(),
            media.path,
            indices,
            config,
            parameters,
            self.settings.ffmpeg_path,
            self.settings.ffprobe_path,
            model_dict,
            vad_dict,
            record.job_id if resume else None,
        )
        roles = tuple((int(i), value) for i, value in parameters.get("roles", {}).items())
        if not resume:
            with transaction(self.factory) as session:
                for index, label in roles:
                    stream = session.scalar(
                        select(AudioStream).where(
                            AudioStream.media_file_id == identifier,
                            AudioStream.stream_index == index,
                        )
                    )
                    stream.role_label = label or None
        self.manager.submit(task)
        self.tickets[task.ticket] = identifier
        record = replace(
            record,
            status="PENDING",
            model=model_dict["model_name"],
            error="",
            roles=roles,
            progress=record.progress if resume else 0,
            elapsed_ms=0,
            job_id=record.job_id if resume else None,
            parameters=record.parameters if resume else {},
        )
        self.records[identifier] = record
        return [DesktopEvent("QUEUED", identifier), DesktopEvent("RECORD", record), disk]

    def poll(self) -> list[DesktopEvent]:
        if self.manager is None:
            return []
        output = []
        for event in self.manager.poll():
            identifier = self.tickets.get(event.ticket)
            if identifier is None:
                continue
            record = self.records[identifier]
            if event.kind == "STARTED":
                self.started[identifier] = time.monotonic()
            if event.job_id:
                record = replace(record, job_id=event.job_id)
            statuses = {
                "STARTED": "ANALYZING",
                "JOB_CREATED": "PROCESSING",
                "PROGRESS": "PROCESSING",
                "PAUSED": "PAUSED",
                "COMPLETED": "COMPLETED",
                "CANCELLED": "CANCELLED",
                "ERROR": "INTERRUPTED",
                "INTERRUPTED": "INTERRUPTED",
                "IPC_ERROR": "INTERRUPTED",
            }
            if event.kind in statuses:
                record = replace(record, status=statuses[event.kind])
                if (
                    event.kind in {"ERROR", "INTERRUPTED", "CANCELLED", "IPC_ERROR"}
                    and record.job_id is None
                ):
                    record = replace(record, status="IMPORTED")
            if event.kind == "JOB_CREATED":
                with transaction(self.factory) as session:
                    record = replace(
                        record,
                        parameters=dict(session.get(TranscriptionJob, event.job_id).parameters),
                    )
            if event.kind == "PROGRESS":
                completed, total = event.payload["completed"], event.payload["total"]
                record = replace(record, progress=completed * 100 / total if total else 0)
            if event.kind in {"ERROR", "INTERRUPTED", "IPC_ERROR"}:
                record = replace(record, error=str(event.payload or "Worker прерван."))
                output.append(DesktopEvent("ERROR", record.error, identifier))
            if event.kind == "PAUSE_DEFERRED":
                output.append(
                    DesktopEvent(
                        "INFO", "Пауза будет подтверждена после текущего участка.", identifier
                    )
                )
            if event.kind in {"COMPLETED", "CANCELLED", "ERROR", "INTERRUPTED", "IPC_ERROR"}:
                self.tickets.pop(event.ticket, None)
                output.append(DesktopEvent("DEQUEUED", identifier))
                if event.kind == "COMPLETED":
                    record = replace(record, progress=100)
                    try:
                        TranscriptService(
                            PostgreSQLTranscriptStore(self.factory), TermRepository(self.factory)
                        ).readable(record.job_id)
                    except Exception:
                        record = replace(
                            record,
                            error="STT завершён, но текст не подготовлен. Повторите text readable после восстановления БД.",
                        )
                        output.append(DesktopEvent("ERROR", record.error, identifier))
            record = replace(
                record,
                elapsed_ms=int(
                    (time.monotonic() - self.started.get(identifier, time.monotonic())) * 1000
                ),
            )
            self.records[identifier] = record
            output.append(DesktopEvent("RECORD", record))
        return output

    def close(self) -> None:
        if self.manager:
            self.manager.shutdown()
            self.manager = None
        if self.engine:
            self.engine.dispose()
            self.engine = self.factory = None
