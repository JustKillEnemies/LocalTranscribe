# Архитектура

Это целевая архитектура. Текущий пакет реализует справку, версию, единый запуск,
настройки и диагностику среды, правила состояний Domain, PostgreSQL-схему и
транзакционные репозитории Infrastructure. Медиа, STT/VAD, pipeline/worker и текстовые сценарии описаны ниже; GUI и экспорт описаны ниже. Решения связаны с
[требованиями](requirements.md) и [журналом решений](decisions.md).
Порядок реализации — [implementation_plan.md](implementation_plan.md);
актуальные статусы находятся только в [progress.md](progress.md).
Полное ТЗ — [ORIGINAL_TZ.md](ORIGINAL_TZ.md), нормализация — requirements.md.
Соответствие требованиям и шагам — [requirements_traceability.md](requirements_traceability.md).
Python окончательно выбран: CPython 3.14 x64 с GIL, >=3.14,<3.15.
[Совместимость зависимостей](python314_compatibility.md) проверена по метаданным;
работа ML/CUDA на машине подтверждается отдельно на соответствующих шагах.

## Модульный монолит и слои

Один Python-проект, пакет `local_transcriber`, общий цикл версионирования и
локальное развёртывание. Выделение GPU worker в процесс не превращает приложение
в набор сетевых микросервисов. Внешние AI-сервисы отсутствуют.

| Слой | Ответственность и граница |
| --- | --- |
| UI Layer | PySide6: отображение, ввод и представление прогресса/ошибок. Вызывает сценарии Application; не содержит SQL, CUDA и обработку медиа. |
| Application Layer | Сценарии обработки, координация шагов, жизненный цикл задачи, отмена и обработка событий worker. Зависит от Domain и контрактов внешних операций. |
| Domain Layer | Модель задачи, результатов и сегментов, инварианты, допустимые переходы состояния. Чистый Python без Qt, SQLAlchemy, FFmpeg и моделей распознавания. |
| Infrastructure Layer | Реализации внешних контрактов: процессы FFmpeg, движок распознавания, БД, файловая система, настройки, IPC и экспорт. |

Направление зависимостей: UI → Application → Domain. Infrastructure реализует
контракты, определённые рядом с использующими их сценариями Application
(или Domain, если контракт выражает доменное правило).
Application и Domain не импортируют конкретные инфраструктурные реализации.
Будущий bootstrap создаёт зависимости и связывает реализации с контрактами.

## Функциональные границы

| Модуль/подсистема | Ответственность |
| --- | --- |
| Media Processing | Проверка файла и ffprobe, выбор аудиодорожки, нормализация/извлечение аудио FFmpeg, выдача ограниченных чанков и связи временных отметок с источником. Не выполняет распознавание и не записывает данные в БД. |
| Transcription Engine | Адаптер faster-whisper / CTranslate2 и Silero VAD, локальная модель, выдача сегментов. CUDA и модель загружаются только в worker. Сохраняет абсолютные времена с учётом VAD, границ чанков и возможного перекрытия. |
| Text Processing | Превращение сегментов в читаемый текст по согласованным правилам. Исходные сегменты сохраняются отдельно; текстовые преобразования не должны незаметно менять смысл. Без облачных AI API. |
| Persistence | SQLAlchemy и локальная PostgreSQL: метаданные файла, задачи, параметры обработки, сегменты и производный текст. Alembic управляет схемой. Не хранит исходные медиа и веса моделей. |
| Export | Преобразование сохранённого результата в согласованные форматы и запись локального файла. Не управляет распознаванием и не меняет исходные медиа. |

В шаге 05 `application.media_decode.MediaDecoder` задаёт порт Application, а
`infrastructure.ffmpeg_decoder.FFmpegMediaDecoder` реализует его локальным
процессом FFmpeg. Контекстный менеджер владеет дочерним процессом и всегда
выполняет terminate/wait, при необходимости kill/wait. Отдельный reader thread
переносит stdout в очередь фиксированной ёмкости; stderr направлен во временный
файл, поэтому заполнение обоих каналов не создаёт deadlock и PCM не растёт с
длиной записи. На выходе только s16le mono 16 kHz блоки.

Диапазоны декодирования задаются абсолютными integer milliseconds и ограничены
15 минутами; рабочее значение по ТЗ — 5 минут. `start_time` дорожки из ffprobe
округляется до ms и сохраняется в PostgreSQL. Отрицательный PTS нормализуется к
нулю, отсутствующий считается нулём, а запрос до положительного стартового PTS
обрезается до начала дорожки. Из-за временной базы контейнера и ресемплинга
граница фактического PCM может отличаться менее чем на 1 ms; отметки блоков
вычисляются по числу выданных 16 kHz samples и остаются на шкале источника.

