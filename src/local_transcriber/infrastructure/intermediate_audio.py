"""Optional bounded WAV capture around the existing streaming decoder."""

import os
import wave
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from local_transcriber.application.media_decode import MediaDecoder
from local_transcriber.domain.audio import (
    PCM_CHANNELS,
    PCM_SAMPLE_RATE,
    PCM_SAMPLE_WIDTH,
    AudioBlock,
)


class RecordingDecoder:
    def __init__(self, decoder: MediaDecoder, directory: Callable[[], Path]) -> None:
        self._decoder, self._directory = decoder, directory

    @contextmanager
    def decode(self, source: Path, **kwargs: Any) -> Iterator[Iterator[AudioBlock]]:
        directory = self._directory()
        directory.mkdir(parents=True, exist_ok=True)
        identifier = uuid4().hex
        interval = kwargs["decode_range"]
        destination = (
            directory
            / f"stream-{kwargs['stream_index']}-{interval.start_ms}-{interval.end_ms}-{identifier}.wav"
        )
        temporary = destination.with_suffix(".tmp")
        try:
            with self._decoder.decode(source, **kwargs) as decoded:
                with wave.open(str(temporary), "wb") as output:
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
                os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
