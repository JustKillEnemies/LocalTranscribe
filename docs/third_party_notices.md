# Компоненты Windows build

В сборке сохраняются license/notice файлы установленных runtime wheels,
Python LICENSE и недостающие upstream texts. Полные тексты находятся в
`_internal/licenses`, ссылки/digests исходников дополнительных текстов —
[bundling/license-sources.json](../bundling/license-sources.json).
Версии, declared dependency inventory и notice paths — `_internal/build-manifest.json`;
фактические файлы bundle и SHA-256 — dist-inventory.json. Dependency inventory
может включать объявленные meta-package dependencies, не используемые в GUI.

| Компонент | Источник / текст |
| --- | --- |
| Python 3.14 | [Python licence](https://docs.python.org/3/license.html), полный LICENSE из текущего Python. |
| PyInstaller bootloader | [PyInstaller license/exception](https://pyinstaller.org/en/stable/license.html); полный notice PyInstaller wheel. |
| Qt/PySide6/shiboken6 | [Qt licensing](https://www.qt.io/licensing/open-source-lgpl-obligations), wheel notices, LGPL-3.0/GPL-3.0 тексты. DLL сохраняются отдельными файлами onedir. |
| SQLAlchemy/Alembic/Pydantic | MIT notices из wheels. |
| psycopg/libpq | LGPL-3.0/поставляемые wheel notices. PostgreSQL server/tools внешние. |
| faster-whisper | [MIT](https://github.com/SYSTRAN/faster-whisper/blob/master/LICENSE), установленный notice. |
| CTranslate2 | [MIT v4.8.2](https://github.com/OpenNMT/CTranslate2/blob/v4.8.2/LICENSE), vendored upstream text. |
| Silero VAD model | [MIT](https://github.com/snakers4/silero-vad/blob/v6.0/LICENSE), отдельный notice включён. |
| ONNX Runtime | MIT/ThirdPartyNotices из wheel. |
| PyAV/FFmpeg libraries | BSD-3-Clause/библиотечные notices из av wheel, LGPL-2.1 text. Внешние FFmpeg/ffprobe executables поставляются отдельно со своими notices/source information. |
| NVIDIA cuBLAS/cuDNN/NVRTC | Проприетарные NVIDIA licence texts из конкретных locked wheels, сохранены в bundle. NVIDIA driver внешний. |
| tokenizers/flatbuffers | [tokenizers v0.23.2](https://github.com/huggingface/tokenizers/blob/v0.23.2/LICENSE), [flatbuffers v25.12.19](https://github.com/google/flatbuffers/blob/v25.12.19/LICENSE), upstream тексты. |
| Остальные declared dependencies | Notices и versions в build-manifest.json; это инвентаризация, не новая лицензия проекта. |

Whisper model и public FLEURS corpus в dist не входят. Атрибуция FLEURS находится
в [benchmark.md](benchmark.md); модель подготавливается отдельно с условиями её
исходной поставки. Исходники Qt/прочих компонентов и условия их поставок доступны
по upstream links/versions; при распространении сохраняйте соответствующие notices.

Лицензия собственного проекта владельцем пока не назначена. Здесь фиксируются
компоненты и исходные тексты лицензий; это не назначение лицензии LocalTranscribe.
Сборка остаётся локальным artifact, публикация/подпись/инсталлятор не выполнялись.
