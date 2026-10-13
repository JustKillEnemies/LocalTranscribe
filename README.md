# Transcribation

Локальное desktop-приложение для преобразования длительных OBS-записей и
аудиофайлов в структурированный, читаемый русский текст.

Целевая среда: Windows 11, NVIDIA RTX 4060 Ti 8 GB и локальная PostgreSQL.
Обработка должна выполняться на компьютере пользователя без платных API и
облачной передачи медиа или транскриптов.

## Текущее состояние

Пакет поддерживает запуск, справку, версию, doctor, `inspect` и `import` медиа.
Настройки читаются из локального окружения или пользовательского .env. GUI пока не реализован; доступны четыре формата экспорта; GPU worker выделен в отдельный spawn-процесс. PostgreSQL-схема, Alembic и
транзакционные репозитории реализованы отдельно; подключения берут AppSettings.

Инспекция поддерживает MKV/MP4/MOV/WAV/MP3/M4A/FLAC/WebM, запускает локальный
ffprobe и выводит JSON с длительностью, размером, контейнером и всеми аудиопотоками.
Импорт сохраняет эти метаданные в PostgreSQL идемпотентно по fingerprint.
Выбранная реальным `stream_index` дорожка декодируется локальным FFmpeg в
ограниченные блоки PCM s16le mono 16 kHz. Декодер поддерживает абсолютные
integer-ms интервалы до 15 минут, стартовый PTS, отмену и тайм-аут; полного WAV
или исходного файла в памяти нет. GUI ещё не реализован.
STT-контракт и offline-first адаптер faster-whisper реализованы: модель лениво
загружается один раз, по умолчанию `large-v3-turbo`, `ru`, beam 5, float16 с
явным fallback `int8_float16`. Автоматическая загрузка модели выключена.
Аппаратный smoke подтверждён на локальной `large-v3-turbo`: 45 секунд русского
аудио распознаны на RTX 4060 Ti в `float16`.
Единственный источник статуса этапов и результатов проверок —
[docs/progress.md](docs/progress.md).
[Исходное ТЗ](docs/ORIGINAL_TZ.md) сохранено и синхронизировано с
[требованиями](docs/requirements.md); [матрица](docs/requirements_traceability.md)
связывает требования, этапы и артефакты.

## Структура

```text
Transcribation/
├── AGENTS.md
├── README.md
├── .gitignore
├── .env.example
├── .python-version
├── pyproject.toml
├── uv.lock
├── alembic.ini
├── migrations/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/{0001_initial,0002_media_import,0003_audio_timeline}.py
├── scripts/check_postgresql.py
├── docs/
│   ├── CODEX_PROMPTS_V2.md
│   ├── LocalTranscribe_Codex_Prompts_V2.md
│   ├── ORIGINAL_TZ.md
│   ├── requirements.md
│   ├── requirements_traceability.md
│   ├── implementation_plan.md
│   ├── architecture.md
│   ├── python314_compatibility.md
│   ├── progress.md
│   └── decisions.md
├── src/
│   ├── main.py
│   └── local_transcriber/
│       ├── __init__.py
│       ├── __main__.py
│       ├── domain/{audio,jobs,media}.py
│       ├── application/{media_decode,media_import,transcription}.py
│       └── infrastructure/
│           ├── settings.py
│           ├── doctor.py
│           ├── media.py
│           ├── ffmpeg_decoder.py
│           ├── faster_whisper_engine.py
│           └── database/{models,session,repositories}.py
└── tests/
    ├── README.md
    ├── test_repository_audit.py
    ├── test_cli.py
    ├── test_settings.py
    ├── test_doctor.py
    ├── test_database_unit.py
    ├── test_ffmpeg_decoder.py
    ├── test_transcription.py
    ├── test_transcription_runtime.py
    └── test_postgresql.py
```

Git-корень — Transcribation/. Каталог .git ранее перенесён из src/ с разрешения
пользователя, история и remote сохранены. Исходный src/main.py сохранён и
делегирует единой функции local_transcriber.__main__:main.
Папка проекта — Transcribation, GitHub — LocalTranscribe, пакет — local_transcriber.

## Документация

- [Требования](docs/requirements.md): полный объём и уточнения владельца.
- [Архитектура](docs/architecture.md): слои, модули, процессы и запуск.
- [Состояние](docs/progress.md): выполненное, проверки и следующий этап.
- [Решения](docs/decisions.md): принятые решения и обоснование.
- [Правила агента](AGENTS.md): постоянные ограничения разработки.
- [Промпты V2](docs/CODEX_PROMPTS_V2.md): указатель на пользовательский исходник.
- [План 00–17](docs/implementation_plan.md): порядок и зависимости.

