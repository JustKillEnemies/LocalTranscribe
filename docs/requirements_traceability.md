# Соответствие требований и шагов 00–17

Источник — [requirements.md](requirements.md), сверенный с
[ORIGINAL_TZ.md](ORIGINAL_TZ.md). Ни один FR/NFR не перенумерован.
«Реализация» указывает распределение по шагам; их результаты находятся в progress.md.
Ниже добавлены ссылки на артефакты шагов 01–03; они не означают приёмку всего MVP.
Статусы — [progress.md](progress.md), названия шагов — [implementation_plan.md](implementation_plan.md).

| Требование | Реализация (шаги) | Приёмка (шаги) | Граница / существенное условие |
| --- | --- | --- | --- |
| FR-01 | 02, 04, 12 | 04, 12, 15, 17 | Форматы, несколько файлов, drag-drop, диск, доступность, повреждения; нет лимита только по размеру. |
| FR-02 | 03, 04, 05, 12, 13 | 04, 05, 15, 17 | Реальный stream_index, раздельная обработка, явное смешивание и пользовательские роли без автоматического угадывания. |
| FR-03 | 05, 08, 09 | 05, 08, 15, 17 | PCM mono 16 kHz, исходные времена, стерео/многоканальность, без перекодирования видео; 5 мин, диапазон 1–15. |
| FR-04 | 07, 08, 12 | 07, 15, 17 | 0.5 / 500 ms / 200 ms; ориентир 30 s, повтор с изменёнными параметрами, защита слов и времени. |
| FR-05 | 02, 06, 09, 12 | 06, 15, 17 | large-v3-turbo / medium / large-v3, float16 → int8_float16, beam 5, temperature 0, word timestamps optional, OOM. |
| FR-06 | 05, 07, 08 | 08, 15, 17 | Ограниченная память, перекрытия и абсолютное время, дедуп без удаления реальных повторов. |
| FR-07 | 03, 08, 09, 12 | 03, 08, 09, 15, 17 | Атомарный результат+статус, fingerprint/resume, точные состояния ТЗ, без потери сохранённого и дублей. |
| FR-08 | 10, 13 | 10, 13, 15, 17 | RAW неизменяем, READABLE/MANUAL отдельно, режимы A/B/C; детерминированный MVP без LLM/подмены смысла. |
| FR-09 | 03, 06, 10, 13 | 10, 13, 15, 17 | CRUD/импорт словаря, варианты; prompts STT только при поддержке, неоднозначную замену не применять безусловно. |
| FR-10 | 11, 13 | 11, 13, 17 | UTF-8 TXT, SRT, JSON с RAW/READABLE/streams/model; дополнительно Markdown, без повторного STT. |
| NFR-01 | 05, 06, 08, 09, 12 | 06, 12, 15, 17 | Один GPU inference, отзывчивость/прогресс; 60 мин за <=15 мин — измеряемая цель, не гарантия. |
| NFR-02 | 05, 06, 07, 08, 09, 14 | 05, 06, 08, 14, 15, 17 | Bounded queues/buffers, освобождение PCM, OOM fallback и контроль временных файлов. |
| NFR-03 | 03, 04, 08, 09, 11, 14 | 03, 08, 09, 11, 14, 15, 17 | Сохранность подтверждённых результатов, безопасная отмена, отсутствие источника и понятные ошибки. |
| NFR-04 | 00, 02, 06, 14, 16 | 06, 14, 16, 17 | Зависимости/модели готовятся отдельно; после подготовки работа offline без отправки пользовательских данных. |
| NFR-05 | 00, 02, 03, 04, 11, 14 | 00, 02, 11, 14, 16, 17 | Секреты вне Git/логов, безопасные пути/команды, явное удаление истории, сохранение оригинальных медиа. |

Ниже дополнительные метки для разделов без идентификаторов. TZ-* — служебные
ссылки этой таблицы, не новые FR/NFR и не придуманные требования.