В шаге 06 `application.transcription.TranscriptionEngine` определяет STT-порт,
`domain.transcription.TranscriptionSegment` хранит относительные integer-ms
границы и текст, а `infrastructure.faster_whisper_engine.FasterWhisperEngine`
адаптирует faster-whisper. Один экземпляр adapter лениво загружает и сохраняет
одну активную модель; это соответствует будущему владению моделью одним worker,
worker/IPC реализованы в шаге 09. Весь lazy generator faster-whisper
потребляется внутри adapter до возврата immutable tuple, чтобы inference и ошибки
не оставались скрытыми после границы вызова.

Вход STT — ограниченный s16le mono 16 kHz диапазон не более 15 минут. Он
преобразуется в float32 NumPy локально; выходные отметки остаются относительными
началу входа. Добавление абсолютного chunk offset выполняет будущий pipeline.
VAD выключен, поскольку его политика относится к шагу 07. Модель берётся из
локального каталога; сетевое получение возможно только через явный
`allow_download=True`, которого AppSettings factory по умолчанию не выставляет.
На Windows adapter подключает только известные DLL-каталоги установленных
`nvidia-cublas-cu12`/`nvidia-cudnn-cu12` и предзагружает cuBLAS Lt, cuBLAS и
cuDNN в порядке зависимостей. Handles принадлежат экземпляру engine; глобальный
системный PATH, CUDA toolkit и драйвер не изменяются.

Это границы ответственности, а не требование создать все каталоги сейчас.
Планируемые группы пакета: `ui`, `application`, `domain`, `infrastructure`;
адаптеры медиа, распознавания, БД, IPC и экспорта появятся только по мере задач.
Чистые правила обработки текста могут находиться в Domain, их сценарии —
в Application. Не следует создавать вторую параллельную иерархию слоёв.

## GPU worker и IPC

Основной процесс содержит GUI, сценарии Application и адаптер Persistence.
GPU worker — отдельный дочерний процесс, запущенный по модели Windows `spawn`.
Его запуск будет защищён `if __name__ == "__main__"`; импорты пакета
не создают процессы и не инициализируют CUDA.

Worker владеет CUDA-контекстом, моделью и подготовкой/распознаванием аудио.
Application управляет задачей и записывает результаты в PostgreSQL.
SQLAlchemy Session, Qt-объекты и CUDA-объекты не передаются между процессами.
Операции БД и ожидание IPC не блокируют Qt event loop; конкретный механизм
фоновой координации будет выбран при реализации UI.

Начальный план IPC — локальные ограниченные очереди `multiprocessing`:
команды запуска/отмены/остановки и события готовности/прогресса/сегментов/
завершения/ошибки. Конкретные DTO и протокол не реализованы.
Сообщения содержат идентификатор задачи, простые сериализуемые поля,
пути и небольшие порции результатов; не целый медиафайл.

Размеры очередей и порций ограничиваются. План протокола должен предусмотреть
обратное давление, наблюдение за состоянием процесса, тайм-ауты и обработку
обрыва без вечного ожидания. Отмена проверяется между ограниченными шагами;
её точные гарантии требуют согласования.

Вначале планируется один GPU worker и одна активная задача распознавания,
чтобы не дублировать модель в 8 GB VRAM. Параллельное распознавание и CPU fallback
требуют отдельного решения. FR-03 задаёт начальный рабочий участок 5 минут с диапазоном 1–15 минут,
внутренние буферы остаются ограниченными. FR-05 задаёт large-v3-turbo, medium/
large-v3, float16 и управляемый int8_float16 fallback, ru/transcribe, beam 5,
temperature 0 и опциональные word timestamps. FR-04 задаёт VAD 16 kHz,
threshold 0.5, min_silence 500 ms, padding 200 ms и ориентир 30 s речи.
Это стартовые параметры ТЗ; их эффективность и расход памяти ещё не измерены.

## Основной поток обработки файла

1. UI передаёт Application путь и согласованные параметры.
2. Application проверяет вход, регистрирует задачу и метаданные через Persistence.
3. Worker запускает ffprobe/FFmpeg через Media Processing и готовит ограниченные
   порции аудио; исходный файл остаётся неизменным.
4. Silero VAD определяет речь; Transcription Engine последовательно распознаёт
   порции и возвращает сегменты с абсолютными временными отметками.
5. Application принимает события, сохраняет результаты ограниченными транзакциями
   и сообщает UI прогресс. Длинная транскрибация не держит открытую транзакцию БД.
6. Text Processing создаёт производный читаемый текст, сохраняя исходные сегменты.
7. После успешного завершения Application фиксирует состояние задачи; Export
   записывает локальный результат по запросу пользователя.
