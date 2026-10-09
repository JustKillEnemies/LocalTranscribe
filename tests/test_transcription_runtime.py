"""Installed Step 06 runtime checks; model inference is a separate manual gate."""

import os
from importlib.metadata import version

import pytest


@pytest.mark.gpu
def test_ctranslate2_sees_target_cuda_compute_types() -> None:
    if os.environ.get("PYTEST_REQUIRE_CUDA") != "1":
        pytest.skip("set PYTEST_REQUIRE_CUDA=1 for the target workstation check")

    import av
    import ctranslate2
    import faster_whisper
    import numpy
    import onnxruntime

    assert faster_whisper.__version__ == "1.2.1"
    assert ctranslate2.__version__ == "4.8.2"
    assert numpy.__version__ == "2.5.3"
    assert av.__version__ == "19.0.1"
    assert onnxruntime.__version__ == "1.31.0"
    assert version("nvidia-cublas-cu12") == "12.9.2.10"
    assert version("nvidia-cudnn-cu12") == "9.27.0.42"
    assert ctranslate2.get_cuda_device_count() >= 1
    compute_types = ctranslate2.get_supported_compute_types("cuda", 0)
    assert {"float16", "int8_float16"} <= compute_types
