"""Export saved text through ports, without media decoding or recognition."""

import json
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Protocol
from uuid import UUID

from local_transcriber.application.transcript import TextVersion
from local_transcriber.domain.text import Term, TextRules, TextSegment, VersionType, make_readable


class ExportError(RuntimeError):
    """Safe public export error."""


class ExportCancelled(ExportError):
    pass


class ExportCollision(ExportError):
    pass


class ExportFormat(StrEnum):
    TXT = "txt"
    SRT = "srt"
    JSON = "json"
    MARKDOWN = "md"


def export_filename(source_name: str, format: ExportFormat) -> str:
    """A portable suggestion, never silently rewrite the destination selected by the user."""
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", source_name.rsplit(".", 1)[0]).strip(" .")[:100]
    if not stem:
        stem = "transcript"
    if re.fullmatch(
        r"(?i:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³]|CONIN\$|CONOUT\$)",
        stem.split(".")[0].rstrip(" ."),
    ):
        stem = "_" + stem
    return f"{stem}.{format.value}"


@dataclass(frozen=True)
class ExportDocument:
    media: dict[str, object]
    job: dict[str, object]
    streams: tuple[dict[str, object], ...]
    segments: tuple[TextSegment, ...]
    raw: TextVersion
    readable: TextVersion | None
    selected: TextVersion


@dataclass(frozen=True)
class ExportOptions:
    format: ExportFormat
    timestamps: bool = False
    roles: bool = False
    overwrite: bool = False


class Cancellation(Protocol):
    def is_set(self) -> bool: ...


class ExportSource(Protocol):
    def load(self, job_id: UUID, version_id: UUID | None = None) -> ExportDocument: ...


class ExportWriter(Protocol):
    def write(
        self,
        destination: Path,
        fragments: Iterable[str],
        *,
        overwrite: bool = False,
        cancel: Cancellation | None = None,
    ) -> Path: ...


def check_cancel(cancel: Cancellation | None) -> None:
    if cancel is not None and cancel.is_set():
        raise ExportCancelled("Экспорт отменён; файл назначения не изменён.")


def timestamp(milliseconds: int, *, srt: bool = False) -> str:
    if type(milliseconds) is not int or milliseconds < 0:
        raise ExportError("Таймкод должен быть целым неотрицательным числом миллисекунд.")
    seconds, fraction = divmod(milliseconds, 1000)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{',' if srt else '.'}{fraction:03d}"


def _blocks(document: ExportDocument) -> tuple[dict[str, object], ...]:
    selected = document.selected
    if selected.kind is VersionType.MANUAL:
        raise ExportError(
            "Ручная версия не имеет привязки к времени; экспортируйте её без таймкодов/ролей или выберите RAW/READABLE."
        )
    if selected.kind is VersionType.RAW:
        return tuple(
            {
                "text": s.raw_text,
                "start_ms": s.start_ms,
                "end_ms": s.end_ms,
                "stream_index": s.stream_index,
                "speaker_label": s.speaker_label,
            }
            for s in sorted(
                document.segments,
                key=lambda s: (
                    s.stream_index,
                    s.start_ms,
                    s.chunk_index,
                    s.segment_index,
                    s.id.int,
                ),
            )
        )
    metadata = selected.metadata
    if metadata.get("processor") != "conservative-text" or metadata.get("rules_version") != "1":
        raise ExportError("Неизвестные правила читаемой версии; выберите RAW или ручной текст.")
    # Old v1 versions have no paragraph map. Rebuild only deterministic formatting from
    # their own saved rules/dictionary, then require an exact match with persisted text.
    try:
        rebuilt = make_readable(
            document.segments,
            rules=TextRules(**metadata["rules"]),
            terms=tuple(
                Term(row["canonical"], tuple(row["variants"]), row["enabled"])
                for row in metadata["dictionary"]
            ),
        )
    except KeyError, TypeError, ValueError:
        raise ExportError("Метаданные читаемой версии повреждены.") from None
    if rebuilt.content != selected.content or rebuilt.metadata["source_digest"] != metadata.get(
        "source_digest"
    ):
        raise ExportError("Читаемая версия не соответствует сохранённым исходным сегментам.")
    return tuple(rebuilt.metadata["paragraphs"])


