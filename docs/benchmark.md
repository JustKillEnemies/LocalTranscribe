# Воспроизводимые E2E измерения

Протокол ШАГА 15, Windows 11 x64 / CPython 3.14 GIL / RTX 4060 Ti 8 GB.
Это измерения конкретных записей, не гарантия скорости или качества приложения.
Фактические результаты проверок и вердикт — только [progress.md](progress.md).
Требования: [requirements.md](requirements.md), NFR-01/02/03 и §11.3–11.4.

## Запуск

Создайте локальный manifest по [benchmark.example.json](benchmark.example.json),
укажите абсолютные пути. Храните заполненный manifest под ignored `tmp/`;
исходники, эталоны, DB cluster и транскрипты не публикуйте. `indices` — реальные
ffprobe stream indices. `end_ms` ограничивает префикс записи; без него обрабатывается
весь файл, включая EOF. При недостаточной длине case помечается NOT TESTED.
Пример содержит placeholders, перед запуском замените их реальными файлами.

```powershell
# Из корня, существующая Python 3.14 .venv; лёгкая psutil — dev dependency.
uv sync --locked
.venv/Scripts/python.exe scripts/check_postgresql.py --benchmark-manifest tmp/private-benchmark.json

# Если отдельная test DB уже настроена через AppSettings:
uv run python scripts/benchmark.py tmp/private-benchmark.json --env-file C:/private/benchmark.env --output tmp/benchmark-new-run
```

Первый launcher использует существующие PostgreSQL 18 binaries, создаёт собственный
SCRAM cluster на loopback/random port и отдельную test DB, выполняет pytest/Ruff/
миграции, затем benchmark, останавливает только свой cluster в finally. Системная
служба и рабочая БД не изменяются. Для другого расположения binaries используйте
`--postgres-bin`. `--pytest-target` позволяет повторить только нужные тесты.
Standalone launcher всегда использует `make_engine(test=True)` и случайную схему;
не удаляет результаты/схему автоматически. Для повторного запуска нужен новый
output directory: чужие и предыдущие результаты не перезаписываются.

## Протокол и артефакты

- Один реальный GPU worker через spawn, SQLAlchemy/PostgreSQL и FFmpeg/Silero/
  faster-whisper; CPU/synthetic ASR не подменяет hardware measurement.
- Общий `prepare_task` с CLI, локальная модель, русский, beam 5, word timestamps,
  чанки 300000 ms, overlap 1000 ms, VAD из AppSettings. Каждый case запускает
  новый worker (cold model load), automatic download/fallback выключены.
- Wall-clock — inspection/task preparation → processing/resume → RAW/READABLE →
  четыре экспорта → shutdown/sampler stop. Отдельный pipeline_seconds заканчивается
  при событии COMPLETED. Начальные pytest/Alembic и создание cluster не входят.
- Audio duration — временной диапазон источника; для нескольких дорожек дополнительно
  stream_audio_duration_ms. RTF = wall_seconds / audio seconds источника. Prefix и
  full-source испытания различаются явно; это не замер полного длинного видео при
  обработке только первых 5/60 минут.