8. При ошибке/отмене состояние и причина сохраняются, UI получает явное событие.
   Приложение освобождает свои ресурсы и временные файлы, не удаляя оригинал.

## Хранение и конфигурация

Медиа, модели, кэш, временное аудио, логи и экспорт находятся в файловой системе.
PostgreSQL содержит пути/идентификаторы и структурированные данные, а не медиа
или PCM. По постоянному контракту V2 все временные отметки — целые миллисекунды.
RAW неизменяем; производный READABLE и пользовательский MANUAL — отдельные
версии. Модели семи таблиц и правила транзакций реализованы в шаге 03;
сценарии текстовых версий и словаря описаны в разделе шага 10 ниже.
Вызовы внешних инструментов — без shell=True; интеграционные тесты БД — только
в отдельной test DB.
Изменение или исчезновение исходного файла должно быть явно обнаружимо;
способ идентификации файла выбирается при проектировании модели данных.

AppSettings в infrastructure/settings.py читает Pydantic Settings: environment
выше явного/user .env, затем defaults; пустые значения используют defaults.
Default data: LOCALAPPDATA/LocalTranscriber, затем APPDATA, затем home/AppData/Local.
cache/models/logs/temp находятся под data_dir; абсолютные пользовательские пути
могут переопределить их. Default .env привязан к стандартному Windows user-data
каталогу, cwd .env автоматически не читается. CLI doctor --env-file выбирает файл.
Пароль и DSN — SecretStr без repr; ошибки конфигурации выводят только имена полей.
Синтаксис/UTF-8/размер .env проверяются. Windows пути используют / либо одинарные
кавычки; управляющие символы отвергаются. Загрузка не создаёт файлы или каталоги.
Каталоги создаются только явным doctor --create-dirs. --dry-run запрещает этот режим.

## Структура и точка входа

Проектный корень — `Transcribation/`, исходники — `src/`, тесты — `tests/`.
Минимальный пакет: `src/local_transcriber/__init__.py` и `__main__.py`.

Единая функция запуска — `local_transcriber.__main__:main(argv=None) -> int`.
`python -m local_transcriber`, console script `local-transcriber` и сохранённый
`src/main.py` делегируют ей, без дублирования разбора аргументов.
Аргументы разбирает стандартный argparse; --version читает версию из метаданных
установленного пакета, единственный источник версии — pyproject.toml.
--help и запуск без аргументов показывают справку; неподдерживаемые аргументы
дают код 2, сокращения отключены. Импорты не запускают процессы и тяжёлые библиотеки.
Hatchling/uv устанавливают пакет в .venv; изменение sys.path/PYTHONPATH не требуется.
Запуск wheel проверяется также вне репозитория в чистой Python 3.14 venv.
--help/--version не загружают настройки; doctor лениво подключает Infrastructure.
Диагностика раздельно сообщает Python/Windows/каталоги/FFmpeg/ffprobe/PostgreSQL/
NVIDIA/CUDA/CTranslate2/модель. Subprocess без shell, с тайм-аутами и скрытыми
окнами Windows; пароль и DSN не передаются аргументами, PG/LOCAL_TRANSCRIBER
переменные удаляются из окружения дочерних инструментов. Не выводится их stderr.
PostgreSQL: только pg_isready readiness, без проверки пароля/схемы и SQL-запросов.
CTranslate2: если установлен, get_cuda_device_count в изолированном дочернем Python;
модель не загружается. Проверяются только локальные model.bin/config/tokenizer.
Операции не скачивают зависимости или модели. dry-run отключает внешние процессы.
Отсутствующие необязательные компоненты дают MISSING без crash; exit doctor=0
означает полученный отчёт, не готовность всей среды. Неверный конфиг даёт exit 2. Версия закреплена владельцем:
только CPython 3.14 x64, >=3.14,<3.15.

## Сверка с ORIGINAL_TZ.md 1.0

Исходные слои §5–6 ТЗ сопоставляются существующим границам:
Media Layer → Media Processing в Infrastructure; Transcription Layer →
Transcription Engine worker; Text Processing → чистые правила Domain и
сценарии Application; Persistence/Export → соответствующие адаптеры.
Дополнительный Domain и единый bootstrap сохраняют направление зависимостей;
предложенное дерево не требует создавать все модули на шаге 00.

- FR-01/02: Application хранит выбор дорожек и пользовательские роли; Media
  поддержит одну/несколько дорожек и смешивание только по явному запросу.
  Номер дорожки не означает личность. Проверка места на диске предшествует записи.
- FR-07: состояния Domain — PENDING, ANALYZING, PROCESSING, PAUSED, INTERRUPTED,
  COMPLETED, FAILED, CANCELLED; сегменты и CHUNK_COMPLETED сохраняются атомарно,
  resume проверяет доступность/fingerprint и не дублирует подтверждённые данные.