def _annotated(block: dict[str, object], options: ExportOptions) -> str:
    prefix = ""
    if options.timestamps:
        prefix += f"[{timestamp(block['start_ms'])} --> {timestamp(block['end_ms'])}] "
    if options.roles:
        prefix += f"[Дорожка {block['stream_index']}] "
        if block["speaker_label"]:
            prefix += f"{block['speaker_label']}: "
    return prefix + str(block["text"])


def _text(document: ExportDocument, options: ExportOptions) -> Iterator[str]:
    if document.selected.kind is VersionType.MANUAL or (
        document.selected.kind is VersionType.RAW and not options.timestamps and not options.roles
    ):
        if document.selected.kind is VersionType.MANUAL and (options.timestamps or options.roles):
            _blocks(document)  # Fail explicitly; don't invent alignment for manual text.
        content = document.selected.content
        yield content
        if content and not content.endswith("\n"):
            yield "\n"
        return
    for block in _blocks(document):
        if str(block["text"]).strip():
            yield _annotated(block, options) + "\n\n"


def _srt(document: ExportDocument, options: ExportOptions) -> Iterator[str]:
    blocks = sorted(
        enumerate(_blocks(document)),
        key=lambda item: (item[1]["start_ms"], item[1]["stream_index"], item[0]),
    )
    number = 0
    for _, block in blocks:
        # Blank source segments aren't subtitles; prevent blank lines breaking SRT cues.
        text = "\n".join(line.strip() for line in str(block["text"]).splitlines() if line.strip())
        if not text:
            continue
        number += 1
        if options.roles:
            label = f"[Дорожка {block['stream_index']}] "
            if block["speaker_label"]:
                label += f"{block['speaker_label']}: "
            text = label + text
        yield (
            f"{number}\n{timestamp(block['start_ms'], srt=True)} --> "
            f"{timestamp(block['end_ms'], srt=True)}\n{text}\n\n"
        )


def _json(document: ExportDocument) -> Iterator[str]:
    selected = document.selected
    data = {
        "schema_version": 1,
        "media": document.media,
        "job": document.job,
        "model": {
            "name": document.job["model_name"],
            "language": document.job["language"],
            "parameters": document.job["parameters"],
        },
        "selected_streams": document.streams,
        "version": {
            "id": str(selected.id),
            "number": selected.number,
            "kind": selected.kind.value,
            "processing_metadata": selected.metadata,
        },
        "text": {
            "raw": document.raw.content,
            "readable": document.readable.content if document.readable else None,
            "selected": selected.content,
        },
        "segments": [
            {
                "id": str(s.id),
                "stream_index": s.stream_index,
                "start_ms": s.start_ms,
                "end_ms": s.end_ms,
                "raw_text": s.raw_text,
                "speaker_label": s.speaker_label,
            }
            for s in sorted(
                document.segments,
                key=lambda s: (
                    s.start_ms,
                    s.stream_index,
                    s.chunk_index,
                    s.segment_index,
                    s.id.int,
                ),
            )
        ],
    }
    yield from json.JSONEncoder(ensure_ascii=False, indent=2).iterencode(data)
    yield "\n"


def render_export(document: ExportDocument, options: ExportOptions) -> Iterator[str]:
    if options.format is ExportFormat.JSON:
        yield from _json(document)
    elif options.format is ExportFormat.SRT:
        yield from _srt(document, options)
    else:
        if options.format is ExportFormat.MARKDOWN:
            # A fixed heading avoids treating an arbitrary media filename as Markdown code.
            yield f"# Транскрипт\n\nМодель: {document.job['model_name']}\n\nВерсия: {document.selected.kind.value}\n\n"
        yield from _text(document, options)


class ExportService:
    def __init__(self, source: ExportSource, writer: ExportWriter) -> None:
        self._source, self._writer = source, writer

    def export(
        self,
        job_id: UUID,
        destination: Path,
        options: ExportOptions,
        *,
        version_id: UUID | None = None,
        cancel: Cancellation | None = None,
    ) -> Path:
        check_cancel(cancel)
        document = self._source.load(job_id, version_id)
        check_cancel(cancel)
        if options.format is ExportFormat.SRT and version_id is None:
            document = replace(document, selected=document.raw)
        source = Path(str(document.media["file_path"]))
        if source.resolve() == destination.resolve() or (
            source.exists() and destination.exists() and source.samefile(destination)
        ):
            raise ExportError("Исходный медиафайл нельзя использовать как путь экспорта.")
        return self._writer.write(
            destination,
            render_export(document, options),
            overwrite=options.overwrite,
            cancel=cancel,
        )