| Раздел ТЗ / метка | Реализация (шаги) | Приёмка (шаги) | Содержание |
| --- | --- | --- | --- |
| §1 / TZ-SCOPE | 00 | 00, 17 | Цели, Windows 11 x64, RTX 4060 Ti 8 GB, русский; исключения MVP. |
| §2 / TZ-STACK | 00, 01, 02, 03, 06, 07, 16 | 00, 01, 03, 06, 07, 16, 17 | Python 3.14, стабильные фиксированные зависимости, CUDA 12/cuDNN проверяются, служба PostgreSQL, без обязательного Docker. |
| §4 / TZ-UI | 12, 13 | 12, 13, 17 | Русский GUI и тёмная тема, четыре экрана, время/модель/прогресс, intermediate audio, общая шкала проигрывания. |
| §5 / TZ-ARCH | 00, 03, 05, 06, 08, 09, 10, 11, 12 | 00, 09, 17 | Модульный монолит, изолированный worker, точные команды/события и последовательная очередь. |
| §6 / TZ-PATHS | 00, 01, 02, 16 | 00, 01, 02, 16, 17 | src-layout; Windows user data вместо Program Files; структура создаётся по этапам. |
| §7 / TZ-DB | 03, 08, 10, 14 | 03, 08, 14, 17 | Все семь таблиц, поля и индексы, UUID/FK/ms, транзакции, версии, явное удаление без удаления источника. |
| §8 / TZ-FLOW | 04, 05, 06, 07, 08, 10, 11 | 15, 17 | Полный цикл импорта → распознавания → сохранения → читаемого текста → экспорта. |
| §10 / TZ-ERRORS | 02, 04, 05, 06, 08, 09, 11, 14 | 02, 04, 05, 06, 08, 09, 11, 14, 17 | Все 10 отказов таблицы ТЗ; диагностика и лог с job_id без приватного содержимого/пароля. |
| §11 / TZ-TESTS | 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 15 | 15, 17 | Unit/integration/E2E; восемь наборов, >=3 ч, >1 GB; WER/CER по RAW, WER <=15% чистой речи — целевой ориентир. |
| §12 / TZ-ACCEPTANCE | 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 15, 16 | 17 | Все 17 критериев MVP обязательны; аудит 00 их не считает выполненными. |
| §13 / TZ-PLAN | 00 | 00, 17 | Макроэтапы оригинала соответствуют детализации V2, см. implementation_plan.md. |
| §14 / TZ-FUTURE | вне 00–17 | не gate MVP | Локальная LLM, FTS по БД, расширенная массовая обработка, диаризация, live WASAPI. |
| §15 / TZ-DELIVERY | 01, 03, 11, 14, 15, 16, 17 | 17 | Все 12 артефактов поставки: исходники/lock/миграции/env, инструкции Windows/CUDA, руководство, тесты, пример экспорта, архитектура, сборка, GPU-результаты. |

## Артефакты и проверки шага 01

Ссылки подтверждают только границу минимального пакета. Полные FR/NFR и
критерии §12 остаются на назначенных этапах. Текущий вердикт — в progress.md.

| Требование / граница этапа | Артефакт | Проверка |
| --- | --- | --- |
| TZ-STACK §2: Python 3.14, виртуальное окружение, фиксированные зависимости | [pyproject.toml](../pyproject.toml), [uv.lock](../uv.lock), [.python-version](../.python-version) | uv sync; uv lock --check; версия интерпретатора; wheel в чистом venv. |
| TZ-PATHS §6: src-layout и единый запуск | [__main__.py](../src/local_transcriber/__main__.py), [main.py](../src/main.py) | test_version_from_all_launchers; test_launch_from_cyrillic_directory_with_spaces. |
| CLI шага 01: --help, --version и запуск без аргументов | [test_cli.py](../tests/test_cli.py) | test_installed_metadata_matches_project; test_help_and_default_command; unit main([]). |
| Отказы шага 01: неизвестный аргумент, сокращение, будущая команда | [test_cli.py](../tests/test_cli.py) | test_invalid_command_reports_error_without_changing_files; код 2, stderr, неизменный контрольный файл. |
| TZ-TESTS §11: тестовая инфраструктура и импорты | [tests/README.md](../tests/README.md), [test_cli.py](../tests/test_cli.py) | Изолированный import smoke, без тяжёлых импортов; pytest/Ruff. Предметные интеграции — позже. |
| TZ-DELIVERY §15 п.1,2,4,5,8,10: начальные исходники, lock, пример env, команды Windows, тесты, архитектура | [README.md](../README.md), [.env.example](../.env.example), [architecture.md](architecture.md) | Команды запуска и сборки, отсутствие credentials в примере, проверка Markdown-ссылок. Полная поставка — 17. |