- §5.3: команды IPC — START_JOB, PAUSE_JOB, RESUME_JOB, CANCEL_JOB, SHUTDOWN;
  события — JOB_STARTED, PROGRESS_UPDATED, CHUNK_COMPLETED, JOB_PAUSED,
  JOB_COMPLETED, JOB_FAILED. Короткие ограниченные DTO реализованы в 09.
  Обрыв worker приводит к INTERRUPTED и понятной ошибке; ресурсы освобождаются.
- §7: Persistence реализует все семь таблиц и поля ТЗ через SQLAlchemy/Alembic,
  UUID/FK/индексы/JSONB/TIMESTAMPTZ и integer ms. Удаление задачи удаляет её
  производные данные только явно; исходное медиа остаётся.
- FR-08/09: неизменяемый RAW, отдельные READABLE и MANUAL; детерминированные
  правила, режимы A/B/C и CRUD/импорт вариантов терминов. Нельзя менять смысл,
  удалять существенное, угадывать неизвестное или представлять пересказ как RAW.
  Кандидат STT prompting не означает безусловную замену неоднозначного термина.
- FR-10: TXT/SRT/JSON, дополнительно Markdown, из сохранённых данных; JSON
  сохраняет исходный/редактированный текст, дорожки, времена, модель и метаданные.
- §4: PySide6, русский UI и тёмная тема; главное окно, настройки задания,
  результаты и настройки приложения. Поиск/редактор/проигрывание используют
  исходный путь и общую шкалу ms, работают с результатом без повторного STT.
- §6: установленные модели/данные/логи/temp хранятся в пользовательском каталоге
  Windows, не в Program Files. Pydantic Settings и выбор путей реализованы отдельно от GUI.
- §10: FFmpeg/БД/кодеки/исчезновение файла/VRAM/место/worker/повреждённый участок/
  экспорт имеют отдельную диагностику; job_id связывает события и логи, секреты
  и приватный текст в лог не попадают, сохранённый транскрипт не повреждается.
- NFR-01/§11: замеряются RAM/VRAM/скорость и RAW WER/CER, пропуски/повторы/
  терминология/таймкоды. 60 мин за <=15 мин и WER <=15% чистой русской речи —
  целевые ориентиры; реальные 5/60 мин, >=3 ч, >1 GB и две дорожки проверяются в 15.
- §15: поставка исходников, lock, миграций, env, руководств Windows/CUDA/пользователя,
  тестов, примера экспорта, архитектуры, сборки и результатов RTX 4060 Ti — gate 17.

Предметные адаптеры и экраны остаются целевой архитектурой. Настройки и doctor
не являются реализацией транскрибации или GUI. PostgreSQL-репозитории и миграции
реализованы отдельно; их проверенный статус находится в progress.md.


## PostgreSQL: границы реализации шага 03

[models.py](../src/local_transcriber/infrastructure/database/models.py) содержит
семь таблиц §7 ТЗ. UUID создаются приложением; время — BIGINT ms, даты —
TIMESTAMPTZ, параметры/metadata/variants — JSONB. В БД нет медиа/PCM.
Начальная [миграция](../migrations/versions/0001_initial.py) содержит фиксированный
DDL; будущие изменения ORM не меняют содержание уже выпущенной миграции.

Domain [jobs.py](../src/local_transcriber/domain/jobs.py) определяет восемь
статусов задания и переходы, не импортируя SQLAlchemy. JobRepository использует
эти правила при изменении состояния, создаёт задачи, считает прогресс и явно
удаляет только задание с его результатами. Перезапуск/worker остаются шагом 09.
ChunkRepository регистрирует ожидаемые участки и сохраняет результаты:
блокировка строки задания → INSERT ON CONFLICT → проверка границ → сегменты →
COMPLETED/дата/счётчики → commit. Любая ошибка откатывает весь результат.
Идентичный повтор — no-op; изменённые границы или подтверждённый RAW отклоняются.

UNIQUE(job_id, stream_id, chunk_index) защищает участки, UNIQUE(chunk_id,
segment_index) — сегменты; версии уникальны по (job_id, version_number), дорожки
по (media_file_id, stream_index), canonical_form терминов уникален.
Дополнительный processing_chunks.media_file_id и составные FK исключают дорожку
другого файла и сегмент чужого задания/участка. CHECK проверяют ms, состояния,
завершение, счётчики, JSON-типы и номера версий. Индекс (job_id, start_ms) и
пакетное чтение обеспечивают упорядоченную выдачу сегментов. Триггеры запрещают
UPDATE сегментов и RAW-версий; явное каскадное удаление задания разрешено.
Счётчики охватывают только зарегистрированные участки: будущий pipeline обязан
сначала зарегистрировать весь известный план, прежде чем показывать общий процент.