## Среда разработки и запуск

Используется обычный CPython 3.14 x64 с GIL, >=3.14,<3.15.
Существующая .venv сохраняется; глобальная установка Python не изменяется.
Hatchling собирает пакет, uv.lock закрепляет версии dev-инструментов.
Runtime-зависимости: Pydantic/Settings/dotenv, SQLAlchemy, Alembic, psycopg[binary]
и faster-whisper 1.2.1 с CUDA 12 cuBLAS/cuDNN runtime и закреплённым графом;
версии закреплены. Модель, CUDA toolkit и GUI-библиотеки автоматически не устанавливаются.
PostgreSQL сервер не устанавливается Python-зависимостями.
[Совместимость ML](docs/python314_compatibility.md) проверяется на своих этапах.

PowerShell, из корня проекта:

```powershell
.\.venv\Scripts\Activate.ps1
python --version
uv sync --locked
uv run python -m local_transcriber --version
uv run python -m local_transcriber --help
uv run python -m local_transcriber
uv run local-transcriber --version
uv run python src/main.py --help
uv run python -m local_transcriber doctor
uv run python -m local_transcriber doctor --dry-run
uv run python -m local_transcriber inspect 'C:/Recordings/OBS запись.mkv'
uv run python -m local_transcriber import 'C:/Recordings/OBS запись.mkv'
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
git diff --check
```

