"""Optional bounded WAV capture around the existing streaming decoder."""

import os
import wave
from collections.abc import Callable, Iterator
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from local_transcriber.application.media_decode import MediaDecoder
from local_transcriber.domain.audio import (
    PCM_CHANNELS,
    PCM_SAMPLE_RATE,
    PCM_SAMPLE_WIDTH,
    AudioBlock,
)
from local_transcriber.infrastructure.temp_storage import ManagedTempFiles


class RecordingDecoder:
    def __init__(
        self,
        decoder: MediaDecoder,
        directory: Callable[[], Path],
        *,
        managed: ManagedTempFiles | None = None,
        job_id: Callable[[], UUID] | None = None,
    ) -> None:
        self._decoder, self._directory = decoder, directory
        if managed is not None and job_id is None:
            raise ValueError("Managed capture requires a job UUID provider")
        self._managed, self._job_id = managed, job_id

    @contextmanager
    def decode(self, source: Path, **kwargs: Any) -> Iterator[Iterator[AudioBlock]]:
        if self._managed is not None:
            identifier = self._job_id()
            context = self._managed.lease(identifier, create=True)
        else:
            identifier = None
            context = nullcontext(self._directory())
        with context as directory:
            with self._record(source, directory, identifier, **kwargs) as recorded:
                yield recorded

    @contextmanager
    def _record(
        self, source: Path, directory: Path, job_id: UUID | None, **kwargs: Any
    ) -> Iterator[Iterator[AudioBlock]]:
        directory.mkdir(parents=True, exist_ok=True)
        identifier = uuid4().hex
        interval = kwargs["decode_range"]
        destination = (
            directory
            / f"stream-{kwargs['stream_index']}-{interval.start_ms}-{interval.end_ms}-{identifier}.wav"
        )
        temporary = destination.with_suffix(".tmp")
        if self._managed is not None:
            self._managed.register(
                directory, job_id, {temporary.name: "temporary", destination.name: "retained"}
            )
        try:
            with self._decoder.decode(source, **kwargs) as decoded:
                with temporary.open("xb") as file, wave.open(file, "wb") as output:
                    output.setnchannels(PCM_CHANNELS)
                    output.setsampwidth(PCM_SAMPLE_WIDTH)
                    output.setframerate(PCM_SAMPLE_RATE)
                    exhausted = False

                    def recorded():
                        nonlocal exhausted
                        for block in decoded:
                            output.writeframesraw(block.pcm)
                            yield block
                        exhausted = True

                    iterator = recorded()
                    try:
                        yield iterator
                    finally:
                        iterator.close()
            if exhausted:
                if os.name == "nt":
                    os.rename(temporary, destination)
                else:
                    os.link(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