Engine/Session и Alembic получают конфигурацию исключительно из AppSettings.
DSN имеет приоритет над отдельными PostgreSQL полями; только loopback host.
Engine ленивый, echo отключён, SQL-параметры скрыты; PersistenceError не раскрывает
драйверные сообщения, credentials или текст. Каждый сценарий имеет свою Session;
Engine/Session нельзя передавать будущему GPU worker между процессами.

Интеграции используют отдельную *_test/test_* БД, отличную от фактической БД DSN;
postgres/template* запрещены. Каждый тест создаёт собственную случайную схему
lt_test_<uuid> и очищает только её. search_path исключает public. Downgrade
ограничен test-режимом. Alembic preflight завершает свою транзакцию до миграции;
autogenerate исключает только служебную alembic_version, не предметные таблицы.
Воспроизводимый запуск отдельного временного PostgreSQL-процесса —
[scripts/check_postgresql.py](../scripts/check_postgresql.py). Он использует
установленные binaries, SCRAM, loopback/свободный порт и tmp/; не устанавливает
сервер, не меняет службу и не обращается к рабочей БД.

## Импорт медиа, шаг 04

`MediaInspector` находится в Infrastructure и запускает только локальный ffprobe:
список аргументов, `shell=False`, абсолютный путь одним аргументом, timeout и
скрытое окно Windows. stdout/stderr направляются во временные файлы, JSON stdout
ограничен 4 MiB; медиа не декодируется и не загружается в RAM. Поддерживаются
MKV/MP4/MOV/WAV/MP3/M4A/FLAC/WebM. Domain DTO `MediaInfo` и `AudioStreamInfo`
не зависят от subprocess, SQLAlchemy или CLI и сохраняют именно `stream.index`
ffprobe, а не порядковый номер аудиодорожки.

Application use case `ImportMedia` координирует инспекцию и `MediaRepository`.
Репозиторий одной транзакцией вставляет media_files и все audio_streams.
UNIQUE(file_fingerprint) и PostgreSQL `ON CONFLICT` обеспечивают идемпотентный
повтор и конкурентный импорт; при том же fingerprint, но других метаданных
операция отклоняется как возможная коллизия. Миграция `0002_media_import`
добавляет эту уникальность и nullable `language_tag`/`title` для меток ffprobe.

Fingerprint `v1` включает размер, `mtime_ns` и BLAKE2b первых/последних 1 MiB.
Он читает ограниченный объём независимо от размера файла и повторно проверяется
после ffprobe. Это практический ключ быстрого импорта, а не криптографическое
доказательство тождества: одинаковые размер/mtime/краевые блоки могут дать
коллизию. Полный hash намеренно не вычисляется для многогигабайтных записей.
Путь/имя не входят в ключ, поэтому перемещение неизменного файла остаётся
идемпотентным. Автоматическое обновление сохранённого пути не выполняется.

## Потоковая сегментация (шаг 07)

Application port `SpeechSegmenter` принимает непрерывный Iterable[AudioBlock] и
выдаёт SpeechChunk с абсолютными integer-ms границами. SileroSpeechSegmenter
использует локальную Silero v6 ONNX из faster-whisper на CPU: 512 samples/frame,
собственные h/c/context на один поток. Незавершённая речь переносится через
границы блоков; последние samples EOF дополняются нулями только для inference,
выдаваемый PCM сохраняет фактическую длину.

Буфер хранит текущую речь до 30 секунд, silence lookahead 500 ms и padding
200 ms. Длинная речь разделяется на core intervals без пересечений с overlapping
PCM-контекстом. `core_start_ms/core_end_ms` определяют владение результатами;
дедупликация распознанных слов по этим границам входит в pipeline шага 08.
Padding сам не создаёт дополнительные core intervals. Входной AudioBlock
ограничен 5 секундами; память не зависит от длительности медиа. При defaults
основной PCM buffer ограничен 990848 bytes, плюс текущий входной блок/frame и
фиксированное состояние ONNX. Удержание всех результатов самим потребителем
может увеличить его память; API выдаёт их лениво.

AppSettings задаёт vad_enabled/threshold/min_silence_ms/padding_ms/max_speech_ms.
Bypass отключает загрузку/inference VAD и сохраняет весь PCM, включая тишину,
с теми же ограничениями длины и ownership. VAD не определяет личность говорящего
и не гарантирует распознавание каждой тихой реплики; параметры можно менять.
Один segment-вызов должен охватывать непрерывную шкалу, а не каждое окно отдельно.

## Конвейер и чекпойнты (шаг 08)

