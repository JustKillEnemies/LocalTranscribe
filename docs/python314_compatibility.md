# Совместимость Python 3.14 на Windows x64

Дата проверки: 2026-10-08. Цель: обычный CPython 3.14 x64 с GIL,
`>=3.14,<3.15`; free-threaded cp314t в эту проверку не входит.
Интерпретатор локальной .venv — 3.14.4. Версия Python окончательно выбрана владельцем.

Проверялись публичные JSON-метаданные PyPI: Requires-Python, Requires-Dist,
неотозванные wheels и их теги. Использованы packaging.tags.cpython_tags /
compatible_tags для cp314, win_amd64 и parse_wheel_filename.
ABI3 и универсальные wheels учитываются, не требуется только буквальный cp314.
Тяжёлые пакеты, CUDA и модели не скачивались и не устанавливались.

## Результат проверки дистрибутивов

Версии ниже — проверенный снимок кандидатов, не runtime lock проекта.
METADATA/WHEEL PASS подтверждает возможность подобрать дистрибутив для Python,
а не успешный import, inference, работу DLL или совместимость всего окружения.

| Пакет | Версия в PyPI | Requires-Python | Совместимый wheel Windows x64 / Python 3.14 | Результат |
| --- | --- | --- | --- | --- |
| faster-whisper | 1.2.1 | >=3.9 | py3-none-any | METADATA/WHEEL PASS |
| CTranslate2 | 4.8.2 | >=3.9 | cp314-cp314-win_amd64 | METADATA/WHEEL PASS |
| silero-vad | 6.2.3 | >=3.8 | py3-none-any | METADATA/WHEEL PASS |
| torch | 2.14.1 | >=3.10 | cp314-cp314-win_amd64 | METADATA/WHEEL PASS |
| torchaudio | 2.11.0 | не указан | cp314-cp314-win_amd64 | WHEEL PASS; не подходит ограничению Silero audio <2.10 |
| onnxruntime (CPU) | 1.30.0 | >=3.11 | cp314-cp314-win_amd64 | METADATA/WHEEL PASS |
| av | 19.0.1 | >=3.12 | cp312-abi3-win_amd64 | METADATA/WHEEL PASS |
| tokenizers | 0.23.2 | >=3.10 | cp310-abi3-win_amd64 | METADATA/WHEEL PASS |
| numpy | 2.5.3 | >=3.12 | cp314-cp314-win_amd64 | METADATA/WHEEL PASS |
| soundfile | 0.14.0 | >=3.10 | py2.py3-none-win_amd64 | METADATA/WHEEL PASS |
| PySide6 | 6.12.0 | >=3.10,<3.16 | cp310-abi3-win_amd64 | METADATA/WHEEL PASS |
| SQLAlchemy | 2.1.4 | >=3.11 | cp314 / py3-none-any | METADATA/WHEEL PASS |
| Alembic | 1.20.0 | >=3.10 | py3-none-any | METADATA/WHEEL PASS |
| pydantic-settings | 2.15.0 | >=3.10 | py3-none-any | METADATA/WHEEL PASS |
| psycopg-binary (кандидат драйвера) | 3.3.6 | >=3.10 | cp314-cp314-win_amd64 | METADATA/WHEEL PASS |
| PyInstaller | 6.22.3 | >=3.8,<3.16 | py3-none-win_amd64 | METADATA/WHEEL PASS |
| uv | 0.12.23 | >=3.8 | py3-none-win_amd64 | METADATA/WHEEL PASS |
| Ruff | 0.16.10 | >=3.7 | py3-none-win_amd64 | METADATA/WHEEL PASS |
| pytest | 9.1.1 | >=3.10 | py3-none-any | METADATA/WHEEL PASS |
| Hatchling | 1.32.4 | >=3.10 | py3-none-any | METADATA/WHEEL PASS |

