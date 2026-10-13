# Тесты

Тесты находятся в корневом tests/, вне runtime-пакета.

- test_repository_audit.py: документы, полный перенос FR/NFR, Python 3.14,
  матрица шагов, внутренние ссылки, Git-исключения и сохранность синтетических данных.
- test_settings.py: Windows defaults, env/.env и приоритет, blank defaults,
  UTF-8/BOM, секреты, некорректные пути/настройки/файлы и Windows escape-регрессия.
- test_doctor.py: mock subprocess/env, все статусы/отказы инструментов, DSN,
  dry-run/явное создание каталогов, права, модель и реальные subprocess/CLI.
- test_cli.py: unit-проверки main и реальные subprocess-проверки установленного
  пакета, python -m, console script и src/main.py. Проверяются версия, справка,
  запуск без аргументов, неизвестные команды/запрет сокращений, кириллица и
  пробелы в пути, отсутствие тяжёлых импортов и изменения пользовательских файлов.

После установки пакета через uv sync, из корня проекта:

```powershell
.\.venv\Scripts\Activate.ps1
uv sync --locked
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

Тесты используют установленный local_transcriber; src не добавляется в sys.path.
Изолированный Python запускается с -I -X utf8: -I игнорирует переменные PYTHON*,
поэтому кодировка вывода задаётся явно для чтения русской справки на Windows.

Негативные сценарии работают только с синтетическими файлами в tmp_path.
CLI и unit-тесты doctor не требуют GPU, моделей, FFmpeg или PostgreSQL; интеграция launcher
проверяется настоящим дочерним процессом. Маркеры integration/gpu предусмотрены
для последующих адаптеров и проверок оборудования. Такие испытания не подменяются CLI.

doctor проверяется также на фактической Windows-машине: отсутствующие
необязательные зависимости — ожидаемая диагностика. Synthetic fixtures модели
проверяют только инспекцию файлов, не готовность STT.
Проверка установки wheel в чистое окружение выполняется отдельно от pytest;
фактические команды и результаты находятся в [progress](../docs/progress.md).
При отказе доступа к общему Windows Temp используйте новый уникальный каталог
в игнорируемом tmp/ и PYTEST_DEBUG_TEMPROOT; пример — в [README](../README.md).


## PostgreSQL, шаг 03

- [test_database_unit.py](test_database_unit.py): Domain transitions, AppSettings
  URL/test guards, PG DDL/offline Alembic, валидация ms. Offline SQL не является
  интеграционной проверкой.
- [test_postgresql.py](test_postgresql.py): только настоящая PostgreSQL; отдельная
  test DB и случайная схема на тест. Без доступа — SKIP; SQLite/mock не используются.
  Подробная настройка и безопасные команды — [README](../README.md).

Для уже установленного PostgreSQL на Windows можно проверить всё автономно:

```powershell
uv run python scripts/check_postgresql.py --postgres-bin 'C:/Program Files/PostgreSQL/18/bin'
```

Runner не устанавливает сервер и не меняет службу: создаёт собственный кластер
в игнорируемом tmp/, случайный SCRAM пароль и loopback порт, только test DB;
передаёт параметры через окружение AppSettings, выполняет pytest и миграционный
цикл, останавливает свой процесс в finally. Bootstrap pwfile удаляется; каталог
проверки/логи остаются в tmp/. PYTEST_REQUIRE_POSTGRES=1 превращает отсутствие
реального подключения в FAIL. Обычный pytest такой сервер автоматически не запускает.

Для уже настроенной отдельной test DB:
```powershell
$env:PYTEST_REQUIRE_POSTGRES = '1'
uv run pytest tests/test_postgresql.py -q
```
Для обычного запуска с честными SKIP удалите только эту тестовую переменную.

## Медиаинспекция, шаг 04

`test_media.py` использует сохранённые ffprobe JSON и unit doubles процесса:
mixed streams, реальные индексы, Unicode, no audio, invalid JSON, output limit,
timeout/kill и безопасные ошибки. Это не выдаётся за реальный FFmpeg.

Реальная проверка находится в `test_postgresql.py`: FFmpeg создаёт короткий MKV
с video stream 0 и audio streams 1/2 разных sample rate, ffprobe инспектирует,
затем данные дважды импортируются в настоящую PostgreSQL. Укажите пути через
`LOCAL_TRANSCRIBER_FFMPEG_PATH` и `LOCAL_TRANSCRIBER_FFPROBE_PATH`; при строгом
runner отсутствие инструмента означает FAIL, в обычном pytest — явный SKIP.

## Потоковое декодирование, шаг 05

`test_ffmpeg_decoder.py` сочетает unit doubles и настоящий FFmpeg. Unit-сценарии
проверяют nonzero exit, усечённый PCM sample, inactivity timeout, отсутствующий
источник, границы диапазона и вычисляемый bounded-buffer limit. Integration
создаёт audio-only MKV: 440 Hz с PTS 0 и 880 Hz с PTS 1000 ms, читает дорожки
раздельно и проверяет 16 kHz mono, длительность и абсолютные отметки. Отдельный
сценарий отменяет чтение после первого блока и проверяет завершение child process.

Для строгого запуска задайте `PYTEST_REQUIRE_FFMPEG=1` и
`LOCAL_TRANSCRIBER_FFMPEG_PATH`. `scripts/check_postgresql.py` автоматически
использует portable build из игнорируемого `tmp/step04-tools`, если он существует,
либо системный FFmpeg, и запрещает SKIP этой интеграции.

## STT, шаг 06

`test_transcription.py` не имитирует готовое распознавание: fake model проверяет
только контракт adapter, полное потребление lazy generator, относительные ms,
однократную загрузку, offline gate и управляемый CUDA fallback. Реальный runtime
проверяет `test_transcription_runtime.py` при `PYTEST_REQUIRE_CUDA=1`: импорты,
закреплённые версии, CUDA device и доступность float16/int8_float16.

Аппаратный smoke выполнен отдельно от автоматического suite на локальной
large-v3-turbo и 45-секундном фрагменте пользовательского видео: float16,
beam 5, два сегмента с относительными ms. Модель лежит в пользовательском
LocalAppData, исходник/PCM/распознанный текст не коммитятся. Повтор требует тех же
локальных данных и поэтому не входит в обычный pytest.

## VAD, шаг 07

`test_segmentation.py`: 10 целевых сценариев (8 unit и 2 integration).
Синтетические scores проверяют только state machine, синус не считается речью.
Реальная Silero ONNX проверяется на тишине и приватном русском видео fixture.
Для видео задайте LOCAL_TRANSCRIBER_VAD_FIXTURE (путь),
LOCAL_TRANSCRIBER_FFMPEG_PATH; fixture использует stream_index=1 и 600–645 s.
Без fixture соответствующий тест явно SKIP; ONNX-silence всегда выполняется.
Для Windows Temp permission error используйте новый уникальный каталог tmp/
и PYTEST_DEBUG_TEMPROOT. Модель/видео/текст в Git не добавляются.

## Pipeline, шаг 08

`test_pipeline.py` — небольшой suite на test doubles: 25-min logical stream,
crash после двух chunks, BaseException, resume/repeat, manifest mismatch,
time/text dedup с настоящим повтором, explicit CLI routing и decode range limit.
Это проверки оркестрации, не имитация успешного CUDA inference.
`test_postgresql.py::test_pipeline_checkpoints_and_resume` проверяет реальные
checkpoints на отдельной test DB. `test_pipeline_real_hour` — opt-in gate с
LOCAL_TRANSCRIBER_PIPELINE_SMOKE (локальный приватный файл >=60 min, >1 GB,
stream index 1), установленными offline моделью/FFmpeg и отдельной PostgreSQL.

Изолированный runner теперь поддерживает повторяемый --pytest-target:

```powershell
uv run python scripts/check_postgresql.py --pytest-target tests/test_pipeline.py --pytest-target tests/test_postgresql.py::test_pipeline_checkpoints_and_resume
```

Без --pytest-target сохранён прежний полный режим. В runner зафиксирован UTF-8
вывод, чтобы Windows cp1251 не прерывал отчёт с Unicode из pytest.
Секреты и пользовательский транскрипт не выводятся. Temp cluster принадлежит
runner, пользовательская БД/служба не меняются.

## Worker, шаг 09

`test_worker.py` — 9 focused spawn-сценариев: FIFO, deferred pause/resume,
current/queued cancel, worker crash/restart, graceful shutdown, IPC errors и
реальный FFmpeg child cleanup Windows Job Object. Fake inference явно является
test double; gates синхронизируются событиями/condition, без flaky sleeps.
FSM проверяется существующей test_job_transitions (64 параметризованные пары).

`test_postgresql.py::test_worker_pause_cancel_and_crash_preserve_checkpoints`
проверяет сохранность первого checkpoint и PAUSED/INTERRUPTED/CANCELLED в
настоящей отдельной DB. Opt-in `test_real_gpu_worker_short_smoke` требует
LOCAL_TRANSCRIBER_WORKER_SMOKE (локальное видео со stream 1), offline модель,
FFmpeg и test PostgreSQL; обрабатывает первые 45 s без публикации текста.
Следует повторять через check_postgresql.py --pytest-target для нужного набора;
полный предыдущий suite для каждого изменения не требуется.

## Текст, шаг 10

`test_text.py` — целевые unit cases: byte-for-byte исходные строки/RAW, повторы,
стоп-слова, quotes/numbers/English/PostgreSQL, пустые сегменты, labels/paragraphs,
неоднозначные/длинные/выключенные варианты, parser и локальные UTF-8 file errors.
`test_postgresql.py::test_text_*`, `test_term_crud_import_updates_and_atomic_rollback`
и `test_empty_completed_transcript_versions` используют реальную отдельную DB:
immutable RAW, append-only READABLE/MANUAL, конкуренция, rollback, пустой результат,
CRUD/upsert словаря и CLI с CRLF ручным файлом. Связь CLI с test schema подменяется,
сама PostgreSQL и SQL-операции — реальные. Тесты вызываются выборочно через
`scripts/check_postgresql.py --pytest-target ...`; полные GPU/stress gates не нужны
для изменения чистых правил текста и выполняются на своих этапах.