`application.pipeline.TranscriptionPipeline` зависит от MediaDecoder,
SpeechSegmenter, TranscriptionEngine и PipelineStore ports. CLI composition root
`infrastructure.transcribe_cli` создаёт адаптеры из AppSettings. PipelineStore
реализован PostgreSQLPipelineStore, который использует существующие Media/Job/
ChunkRepository и их транзакции. Новых таблиц и миграций не требуется.

Порядок: validate fingerprint/manifest → job → выбранные streams → план logical
chunks → decode расширенного окна → VAD → STT → ownership/dedup → atomic save.
Logical core по умолчанию 5 min, контекст 1 s с каждой стороны. VAD сохраняет
состояние внутри расширенного окна; между logical chunks оно пересоздаётся с
lookbehind/lookahead. CLI требует overlap >= VAD min_silence+padding. Даже logical
chunk 15 min+контекст decode разбивается на поддиапазоны <=15 min и передаётся
VAD непрерывным iterator. FFmpeg queue остаётся фиксированной; PCM всех chunks
не накапливается. Только текущий logical chunk хранит небольшой список результатов.

CLI включает word timestamps. Относительное время слова смещается на start_ms
SpeechChunk. Полуоткрытые logical/core intervals владеют словом по середине его
таймкода; context words вне ownership не записываются. Перед сохранением границы
обрезаются к logical core. Соседние совпадения удаляются только при временном
пересечении >=50% меньшего интервала и нормализованном text similarity >=0.92.
Раздельные во времени повторения сохраняются; алгоритм не удаляет слова-паразиты.
Сегменты без word timestamps используют midpoint целого сегмента и менее точны
на границах; production CLI всегда запрашивает слова.

ChunkRepository одной транзакцией сохраняет сегменты, COMPLETED и job counters.
При ошибке текущий chunk/job помечаются FAILED, прежние результаты остаются.
При hard stop статус может остаться PROCESSING; explicit --resume проверяет
manifest и обрабатывает только неготовые chunks, включая последний незавершённый.
Автоматическое обнаружение INTERRUPTED и управление worker — шаг 09.
Resume связывает fingerprint, duration, selected indices, engine config, VAD,
chunk/overlap/end, версии runtime и идентичность локальных model files. Ошибки
журналируются с job_id/stream/chunk без сырого текста и credentials.
Одновременные CLI-писатели одного job на этом этапе не поддерживаются.

## Worker и IPC — реализация шага 09

`application.worker_protocol` содержит serializable WorkerTask/Command/Event и
bounded store RPC. Основной процесс создаёт WorkerManager; его supervisor thread
планирует FIFO и последовательно выполняет Persistence requests. Public submit,
command и poll не выполняют SQL/inference. Дочерний worker запускается только
явно через multiprocessing.get_context('spawn'); module imports не запускают
процессы и не создают CUDA-контекст. Worker main — module-level spawn target.

Worker исполняет Application pipeline через RemoteStore, который передаёт
метаданные и ограниченную порцию сегментов в родительский процесс, ожидая ACK.
В родителе PostgreSQLPipelineStore выполняет atomic save и только после commit
публикует CHUNK_COMPLETED. Session, Engine, CUDA/Qt-объекты и PCM через IPC не
передаются. Модель lazy-loaded в worker и кешируется для той же model config.

Команды: START_JOB/PAUSE_JOB/RESUME_JOB/CANCEL_JOB/SHUTDOWN; WorkerCommand.START /
PAUSE / RESUME / CANCEL — короткие aliases. WorkerEvent.kind использует внутренний
status, WorkerEvent.name — канонические JOB_STARTED/PROGRESS_UPDATED/
CHUNK_COMPLETED/JOB_PAUSED/JOB_COMPLETED/JOB_FAILED. Дополнительно READY,
QUEUED, JOB_CREATED, PAUSE_DEFERRED, CANCELLED, INTERRUPTED, IPC_ERROR.
Queue capacities по умолчанию 16, максимум 64; UI event history ограничена 128.
Result RPC ограничен 50000 сегментов / 1000000 text characters; текст — часть
результата, но PCM всегда остаётся в worker. RPC ждёт ACK не более 30 s.

Control listener работает независимо от inference: pause лишь запрашивает
отложенную остановку, а PipelineControl.checkpoint после commit переводит job
в PAUSED. Resume продолжает PROCESSING без reload модели. Cancel задаёт token,
FFmpeg watchdog завершает процесс независимо от следующего stdout read; native
CUDA-вызов не прерывается внутри C++, проверка token выполняется перед/после него.
На accepted cancel parent отвергает новый save/finish. Уже начатый atomic commit
может завершиться и остаётся сохранённым checkpoint. Status updates и saves
выполняются одним supervisor, исключая конкурирующий статусный writer.