Источники снимка: официальные метаданные
[faster-whisper](https://pypi.org/pypi/faster-whisper/1.2.1/json),
[CTranslate2](https://pypi.org/pypi/ctranslate2/4.8.2/json),
[Silero VAD](https://pypi.org/pypi/silero-vad/6.2.3/json),
[torch](https://pypi.org/pypi/torch/2.14.1/json),
[torchaudio](https://pypi.org/pypi/torchaudio/2.11.0/json),
[ONNX Runtime](https://pypi.org/pypi/onnxruntime/1.30.0/json),
[PyAV](https://pypi.org/pypi/av/19.0.1/json),
[tokenizers](https://pypi.org/pypi/tokenizers/0.23.2/json),
[NumPy](https://pypi.org/pypi/numpy/2.5.3/json),
[SoundFile](https://pypi.org/pypi/soundfile/0.14.0/json),
[PySide6](https://pypi.org/pypi/PySide6/6.12.0/json),
[SQLAlchemy](https://pypi.org/pypi/SQLAlchemy/2.1.4/json),
[Alembic](https://pypi.org/pypi/alembic/1.20.0/json),
[Pydantic Settings](https://pypi.org/pypi/pydantic-settings/2.15.0/json),
[psycopg-binary](https://pypi.org/pypi/psycopg-binary/3.3.6/json),
[PyInstaller](https://pypi.org/pypi/pyinstaller/6.22.3/json),
[uv](https://pypi.org/pypi/uv/0.12.23/json),
[Ruff](https://pypi.org/pypi/ruff/0.16.10/json),
[pytest](https://pypi.org/pypi/pytest/9.1.1/json),
[Hatchling](https://pypi.org/pypi/hatchling/1.32.4/json).

Наличие отдельного wheel Pydantic Settings не проверяет его pydantic-core;
PySide6 требует соответствующих компонентов и DLL; SoundFile — CFFI/libsndfile.
Полное транзитивное runtime-окружение разрешается и испытывается на своих шагах,
не выдаётся за проверенное на основании этой таблицы.

## Особые риски и план проверки

| Риск | Что установлено сейчас | Проверка до использования |
| --- | --- | --- |
| faster-whisper и бинарные зависимости | 1.2.1 требует ctranslate2 >=4,<5, tokenizers >=0.13,<1, onnxruntime >=1.14,<2 и av >=11; снимок удовлетворяет этим прямым ограничениям. | В 06 разрешить весь граф, зафиксировать версии, проверить импорты и 30–60 s русского аудио на RTX 4060 Ti; потребить генератор сегментов. |
| CUDA/cuDNN/CTranslate2 DLL | [faster-whisper](https://github.com/SYSTRAN/faster-whisper#gpu) указывает CUDA 12/cuDNN 9. [Документация CT2](https://opennmt.net/CTranslate2/installation.html) ещё упоминает cuDNN 8; [Windows build v4.8.2](https://github.com/OpenNMT/CTranslate2/blob/v4.8.2/python/tools/prepare_build_environment_windows.sh) использует cuDNN 9. Есть расхождение источников. | В 06 ориентироваться на конкретный релиз/бинарник, проверить драйвер, VC++ Runtime, DLL search path, CUDA 12/cuDNN 9 и реальный FP16; записать версии и ошибки. На 00 ничего не устанавливать. |
| Silero VAD и PyTorch | silero-vad 6.2.3 требует torch >=1.12 даже в extras ONNX. Audio/all extras ограничивают torchaudio <2.10; «последняя версия каждого пакета» не образует автоматически совместимый набор. | В 07 выбрать JIT/ONNX и минимальные extras, проверить импорт, 16 kHz PCM, границы/паузы и offline; зафиксировать проверенный набор. Использование собственного FFmpeg I/O вместо helper read_audio — кандидат, не реализованное решение. |
| Пара torch/torchaudio | Отдельно проверены [torch 2.9.1](https://pypi.org/pypi/torch/2.9.1/json) и [torchaudio 2.9.1](https://pypi.org/pypi/torchaudio/2.9.1/json): оба имеют cp314 Windows x64 wheels; torchaudio требует torch==2.9.1 и проходит <2.10. Это кандидат при необходимости audio extras. | В 07 проверить актуальность API и выбранную CPU/CUDA сборку, не смешивать произвольные версии. Python остаётся 3.14. |
| ONNX Runtime | CPU wheel доступен. onnxruntime-gpu не требуется для этой проверки и не проверен; пакеты CPU/GPU нельзя считать взаимозаменяемыми. | В 07 проверить загрузку конкретной Silero ONNX-модели, CPUExecutionProvider и результаты; GPU provider проверять отдельно только при принятом решении. |
| Влияние VAD на GPU-память | Использование torch для VAD не означает обязательную загрузку VAD в CUDA; владение GPU у одного worker. | В 06–07 выбрать размещение VAD, измерить RSS/VRAM, исключить дублирование модели и проверить fallback FR-05/NFR-02. |
| Упаковка и GUI | Теги wheels подтверждены, приложение ещё не реализовано. | В 12–13 GUI и воспроизведение; в 16 PyInstaller/VC++/Qt DLL, чистый Windows-профиль и offline smoke. |

Работа ML/CUDA, импорт runtime-пакетов и аппаратные тесты: **NOT RUN**.
По запросу владельца библиотеки и модели не установлены. Это технический долг
для 06–07 и 16, а не причина менять Python и не аппаратный gate шага 00.


## Проверка PostgreSQL в шаге 03

SQLAlchemy 2.1.4, Alembic 1.20.0, psycopg и psycopg-binary 3.3.6 установлены
в существующую .venv CPython 3.14.4 Windows x64. Импорты, реальные запросы,
транзакции, constraints и миграционный цикл проверены с PostgreSQL 18.3.
Это подтверждает только выбранную persistence цепочку, не ML/CUDA/GUI.
Команды и результаты — [progress.md](progress.md).