## Артефакты и проверки шага 02

| Требование / граница | Артефакт | Проверка и граница приёмки |
| --- | --- | --- |
| TZ-STACK / TZ-PATHS / §4.4: настройки и пользовательские каталоги Windows | [settings.py](../src/local_transcriber/infrastructure/settings.py), [.env.example](../.env.example) | test_defaults_do_not_create_files, AppData/home fallback, env priority, UTF-8/BOM, single-quoted Windows paths. |
| FR-05: параметры device/GPU/model/precision | [settings.py](../src/local_transcriber/infrastructure/settings.py) | Валидация defaults/env, GPU index и моделей. Это конфигурация, не STT из 06. |
| TZ-ERRORS: отсутствующие FFmpeg/ffprobe/PostgreSQL/GPU/модель | [doctor.py](../src/local_transcriber/infrastructure/doctor.py), [test_doctor.py](../tests/test_doctor.py) | Раздельные OK/MISSING/ERROR/SKIP, timeout/permission/bad response, CLI без GPU. |
| NFR-04: локальная диагностика без автоматической загрузки | [doctor.py](../src/local_transcriber/infrastructure/doctor.py) | Dry-run без subprocess/файлов, only local PostgreSQL, CUDA в отдельном процессе, model files only. |
| NFR-05: пароли и сохранность данных | [test_settings.py](../tests/test_settings.py), [test_doctor.py](../tests/test_doctor.py) | SecretStr/repr, безопасные ошибки DSN/env, secret-free subprocess, явное создание каталогов, неизменные sentinel файлы. |
| TZ-TESTS: положительные/негативные Windows сценарии | [test_settings.py](../tests/test_settings.py), [test_doctor.py](../tests/test_doctor.py) | .env escapes и синтаксис, DSN port=0, кириллица/пробелы, реальные процессы и все launcher. |
| CLI/точки входа шага 01 сохраняются | [__main__.py](../src/local_transcriber/__main__.py), [test_cli.py](../tests/test_cli.py) | Версия/справка и import smoke сохранены; doctor добавлен с ленивой загрузкой Infrastructure. |
| TZ-DELIVERY: настройки и инструкции | [README.md](../README.md), [uv.lock](../uv.lock) | На шаге 02 закреплены лёгкие настройки; CUDA/ML не добавлены, миграции/репозитории относятся к 03. |

Итоговые статусы и фактическая среда — [progress.md](progress.md).
pg_isready не подтверждает authentication/схему БД; полная приёмка БД — шаг 03.
Модель/CUDA checks не подтверждают inference — шаги 06–07.


## Артефакты и проверки шага 03

Это приёмка границ хранения §7, не всей транскрибации FR-07 или MVP.
Результаты и состояние среды — только [progress.md](progress.md).