При death/IPC failure supervisor прекращает принимать stale RPC, сохраняет
INTERRUPTED, закрывает Windows Job Object (KILL_ON_JOB_CLOSE) и его собственных
FFmpeg children. restart создаёт новые каналы/process; неподтверждённый chunk
повторяется через существующий fingerprint/config gate. Graceful shutdown
прерывает active job, помечает queued resume jobs и ждёт процесс с timeout;
сломанный command channel ведёт к forced cleanup. Поддерживается один manager
для одной очереди; несколько независимых GPU managers не координируются.
События failure/recovery журналируются в основном процессе с job_id.

## Обработка текста и версии (границы шага 10)

`domain.text` содержит immutable DTO сегментов/терминов/правил, stream/time
aggregation и детерминированный `conservative-text` v1. Domain не импортирует
SQLAlchemy, файловую систему, GUI или STT. `application.transcript` задаёт порты
TranscriptStore/TermSource и сценарии RAW/READABLE/MANUAL. Infrastructure
`database.text_store` реализует их поверх существующих таблиц, `text_cli`
проверяет локальные UTF-8 файлы и связывает сценарии с AppSettings.

RAW snapshot создаётся после COMPLETED и проверки завершённости chunks;
порядок stream_index/start_ms/chunk_index/segment_index/id. Строки сегментов
не изменяются; пробел вставляется только при отсутствии граничного whitespace,
дорожки разделены пустой строкой. SHA-256 фиксирует исходные сегменты, время,
порядок и подписи. Повтор возвращает прежний RAW; несоответствие snapshot — отказ.
Во время обработки/после аварии доступны исходные durable segments, окончательный
RAW не объявляется готовым до завершения задания.

READABLE/MANUAL — append-only на уровне сценариев. Номер версии выделяется
под FOR UPDATE lock задания (тот же порядок блокировок, что checkpoint pipeline).
Ручная версия ссылается на base_version_id и RAW своего задания; даже пустая
редакция допустима. Пересчёт READABLE создаёт новую запись с processor,
rules_version, параметрами, снимком включённых терминов и raw_version_id;
MANUAL и предыдущие READABLE сохраняются. RAW по-прежнему защищён SQL-триггером.

Правила READABLE: whitespace и безопасные пробелы перед имеющимися знаками,
конечная точка при отсутствии знака, абзацы по смене дорожки/подписи, паузе
>=2000 ms и 800 символам на границе сегмента. Labels — предоставленные метаданные,
не диаризация. Числа, слова, повторы, стоп-слова, регистр и цитаты сохраняются.
Не восстанавливаются смысловые запятые и не угадываются неизвестные слова.
Словарь заменяет только точные целые варианты (case-insensitive), longest-first
одним проходом, пропускает неоднозначные варианты и выключенные термины.
Автоматического seed словаря и новых STT prompts нет.

CRUD/атомарный импорт словаря работают в PostgreSQL; текстовый формат —
canonical<TAB>variant|variant, UTF-8/BOM, # комментарии. Импорт валидируется до
транзакции, upsert по canonical заменяет варианты/enabled без удаления остальных.
Ограничения файлов: 4 MiB/10000 терминов, 16 MiB ручного текста. Выборки сегментов
идут driver batches по 1000, но snapshot/готовый текст материализуется в памяти;
это текстовые данные, не PCM/медиа. RAW сборка использует список фрагментов,
избегая квадратичного копирования длинной строки.

CLI transcribe после JOB_COMPLETED вызывает текстовые сценарии в основном
процессе и публикует TEXT_COMPLETED. При ошибке текста STT остаётся COMPLETED,
его segments/RAW не удаляются; `text readable` позволяет повторить без STT.
Сценарии можно вызывать будущим GUI вне event loop. GUI/экспорт не входят в шаг 10.

## Экспорт (границы шага 11)

`application.export.ExportService` использует ExportSource/ExportWriter порты и
чистые форматтеры; не зависит от SQLAlchemy, GPU, FFmpeg или GUI. Concrete
`database.export_store.PostgreSQLExportSource` читает repeatable-read snapshot:
метаданные, последний RAW/READABLE/MANUAL, явную выбранную версию, потоки из
processing_chunks и исходные сегменты. Выбираются только нужные версии, не вся
история. Source digest сверяется с RAW; экспорт не имеет записей в БД.

При отсутствии явного UUID TXT/Markdown/JSON предпочитают MANUAL, затем READABLE,
затем RAW; SRT — RAW. JSON v1 содержит media/job/model/selected_streams/version,
raw/readable/selected text и chronological segments. TXT/Markdown — выбранный текст
и optional timestamp/role; SRT — нумерация, absolute ms, стабильный chronological
order с сохранением overlap. Empty cue пропускается, время >1 h/24 h не обнуляется.

