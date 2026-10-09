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