| Требование / граница | Артефакт | Проверка и граница приёмки |
| --- | --- | --- |
| TZ-DB §7.1–7.7, TZ-STACK: все семь таблиц и типы | [models.py](../src/local_transcriber/infrastructure/database/models.py), [0001_initial.py](../migrations/versions/0001_initial.py) | PostgreSQL integration: upgrade/repeat/check/downgrade/upgrade; UUID, JSONB, TIMESTAMPTZ, BIGINT, FK, CHECK, UNIQUE и индексы. |
| FR-02: несколько дорожек одного файла | [models.py](../src/local_transcriber/infrastructure/database/models.py), [test_postgresql.py](../tests/test_postgresql.py) | Две дорожки/два задания; составные FK отклоняют другой файл и чужой job/chunk. Выбор/смешивание дорожек — 04–05/12–13. |
| FR-07, NFR-03: атомарность и повтор без дублей | [repositories.py](../src/local_transcriber/infrastructure/database/repositories.py), [test_postgresql.py](../tests/test_postgresql.py) | Commit/rollback после ошибки flush, одинаковый и конфликтующий повтор, конкурентное сохранение, прогресс из DB. Полное resume/fingerprint/worker — 04/08–09. |
| FR-07 / TZ-ARCH: состояния задания | [jobs.py](../src/local_transcriber/domain/jobs.py), [test_database_unit.py](../tests/test_database_unit.py) | Все 64 пары переходов, терминальные состояния, сохранение переходов в PostgreSQL. Управление процессами — 09. |
| FR-08 / TZ-DB §7.5–7.6: сохранность RAW | [0001_initial.py](../migrations/versions/0001_initial.py), [test_postgresql.py](../tests/test_postgresql.py) | Реальный SQL UPDATE сегментов/RAW-версии отвергается; уникальность версий; RAW не меняется после конфликтующего повтора. Обработка/редактор — 10/13. |
| FR-09 / TZ-DB §7.7: схема терминов | [models.py](../src/local_transcriber/infrastructure/database/models.py) | canonical_form/variants/enabled/created_at, CHECK и уникальность. CRUD/импорт/преобразования не реализованы: 10/13. |
| NFR-05 / §7.8: секреты и исходные файлы | [session.py](../src/local_transcriber/infrastructure/database/session.py), [test_postgresql.py](../tests/test_postgresql.py) | URL escaping, безопасные ошибки, CASCADE результатов при удалении задания; исходный файл/другое задание сохраняются. |
| TZ-TESTS §11: реальная изолированная БД | [test_postgresql.py](../tests/test_postgresql.py), [check_postgresql.py](../scripts/check_postgresql.py) | Test DB guard, случайная схема, strict runner; настоящая PostgreSQL без SQLite/mock, собственный процесс останавливается. |
| TZ-DELIVERY §15: воспроизводимые миграции/инструкции | [alembic.ini](../alembic.ini), [env.py](../migrations/env.py), [README.md](../README.md), [uv.lock](../uv.lock) | Единый AppSettings, без DSN в ini; offline SQL — unit, реальный миграционный цикл — отдельная integration. |

## Артефакты и проверки шага 04

| Требование / граница | Артефакт | Проверка и граница приёмки |
| --- | --- | --- |
| FR-01: MKV/MP4/MOV/WAV/MP3/M4A/FLAC/WebM, доступность и ffprobe | [media.py](../src/local_transcriber/infrastructure/media.py), [test_media.py](../tests/test_media.py) | Extension contract, Unicode/пробелы, saved JSON, no audio, invalid JSON, timeout, tool/file/format errors. GUI multi-select/drag-drop — 12. |
| FR-01: длительность/размер/контейнер/кодеки/число аудиопотоков | [media.py](../src/local_transcriber/domain/media.py), [__main__.py](../src/local_transcriber/__main__.py) | CLI inspect; integer ms, stat size, format_name, codec/rate/channels; реальный MKV. Свободное место проверяется перед временными данными в 05. |
| FR-02: реальные индексы и labels всех дорожек | [media.py](../src/local_transcriber/infrastructure/media.py), [0002_media_import.py](../migrations/versions/0002_media_import.py) | Mixed video/subtitle/audio fixture даёт 1 и 4; реальный MKV даёт 1 и 2; language/title сохранены. Выбор/роли/смешивание — 05/12. |
| FR-07 / NFR-03: fingerprint и безопасный повтор | [media_import.py](../src/local_transcriber/application/media_import.py), [repositories.py](../src/local_transcriber/infrastructure/database/repositories.py) | UNIQUE/upsert, одинаковый повтор возвращает тот же UUID, конфликт metadata отклонён, исходник и прежняя запись сохранены. Resume job — 09. |
| NFR-02: импорт длинных файлов без роста RAM | [media.py](../src/local_transcriber/infrastructure/media.py) | Только первые/последние 1 MiB; ffprobe output <=4 MiB через tempfile; без decode. Реальный >1 GB сценарий — 15. |
| NFR-05: безопасный subprocess/локальность | [media.py](../src/local_transcriber/infrastructure/media.py), [test_media.py](../tests/test_media.py) | Абсолютный путь одним аргументом, shell=False, timeout kill/wait, stderr скрыт; внешние сервисы отсутствуют. |
| TZ-TESTS §11: FFmpeg/PostgreSQL integration | [test_postgresql.py](../tests/test_postgresql.py) | Настоящие FFmpeg 9.0.2/ffprobe и PostgreSQL 18.3: synthetic MKV с video + 2 audio, inspect/import/repeat/corruption. SQLite/mock не используются. |