Для READABLE conservative-text v1 сохраняет paragraph map (text, stream_index,
start/end ms, speaker_label) в processing_metadata; содержимое/версия правил не
менялись. Legacy v1 без map восстанавливается детерминированно по своим сохранённым
rules/dictionary/segments с обязательным точным совпадением текста и digest.
Экспорт не использует текущий словарь и не создаёт новую READABLE. Неизвестная или
повреждённая версия отвергается. У MANUAL нет alignment: разрешены plain TXT/MD/JSON,
SRT/аннотированный текст отвергается, автоматического привязывания правок нет.

`infrastructure.export_files.AtomicExportWriter` пишет UTF-8 в temp в том же
каталоге, flush/fsync и закрывает дескриптор до публикации (важно для Windows).
Без overwrite Windows os.rename атомарно отказывает при существующем имени;
POSIX использует exclusive os.link + удаление собственного temp. При подтверждённом
overwrite используется os.replace. Preflight не заменяет защиту от гонки имён.
Cancellation проверяется до загрузки/по фрагментам/после fsync/до publish, finally
чистит только собственный temp. Успешный publish — граница завершения экспорта.
Это гарантии атомарной видимости файла на подходящей локальной FS, не обещание
сохранения каталогов после отключения питания/произвольного сетевого диска.

Service запрещает destination, совпадающий с источником по resolved path/samefile,
даже с overwrite. Writer проверяет reserved Windows filenames, directory, collisions
и ошибки доступа/диска. Не создаёт пользовательские каталоги автоматически.
`export_cli` только связывает AppSettings/PostgreSQL/Service/Writer; импорты и
сценарий экспорта не загружают движок/модель. Фрагменты файлов/JSON пишутся постепенно;
текстовый snapshot/segments материализуются как в шаге 10, медиа/PCM не читаются.

## Desktop GUI (границы шага 12)

Application desktop DTO: immutable DesktopRecord/DesktopEvent/JobChoices и
доступность действий по Domain FSM. `ui.window.MainWindow` содержит только
представление, пользовательский ввод и состояния виджетов; Qt объекты/SQLAlchemy
Session не пересекают процессы. GUI открывается командой gui через lazy bootstrap,
существующие CLI и launchers сохраняются. Тёмная тема — Fusion/QPalette, scroll
для панели настроек, размеры 1180×760 logical pixels, minimum 880×600.

DesktopBridge — bounded command actor (64 команды) с собственным thread;
execute/poll конкретного infrastructure.DesktopService проходят вне event loop.
WorkerManager сохраняет прежнюю bounded FIFO (16), один spawn-worker/model cache.
Qt signals явно QueuedConnection; widgets меняются только в main thread. Driver
БД/ffprobe/model fingerprint/disk check и генерация READABLE не исполняются в UI.
Worker создаётся лениво при первом запуске задания, окно/история не загружают GPU.

DesktopService использует AppSettings и существующие ImportMedia/MediaRepository,
pipeline store/worker/TextService. В истории — последний DB job для каждой из
500 последних media; queued состояние до prepare виртуальное и не выдаётся за
сохранённый DB job. Новое задание очищает ссылку на прежний job; ошибка до prepare
оставляет запись готовой к повторному запуску. Resume использует полный saved
manifest/engine/VAD/границы; changing current controls не меняет прежний RAW.
Переподключение/.env change допускается только без active/pending tickets.

Пользовательские роли сохраняются в media audio_streams и immutable job manifest;
PipelineStore добавляет speaker_label к новым сегментам из manifest, а не из
изменяемой позднее подписи media. Существующие RAW/роли не переименовываются.
GUI допускает только раздельную обработку выбранных stream_index; смешивание,
результаты/редактор/воспроизведение требуют своих сценариев следующих шагов.

RecordingDecoder — optional Infrastructure decorator MediaDecoder. Никакой
передачи PCM между процессами: tee блоков в WAV происходит в worker, по одному
decode-range <=15 min. Root directory — temp_dir/intermediate/job_id, random file
suffix, source-ms interval в имени, temp удаляется при incomplete/cancel. Полностью
декодированные диапазоны сохраняются как WAV по явной настройке пользователя;
они могут перекрываться. Disk estimate = PCM duration×selected streams×1.05,
minimum reserve 128 MiB; это проверка наличия места, не отказ по размеру исходника.

Closing handshake: closeEvent откладывает закрытие, bridge получает stop,
background backend.shutdown останавливает manager и DB, closed сигнал закрывает
окно и завершает QApplication. Quit-on-last-window отключён, DeferredDelete
доставляется явно до уничтожения QApplication. Это устраняет native Windows abort
при high-DPI закрытии; регрессия проверяется новым процессом, а не только qtbot.
Ошибки доступны в bounded diagnostic view и строке записи; PipelineError передаётся
из worker как безопасное подробное сообщение, неизвестные исключения — только тип.
