"""Application port for bounded local media decoding."""

from collections.abc import Iterator
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Protocol

from local_transcriber.domain.audio import AudioBlock, DecodeRange


class CancellationToken(Protocol):
    def is_set(self) -> bool: ...


class MediaDecoder(Protocol):
    def decode(
        self,
        source: Path,
        *,
        stream_index: int,
        decode_range: DecodeRange,
        stream_start_ms: int = 0,
        cancel: CancellationToken | None = None,
    ) -> AbstractContextManager[Iterator[AudioBlock]]: ...