- RSS: сумма sampled working sets launcher + recursive children (GPU worker/FFmpeg),
  PostgreSQL исключён. Shared pages могут учитываться несколько раз. API:
  [psutil memory_info/children](https://psutil.readthedocs.io/stable/index.html).
- VRAM: `nvidia-smi --id=... --query-gpu=memory.used`; весь выбранный GPU, включая
  desktop/другие приложения. Baseline записывается отдельно; разность не объявляется
  точной памятью worker. Интервал 0.5 s плюс время команды; пики sampled, короткий
  выброс может быть пропущен. Ошибки/число samples сохраняются, отсутствие данных
  не заменяется нулём. JSONL samples позволяют построить профиль роста памяти.
- events.jsonl: только тип события/числовой progress/относительное время, без текста
  и error payload. Разность PROGRESS-времён — end-to-end chunk latency; первый
  включает load/inspection/planning. Она не разделяет CUDA/VAD/decode без profiling.
- metrics.json / benchmark.json: версии окружения, Git HEAD, digest dirty tracked
  diff и SHA-256 всех source scripts/modules (включая untracked), model/source fingerprints, диапазон, chunks, segments, RTF, RSS/VRAM, ошибки.
  Fingerprint — существующая идентификация sampled bytes/stat, не полный SHA видео.
  Индивидуальные `profile` — человеческие аннотации, default UNREVIEWED.
- После шестого COMMITTED chunk часовой записи harness убивает только своего
  worker, ждёт INTERRUPTED, запускает новый worker и resume того же job. Сравнивает
  ID/digest/attempt/completion time ранее подтверждённых chunks/segments, полное
  покрытие диапазонов, отсутствие duplicate keys и bounds segment timestamps.
- RAW/READABLE сохраняются, TXT/SRT/JSON/Markdown экспортируются в private owned
  output. Эти файлы содержат приватный текст и не включаются в Git. GPU/SQL ошибки
  в публичном отчёте содержат только class/code, без credentials/media/transcript.

## Качество и ручная приёмка

WER/CER вычисляются исключительно по сохранённым RAW segments отдельной дорожки,
если для неё указан независимый человеческий эталон UTF-8 ≤1 MiB. Эталон должен
покрывать тот же диапазон. MANUAL/READABLE и результат ASR не являются эталоном.
Без эталона — NOT RUN, даже если распознавание завершилось.

Явный протокол `nfc-casefold-whitespace-v1`: NFC, casefold, collapse whitespace;
пунктуация, цифры, ё сохраняются; CER включает нормализованные пробелы. Одинаковая
нормализация обеих сторон, Levenshtein S+D+I / длина эталона. Пустой эталон отвергается,
пустая гипотеза даёт 1, вставки могут дать >1. Нельзя менять нормализацию задним числом
для улучшения оценки. Для приёмочной выборки владелец согласует этот протокол;
для первоначальных OBS cases эталоны не предоставлены; публичная FLEURS выборка описана ниже. CPU budget — 25M cells
после удаления общего prefix/suffix; при превышении нужно разбить независимые
эталоны на согласованные диапазоны, а не сообщать фиктивные метрики.

Человек отдельно проверяет чистую русскую речь, технические термины, шум,
тишину, пропуски/повторы, слышимость на границах chunks и последний речевой участок.
DB timeline validation не доказывает отсутствие пропуска слов или галлюцинаций.
Формат подписи: case ID, источник fingerprint, reviewer/date, профиль речи,
проверенные интервалы и замечания; подпись агента не подменяет прослушивание.
Ручной original OBS MKV/MP4 playback из ШАГА 13 также остаётся отдельным gate.

## Измеренное окружение и результаты

Измерения 2026-10-14 (UTC start исходного набора 2026-10-13 19:29:42).
Исполнитель автоматизированного запуска — Codex на локальном ПК. Это подпись
запуска/сбора метрик; reviewer speech quality отсутствует, profiles UNREVIEWED.

| Компонент | Измеренная версия/конфигурация |
| --- | --- |
| ОС | Windows-11-10.0.26200-SP0 |
| Python | 3.14.4 x64 GIL, существующая .venv |
| GPU / driver / memory | NVIDIA GeForce RTX 4060 Ti, 596.21, 8188 MiB |
| CPU / logical CPUs / RAM | AMD64 Family 25 Model 33 Stepping 2, AuthenticAMD / 12 / 31.92 GiB |
| FFmpeg / ffprobe | 9.0.2 essentials |
| PostgreSQL | 18.3, separate test DB/random schema |
| faster-whisper / CTranslate2 / ONNX Runtime | 1.2.1 / 4.8.2 / 1.31.0 |
| SQLAlchemy / psycopg / PySide6 / psutil | 2.1.4 / 3.3.6 / 6.12.0 / 7.2.2 |
| Model / compute | large-v3-turbo / cuda float16, fallback off, beam 5, word timestamps |
| VAD | enabled=true, threshold=0.5, min_silence=500 ms, padding=200 ms, max_speech=30000 ms |
| Pipeline | chunk 300000 ms / overlap 1000 ms |
| Git base | a9b706e; uncommitted STEP 15 code, source digests в локальных artifacts |

Каждый case — новый worker/model load; OS filesystem cache не очищался. VRAM
всей видеокарты, не allocation одного worker. Private paths/тексты не публикуются.

| Case | Audio timeline, s | Range | Wall, s | RTF | Peak RSS, GiB | Whole GPU VRAM, GiB | Baseline VRAM, GiB | Chunks / segments | Samples |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| five-minutes | 300.000 | prefix | 20.802 | 0.069341 | 1.688 | 4.240 | 1.931 | 1 / 481 | 35 |
| one-hour | 3600.000 | prefix | 209.777 | 0.058272 | 1.781 | 4.312 | 1.932 | 12 / 4652 | 361 |
| hour-crash-resume | 3600.000 | prefix | 201.841 | 0.056067 | 1.700 | 4.276 | 1.961 | 12 / 4652 | 350 |
| end-of-video | 13.100 | full | 4.810 | 0.367195 | 1.863 | 4.170 | 1.954 | 1 / 26 | 8 |
| five-minutes-final | 300.000 | prefix | 19.384 | 0.064614 | 1.895 | 4.396 | 1.996 | 1 / 481 | 33 |
| full-95-minutes | 5717.000 | full | 322.383 | 0.056390 | 1.721 | 4.333 | 2.004 | 20 / 11943 | 558 |

Это source timeline, а не сумма speech PCM после VAD. `one-hour` и crash/resume
обрабатывают первые 3600 s записи длиной 3795.233 s, размер источника 2.927 GB.
Five-minute — prefix источника 1584.067 s / 1.212 GB. `full-95-minutes` — весь
реальный MP4 5717 s / 4.405 GB, подтверждённый владельцем; это не ≥3h и не MKV.
Размеры GB десятичные, memory GiB двоичные. Ошибки RSS/VRAM и runtime errors во всех
завершённых OBS cases — 0. Для них WER/CER не вычислялись; публичная эталонная оценка добавлена ниже.

Часовой case: последующие end-to-end интервалы между committed PROGRESS —
12.759–22.227 s, median 15.890 s.
Во время crash/resume worker убит на 112.123 s
после 6 committed chunks, новый worker продолжил с chunk 7. Сравнивались identities/
digests/attempt/completion timestamps шести checkpoints; финальные counts 12/4652
совпали с uninterrupted запуском, unique chunk coverage сохранён.
Это DB/таймкодная проверка, не доказательство правильности всех слов по слуху.

Все завершённые cases сохраняют RAW/READABLE и четыре local exports. Last speech
segment ends в полном 95min case: 5714324 ms;
общий конец источника 5717000 ms. Автоматическая проверка bounds/EOF не подменяет
ручное прослушивание последнего речевого участка.

Артефакты в ignored private `tmp/step03-pg-.../benchmark/`: исходный набор
e0b3464ae42644e1bb1bf338fc68cb3d, final 5min rerun d95d0c94f91b41e794da45a23c2e99e2,
full95 57bb19ade00a4f18aaae1b5c063db5e4. Каждый содержит benchmark.json, per-case
metrics/events/resources и приватные экспорты. Own clusters после запусков остановлены.
Первый снимок code hashes добавлен из копии, захваченной во время прогона до дальнейших
правок metadata; последующие harness запускают автоматический startup source snapshot,
включая ещё не tracked modules. Между длинными замерами менялись metadata/logging,
а алгоритм pipeline, GPU/VAD/config не оптимизировался.

По измеренным sampled profiles рост RSS не выглядит линейным с длиной записи:
начальные peaks не растут пропорционально 5→60→95 min. Это наблюдение конкретных
прогонов, не обещание для ≥3h. Chunk latency меняется с записью; конкретный bottleneck
decode/VAD/STT/SQL не установлен, отдельного stage profiling не выполнялось.
Оптимизации не вводились. Сводные результаты проверок/непройденные gates — progress.md.


Цель 60 минут ≤15 минут и WER ≤15% чистой русской речи — проверяемые ориентиры,
не заявленные свойства. Оптимизировать только измеренный bottleneck, сохранив
baseline. Пока не выполнено раздельное stage profiling, причина chunk latency
не приписывается модели, VAD, decoder или БД по предположению.

## Публичная эталонная выборка FLEURS ru_ru

Источник: [Google FLEURS](https://huggingface.co/datasets/google/fleurs),
Conneau et al., [FLEURS (2022)](https://arxiv.org/abs/2205.12446),
лицензия [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Revision `70bb2e84b976b7e960aa89f1c648e09c59f894dd`, config ru_ru, split test.
Независимый reference — поле raw_transcription поставщика: исходные предложения
для записанного чтения, не результат нашего ASR/READABLE/MANUAL. Собственная
повторная ручная проверка этих эталонов не выполнялась.

Выбор зафиксирован до inference: первые 32 WAV в порядке pinned test.tar.gz,
31 уникальный sentence ID; без исключения неудобных примеров или настройки модели
по результатам. Test TSV и SHA-256 каждого WAV/reference сохранены в provenance.
Это подвыборка, не полный FLEURS test и не доказательство отсутствия пересечения
с исходными обучающими данными Whisper. Всего 406.620 s, WAV 24.82 MiB.

| Протокол | Reference words | Word errors | WER | Reference chars | Char errors | CER |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Primary: nfc-casefold-whitespace-v1, пунктуация сохраняется | 659 | 93 | 14.1123% | 4784 | 151 | 3.1564% |
| Secondary: nfc-casefold-punctuation-space-v1 | 670 | 53 | 7.9104% | 4679 | 114 | 2.4364% |

Оба протокола объявлены до inference в provenance и комментарии запуска.
Secondary заменяет Unicode category P на пробелы с обеих сторон; NFC/casefold/
whitespace те же. Цифры и ё не переписываются. Дефисы разделяют слова, поэтому
число reference words различается. Primary не заменён более выгодной метрикой.
Корпусные WER/CER = сумма edit errors / сумма reference units, а не среднее
процентов отдельных коротких реплик. Все 32 примера входят в знаменатель.

На один corpus ушло 159.777 s wall sum; каждый clip использовал
новый cold GPU worker, поэтому время не сравнивается напрямую с одним длинным
файлом. large-v3-turbo/cuda float16/beam5/word timestamps/VAD — прежние параметры,
никакого дообучения или изменения production pipeline. RAW/READABLE, четыре
экспорта и in-pipeline vs exported-RAW scoring проверены во всех cases.
Индивидуальный primary WER: 5 реплик без word errors, median 14.36%, max 61.54%;
corpus average не означает одинакового качества каждого фрагмента.

Воспроизведение из корня (новая output directory, файлы остаются ignored/local):

```powershell
uv run python scripts/public_benchmark.py prepare tmp/fleurs-ru-test-32 --count 32
.venv/Scripts/python.exe scripts/check_postgresql.py --pytest-target tests/test_public_benchmark.py --pytest-target tests/test_benchmark.py --pytest-target tests/test_repository_audit.py --benchmark-manifest tmp/fleurs-ru-test-32/manifest.json
uv run python scripts/public_benchmark.py score tmp/fleurs-ru-test-32 tmp/step03-pg-RUN_ID/benchmark/benchmark.json
```

RUN_ID берётся из ARTIFACT launcher. Текущий artifact:
tmp/step03-pg-95b78fa5209444edbdb01cc1d67067a1/benchmark/quality-summary.json.
Prepare потоково читает pinned public archive и сохраняет только первые N WAV,
не выполняет удалённый loader, не использует extractall/links, не загружает
пользовательские media/text куда-либо. Никаких новых dependencies не установлено.
Score проверяет hashes и полноту corpus, не исключает failure cases молча.

Эта оценка покрывает эталонное русское чтение. Она не измеряет отдельно точность
на разговоре с HR, шуме/перебиваниях/техническом жаргоне, идентификацию говорящих
или субъективное качество пунктуации/таймкодов. Прежние real OBS stress tests
остаются отдельной проверкой длительности/памяти/resume. Сводный gate status —
[progress.md](progress.md); ручная расшифровка пользовательского видео для этой
публичной оценки не требуется.