uv sync устанавливает сам пакет и dev-группу в .venv. Режим --only-dev
предназначен только для инструментов: в нём пакет и console script не устанавливаются.
Без активации используйте .venv/Scripts/uv.exe вместо uv.
Если .venv ещё нет, создайте её установленным Python 3.14 и установите uv локально:

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install uv==0.12.23
.\.venv\Scripts\uv.exe sync --locked --python .\.venv\Scripts\python.exe
```

Все способы запуска обращаются к одной функции main. --version выводит версию
установленного пакета; --help и запуск без аргументов показывают справку и дают
код 0. Неизвестные аргументы дают код 2 и диагностику в stderr.
Сокращения вроде --vers не поддерживаются. Информационные команды не читают .env.
doctor читает настройки; модели и worker не загружаются.

## Проверка установки в чистое окружение

Для воспроизведения проверки wheel создайте отдельное уникальное окружение;
основная .venv сохраняется. Пример запуска из пути с кириллицей и пробелами:

```powershell
$step01CheckRoot = Join-Path (Get-Location).Path ('tmp/Проверка пакета ' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $step01CheckRoot | Out-Null
uv build --wheel --out-dir (Join-Path $step01CheckRoot 'wheel')
uv venv --python .\.venv\Scripts\python.exe (Join-Path $step01CheckRoot 'venv')
$step01CheckPython = Join-Path $step01CheckRoot 'venv/Scripts/python.exe'
$step01Wheel = (Get-ChildItem -LiteralPath (Join-Path $step01CheckRoot 'wheel') -Filter '*.whl').FullName
uv pip install --python $step01CheckPython --no-deps $step01Wheel
Push-Location -LiteralPath $step01CheckRoot
try {
    & $step01CheckPython -I -X utf8 -m local_transcriber --version
    & $step01CheckPython -I -X utf8 -m local_transcriber --help
} finally {
    Pop-Location
}
```

Это инструкция для повторения; фактический отчёт — в progress.md.
Проверка пакета не означает готовность полного desktop-приложения.

## Локальные данные

Git исключает media/, recordings/, models/, data/, transcripts/, exports/,
logs/, tmp/, backups/ и dumps/. Секреты хранятся локально, никогда в коде.
.env.example содержит безопасные примеры и пустой пароль.
Настройки и пользовательские пути описаны ниже.
SQL-миграции можно хранить в Git; SQL-дампы помещайте в backups/ или dumps/.
Медиа и транскрипты не отправляются во внешние сервисы.

Если pytest сообщает PermissionError для общего Windows Temp, создайте новый
уникальный каталог, сохраняя чужие временные данные:

```powershell
$pytestTempRoot = Join-Path (Get-Location).Path ('tmp/pytest-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $pytestTempRoot | Out-Null
$env:PYTEST_DEBUG_TEMPROOT = $pytestTempRoot
uv run pytest -q
```

Для ограниченной среды uv можно задать $env:UV_CACHE_DIR на .cache/uv в корне
проекта и $env:UV_PYTHON_DOWNLOADS='never'. Offline-проверка:
uv --cache-dir .cache/uv lock --check --offline.
Это настройки текущего процесса; глобальный Python и ACL каталогов не меняются.

## Настройки и doctor

Настройки воспроизводимы: environment > выбранный .env > defaults.
Без --env-file читается только %LOCALAPPDATA%/LocalTranscriber/.env;
при отсутствии LOCALAPPDATA — APPDATA, затем home/AppData/Local.
.env из текущего рабочего каталога автоматически не читается.

Default data_dir — тот же пользовательский каталог; cache, models, logs, temp
находятся внутри него. Переопределения каталогов должны быть абсолютными.
Default model_path: models_dir/model_name. Загрузка настроек не создаёт каталогов.
Для .env используйте UTF-8 (BOM поддерживается) и Windows пути с / либо
одинарными кавычками: 'C:\Users\USER\Рабочие данные'.
В двойных кавычках обратные слеши обрабатываются как escapes; пути с
управляющими символами отклоняются. Синтаксически повреждённый .env не принимается.

```powershell
uv run python -m local_transcriber doctor --env-file .env.example
uv run python -m local_transcriber doctor --env-file .env.example --dry-run
# Явно создать только настроенные data/cache/models/logs/temp:
uv run python -m local_transcriber doctor --create-dirs
```

doctor по умолчанию выполняет проверки без создания папок/логов и загрузок.
--dry-run не запускает внешние инструменты, не импортирует CUDA и не создаёт
каталоги; локальные пути и файлы модели проверяются чтением.
--create-dirs несовместим с --dry-run. Файлы не удаляются и не перезаписываются.

.env.example перечисляет все переменные LOCAL_TRANSCRIBER_:
каталоги, исполняемые файлы, timeout 1–30 s, локальную БД, device cuda/cpu,
gpu_index, model_name, model_path и compute_type.
Имена исполняемых файлов ищутся в PATH; полный путь передаётся одним аргументом
без shell. Windows .bat/.cmd/.ps1 для инструментов отклоняются.
Пароль и DSN скрыты в repr/выводе; ошибки конфигурации не печатают значения.
Не добавляйте реальные credentials в примеры или Git.

| Статус | Значение |
| --- | --- |
| OK | Конкретная проверка успешна, в сообщении указана её граница. |
| MISSING | Инструмент, GPU или локальные файлы отсутствуют. |
| ERROR | Ошибка конфигурации, ответ инструмента, права или timeout. |
| SKIP | Проверка явно отключена dry-run/CPU. |

doctor exit 0 означает, что диагностический отчёт получен, даже с MISSING/ERROR;
неверная конфигурация даёт exit 2 без traceback. --help/--version не читают .env.

PostgreSQL: укажите pg_isready из установленного PostgreSQL/bin.
Проверяется только готовность локального сервера принимать подключения.
Doctor не проверяет пароль, наличие конкретной БД или SQL-схему.
Эти проверки выполняются миграциями и интеграционными тестами шага 03.
Опциональный DSN разрешает postgres/postgresql, один loopback host, корректный
порт и имя БД; query/fragment и внешние host отклоняются. DSN не передаётся инструменту.
Отдельные HOST/PORT применяются, если DSN пуст.

NVIDIA проверяется через nvidia-smi. Это не подтверждает CUDA/cuDNN.
При установленном CTranslate2 get_cuda_device_count выполняется в дочернем Python
с тайм-аутом. ML-библиотеки автоматически не устанавливаются.
Модель: только локальные непустые model.bin, config.json и tokenizer.json;
JSON проверяется, веса не читаются. OK здесь не подтверждает качество модели
или inference. Сетевых загрузок doctor не выполняет.


## PostgreSQL и миграции

Схема §7 ТЗ: media_files, audio_streams, transcription_jobs, processing_chunks,
transcript_segments, transcript_versions, custom_terms. Метаданные/текст хранятся
в БД; медиа/PCM остаются файлами. Миграции никогда не запускаются при import,
--help/--version или doctor. Ни SQLite, ни mock не заменяют PostgreSQL.

AppSettings шага 02 — единственная конфигурация. Задайте USER/PASSWORD/HOST/PORT/
DB/TEST_DB в пользовательском %LOCALAPPDATA%/LocalTranscriber/.env либо окружении.
DSN, если задан, имеет приоритет над отдельными полями; его рабочая database
заменяется на TEST_DB только в test-режиме. Пароль/DSN не передавайте в аргументах
команд или Git. [Пример](.env.example) не содержит credentials.
Отдельная test DB должна существовать, отличаться от рабочей и иметь имя *_test
или test_*; postgres/template* запрещены. Роль должна иметь CONNECT и CREATE
на test DB для собственных схем. Приложение не создаёт базы/роли/службы автоматически.

На Windows с уже установленными PostgreSQL binaries безопасный автономный прогон:

```powershell
uv run python scripts/check_postgresql.py --postgres-bin 'C:/Program Files/PostgreSQL/18/bin'
```

Создаётся отдельный временный кластер в tmp/ с SCRAM/случайным паролем, loopback
и свободным портом, только local_transcriber_test. Рабочая служба/БД не используются.
Настройки передаются AppSettings через окружение только дочерних команд;
runner запускает все тесты, реальный migration cycle и Ruff, затем останавливает
собственный процесс в finally. Его временный каталог и логи остаются игнорируемыми;
pwfile удаляется. Установка PostgreSQL или управление системной службой не выполняются.

Для вашей уже настроенной отдельной test DB, из корня проекта:

```powershell
uv run pytest tests/test_database_unit.py -q
$env:PYTEST_REQUIRE_POSTGRES = '1'
uv run pytest tests/test_postgresql.py -q
uv run alembic -x test=true upgrade head
uv run alembic -x test=true upgrade head
uv run alembic -x test=true check
# Только в выделенной disposable test DB: удаляет таблицы приложения!
uv run alembic -x test=true downgrade base
uv run alembic -x test=true upgrade head
```

pytest создаёт и очищает только свои lt_test_<uuid> схемы. CLI Alembic работает
с public выбранной test DB: команды downgrade допустимы только если эта база
выделена для таких испытаний. Test mode дополнительно проверяет current_database.
Без доступа обычный pytest явно SKIP; строгий режим и runner дают FAIL.

Для намеренного развёртывания схемы приложения после настройки рабочей базы:

```powershell
uv run alembic upgrade head
uv run alembic current
# При отдельном .env (полный локальный путь, без секретов в аргументах):
uv run alembic -x env_file='C:/Users/USER/AppData/Local/LocalTranscriber/.env' upgrade head
```

Рабочие миграции выполняются только вручную; downgrade рабочей БД запрещён.
Фактические проверки и ограничения машины перечислены в docs/progress.md.

## Речевая сегментация

Реализован streaming SpeechSegmenter: локальный Silero ONNX на CPU, 16 kHz,
порог 0.5, пауза 500 ms и padding 200 ms. Речь выдаётся с исходными таймкодами,
короткие ответы сохраняются, непрерывная речь делится на 30-секундные core
intervals с контекстом. Настройка LOCAL_TRANSCRIBER_VAD_ENABLED=false включает
bypass. Модель уже входит в faster-whisper; дополнительных загрузок нет.
Конвейер и PostgreSQL-чекпойнты реализованы в шаге 08.

## Транскрибация и возобновление

После настройки локальной PostgreSQL, миграций и локальной модели:

```powershell
uv run local-transcriber transcribe 'C:/Users/USER/Videos/recording.mkv' --stream-index 1
# Несколько независимых дорожек: --stream-index 1 --stream-index 2
# Возобновить UUID из результата/ошибки CLI с теми же параметрами:
uv run local-transcriber transcribe 'C:/Users/USER/Videos/recording.mkv' --stream-index 1 --resume JOB_UUID
```

CLI последовательно обрабатывает logical chunks по 5 минут с контекстом по 1000 ms,
запускает VAD и offline STT с word timestamps. Сегменты в исходных ms и COMPLETED
чекпойнт сохраняются одной PostgreSQL-транзакцией. `--chunk-ms` задаёт 1–15 минут,
`--overlap-ms` — 200–5000 ms (не меньше VAD pause+padding); `--end-ms` ограничивает
обработку начальным диапазоном для локальной проверки. Общая длина файла не ограничена.

`--resume` пропускает готовые chunks и отклоняет изменения fingerprint, выбранных
дорожек, модели, VAD и параметров участков. Завершённый job возвращается без повторного
STT. Запуск без --resume создаёт отдельное задание. Сохранённые RAW не перезаписываются.
CLI выводит JSON progress/job_id без транскрипта; ошибки с job_id записываются в
пользовательский logs/pipeline-errors.log. Исходник и PCM в PostgreSQL не хранятся.
Inference выполняется в отдельном worker; CLI получает события и сохраняет результаты в основном процессе.

## Управление worker

Один Windows `spawn`-worker обслуживает FIFO-очередь. API WorkerManager.submit /
command / poll позволяет будущему GUI получать события без ожидания inference
или SQL на UI-потоке. Модель повторно используется для одинаковой конфигурации;
смена модели сначала освобождает прежнюю. SQLAlchemy Session/Engine не передаются
в worker, аудио остаётся внутри worker.

```powershell
uv run local-transcriber transcribe 'C:/Users/USER/Videos/recording.mkv' --stream-index 1 --interactive
```

В интерактивном режиме вводите `pause`, `resume`, `cancel`. Pause сначала выдаёт
PAUSE_DEFERRED, затем JOB_PAUSED после сохранения текущего logical chunk.
Cancel прекращает FFmpeg, сохраняет прежние checkpoints и отменяет незавершённый
chunk. Текущий native STT-вызов может закончиться до подтверждения cancel; его
результат после принятия отмены не записывается. Ctrl+C также запрашивает cancel.

Закрытие manager выполняет SHUTDOWN и сохраняет INTERRUPTED для незавершённого
job. При аварии supervisor ставит INTERRUPTED и позволяет restart + --resume.
Windows Job Object гарантирует cleanup собственных FFmpeg children при убийстве
worker. Рабочая БД/службы и чужие процессы не затрагиваются. restart/shutdown —
операции завершения с тайм-аутом; будущий GUI вызывает их вне Qt event loop.

## Текст и словарь

После завершения `transcribe` основной процесс сохраняет RAW и новую READABLE,
сообщая `TEXT_COMPLETED`. Ошибка обработки текста не удаляет результаты STT:
повторить этот этап можно командой `text readable`, без повторного распознавания.
Версии и словарь используют существующие AppSettings/PostgreSQL; миграции не менялись.

```powershell
uv run python -m local_transcriber text raw JOB_UUID
uv run python -m local_transcriber text readable JOB_UUID
uv run python -m local_transcriber text readable JOB_UUID --paragraph-gap-ms 3000 --no-terms
uv run python -m local_transcriber text versions JOB_UUID
uv run python -m local_transcriber text show JOB_UUID --version VERSION_UUID
uv run python -m local_transcriber text manual JOB_UUID --base VERSION_UUID --file 'C:/LocalData/Ручная версия.txt'
uv run python -m local_transcriber terms add PostgreSQL --variant postgres --variant постгрес
uv run python -m local_transcriber terms list
uv run python -m local_transcriber terms update TERM_UUID PostgreSQL --variant постгрес --disabled
uv run python -m local_transcriber terms delete TERM_UUID
uv run python -m local_transcriber terms import 'C:/LocalData/Словарь.txt'
```

`JOB_UUID`, `VERSION_UUID`, `TERM_UUID` заменяются реальными UUID. Каждая leaf-команда
поддерживает `--env-file`. Вывод text/terms — локальный JSON; запись файлов описана в разделе экспорта ниже.
`text versions` возвращает номера/типы/метаданные, `text show` — выбранный текст.
`terms update` заменяет варианты целиком; без `--disabled` термин включается.

RAW собирается по номеру дорожки/времени, сохраняет все символы сегментов,
добавляя только необходимые разделительные пробелы и пустую строку между дорожками.
Оригинальные сегменты и времена остаются доступными отдельно. RAW-версия создаётся
для COMPLETED; у прерванного задания доступны уже сохранённые исходные checkpoints.
Повтор RAW возвращает ту же версию. Каждый READABLE/MANUAL добавляется отдельно:
новый READABLE не заменяет MANUAL, ручная версия может основываться на любой версии
того же задания. Редактор GUI появится на шаге 13.

READABLE использует `conservative-text` v1: нормализует пробелы, убирает пробел
перед существующей пунктуацией, кроме цифровых границ, добавляет конечную точку
при отсутствии знака. Абзац начинается при смене дорожки/подписи, паузе >=2000 ms
или достижении 800 символов на границе сегмента. Подписи берутся из данных;
идентификация говорящих не выполняется. Повторы, стоп-слова, цифры, цитаты и регистр
сохраняются; смысловые запятые/перефразирование/LLM и удаление слов не используются.
`--no-terminal-period` отключает добавление точки.

Словарь: UTF-8 с необязательным BOM, по одной строке на термин:
`canonical<TAB>variant|variant`; строка только с canonical также допустима.
Пустые строки и комментарии `#` игнорируются. Например `PostgreSQL`, TAB,
`postgres|постгрес`. Импорт ограничен 4 MiB/10000 строками, ручной текст — 16 MiB;
ошибка формата/кодировки/SQL откатывает импорт целиком. Совпадающий canonical
обновляет варианты и enabled, остальные записи сохраняются.
Замены работают по границам слов, длинные варианты первыми, за один проход;
вариант нескольких включённых терминов оставляется без изменения.
Метаданные READABLE содержат правила, версию обработчика, снимок словаря и ссылку
на RAW; применение словаря как STT prompt не включалось в этом шаге.

## Экспорт из сохранённых результатов

Экспорт работает после перезапуска, без GPU, модели, FFmpeg и исходного медиафайла.
Требуется только доступ к локальной PostgreSQL и уже сохранённый RAW; экспорт не
создаёт/не изменяет версии и не запускает STT. Если RAW ещё не финализирован,
сначала выполните `text raw`/`text readable` для завершённого задания.

```powershell
uv run python -m local_transcriber export JOB_UUID 'C:/LocalData/Результат.txt'
uv run python -m local_transcriber export JOB_UUID 'C:/LocalData/Результат.txt' --timestamps --roles
uv run python -m local_transcriber export JOB_UUID 'C:/LocalData/Субтитры.srt'
uv run python -m local_transcriber export JOB_UUID 'C:/LocalData/Результат.json'
uv run python -m local_transcriber export JOB_UUID 'C:/LocalData/Результат.md'
uv run python -m local_transcriber export JOB_UUID 'C:/LocalData/Текст.txt' --version VERSION_UUID --overwrite
```

`--format txt/srt/json/md` позволяет явно выбрать формат независимо от расширения;
обычно он определяется расширением, включая верхний регистр. `--env-file` работает
как у других команд. Родительский каталог должен существовать. Для TXT/Markdown/JSON
без `--version` выбирается последняя MANUAL, затем READABLE, затем RAW; SRT по
умолчанию использует RAW. Конкретный UUID можно взять из `text versions`.

TXT и Markdown сохраняют выбранный текст, опционально добавляя роли/таймкоды.
У READABLE оформления ролей/дорожек берутся из структурной привязки, поэтому
без `--roles` эти подписи опускаются. Ручной текст без внешних аннотаций сохраняется
точно, включая CRLF; к нему нельзя добавлять выдуманные времена или speaker labels.
Для MANUAL доступны обычные TXT/Markdown и JSON; SRT/таймкоды/роли требуют RAW
или READABLE с привязкой к исходным сегментам. `--timestamps` касается TXT/Markdown;
SRT/JSON всегда содержат время, `--roles` добавляет подписи в TXT/Markdown/SRT.

SRT: последовательная нумерация с 1, `HH:MM:SS,mmm` (часы не обнуляются после 24),
стабильный порядок start_ms/stream_index/исходный порядок. Перекрывающиеся cues
не обрезаются/не объединяются, пустые сегменты пропускаются. Пустые строки внутри
cue убираются ради корректного SRT, исходные сегменты в БД не меняются. RAW SRT
использует гранулярность сохранённых сегментов (в pipeline это word timestamps).

JSON schema_version=1: media/job/model, selected_streams, выбранная version с
processing_metadata, text.raw/readable/selected, chronological segments с integer
ms и stream_index/speaker_label. Экспорт содержит путь источника и сохранённые параметры обработки.
Markdown содержит заголовок, модель, тип версии и выбранный текст.

Все форматы пишутся UTF-8 без BOM, структурные разделители — LF. Запись идёт в
собственный temp рядом с назначением, flush/fsync, затем атомарная публикация.
Существующий файл остаётся нетронутым без явного `--overwrite`, в том числе если
его создали после начала записи. Исходный медиафайл никогда не заменяется экспортом.
Ctrl+C отменяет незавершённую запись и удаляет только её temp; программный
ExportService принимает cancellation event. Отмена проверяется до публикации;
после успешного rename файл уже считается записанным. Ошибки доступа/read-only,
диска/каталога сообщаются явно, ранее существующий результат сохраняется.
