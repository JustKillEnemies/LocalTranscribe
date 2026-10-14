"""Frozen entry: divert spawn children before importing CLI/Qt/ML."""

import multiprocessing
import sys

if __name__ == "__main__":
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name)
        if stream is not None:
            stream.reconfigure(encoding="utf-8")
    multiprocessing.freeze_support()
    if sys.argv[1:] == ["--_cuda-count"]:
        import json

        import ctranslate2

        print(json.dumps(ctranslate2.get_cuda_device_count()))
        raise SystemExit(0)
    from local_transcriber.__main__ import main

    raise SystemExit(main(sys.argv[1:] or ["gui"]))
