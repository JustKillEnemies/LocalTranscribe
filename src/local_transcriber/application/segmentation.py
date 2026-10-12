"""Application port for streaming source-timed speech segmentation."""

from collections.abc import Iterable, Iterator
from typing import Protocol

from local_transcriber.domain.audio import AudioBlock
from local_transcriber.domain.speech import SpeechChunk


class SpeechSegmenter(Protocol):
    def segment(self, blocks: Iterable[AudioBlock]) -> Iterator[SpeechChunk]: ...
