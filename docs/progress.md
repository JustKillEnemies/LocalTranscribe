# Состояние проекта

Дата: 2026-10-14.

## Текущий шаг

ШАГ 16 — сборка Windows и инструкции установки.
**IMPLEMENTED / WINDOWS BUILD VERIFIED / CLEAN-OS VERIFICATION PENDING — BLOCKED FOR STEP 17**.
Готовый локальный exe: dist/LocalTranscribe Windows x64/LocalTranscribe/LocalTranscribe.exe.
Реальное packaged GPU/PG/native GUI испытание на текущем Windows 11 — PASS.
Полная setup-приёмка на отдельном чистом Windows account/VM пока NOT RUN.
По запросу владельца ШАГ 15 закоммичен и запушен: **0416431**, origin/main.
Запрос «закоммить и запушь потом след шаг» разрешает текущий ШАГ 16 с сохранением
долга ШАГА 15: ≥3h/original two-track OBS MKV и manual original GUI/playback review
не объявляются проверенными. Владелец подтвердил наличие только 95min MP4;
stress/quality измерения на доступном файле и FLEURS сохранены в архиве ниже.
ШАГ 17 не начат. Изменения ШАГА 16 не коммитились/не пушились.

## Реализовано в ШАГЕ 16

- CPython 3.14.4 x64 GIL, существующая .venv; dev PyInstaller 6.22.3/hooks 2026.8
  закреплены lock. Глобальный Python, службы/driver/модель не устанавливались.
- Реальный Windows onedir build, explicit inputs, separate model/config/media/DB,
  bundled NVIDIA runtime/Qt/ORT/PyAV/psycopg; distribution manifest/notice copies и
  SHA-256 inventory. FFmpeg/ffprobe/PostgreSQL server/tools внешние.
- Frozen entry freeze_support/UTF-8/default GUI, fixed CUDA probe protocol,
  bundled DLL directories; db-upgrade/repeat head на существующих scripts/AppSettings.
- Fresh output guard, no repo recursive collection, no .env/media/private data,
  основной Whisper model исключён, Silero runtime ONNX — разрешённый asset.
- Setup/user guides, третьесторонние license/source files, architecture/ADR/matrix.
- Unit build-audit/frozen regressions и opt-in actual packaged GPU/PG/native Qt/
  read-only ACL/PATH/fresh settings/offline audit smoke. Отдельная OS VM не имитируется.

## Проверено на момент реализации

- Commit/push ШАГА 15 — PASS, remote main 0416431, рабочее дерево после push чистое.
- 3 реальные Windows builds через scripts/build_windows.py:
  dist/step16-windows, dist/step16 Windows, окончательный dist/LocalTranscribe Windows x64.
  Последний до notice enrichment: 1161 files/2499658449 B. В конце добавлены
  PyInstaller bootloader/tool licence notices, audit/inventory повторно сформированы:
  **1183 files/2499784158 B**, 52 declared dependency notice entries.
  Notice enrichment не изменял frozen code, driver/модель или SQL.
- PyInstaller logs: tmp/windows-build-ca668e4420dd489bb40a3a2495f8c724,
  tmp/windows-build-bd593a1e98d54b37a930afddb0e009c8,
  tmp/windows-build-fb00487d90cf4267ad10836839fc4ea8/pyinstaller.log.
- First exe --version и doctor --dry-run — PASS. Найдена CP1251 pipe output:
  entry теперь явно UTF-8; development direct_url/RECORD исключены из metadata.
- Первая packaged проверка: **3 passed / 1 failed, 21.51 s**. До failure реально
  прошли doctor/schema/repeat/import/GPU inference/DB RAW+READABLE/export/native GUI/
  missing model/read-only source и bundle. Failure — отсутствие sentinel-файла
  offline audit в первом build (hook ещё не писал ACTIVE). Добавлен явный ACTIVE,
  bundle пересобран; этот первый run не объявляется полностью PASS.
  Own PG остановлен, artifact ACL восстановлен finally.
  Артефакт: tmp/step03-pg-582da5d49bf745ab9d8411c8dd435f6b/checks.json.
- **PASS**: `scripts/check_postgresql.py --pytest-target tests --packaged-exe
  "dist/LocalTranscribe Windows x64/LocalTranscribe/LocalTranscribe.exe"`,
  PYTEST_REQUIRE_CUDA=1 и реальный VAD fixture: **443 passed, 2 skipped, 78.52 s**.
  SKIP только прежние opt-in direct hour/worker smoke без отдельных env flags;
  packaged integration действительно выполнялась, не заменялась mock/SQLite.
  Реальная PostgreSQL 18.3, Alembic upgrade/repeat/check/downgrade/base/upgrade/
  current 0003, Ruff check/format (106 files на том запуске), diff — PASS.
  Артефакт: tmp/step03-pg-12c3be9728b140c69d190fc765965d00/checks.json.
- **PASS** после добавления явных Unicode path round-trip asserts и документации:
  `scripts/check_postgresql.py --pytest-target tests/test_packaging.py
  --pytest-target tests/test_repository_audit.py --packaged-exe
  "dist/LocalTranscribe Windows x64/LocalTranscribe/LocalTranscribe.exe"`:
  **77 passed, 0 skipped, 21.56 s**. Package tests повторно прошли с полным build.
  До этого preflight format check обнаружил CRLF после Windows write_text нового
  assert; ruff format нормализовал LF, финальный runner format — PASS (109 files).
  Артефакт: tmp/step03-pg-afc7ddc503ae474f9ac665de3a4cf566/checks.json.
- Реальный packaged smoke: --version/--help/doctor, head/repeat migrations,
  inspect/import source с кириллицей/пробелами/& и read-only attribute,
  cold spawned CUDA worker (реальная речь из public FLEURS, 8 s), SQL COMPLETED/
  segments>0/RAW+READABLE, TXT export, native visible GUI и WM_CLOSE exit 0.
  PATH только System32, fresh AppSettings/env data dirs, app folder deny-write ACL
  реально проверен PermissionError. Source SHA и набор bundle files неизменны;
  ACL восстановлен в finally. Own clusters обоих успешных runs остановлены.
- Negative packaged case missing model — корректный nonzero, без пароля и без
  авто-download; source сохранён. Frozen doctor probe и _MEIPASS CUDA directory
  unit regressions — PASS. Аудит Python sockets подтверждён ACTIVE в actual exe/
  worker, REMOTE_ATTEMPT нет, HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE включены.
  Это конкретная проверка Python/offline local-model flow, не OS firewall trace.
- **PASS**: `uv lock --check` (66 packages), Git excludes dist/tmp, preservation
  AGENTS/ORIGINAL_TZ/requirements/implementation_plan/src/main.py/.gitignore.
  Vendor notices: Python, Qt LGPL/GPL, NVIDIA wheels, PyInstaller bootloader
  exception, CTranslate2/tokenizers/flatbuffers/Silero и wheel third-party notices.
  Build audit не нашёл .env/private media/основной model/known credential prefixes;
  scanner ограничен explicit-input checks/allowlists/известными prefix patterns.
  Код сборки и artifacts не опубликованы/не подписаны/не запушены.

## Финальный аудит metadata и повтор

При последней проверке уже собранного dist обнаружено: automatic PyInstaller
metadata hook повторно добавил direct_url.json и несколько RECORD, несмотря на
фильтр explicit copy_metadata. Это metadata разработки, не исходники/пароли.
Исправлено финальным фильтром Analysis.a.datas в spec и fail-guard в audit_bundle;
regression tests теперь отвергают эти файлы и проверяют их отсутствие в реальном
packaged artifact. В собственном проверенном dist удалены только generated
*.dist-info/direct_url.json и RECORD, source/model/user files не затронуты.
Post-collection filter записан в build-manifest, input hashes обновлены, inventory
пересчитан: окончательно **1174 files / 2499670521 B** (без самого inventory).
Frozen code не менялся. SHA-256 остальных файлов после GUI/GPU испытаний совпали.

`scripts/check_postgresql.py --pytest-target tests/test_packaging.py
--pytest-target tests/test_repository_audit.py --packaged-exe
"dist/LocalTranscribe Windows x64/LocalTranscribe/LocalTranscribe.exe"` после fix:
**77 passed, 0 skipped, 21.12 s**, включая Unicode path/filename equality,
actual CUDA/PG/native GUI/read-only/offline и no-direct_url/RECORD regressions.
Alembic upgrade/repeat/check/downgrade/base/upgrade/current 0003, Ruff check,
format (109 files на этом запуске), git diff --check — PASS. Own PG остановлен,
ACL восстановлен. Артефакт: tmp/step03-pg-b1d51d58cf7949029536ae64440d53e0/checks.json.
Предыдущая полная регрессия 443 passed/2 skipped относится к тому же frozen code;
после metadata-only filter повторена целевая packaged/documentation regression.

## Файлы ШАГА 16

Созданы bundling/LocalTranscribe.spec, entry.py, offline_audit.py,
license-sources.json и 7 upstream license texts; scripts/build_windows.py;
infrastructure/database/migrate.py; tests/test_packaging.py; docs/windows_setup.md,
user_guide.md, third_party_notices.md. Изменены __main__.py, doctor.py,
faster_whisper_engine.py, scripts/check_postgresql.py, pyproject.toml/uv.lock,
README/tests README и architecture/decisions/progress/requirements_traceability.
Основной pipeline/Domain/GUI бизнес-логика не переписывались; точки source entry
сохранены. Existing tests/models/user files/working DB/service не удалялись.

## Ручной чек-лист remaining setup acceptance

1. На отдельном чистом Windows 11 x64/профиле (затем Windows 10 при поддержке)
   скопировать весь onedir, подготовить driver/VC runtime, внешние FFmpeg/PG/model.
2. По windows_setup создать свою role/DB/.env, db-upgrade → doctor → GUI.
3. При отключённом внешнем интернете выполнить import/transcribe/export и
   проверить оригинальный OBS playback/codec/таймкоды/закрытие приложения.
4. Подписать фактическое окружение/результат; до этого clean-OS/offline-native
   gates остаются NOT RUN. Старый ≥3h/two-track/manual OBS долг не закрывается
   замером available 95min/FLEURS или текущим native packaged GUI smoke.

## Ограничения и критерии приёмки

Отдельный настоящий чистый Windows account/VM — NOT RUN: VM не предоставлена,
WindowsSandbox.exe отсутствует. Изолированные env/data dirs не выдаются за
чистую ОС. Windows 10 отдельно — NOT TESTED. Offline Python socket guard/HF flags
не подменяют физически отключённую сеть/OS firewall/native network trace.
Свой project licence владельцем не назначен; публикация/инсталлятор/signing не
выполнялись, vendor notices не назначают лицензию проекта. Недоступные gates ШАГА 15
сохранены. Для READY FOR STEP 17 требуется фактическая приёмка setup на чистой
целевой ОС либо явное разрешение владельца продолжить с этим долгом.

Документы: [windows_setup.md](windows_setup.md), [user_guide.md](user_guide.md),
[third_party_notices.md](third_party_notices.md). Следующий этап — ШАГ 17 только
по отдельному запросу; эта работа его не начинает.

---

# Состояние проекта

Дата: 2026-10-14.

## Архив: ШАГ 15 (до разрешённого перехода)

ШАГ 15 — нагрузочные и качественные E2E тесты на реальном ПК.
**IMPLEMENTED / PUBLIC QUALITY PASS / VERIFICATION PARTIAL — BLOCKED FOR STEP 16**.
Harness/длинные OBS прогоны выполнены. Эталонная публичная quality проверка
FLEURS ru_ru выполнена, primary corpus WER ≤15% достигнут. Не закрыты остальные
исходные gates: ≥3h/original OBS two-track MKV и ручной GUI/playback/quality review.
Пользователь подтвердил, что доступен только 95min MP4, и разрешил найти публичные
эталоны вместо ручной расшифровки собственного видео. Отсутствующие scenarios
не объявляются проверенными; ШАГ 16 в этом запросе не разрешён/не начат.
По запросу владельца ШАГ 14 закоммичен и запушен: `a9b706e`, origin/main.
После push рабочее дерево было чистым. Разрешение следующего этапа относится
к ШАГУ 15, не снимает долг ручной original OBS MKV/MP4 приёмки ШАГА 13.
CPython 3.14.4, существующая .venv; добавлена только dev psutil 7.2.2.
Модели/CUDA/глобальный Python/системные службы не устанавливались и не изменялись.
ШАГ 16 не начат. Изменения ШАГА 15 не коммитились/не пушились.

## Дополнение ШАГА 15: публичная оценка качества — 2026-10-14

По запросу владельца самостоятельно найден и скачан Google FLEURS ru_ru test,
CC BY 4.0, revision 70bb2e84b976b7e960aa89f1c648e09c59f894dd. Первые 32 WAV по порядку
pinned test archive зафиксированы до inference, 31 уникальный sentence ID,
406.620 s / 24.82 MiB WAV. Эталоны — raw_transcription поставщика, не Whisper
output и не MANUAL. Модель и production pipeline не менялись, новые зависимости
не устанавливались. Исходные пользовательские записи не отправлялись в сеть.

- **PASS**: 32/32 real cuda float16 GPU cases с отдельной PostgreSQL 18.3/random
  schema, прежним VAD и RAW/READABLE/4 exports. Ошибок recognition infrastructure/
  RSS/VRAM sampler нет; own cluster остановлен. Cold-worker wall sum 159.777 s.
- **PASS, primary corpus quality goal на этой подвыборке**:
  WER **14.1123%** (93/659),
  CER **3.1564%** (151/4784).
  Прежний nfc-casefold-whitespace-v1 сохраняет пунктуацию; corpus WER ≤15%.
- Дополнительный заранее объявленный punctuation-space protocol:
  WER **7.9104%** (53/670),
  CER **2.4364%** (114/4679).
  Primary не менялся. Micro-average по сумме errors/reference units, не среднее
  индивидуальных процентов. 0 failure cases исключено из denominator.
- **PASS**: `scripts/check_postgresql.py --pytest-target tests/test_public_benchmark.py
  --pytest-target tests/test_benchmark.py --pytest-target tests/test_repository_audit.py
  --benchmark-manifest tmp/fleurs-ru-test-32/manifest.json`: **96 passed, 6.96 s,
  0 skipped**; python 3.14.4, Alembic upgrade/repeat/check/downgrade/base/upgrade/
  current 0003, Ruff check/format (101 files), git diff --check — PASS.
- **PASS**: `scripts/public_benchmark.py score tmp/fleurs-ru-test-32
  tmp/step03-pg-95b78fa5209444edbdb01cc1d67067a1/benchmark/benchmark.json`:
  проверены SHA-256 каждого audio/reference и equality exported RAW vs in-pipeline
  quality; сохранены strict/secondary corpus counts и provenance digest.
- Артефакты: tmp/fleurs-ru-test-32/{manifest,provenance,test.tsv,*.wav,*.txt};
  tmp/step03-pg-95b78fa5209444edbdb01cc1d67067a1/{checks.json,benchmark/quality-summary.json}.
  Всё остаётся локально и ignored, источники/модели/рабочая БД не изменены.
- Созданы infrastructure/public_benchmark.py, scripts/public_benchmark.py,
  tests/test_public_benchmark.py; обновлены benchmark/progress/матрица/ADR/test docs.
  Предыдущие 18 незакоммиченных файлов ШАГА 15 сохранены. Commit/push не выполнялись.

Ограничения: это 32 коротких read-speech utterances, не весь test corpus и не
диалог с HR/OBS noise/technical terms. Индивидуальный WER до 61.54%, поэтому
средний <15% не обещает точность каждой реплики. Не утверждается, что публичные
данные не встречались при pretraining Whisper; самостоятельно эталоны не
прослушивались заново. Ручная расшифровка собственного видео для этой проверки
больше не требуется. Остальные gates текущего исходного ТЗ остаются NOT TESTED/
NOT RUN, не снимаются молча. Методы/источники — [benchmark.md](benchmark.md).

Финальный повтор после обновления документации:
`uv run pytest -q tests/test_public_benchmark.py tests/test_benchmark.py
 tests/test_repository_audit.py` — **96 passed, 3.05 s, 0 skipped**;
Ruff check/format (101 files), git diff --check — PASS. Git check-ignore
подтвердил исключение manifest/provenance/quality-summary и исходных public media.
Новая full-suite regression в этом дополнении не запускалась: production код
не менялся; прежние 431 passed/2 skipped относятся к предыдущему полному прогону.

## Реализовано в ШАГЕ 15

- Reproducible JSON manifest/cases, отдельный dev launcher и расширение owned
  PostgreSQL test runner; shared prepare_task с CLI, real cold GPU worker,
  local-only модели, fallback/download off для измерений.
- Wall/audio duration/RTF, sampled process-tree RSS и whole-device VRAM с baseline,
  streamed JSONL events/resources, environment/model/source fingerprints,
  chunk/segment counts/error classes. Private owned output, original untouched.
- Real PG → RAW/READABLE → TXT/SRT/JSON/MD, chunk coverage/таймкоды; own worker
  kill после committed midpoint, INTERRUPTED → restart/resume, compare checkpoint
  identities/digests/attempt/completion и отсутствие duplicate chunk keys.
- RAW per-track WER/CER только с независимым reference и явной нормализацией;
  empty/malformed/budget scenarios не подменяются фиктивными оценками.
- [Протокол и измерения](benchmark.md), [manifest example](benchmark.example.json),
  architecture/ADR/матрица/README/test instructions.

## Проверки ШАГА 15

- Initial focused uv pytest: 16 passed, 25 setup errors из-за недоступного
  системного pytest-of-jke. Повтор с новой собственной PYTEST_DEBUG_TEMPROOT:
  `uv run pytest -q tests/test_benchmark.py tests/test_cli.py` — **41 passed, 6.30 s**.
- `scripts/check_postgresql.py --benchmark-manifest tmp/step15-manifest.json`
  с PYTEST_REQUIRE_CUDA=1/реальным VAD fixture: **429 passed, 2 skipped, 67.17 s**;
  отдельно database unit **83 passed, 0.94 s**, real PG **38 passed, 2 skipped, 29.15 s**.
  SKIP: старые direct-hour/worker smoke без своих explicit environment paths;
  новые real GPU gates выполняются через harness, skip не объявляется PASS.
- Первая orchestration остановилась до benchmark на Ruff-format после добавления
  type hints во время проверок; формат исправлен. Own cluster остановлен.
  Артефакт: tmp/step03-pg-8a4b957d01014e2181a64110c41f3102/checks.json.
- Повтор после исправления: `scripts/check_postgresql.py --pytest-target
  tests/test_benchmark.py --pytest-target tests/test_cli.py --pytest-target
  tests/test_postgresql.py --benchmark-manifest tmp/step15-manifest.json`:
  **79 passed, 2 skipped, 33.08 s**; Alembic upgrade/repeat/check/downgrade/base/
  upgrade/current 0003_audio_timeline, Ruff и git diff --check — PASS.
- Real benchmark выполняется в отдельном PostgreSQL 18.3/random schema:
  tmp/step03-pg-e0b3464ae42644e1bb1bf338fc68cb3d/benchmark/benchmark.json.
  На момент записи первый 5 min prefix — wall 20.802 s, RTF 0.069341,
  RSS 1812992000 B, whole-GPU VRAM 4552916992 B (baseline 2073034752 B),
  1 chunk/481 segments/35 samples, timeline/RAW/READABLE/4 exports — PASS.
  Исходный набор затем завершился: hour 209.777 s/RTF 0.058272,
  crash/resume 201.841 s/RTF 0.056067, EOF 13.1 s source за 4.810 s — PASS.
  Crash после 6/12 chunks: INTERRUPTED → restart/resume, прежние checkpoints
  неизменны, финально 12 chunks/4652 segments, без дублей. Source ≥3h отсутствует:
  соответствующий case — NOT TESTED (не удлинялся synthetic looping).

- При ревизии воспроизводимости обнаружено: Git HEAD/diff не включал новые
  untracked modules. Добавлен SHA-256 source snapshot (без .env) и regression test;
  sampler thread/output failure теперь сообщает FAIL, не перезаписывает файл и
  не подменяет отсутствующие метрики. Private DiagnosticLog lifecycle соблюдён.
- Финальная полная проверка `scripts/check_postgresql.py --pytest-target tests
  --benchmark-manifest tmp/step15-final-manifest.json` — **431 passed, 2 skipped,
  64.17 s**. По pytest markers: **380 not integration/gpu passed; 50 integration
  passed + 2 skipped; 1 actual CUDA runtime passed**. Real PostgreSQL 18.3,
  FFmpeg/VAD/native Qt/Windows worker regressions включены. Старые 2 opt-in GPU
  smoke не запускались, новый harness отдельно выполнил реальные inference gates.
  Final 5min case: 19.384 s, RTF 0.064614, 1 chunk/481 segments — PASS.
  Alembic upgrade/repeat/check/downgrade/base/upgrade/head 0003, Ruff check,
  Ruff format (98 files), git diff --check — PASS; own cluster остановлен.
  Артефакт: tmp/step03-pg-d95d0c94f91b41e794da45a23c2e99e2/checks.json.
- Владелец подтвердил имеющийся файл 2026-08-30 16-04-02.mp4 (~95 min),
  более длинных нет. Дополнительный full-source GPU E2E:
  `scripts/check_postgresql.py --pytest-target tests/test_benchmark.py
  --benchmark-manifest tmp/step15-full95-manifest.json` — **15 passed, 0 skipped,
  0.97 s** до GPU; настоящий pipeline обработал 5717 s / 4.405 GB целиком за
  **322.383 s**, RTF **0.056390**,
  20 chunks/11943 segments,
  sampled RSS 1848311808 B,
  whole-device VRAM 4652531712 B — **PASS**.
  EOF/coverage/timeline/RAW/READABLE/4 exports проверены; memory sampler errors=0,
  original fingerprint не изменился, системная служба/рабочая БД не изменялись.
  Alembic/Ruff/diff и stop owned cluster — PASS.
  Артефакт: tmp/step03-pg-57bb19ade00a4f18aaae1b5c063db5e4/checks.json.
- Сводка реальных hardware cases: **6 PASS**, отдельный ≥3h case **NOT TESTED**;
  quality WER/CER без эталона **NOT RUN**. Цель 60 min ≤15 min достигнута на одном
  measured prefix, не обещается на иных источниках/моделях/профилях.

- После финального заполнения документации: `uv run pytest -q
  tests/test_repository_audit.py` — **73 passed, 1.88 s**; `uv run ruff check .`,
  `uv run ruff format --check .` (98 files), `git diff --check` — **PASS**.
  `uv lock --check` — **PASS**, 59 packages. Internal links/обязательные документы
  согласованы; known credential-prefix scan новых/изменённых UTF-8 файлов — 0
  matches (ограниченная проверка, не universal secret detector).
  `git check-ignore` подтверждает .env/.venv/tmp manifests/models/recordings/
  transcripts/logs. `git diff --exit-code` подтверждает сохранность AGENTS,
  ORIGINAL_TZ/requirements/implementation_plan/migrations/main.py/.gitignore.
  После всех hardware runs отдельно пересчитаны исходные fingerprints пяти cases:
  **PASS**, исходники не изменены. `main...origin/main`: 0/0, HEAD a9b706e;
  только 18 файлов ШАГА 15 остаются изменёнными/новыми, собственные helpers удалены.

## Не выполнено / ограничения

- В Videos максимальная запись 5717 s (~95 min), все 22 MP4 с одной дорожкой.
  Original MKV >1GB с двумя OBS audio streams и ≥3h записи не предоставлены:
  NOT TESTED. Real >1GB MP4 проверен, remux/дублирование дорожки не выдавались
  за отсутствующую original OBS fixture.
- Для original OBS записей независимый эталон/ручные профили отсутствуют:
  WER/CER на них NOT RUN. Публичная FLEURS quality проверка теперь выполнена выше;
  NOT RUN больше не относится ко всей оценке ASR.
  Тишина/границы unit/integration (включая реальный Silero silence/partial frame)
  не заменяют прослушивание реальных speech spans. Noise/technical terms/omissions/
  false repeats по эталону и подписанные человеческие профили — NOT RUN.
- Manual original OBS playback ШАГА 13 — NOT RUN. Общая готовность MVP не заявляется.
- RSS/VRAM sampled, VRAM включает посторонние приложения. Нет раздельного stage
  profiling, bottleneck не приписывается компоненту без измерений; оптимизации нет.

## Созданные и изменённые файлы ШАГА 15

Созданы: scripts/benchmark.py; src/local_transcriber/infrastructure/benchmark.py,
benchmark_resources.py, benchmark_quality.py, transcription_task.py;
tests/test_benchmark.py; docs/benchmark.md, docs/benchmark.example.json.
Изменены: infrastructure/transcribe_cli.py (общая task composition, CLI preserved),
scripts/check_postgresql.py, pyproject.toml/uv.lock (только dev psutil), README.md,
tests/README.md; docs/architecture.md, decisions.md (ADR-095–099), progress.md,
requirements_traceability.md. Original ТЗ, нормализованные requirements, migrations,
src/main.py, GUI/Domain/pipeline алгоритмы не пересоздавались.

## Ручной чек-лист оставшейся приёмки

- Предоставить реальную ≥3h запись и original OBS MKV >1GB с двумя независимыми
  audio streams; заполнить local manifest и выполнить тот же harness.
- Согласовать normalization и независимый human reference по дорожке/диапазону;
  отдельно чистая речь (WER цель ≤15%), шум, терминология, тишина/повторы/пропуски.
- Прослушать границы chunks/последнюю речь и сравнить таймкоды, подписать reviewer/
  date/case/profile, закрыть original OBS playback MKV/MP4 долг ШАГА 13.
- Результаты хранить локально; не коммитить записи/эталоны/экспорты/.env/cluster.

## Критерии готовности и следующий этап

ШАГ 15 будет принят после фактических hardware measurements, crash/resume,
длинной ≥3h/original MKV/two-track и ручной quality/reference проверки.
Недостающие gates не считаются пройденными. Следующий этап — ШАГ 16 только
по отдельному разрешению после приёмки либо явного принятия оставшегося долга.

---

# Состояние проекта

Дата: 2026-10-13.

## Архив: ШАГ 14 (состояние на момент сдачи)

ШАГ 14 — устойчивость, приватность и журналирование.
**READY FOR STEP 15** по реализации и проверкам этого этапа; ШАГ 15 не начат.
CPython 3.14.4, прежняя .venv; никаких новых библиотек/моделей/CUDA/migrations.
ШАГ 13 по разрешению владельца закоммичен/запушен: `b11e4c4`, origin/main.
Новый запрос «сделай что дальше требуется» принят как разрешение ШАГА 14 с явно
сохранённым долгом: ручная Windows original OBS MKV/MP4 проверка шага 13 — NOT RUN,
сама приёмка ШАГА 13 не объявляется завершённой. Это не разрешение считать весь MVP готовым.
Изменения шага 14 не коммитились/не пушились, пользовательские данные не удалялись.

## Реализовано

- Strict JSON diagnostics только time/event/level/job UUID; никаких raw log messages,
  args, exception text/traceback/paths/transcripts/passwords. Rotation 1 MB ×4,
  journal write/close failure не печатает приватный record и не ломает успешную операцию.
- Dedicated managed dirs + ownership markers/private Windows DACL; custom/source
  parents не chmod/recurse. После ACL отказа удаляется только только что созданный
  пустой собственный dir, безопасный retry проверен на Windows.
- Secrets удаляются из окружения FFmpeg/ffprobe/doctor/ACL tools, subprocess shell=False;
  FFmpeg/ffprobe file,pipe protocols, Qt file-only + suppressed media dumps/raw messages.
  Scoped Qt policy восстанавливается при завершении, исходные media не копируются.
- ManagedTempFiles exact registration, per-job OS lease, validated bounded registry/
  scan и 24 h TTL из AppSettings; normal fresh/retained/source/unknown files не чистятся.
  Повреждённый реестр/traversal/symlink/junction/hardlink отказ, cleanup report/retry.
- RecordingDecoder в real worker пишет registered bounded WAV без overwrite; старые
  незарегистрированные intermediate files не присваиваются новой политике.
- Явное удаление session из GUI/CLI: DB locks/active rejection/FK transaction cascade;
  source protection metadata до DELETE, originals/custom dictionary/exports сохраняются.
  Registered WAV source flag переживает удаление DB metadata. FS cleanup после DB commit
  opt-in; partial cleanup_pending и explicit job UUID retry. Исходные OBS никогда unlink.
- GUI default No/derived checkbox; selection UUID snapshot до modal confirmation,
  запрет при editor/active/queue; REMOVED обновляет таблицу/состояние. Terminal event
  priority при bounded progress overflow. Прежний graceful worker shutdown сохранён.
- .env.example/README/architecture/ADR/traceability/testing обновлены. Consent участников
  упомянуто без заявления о конкретных правовых требованиях для юрисдикции пользователя.

Созданы application/maintenance.py; infrastructure/{privacy,diagnostics,temp_storage,
maintenance_cli}.py; infrastructure/database/history_store.py; tests/test_privacy.py.
Изменены __main__.py, application/export.py, infrastructure/{desktop_backend,doctor,
export_cli,export_files,ffmpeg_decoder,media,settings,intermediate_audio,transcribe_cli,
worker_manager,worker_process}.py, ui/{window,results,bridge,bootstrap}.py,
scripts/check_postgresql.py, tests/test_postgresql.py, .env.example, README.md,
tests/README.md, docs/{architecture,decisions,requirements_traceability,progress}.md.
Python пути выше относительно src/local_transcriber/. requirements/ORIGINAL_TZ,
pyproject/uv.lock/.gitignore и existing source/launchers сохранены.

## Реально выполненные проверки

| Команда / сценарий | Результат |
| --- | --- |
| Python --version / окружение | PASS: CPython 3.14.4, существующая .venv. |
| Initial privacy/desktop/results | 23 passed, 1 failed in 7.30s; Windows icacls /save UTF-16LE без BOM. Исправлено только чтение test artifact. |
| Isolated PG runner: privacy/desktop/results/CLI/worker + 3 PG targets + doc links | PASS: 65 passed in 21.51s, без SKIP; реальная PostgreSQL 18.3 test DB/random schemas, cluster остановлен. |
| PG deletion | PASS: CLI подтверждение/cascade media/audio/jobs/chunks/segments/RAW+READABLE+MANUAL, original bytes/unknown files/shared terms preserved, restart history empty/no worker. |
| PG failures | PASS: active session reject; real SQL integrity/schema fault rolls back parent+children; unavailable loopback endpoint даёт безопасный PersistenceError без секретов. Физическое повреждение PostgreSQL files не моделировалось. |
| Worker crash/checkpoints/recovery | PASS: существующий real spawn/PG scenario (synthetic executor, не CUDA/STT) pause→kill→INTERRUPTED→restart→resume→cancel, подтверждённые checkpoints сохранены. |
| Alembic upgrade/repeat/check/downgrade/upgrade/current | PASS: head 0003_audio_timeline, No new upgrade operations detected; новых migrations нет. |
| Focused privacy/media/decoder/export/doctor/settings | PASS: 120 passed in 12.25s, без SKIP, после managed WAV/GUI selection regression. |
| После Qt protocol/log policy: privacy/desktop/media/decoder | PASS: 47 passed in 9.59s, без SKIP; fresh native Windows Qt load/messages без private output/Input dump при намеренно включённом debug env. |
| После ACL recovery: python -m pytest -q tests/test_privacy.py | PASS: 11 passed in 4.68s; real Windows DACL + safe retry, FFmpeg managed WAV/paths/env, native Qt, lease/registry/permission/log failures. |
| Ruff/diff в успешном PG runner | PASS: All checks passed, 91 files formatted, git diff --check. |
| Финальные проверки после docs/filename correction | PASS: uv pytest final targets — 62 passed in 9.97s, без SKIP; после уточнения job UUID отдельно 1 passed in 0.16s; Ruff All checks passed, 91 files formatted; git diff --check, uv lock --check (58 packages), внутренние ссылки — PASS. |
| Git exclusions / secrets / ownership | PASS: .env/.venv и конкретные log/model/media/recording/transcript/tmp paths игнорируются, git status не показывает пользовательские данные; новые password literals только synthetic; known credential/private-key pattern scan новых/изменённых файлов: 0 matches (не универсальный secret detector). git diff --exit-code подтвердил неизменность ORIGINAL_TZ/requirements/pyproject/uv.lock/src/main.py. |
| POSIX ACL/leases / full regression / real CUDA/new E2E | NOT RUN: целевая Windows, stage-specific checks; E2E/quality/performance — 15, не реализованы этим этапом. |
| Ручной original OBS MKV/MP4 gate ШАГА 13 | NOT RUN: долг сохранён по явному разрешению продолжения, не заменён native automatic smoke. |

Фактические команды:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
$env:PYTEST_QT_API = 'pyside6'
$env:PATH = (Join-Path (Get-Location) 'tmp/step04-tools/ffmpeg-9.0.2-essentials_build/bin') + ';' + $env:PATH
.\.venv\Scripts\python.exe scripts/check_postgresql.py --pytest-target tests/test_privacy.py --pytest-target tests/test_desktop.py --pytest-target tests/test_results.py --pytest-target tests/test_cli.py --pytest-target tests/test_worker.py --pytest-target tests/test_postgresql.py::test_history_delete_real_cascade_source_preservation --pytest-target tests/test_postgresql.py::test_history_active_corrupt_database_and_rollback --pytest-target tests/test_postgresql.py::test_worker_pause_cancel_and_crash_preserve_checkpoints --pytest-target tests/test_repository_audit.py::test_all_internal_document_links_resolve
uv run pytest -q tests/test_privacy.py tests/test_media.py tests/test_ffmpeg_decoder.py tests/test_export.py tests/test_doctor.py tests/test_settings.py
python -m pytest -q tests/test_privacy.py tests/test_desktop.py tests/test_media.py tests/test_ffmpeg_decoder.py
python -m pytest -q tests/test_privacy.py
uv run ruff check .
uv run ruff format --check .
git diff --check
```

FFmpeg/ffprobe paths и PYTEST_DEBUG_TEMPROOT задавались portable_bin/unique workspace
tmp/, никакая служба PostgreSQL/глобальный Python/working DB не менялись.
PG artifact: tmp/step03-pg-1c13df6442de48a0b08b0d0c136fd5ec/checks.json.
Native Qt проверка находится в test_privacy.py, auto media load/opacity, не human playback.
Фиксированные fake password/transcript literals в tests не являются пользовательскими секретами.

## Исправленные ошибки и ограничения

Устранены: DB secrets в media child env; стандартный logging.handleError disclosure
при disk-full; early ticket ошибочно мог считаться job UUID (исправлено/проверено); Qt media metadata dump; UTF-16LE/no-BOM ACL artifact reading; async
selection race при delete confirm; ACL refusal blocking safe retry; terminal ack
вытеснялся progress updates. Production behavior подтверждён целевыми regressions.

Файлы и БД не имеют общей транзакции: DB commit + cleanup_pending для FS.
Unknown/legacy WAV, user exports, stale roots, manifest swap orphans/metadata не
удаляются автоматикой. Retained WAV могут занимать место до explicit registered
derived deletion; source-flag WAV всегда защищены. Scan <=5000 dirs, registry <=1 MiB/
4096 entries; это не бесконечное хранилище. Текущий temp root обслуживается отдельно
от прежних пользовательских roots; неизвестные owned markers не реконструируются.
ACL не шифрует, Admin/SYSTEM/owner имеют доступ; ACL исходников/службы PG не менялся.
Windows local filesystem — проверенная цель; network FS/POSIX не объявляются проверенными.
Qt FFmpeg config private API требует повторения native privacy test при обновлении Qt.
Terminal deque не заменяет durable DB, сторонний caller должен регулярно poll.

## Критерии готовности / ручной чек-лист

- [x] Нет паролей/транскриптов в managed diagnostics, включая write failure/native Qt.
- [x] Safe processes/env/protocols/paths/export names, private owned ACL на Windows.
- [x] Auto cleanup по ownership/TTL/lease, retained/source/unknown preserved.
- [x] Confirmed session deletion, active rejection, transactional rollback/cascade,
  original/shared terms preserved, retryable derived cleanup.
- [x] Worker crash/restart/checkpoints, bounded events/queue, no secret/media Git additions.
- [x] Docs/traceability/ADR актуализированы; статус проверок различает actual/NOT RUN.

Ручная проверка в своей среде (не требуется удалять реальные записи для теста):
1. Открыть GUI, убедиться в понятной диагностике без DB/при inaccessible temp/log dirs.
2. На отдельной synthetic/imported session отменить «Удалить историю» — строка остаётся;
   подтвердить delete с нужным derived выбором — original должен остаться на диске.
3. При cleanup_pending закрыть writer/исправить права и повторить maintenance cleanup
   по прежнему job UUID; неизвестные файлы/экспорты не удалять этой командой.
4. Проверить diagnostics.jsonl: только разрешённые поля; при необходимости получить
   согласие участников до импорта и отдельно закрыть ручной playback gate шага 13.

Блокирующих проблем ШАГА 14 не выявлено. **READY FOR STEP 15**, только по новому
разрешению; ручной долг ШАГА 13 остаётся открытым и войдёт в общую релизную приёмку.

<details>
<summary>История ШАГА 13 и предыдущих этапов</summary>

# Состояние проекта

Дата: 2026-10-13.

## Текущий шаг

ШАГ 13 — PySide6: редактор, поиск и воспроизведение.
**IMPLEMENTED / MANUAL VERIFICATION PENDING — BLOCKED FOR ACCEPTANCE**.
CPython 3.14.4, существующая .venv; новых зависимостей/миграций нет.
По прямому разрешению пользователя завершённый ШАГ 12 закоммичен и запушен
в origin/main: `a923bcb`. Изменения шага 13 не коммитились/не пушились.
ШАГ 14 не начат. Программные критерии выполнены; обязательная ручная проверка
звука/видео на Windows original OBS MKV и MP4 ещё не подтверждена человеком.

## Реализовано

- «Открыть транскрипт» для completed job, отдельное окно результатов, повторное
  открытие из PostgreSQL без модели/worker; read-only snapshot последних версий.
- Virtual table: absolute start/end integer ms, stream_index, speaker_label, RAW
  segment text; поиск с подсветкой полного текста/строк, stream/role filters.
  1000 сегментов без отдельных widgets; debounce, heartbeat и latency проверены.
- RAW/READABLE read-only, MANUAL draft/save append-only. Черновик переживает mode
  switch; failed save его сохраняет. RAW UUID/content не изменяется в настоящей DB.
- Экспорт выбранной сохранённой версии TXT/SRT/JSON/MD прежним ExportService и
  atomic writer; overwrite подтверждается. MANUAL unaligned SRT отвергается,
  исходник/версии не меняются, никакого STT. Unsaved MANUAL требует сохранения.
- Qt Multimedia: original local source path, video/audio, pause, ms seek,
  proportional slider без int32 ограничения времени; positionChanged подсвечивает
  исходные active segments/overlap. Follow учитывает фильтр, Qt audio-track selector.
- Missing source/corrupt container/codec error оставляют текст/правки/экспорт.
  Текст/воспроизведение не смешиваются с вымышленным alignment ручных правок.
- Result requests/events коррелируются UUID; БД/save/export в background actor.
  Escape/close/main exit защищают dirty/saving. .env нельзя сменить при открытых
  результатах. CLI сохранён, help обновлён; placeholder читаем в тёмной теме.

Созданы `src/local_transcriber/application/results.py`, `src/local_transcriber/ui/results.py`,
`tests/test_results.py`. Изменены `src/local_transcriber/__main__.py`,
`src/local_transcriber/infrastructure/desktop_backend.py`, `src/local_transcriber/ui/{window,bridge,bootstrap}.py`,
`tests/{test_cli,test_postgresql}.py`, `README.md`, `tests/README.md`,
`docs/{architecture,decisions,requirements_traceability,progress}.md`.
pyproject/uv.lock/.gitignore/Python/схема БД и оригинальное ТЗ не изменены.
Собственные временные helper scripts удалены; artifacts остаются в ignored tmp/.

## Реально выполненные проверки

| Проверка / команда | Результат |
| --- | --- |
| Python --version | PASS: Python 3.14.4, прежняя .venv. |
| uv run pytest -q tests/test_results.py tests/test_desktop.py | PASS: первичный 13 passed in 4.71s. |
| Первый isolated PG runner | FAIL: 14 passed, 1 failed in 5.18s; только ожидание TXT без финального LF. Исправлена проверка, формат экспортера сохранён. |
| Повтор isolated PG runner, results/desktop/PG editor/doc links | PASS: 16 passed in 5.08s, без SKIP; PostgreSQL 18.3 настоящая, отдельная test DB/random schema, cluster остановлен. |
| Unit/Qt/editor scenarios | PASS: 1000/search/highlight/roles/stream/seek, RAW mode immutable, MANUAL draft/save/export, failed save/close guards, empty/missing source. Test doubles явно отделены от DB proof. |
| Real PG editor integration | PASS: новая MANUAL, RAW id/content preserved, реальный TXT, failed MANUAL SRT, reload fresh adapter, manager None. |
| Real Qt WAV | PASS: decode/load duration 3000 ms, seek 1500 ms, playback position >1600, pause и общая шкала. |
| Alembic upgrade/repeat/check/downgrade/upgrade/current | PASS: head 0003_audio_timeline; No new upgrade operations detected. Новых migrations нет. |
| Native Windows OBS MP4 H.264/AAC | PASS (automated): original source, 13100 ms, seek 1000, playing +17 frames, pause, NoError, exit 0. |
| Native Windows MKV remux fixture H.264/AAC | PASS (automated): 6-second own fixture из OBS MP4, 6037 ms, seek 1000, +18 frames, pause, NoError, exit 0. Не original OBS MKV. |
| Native DPR 1.5 / visual synthetic screenshot | PASS: MP4 +19 frames, seek/pause, NoError, exit 0; screenshot просмотрен, личный video frame скрыт. |
| Последний focused uv pytest после corrupt-container test | PASS: 42 passed in 8.74s (results 6 + desktop 8 + CLI 28), без SKIP. Настоящий corrupt MP4 оставляет текст. |
| Финальные pytest/Ruff/format/diff/doc links | PASS после всех правок: 43 passed in 8.49s (results 6 + desktop 8 + CLI 28 + links 1); Ruff All checks passed, 84 files formatted; git diff --check, uv lock --check (58 packages) и gitignore — PASS. |
| Ручное прослушивание/визуальная sync на original OBS MKV и MP4 | NOT RUN: человеческое подтверждение отсутствует, MKV в Videos (включая подпапки) не найден. Поэтому gate приёмки остаётся BLOCKED. |
| Full regression / CUDA inference / 3-hour stress | NOT RUN: целевые проверки этого этапа; распознавание не менялось, не запускалось. |

Фактические команды из корня:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
$env:PYTEST_QT_API = 'pyside6'
.\.venv\Scripts\python.exe scripts/check_postgresql.py --pytest-target tests/test_results.py --pytest-target tests/test_desktop.py --pytest-target tests/test_postgresql.py::test_results_editor_real_postgresql_save_reload_export --pytest-target tests/test_repository_audit.py::test_all_internal_document_links_resolve
uv run pytest -q tests/test_results.py tests/test_desktop.py tests/test_cli.py tests/test_repository_audit.py::test_all_internal_document_links_resolve
uv run ruff check .
uv run ruff format --check .
git diff --check
```

Focused pytest использует отдельный PYTEST_DEBUG_TEMPROOT в tmp/ (Windows ACL).
Успешный real PG runner: `tmp/step03-pg-312a13ab8600453fa9d83a1a69ca0292/checks.json`.
Первичный assertion failure: `tmp/step03-pg-f47bee3eda324845aba03fc77749c0fe/checks.json`.
Native metrics: `tmp/step13-native/{obs-mp4,obs-mkv-remux,obs-mp4-dpr150}.json`.
Temporary native script использовал QT_QPA_PLATFORM=windows, synthetic 1000 rows,
muted audio и реальные QMediaPlayer/videoSink frames; не real STT/ручное прослушивание.
Fixture remux: `ffmpeg -nostdin -n -i OBS_MP4 -t 6 -map 0 -c copy tmp/step13-native/obs-fixture.mkv`;
исходный OBS MP4 не изменялся. Видео/транскрипты не отправлялись внешним сервисам.

## Ограничения кодеков и найденные ошибки

Подтверждены H.264 High + AAC LC в OBS MP4/MKV fixture и WAV PCM16/16kHz.
Несовместимый настоящий codec в предоставленном наборе не найден; другие codecs
(AV1/HEVC/Opus и т.д.) не объявляются проверенными. Corrupt MP4 реально вызывает
Qt FormatError и не скрывает транскрипт. Qt FFmpeg log сообщает UDTA retry/AV1 encoder
MFT probe warning при этом H.264 playback успешен, это не доказательство AV1 decoder failure.
Проигрывание может seek к ближайшему keyframe; segment target хранится в ms.
Qt audio-track ordinals не равны ffprobe indices; дорожка выбирается явно.

Исправлены: UTF-16 highlight offsets для emoji; correlation failed-save/queue-full;
Escape и main-close guards; filtered active-row follow; readable dark placeholder;
CLI help regression актуализирован без изменения entrypoints. Ошибка теста о TXT LF
исправлена с сохранением прежнего формата. Нет новых production data/migration bugs.

В памяти GUI находятся текст/segment snapshot, не PCM/медиа. Pagination по очень
большим transcript/history не добавлена. Окно показывает последние RAW/READABLE/MANUAL,
прошлые ревизии сохранены в БД. Полный текст не фильтруется, только исходная таблица.
MANUAL alignment отсутствует. Для legacy completed jobs без RAW использовать
существующий text raw/readable; новые GUI jobs формируют версии автоматически.
Dictionary CRUD остаётся прежним CLI шага 10. Поиск по всей PostgreSQL — вне MVP.

## Критерии приёмки и ручной checklist

- [x] Прочитать/найти/исправить/сохранить/экспортировать без модели.
- [x] Тесты 1000 segments, time selection, MANUAL/RAW preservation, missing/empty/corrupt.
- [x] Реальная PostgreSQL и реальный Qt playback, ошибки сохраняют пользовательские данные.
- [x] Targeted regression, Ruff/diff/docs и матрица/ADR актуализированы.
- [ ] Ручной Windows original OBS MKV и MP4, звук/кадр/sync/codecs.

Для закрытия последнего gate:
1. Запустить `uv run python -m local_transcriber gui --env-file PATH` с рабочей локальной DB.
2. Открыть completed transcript, проверить поиск/фильтр, mode switch и новую MANUAL;
   вернуться RAW, экспортировать сохранённый TXT/JSON, RAW/READABLE SRT.
3. На original OBS MP4 и MKV выбрать нужный звук плеера, послушать начало/середину,
   кликнуть timecode, проверить кадр/звук/active row и pause; записать codecs/результат.
4. Для неподдерживаемого codec подтвердить diagnostic и доступность текста; отсутствие
   исходника не мешает сохранению/экспорту. Файл для этой проверки отдельно не удалять.

Блокирующих дефектов реализации не обнаружено; статус **BLOCKED FOR ACCEPTANCE**
обусловлен невыполненным обязательным ручным gate из ШАГА 13. ШАГ 14 не начинается.
После подтверждения ручной проверки обновить progress; продолжать только по новому
явному разрешению владельца, не автоматически.

<details>
<summary>История ШАГА 12 и предыдущих этапов</summary>

# Состояние проекта

Дата: 2026-10-13.

## Текущий шаг

ШАГ 12 — PySide6: импорт, настройки и список заданий. **READY FOR STEP 13**.
Python 3.14.4, существующая .venv; PySide6 6.12.0, pytest-qt 4.5.0.
ШАГ 13 не начат. До реализации по прямому разрешению владельца ШАГ 11
закоммичен и запушен: `01db477`, origin/main. Изменения шага 12 не коммитились/не пушились.
При подготовке предыдущего коммита staged whitespace check нашёл предусмотренные
конечные пустые строки golden: .gitattributes дополнили whitespace=-blank-at-eof
только для synthetic .golden, сохранив их byte-exact содержимое.

## Реализовано

- Русский MainWindow, тёмная Fusion/QPalette тема, адаптивный splitter/scroll,
  выбор одного/нескольких файлов и local-only drag/drop, список записей и метаданные.
- Реальные stream_index/кодек/каналы/rate/language/title, выбор нескольких дорожек
  по отдельности; редактируемые пользовательские роли, без угадывания говорящих.
- Модель/ru/CUDA или CPU/compute quality/VAD/keep intermediate audio.
  Модели только локальные; открытие GUI/истории не требует модели/GPU.
- Импорт через существующий ImportMedia/MediaRepository, история latest job/media
  в PostgreSQL (500 последних media), диагностика отсутствия БД и перечитывание .env.
- БД/ffprobe/hash/disk/READABLE вне UI: bounded background actor, queued Qt signals.
  Один lazy spawn-worker и прежняя FIFO; pause/resume/cancel, progress/error.
- Состояния кнопок по FSM; resume по saved manifest; новый start не присваивает
  себе UUID прошлой job. Pending до prepare виртуален, ранняя ошибка позволяет retry.
- Время обработки обновляется GUI timer между checkpoints; errors доступны в
  bounded диагностике. Завершение STT готовит RAW/READABLE существующим TextService.
- Role snapshot в job manifest → speaker_label новых segments, прежний RAW неизменён.
- Optional RecordingDecoder tee потоковых блоков в WAV по диапазонам <=15 min,
  temp_dir/intermediate/JOB_UUID; incomplete temp удаляется, complete WAV сохраняется.
  Free disk check учитывает длину/потоки, нет отказа только по размеру файла.
- Async closing handshake с manager shutdown, closed→Qt quit и explicit DeferredDelete:
  UI остаётся отзывчивым, найденный native high-DPI abort исправлен.
- Команда gui сохраняет прежние CLI/launchers; Python/GIL/global install не менялись.
  PySide6/pytest-qt установлены в .venv, pyproject/uv.lock обновлены, новых миграций нет.

Созданы application/desktop.py, infrastructure/desktop_backend.py,
infrastructure/intermediate_audio.py, ui/{__init__,bridge,window,bootstrap}.py,
tests/test_desktop.py. Изменены __main__.py, infrastructure/worker_process.py,
infrastructure/database/pipeline_store.py, pyproject.toml, uv.lock,
tests/test_cli.py, tests/test_postgresql.py, tests/README.md, README.md,
docs/architecture.md, decisions.md, requirements_traceability.md,
python314_compatibility.md и progress.md. Python пути относительно src/local_transcriber/.

## Реально выполненные проверки

Использовались изолированная PostgreSQL 18.3 test DB на loopback/random port,
random schemas, реальные ffprobe/FFmpeg/Windows spawn. Рабочая БД/служба не менялись,
собственные кластеры остановлены. В GUI integration распознавание явно synthetic
executor с test-only model files; это не объявляется реальным CUDA/STT.

| Команда / проверка | Результат |
| --- | --- |
| uv add pyside6==6.12.0; uv add --dev pytest-qt==4.5.0 | PASS после возобновления прерванной установки; существующая .venv/Python 3.14.4. |
| Первичный isolated runner: desktop/CLI/pipeline + 2 PG targets | PASS: 45 passed in 11.54s, без SKIP; Alembic/lint/format/diff — PASS. |
| Последний общий runner: desktop/CLI/pipeline/worker + 2 PG targets | 46 passed, 9 failed in 14.69s: только CLI help assertions на перенос argparse между «следующих» и «этапах». Функциональные Qt/worker/pipeline/PG сценарии прошли. |
| python -m pytest -q tests/test_cli.py tests/test_repository_audit.py::test_all_internal_document_links_resolve | PASS после исправления whitespace-normalized assertion: 29 passed in 8.07s. |
| python -m pytest -q tests/test_desktop.py tests/test_worker.py (FFmpeg in PATH) | PASS: 17 passed in 8.44s, без SKIP. Предыдущий focused run пропускал real FFmpeg child test, повтор устранил SKIP. |
| Последний python -m pytest -q tests/test_desktop.py после GUI timer | PASS: 8 passed in 3.14s, включая native shutdown regression. |
| Real PG GUI/import/role/RAW/READABLE/WAV/history | PASS: настоящая DB и FFmpeg/spawn, source bytes preserved, history после shutdown, worker не стартует при загрузке истории. |
| Real PG pipeline checkpoints/resume | PASS: роль совместима с существующей атомарной схемой/checkpoints. |
| Alembic upgrade/repeat/check/downgrade/upgrade/current | PASS в первом успешном runner, head 0003_audio_timeline, No new upgrade operations detected. Схема впоследствии не менялась. |
| Native Windows + visual inspection screenshots | PASS после fix: DPR 1.25 и 1.5, visible window, dark #1c2028, size 1180×760, exit 0; 64/62 heartbeat ticks за smoke. |
| uv run ruff check . / uv run ruff format --check . / git diff --check | PASS после всех правок: All checks passed, 81 files already formatted, whitespace ошибок нет. |
| uv lock --check | PASS: Resolved 58 packages. |
| Внутренние ссылки после progress / gitignore / secret patterns | PASS: 1 passed in 0.05s; .env и native artifacts игнорируются; указанных credential patterns в новых файлах не найдено. |
| Полный regression/новый реальный CUDA inference/3-hour stress | NOT RUN: целевые сценарии текущего этапа, GPU не требовалась; hardware/STT подтверждены прежними этапами. |
| Ручная пользовательская транскрибация через GUI | NOT RUN: native окно и снимки проверены, функциональная транскрибация здесь использовала mock/synthetic recognizer. |

В целевом наборе 55 разных сценариев: desktop 8, CLI 28, pipeline 8, worker 9,
PG 2. После исправлений все они прошли в соответствующих прогонах, но последний
общий runner не выдаётся за exit 0: CLI-исправление проверено отдельным набором,
без повторения уже прошедших DB/worker tests. Дополнительно прошла проверка ссылок.

Фактические команды из корня:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
$env:PYTEST_QT_API = 'pyside6'
$env:PATH = (Join-Path (Get-Location) 'tmp/step04-tools/ffmpeg-9.0.2-essentials_build/bin') + ';' + $env:PATH
.\.venv\Scripts\python.exe scripts/check_postgresql.py --pytest-target tests/test_desktop.py --pytest-target tests/test_cli.py --pytest-target tests/test_pipeline.py --pytest-target tests/test_worker.py --pytest-target tests/test_postgresql.py::test_desktop_real_import_history_roles_and_worker --pytest-target tests/test_postgresql.py::test_pipeline_checkpoints_and_resume
.\.venv\Scripts\python.exe -m pytest -q tests/test_cli.py tests/test_repository_audit.py::test_all_internal_document_links_resolve
.\.venv\Scripts\python.exe -m pytest -q tests/test_desktop.py tests/test_worker.py
.\.venv\Scripts\python.exe -m pytest -q tests/test_desktop.py
```

PYTEST_DEBUG_TEMPROOT задавался уникальным tmp/ каталогом для каждого focused run.
Успешный initial runner: tmp/step03-pg-cf68faefcfad405085181ecaa11045fc/checks.json.
Последний общий runner с CLI-only failures:
tmp/step03-pg-846a076848d142bab3f316e8f2f9cc9b/checks.json.
Native screenshots/metrics: tmp/step12-native/scale125.{png,json}, scale150.{png,json}.
Временный smoke helper удалён; постоянная native regression находится в test_desktop.py.
Все артефакты игнорируются Git, пользовательские записи не использовались.

## Найденные и исправленные ошибки

- Прерванная установка PySide6 завершена повторно без пересоздания среды.
- pytest-qt teardown удалял окно до fixture close; cleanup проверяет shiboken isValid.
- Native high-DPI smoke initially abort после capture/close: исправлен lifecycle
  QApplication/worker/widgets; bare Qt не падал, регрессия подтверждена новым процессом.
- Масштаб учитывает базовый Windows DPI: конечный DPR проверен как 1.25/1.5,
  а не только относительный QT_SCALE_FACTOR.
- CLI help test нормализует whitespace; переносы argparse не считаются поломкой CLI.
- Новый start очищает старый job_id/manifest; ранняя ошибка без DB job даёт retry,
  а не фиктивный resume прошлого задания.

## Критерии приёмки и ограничения

- [x] Русский тёмный GUI, import/multiple/drop/metadata/streams/roles/STT settings.
- [x] Queue/progress/error/FSM buttons, UI heartbeat при mock STT и медленном backend.
- [x] Окно открывается без GPU и при отсутствии БД показывает диагностическое состояние.
- [x] Real PG/FFmpeg/spawn flow, role/versions/WAV/history, source preservation.
- [x] Native Windows DPI 125–150%, screenshots inspection, shutdown regression.
- [x] Целевые проверки исправлены, документация/матрица/ADR обновлены.

Ограничения: one owner manager/app, история последней job для 500 media;
неисполненные pending commands/виртуальная очередь не сохраняются после выхода.
Роли вручную; mixing/диаризация не реализованы. Model download только отдельным
согласованным действием, CPU/GPU inference quality повторно не измерялась.
System settings берутся из существующего .env/AppSettings, отдельного GUI редактора
секретов нет. Retained WAV имеют overlap и сохраняются отдельно, cleanup policy — 14.
Редактор/поиск/проигрывание/экспорт из окна результатов — 13, не реализованы здесь.

Пользовательский checklist: `uv run python -m local_transcriber gui --env-file PATH`,
добавить несколько файлов, назначить роли, проверить модель локально, запустить;
pause→подтверждение→resume/cancel; закрыть активное окно и затем resume из истории.
При отсутствии БД настройте .env/миграции и обновите подключение. Пользовательские
медиа не изменяются, сохранение промежуточного аудио включается явно.

Блокирующих проблем текущего этапа нет. Следующий этап — **ШАГ 13: PySide6,
редактор, поиск и воспроизведение**, только после нового разрешения владельца.

<details>
<summary>История ШАГА 11 и предыдущих этапов</summary>


# Состояние проекта

Дата: 2026-10-13.

## Текущий шаг

ШАГ 11 — экспорт TXT, SRT, JSON и Markdown. **READY FOR STEP 12**.
Python 3.14.4, существующая .venv. ШАГ 12 не начат.
До начала шага 11 по прямому разрешению владельца закоммичен/запушен ШАГ 10:
`669de2e`, origin/main. Изменения шага 11 не коммитились и не пушились.

## Реализовано

- ExportService с ExportSource/ExportWriter ports; только сохранённые DB данные,
  без STT/модели/GPU/исходного медиафайла. Read-only repeatable-read snapshot.
- UTF-8 TXT с/без времени и ролей, SRT со стабильными индексами/таймкодами,
  JSON v1 с записью/моделью/потоками/versions/segments, Markdown.
- Integer absolute ms, HH:MM:SS,mmm, >1h/>24h, overlap сохраняется; пустые cues
  пропускаются, новые слова/таймкоды не придумываются.
- Выбор версии по UUID; TXT/MD/JSON default MANUAL→READABLE→RAW, SRT default RAW.
- READABLE сохраняет paragraph alignment в metadata; для старого v1 восстанавливается
  оформление из его сохранённых rules/dictionary с exact content/digest check.
  Содержимое прежних версий и правила conservative-text v1 не изменялись.
- MANUAL без привязки: обычный TXT/MD/JSON, с точным CRLF; timed TXT/SRT/role annotation
  отклоняются явно, исходные времена не присваиваются ручным правкам автоматически.
- Temp рядом с destination + flush/fsync/close + atomic rename. Без overwrite
  коллизия/гонка имён не перезаписывает чужой файл; --overwrite даёт явное разрешение.
- Cancel event/Ctrl+C до публикации чистит только свой temp; ошибки permissions,
  read-only, disk full/parent/reserved Windows name сохраняют прежний файл.
- Destination, совпадающий с исходным медиа по resolved path/samefile, запрещён.
- CLI export, расширение/--format, --version/--timestamps/--roles/--overwrite/--env-file;
  существующие точки входа сохранены. Новых зависимостей/миграций нет.
- Четыре synthetic golden fixture; .gitattributes закрепляет LF для Windows checkout.
- README/architecture/ADR-072–076/traceability/tests README обновлены.

Новые файлы: application/export.py, infrastructure/database/export_store.py,
infrastructure/export_files.py, infrastructure/export_cli.py, tests/test_export.py,
tests/fixtures/export/expected.{txt,srt,json,md}.golden, .gitattributes.
Изменены: __main__.py, domain/text.py, tests/test_postgresql.py, tests/README.md,
README.md, docs/architecture.md, docs/decisions.md, docs/requirements_traceability.md
и этот документ. Python paths относительно src/local_transcriber/.

## Проверки

Изолированный runner использовал PostgreSQL 18.3: отдельная local_transcriber_test,
случайный loopback port и random schema на тест. Рабочая БД/служба не менялись,
собственный кластер остановлен; реальное подключение подтверждено.

Фактическая команда из корня:

```powershell
.\.venv\Scripts\python.exe scripts/check_postgresql.py --pytest-target tests/test_export.py --pytest-target tests/test_text.py --pytest-target tests/test_cli.py --pytest-target tests/test_postgresql.py::test_export_after_restart_without_gpu_and_without_database_changes --pytest-target tests/test_postgresql.py::test_export_failures_keep_versions_and_original_media
```

| Проверка / фактическая команда | Статус | Результат |
| --- | --- | --- |
| uv run python --version (runner .venv) | PASS | Python 3.14.4. |
| uv run pytest -q (targets выше, runner) | PASS | 60 passed in 10.50s, без SKIP. |
| Export suite | PASS | 16 cases: 4 golden, time/overlap/empty/manual/legacy, атомарные файлы/гонка/отмена/ошибки, source guard и real ffprobe. |
| Text/CLI unit regression | PASS | 14 text cases + 28 прежних CLI cases; текст/точки входа не сломаны. |
| Real PostgreSQL export integration | PASS | 2 tests: TXT/SRT/JSON/MD в четырёх fresh Python processes; heavy imports отсутствуют; версии/данные не меняются; source/foreign/missing errors. |
| Real ffprobe -f srt -show_packets -of json | PASS | 3 cues, первая отметка 3600.001000 s, UTF-8/overlap корректно разобраны. |
| Windows filesystem | PASS | Unicode/spaces, read-only destination, Ctrl+C/temp cleanup, missing parent, CON.txt; old bytes preserved. |
| Alembic upgrade/repeat/check/downgrade/upgrade/current | PASS | 0003_audio_timeline (head), No new upgrade operations detected. |
| uv run ruff check . | PASS | All checks passed. |
| uv run ruff format --check . | PASS | 73 files already formatted. |
| git diff --check | PASS | Whitespace ошибок нет. |
| git check-attr text eol для четырёх golden | PASS | text=set, eol=lf. |
| Полный regression/GPU/long stress | NOT RUN | Целевой набор по просьбе владельца; экспорт не требует повторного STT/GPU. |
| Ручная визуальная проверка в плеере / GUI | NOT RUN | SRT проверен настоящим ffprobe; визуальную загрузку в плеер пользователь может выполнить по checklist ниже. GUI — шаг 12+. |

Артефакт успешного runner (игнорируется Git):
`tmp/step03-pg-fcaa483ebd524195a3c00e261afcbf7c/checks.json`, exit 0.
После обновления документации: uv run pytest -q -p no:cacheprovider tests/test_repository_audit.py::test_all_internal_document_links_resolve — 1 passed in 0.04s; uv run ruff check . / format --check . и git diff --check — PASS. Git check-ignore подтвердил исключение exports/*.txt/srt/json/md и .env.

## Ограничения и ручной чек-лист

- SRT RAW использует сохранённую гранулярность (в текущем pipeline — слова),
  overlap не устраняется. MANUAL не имеет alignment и не экспортируется в SRT.
- Итоговый text snapshot материализуется в RAM, как в шаге 10; файлы пишутся
  фрагментами, исходные медиа/PCM не читаются. Нагрузочные замеры — этап 15.
- Отмена действует до atomic publication; успешно опубликованный файл уже считается
  записанным. Existing destination заменяется только с --overwrite.
- Plain MANUAL сохраняет введённые подписи как часть пользовательского текста;
  --roles управляет внешними подписями RAW/READABLE и не удаляет слова из MANUAL.
- Legacy READABLE поддержан для conservative-text v1; неизвестный обработчик или
  повреждённый snapshot вызывает явную ошибку без публикации результата.
- Проверка пользователем: export JOB_UUID output.txt; повтор без --overwrite
  должен сохранить файл; export output.srt, открыть в локальном плеере с исходным
  видео и проверить времена >1h; export JSON и открыть выбранную MANUAL в TXT/MD.
  Папка назначения должна существовать, UUID берётся из text versions.

## Критерии приёмки

- [x] Все четыре формата выгружаются из сохранённых данных после перезапуска.
- [x] TXT readable/optional timestamps/roles, SRT indexes/ms/order, JSON metadata/model/segments,
  RAW/READABLE/selected text, Markdown, Unicode и Windows-пути.
- [x] SRT разбирается реальным subtitle demuxer ffprobe; визуальная ручная проверка отмечена отдельно.
- [x] Коллизии/отмена/permission/disk errors не повреждают прежний файл или RAW.
- [x] Unit/golden + реальные PG/FS integration, Ruff/format/diff, документы и матрица.

Блокирующих проблем текущего этапа нет. Следующий этап — **ШАГ 12, PySide6: импорт, настройки и список заданий**, только после нового разрешения владельца.

<details>
<summary>История ШАГА 10 и предыдущих этапов</summary>


# Состояние проекта

Дата: 2026-10-13.

## Текущий шаг

ШАГ 10 — RAW-транскрипт, читаемый текст и версионирование. **READY FOR STEP 11**.
Python 3.14.4, существующая .venv. ШАГ 11 не начат.
По прямому разрешению владельца ШАГ 09 закоммичен и запушен до начала шага 10:
`39b646b`, origin/main. Изменения шага 10 не коммитились/не пушились.

## Реализовано

- Domain: immutable TextSegment/Term/TextRules, aggregation по stream/time,
  SHA-256 source digest и детерминированный conservative-text v1.
- RAW сохраняет символы сегментов, включая исходные пробелы, повторы и цифры;
  сборка добавляет лишь граничные разделители. SQL-триггер запрещает UPDATE RAW.
- TextService и PostgreSQL adapter: RAW snapshot после COMPLETED, повтор RAW —
  прежний ID; новые READABLE/MANUAL с последовательными номерами под job lock.
- Ручная редакция с base/RAW ссылками сохраняется отдельно, включая Windows CRLF
  и пустой текст. Новый READABLE сохраняет все предыдущие MANUAL/READABLE.
- Читаемый режим: whitespace, безопасное оформление существующей пунктуации,
  конечная точка, абзацы по pause/stream/speaker/length; слова и смысл не переписываются.
- Терминология: longest-first whole-word single-pass, ambiguous/disabled skip;
  PostgreSQL CRUD, включение/выключение и атомарный UTF-8/BOM импорт/upsert.
- Метаданные READABLE: processor/rules_version, настройки, снимок словаря,
  source_digest и raw_version_id; воспроизводимость без LLM/сети.
- CLI text raw/readable/manual/versions/show и terms list/add/update/delete/import;
  проверка файлов/правил, лимиты, понятные ошибки с сохранностью данных.
- CLI transcribe после JOB_COMPLETED сохраняет RAW/READABLE в основном процессе,
  сообщает TEXT_COMPLETED; повтор текстового этапа не требует STT.
- Существующие точки входа сохранены, новых зависимостей/миграций нет.
- README, архитектура, ADR-067–071, матрица требований и инструкция тестов обновлены.

Новые файлы: domain/text.py, application/transcript.py,
infrastructure/database/text_store.py, infrastructure/text_cli.py, tests/test_text.py.
Изменены: __main__.py, transcribe_cli.py, tests/test_postgresql.py, tests/README.md,
README.md, docs/architecture.md, docs/decisions.md, docs/requirements_traceability.md
и этот документ. Все пути Python относительно src/local_transcriber/.

## Проверки

Выполнен целевой набор, без полного regression/GPU/stress. Runner использовал
PostgreSQL 18.3 в собственной отдельной local_transcriber_test на случайном
loopback-порту, random schema на тест; рабочая БД и служба не менялись.
Собственный кластер остановлен по завершении каждого прогона.

Итоговая команда из корня:

```powershell
.\.venv\Scripts\python.exe scripts/check_postgresql.py --pytest-target tests/test_text.py --pytest-target tests/test_cli.py --pytest-target tests/test_repository_audit.py::test_all_internal_document_links_resolve --pytest-target tests/test_postgresql.py::test_text_versions_preserve_raw_and_manual_after_reprocessing --pytest-target tests/test_postgresql.py::test_text_foreign_base_incomplete_job_and_bad_snapshot_rollback --pytest-target tests/test_postgresql.py::test_text_parallel_version_numbers_are_unique --pytest-target tests/test_postgresql.py::test_term_crud_import_updates_and_atomic_rollback --pytest-target tests/test_postgresql.py::test_empty_completed_transcript_versions --pytest-target tests/test_postgresql.py::test_text_cli_real_database_versions_and_manual_file
```

| Проверка / фактическая команда | Статус | Результат |
| --- | --- | --- |
| python --version (runner .venv) | PASS | Python 3.14.4. |
| uv run pytest -q (targets выше, runner) | PASS | 49 passed in 7.24s, без SKIP; 14 text unit, 28 CLI regression, 1 doc-links, 6 real PG integration. |
| RAW/READABLE/MANUAL real PostgreSQL | PASS | Точный RAW до/после редактирования/пересчёта, immutable SQL UPDATE, уникальные номера, 4 parallel RAW/6 READABLE, чужая base/digest mismatch, пустой результат. |
| Словарь и отказы real PostgreSQL | PASS | CRUD/enabled/upsert, duplicate constraint, реальный SQL CHECK failure откатывает целиком предшествующее обновление словаря. |
| Локальные файлы и CLI | PASS | Кириллица/пробелы в пути, UTF-8/BOM/CRLF, missing file, invalid encoding/format/size/rules; реальные текстовые команды на test schema. |
| Alembic upgrade/repeat/check/downgrade/upgrade/current | PASS | 0003_audio_timeline (head); No new upgrade operations detected. |
| uv run ruff check . (runner), финальный .venv/Scripts/ruff.exe check . | PASS | All checks passed. |
| uv run ruff format --check . после исправления форматирования | PASS | 68 files already formatted. |
| git diff --check | PASS | Whitespace ошибок нет; LF/CRLF warnings не являются ошибкой. |
| Внутренние ссылки README/docs | PASS | Все цели существуют; после обновления progress отдельно 1 passed in 0.03s. |
| git check-ignore --no-index (6 приватных путей) | PASS | .env, media, model, tmp, transcripts, exports игнорируются. |
| Полный regression/GPU/STT→text E2E/long stress | NOT RUN | Ограничены проверки текущим текстовым этапом; GPU/STT повторно не запускались, GUI/экспорт — следующие шаги. |
| Ручная интерактивная проверка CLI с пользовательскими данными | NOT RUN | Для этого шага выполнялись автоматические synthetic проверки на отдельной DB. |

Артефакт последнего runner (игнорируется Git):
`tmp/step03-pg-2f0d826aa03f4a75baee40efec9ef882/checks.json`.
Этот runner завершился exit 1 только на format --check после успешных pytest и
миграций: одно условие было не отформатировано. Оно исправлено, затем отдельно
выполнены успешные финальные Ruff check/format --check и git diff --check;
повторять весь DB набор после whitespace-only изменения не потребовалось.

## Исправления по результатам проверок

- Тест ручного файла сравнивает сохранённый текст с decode исходных bytes,
  а не universal-newline read_text: Windows CRLF сохраняется точно.
- Проверка сохранности прежних сегментов не предполагает порядок случайных UUID
  при совпадающих временах старого iter_segments. Новый RAW явно сортирует stream_index.
- Ruff B008 устранён: экземпляры правил не создаются в аргументах по умолчанию.
- Финальный format failure исправлен; неизменность бизнес-логики сохранена.

## Ограничения и ручной чек-лист

- Смысловые запятые, устранение повторов/стоп-слов, LLM, диаризация и STT prompting
  не включены; правила оформления намеренно сохраняют слова. Неполную пунктуацию
  можно исправить отдельным MANUAL; редактор GUI относится к шагу 13.
- RAW snapshot финализируется только для COMPLETED. При crash/pause/cancel
  доступны ранее сохранённые segments, а не объявленный полным RAW.
- Driver segments batches ограничены 1000; итоговый текст/snapshot/история версий
  материализуется в RAM. Это не медиа/PCM; нагрузочная оценка текстовой истории — 15.
- При сбое текстового этапа COMPLETED STT остаётся доступным; выполните text readable
  после восстановления БД. Новый READABLE не выбирает/не перезаписывает MANUAL.
- Проверка пользователем: text raw/readable/versions; сохранить manual из UTF-8
  файла, пересчитать readable с --no-terms, открыть manual через text show;
  terms import/list/update с disabled. Используйте собственные UUID и локальные пути.

## Критерии приёмки

- [x] Дословный RAW сохраняется неизменным и доступен после обработки.
- [x] READABLE — отдельный текст с абзацами/пунктуацией и без подмены слов/фактов.
- [x] MANUAL сохраняется отдельно и не теряется при повторном READABLE.
- [x] PostgreSQL версии/словарь, безопасная терминология, processor/rules version.
- [x] Unit и реальная PG integration, негативные сценарии, Ruff/diff; документация обновлена.

Блокирующих проблем текущего этапа нет. Следующий этап — **ШАГ 11, экспорт**,
только после нового разрешения владельца.

<details>
<summary>История ШАГА 09 и предыдущих этапов</summary>


# Состояние проекта

Дата: 2026-10-13.

## Текущий шаг

ШАГ 09 — worker, IPC, очередь и управление заданиями. **READY FOR STEP 10**.
Python 3.14.4, существующая .venv. ШАГ 10 не начат.

## Реализовано

- Один отдельный GPU process через Windows spawn и model cache на worker.
- WorkerManager: асинхронные submit/control/poll и bounded FIFO.
- Canonical START_JOB/PAUSE_JOB/RESUME_JOB/CANCEL_JOB/SHUTDOWN и события ТЗ.
- Persistence в parent supervisor thread, bounded RPC/ACK после atomic save;
  Session/CUDA/PCM не передаются через процессы.
- Deferred pause подтверждается после чекпойнта, resume без reload модели.
- Cancel останавливает FFmpeg, отбрасывает current chunk, сохраняет completed.
- Graceful shutdown/авария → INTERRUPTED, explicit restart/resume; queued cancel.
- Windows Job Object закрывает собственные FFmpeg children после kill worker.
- CLI --interactive с stdin pause/resume/cancel; Ctrl+C отправляет cancel.
- Parent error/recovery log по job_id; README/architecture/traceability/ADR обновлены.

## Проверки

Выполнен целевой набор, без полного regression. Изолированный PostgreSQL runner
не менял рабочую БД/службу и остановил собственный кластер после тестов.

| Проверка | Статус | Результат |
| --- | --- | --- |
| uv run pytest -q (выбранные worker/pipeline/CLI/FFmpeg/PG/FSM targets) | PASS | 119 passed in 19.99s, без SKIP. |
| FSM JobStatus | PASS | 64 пары текущих/целевых состояний. |
| Windows spawn fake inference | PASS | FIFO, pause/resume, active/queued cancel, shutdown, crash/restart, IPC errors. |
| Real PostgreSQL worker lifecycle | PASS | Первый checkpoint сохраняется; PAUSED → INTERRUPTED после kill → restart → CANCELLED, без потери RAW. |
| Real FFmpeg child cleanup | PASS | После kill worker owned child handle получает process-exit signal за <=5 s. |
| Real GPU worker 45 s smoke | PASS | 9.095 s включая startup/decode/VAD/STT/persist, 95 word-level segments; offline модель/RTX 4060 Ti. |
| Последний focused worker/pipeline после canonical-name mapping | PASS | 17 passed in 5.32s, включая startup failure и queued-ticket recovery. |
| Alembic upgrade/repeat/check/downgrade/upgrade/current | PASS | 0003_audio_timeline (head), schema diff отсутствует; новых миграций нет. |
| Ruff check / format --check | PASS | All checks passed; 63 files already formatted. |
| git diff --check | PASS | Whitespace ошибок нет. |
| Полный regression/GUI/3-hour stress | NOT RUN | По запросу ограничены проверки текущим этапом; GUI/stress — позднее. |

Новых зависимостей/моделей не скачивалось. 45 s fixture взят из разрешённого
Videos; исходный файл и рабочая PostgreSQL не менялись, PCM/текст в Git отсутствуют.
GPU model загрузилась только в worker, сохранение выполнялось parent RPC.

## Исправленные ошибки

1. Закрытый command channel раньше прерывал shutdown до cleanup и оставлял worker.
   Теперь fallback завершает собственный process/Job Object; regression passed.
2. Parent event append/poll сериализованы коротким lock, чтобы poll не терял
   событие между чтением и очисткой. SQL не удерживает этот UI lock.
3. Cancel queued resume теперь сохраняет CANCELLED вне UI thread без запуска
   inference; shutdown маркирует queued resume как INTERRUPTED.
4. START следующего ticket не теряет control state при finally предыдущего job.
5. При смерти до READY pending tickets уведомляются INTERRUPTED, чтобы CLI не
   ждал бесконечно; до restart новая подача запрещена.

## Ограничения и ручной чек-лист

- Один manager на приложение; несколько независимых CLI одновременно не имеют
  общего глобального scheduler. GUI ещё не реализован.
- Native CUDA вызов заканчивается до подтверждения cancel; decode уже прекращён,
  новый result не сохраняется. При shutdown timeout worker завершается принудительно.
- При недоступной БД supervisor сообщает failure recovery; persistent status можно
  восстановить лишь после возвращения доступа. Завершённые atomic checkpoints остаются.
- restart/shutdown могут ждать cleanup и вызываются будущим UI вне event loop;
  submit/command/poll не ждут inference/SQL.
- Для ручной проверки: transcribe --interactive; pause → PAUSE_DEFERRED → JOB_PAUSED;
  resume; cancel. Для аварии используйте только owned worker PID, затем --resume UUID.
- Worker UI event history ограничена 128; потребитель должен регулярно poll.
- Long/stress и полная оценка качества не повторялись; шаг 08 уже проверил 60 min.
- Блокеров для шага 10 нет.

## Критерии готовности / следующий этап

- [x] Отдельный spawn GPU worker, FIFO, bounded IPC, parent persistence реализованы.
- [x] Pause/resume/cancel/shutdown и checkpoint/status ordering проверены.
- [x] Crash/IPC recovery → INTERRUPTED, restart и process-tree cleanup проверены.
- [x] Реальная PostgreSQL и короткий GPU worker smoke выполнены.
- [x] Целевые pytest/Ruff/Alembic/diff проходят.
- [ ] Владелец разрешил ШАГ 10.

Следующий этап — 10: RAW/READABLE и текстовые версии; только после разрешения.

<details>
<summary>История шага 08</summary>

# Состояние проекта

Дата: 2026-10-13.

## Текущий шаг

ШАГ 08 — конвейер длинных файлов и чекпойнты. **READY FOR STEP 09**.
Python 3.14.4, существующая .venv. ШАГ 09 не начат.

## Выполнено

- Application pipeline: job → streams → logical chunks → decode → VAD → STT → persist.
- Default core 5 min, configurable 1–15 min, overlap 1000 ms; bounded decoder queue/VAD.
- Word source-ms ownership и time/text dedup сохраняют раздельные реальные повторы.
- Атомарные RAW+COMPLETED checkpoints существующего ChunkRepository; progress из БД.
- Explicit resume только неготовых chunks; fingerprint и model/VAD/chunk manifest gate.
- CLI transcribe, --stream-index, --resume, --chunk-ms, --overlap-ms, --end-ms.
- Журнал pipeline-errors.log с job_id; безопасные ошибки и закрытие decoder iterator.
- Новых зависимостей/схем/миграций нет; ADR-056–060 и матрица обновлены.

## Фактические проверки

По просьбе владельца выбран небольшой целевой набор, без полного регрессионного
suite предыдущих шагов. Runner создал отдельный SCRAM PostgreSQL cluster/test DB
из установленных binaries и остановил его; рабочая БД/служба не менялись.

| Проверка | Статус | Результат |
| --- | --- | --- |
| uv run pytest -q tests/test_pipeline.py tests/test_cli.py tests/test_transcription.py::test_zero_duration_word_alignment_keeps_text_inside_audio tests/test_postgresql.py::test_pipeline_checkpoints_and_resume tests/test_postgresql.py::test_pipeline_real_hour | PASS | 36 passed in 202.02s; реальные PostgreSQL 18.3, FFmpeg и CUDA, без SKIP. |
| Дополнительный tests/test_pipeline.py после новых guard-тестов | PASS | 8 passed in 0.50s: BaseException, CLI routing, decode <=15 min. |
| Fake 25-min crash/resume/repeat | PASS | Два chunks сохранены до сбоя; resume оставшихся; completed repeat без decode/STT/дублей. |
| Fingerprint/model parameters mismatch | PASS | Resume блокируется, подтверждённые результаты сохраняются. |
| Реальный 60-min прогон | PASS | 12/12 checkpoints, 7495 word-level сегментов; 196.312 s pipeline, float16. |
| Memory snapshot после ~30 min | PASS | RSS ~762 MiB, peak WorkingSet ~1955 MiB (включая load модели); общая GPU memory ~4120 MiB. |
| Alembic upgrade/repeat/check/downgrade/upgrade/current | PASS | 0003_audio_timeline (head), No new upgrade operations detected. |
| uv run ruff check . | PASS | All checks passed. |
| uv run ruff format --check . | PASS | 58 files already formatted. |
| git diff --check | PASS | Whitespace ошибок нет. |
| Полный regression / 3-hour stress / WER | NOT RUN | Ограничены проверки текущим этапом; широкая качественная/stress приёмка — 15. |

60-min gate обработал первые 3600000 ms локального OBS-видео длительностью
5717000 ms и размером 4405287908 bytes из ранее разрешённого Videos. Выбрана
дорожка 1. Модель large-v3-turbo offline, ru/transcribe, beam 5, float16,
word_timestamps=true. Исходные size/mtime_ns неизменны. Текст/PCM/видео в Git не
добавлены; PostgreSQL-тест удалил свою случайную схему с результатами. Подробная
эталонная разметка, WER и прослушивание всех границ не выполнялись.

## Найденные и исправленные ошибки

1. Whisper word alignment иногда выдаёт нулевой duration. Раньше первый logical
   chunk останавливался TranscriptionError. Слово теперь сохраняется как 1 ms
   внутри input; обратный interval по-прежнему отвергается. Добавлен regression test.
2. Windows cp1251 прерывал вывод pytest UnicodeEncodeError. Runner теперь явно
   использует UTF-8 для своего stdout и дочернего Python; собственный PG всё равно
   был остановлен в finally до исправления. Успешный повтор подтверждён.
3. Decoder generator теперь явно закрывается также при BaseException; тест
   подтверждает отсутствие активного decoder после abrupt interruption.

## Ограничения и ручной чек-лист

- Сейчас CLI синхронный и один writer на job; worker/FIFO/pause/cancel/автоматическое
  INTERRUPTED recovery — шаг 09. Explicit --resume уже работает после hard stop.
- Pipeline включает words в production CLI; fallback без word timestamps имеет
  более грубую midpoint ownership целого сегмента.
- Dedup — локальная time/text эвристика; не гарантируется отсутствие всех ошибок
  alignment. Раздельные повторы покрыты тестом; WER/CER и полная boundary-разметка — 15.
- Memory snapshot не заменяет stress/profile; PCM и pending results ограничены
  текущим logical chunk, а peak load модели отдельно входит в RSS.
- Для ручного запуска: настроить локальную рабочую БД и миграции; transcribe с
  выбранным stream index; сохранить job_id; повторить --resume с теми же параметрами.
- Блокирующих проблем для шага 09 нет.

## Критерии готовности / следующий этап

- [x] Decode/VAD/STT/persist и CLI реализованы.
- [x] Atomic checkpoints/progress/resume без повторной записи RAW проверены в PG.
- [x] Fingerprint/manifest validation и time/text dedup проверены.
- [x] Fake 25-min и реальный 60-min pipeline завершены, память ограничена архитектурно.
- [x] Целевые pytest/Ruff/Alembic/diff проходят.
- [ ] Владелец разрешил ШАГ 09.

Следующий шаг — 09: GPU worker, IPC и управление заданиями; только после разрешения.

<details>
<summary>История шага 07</summary>

# Состояние проекта

Дата: 2026-10-12.

## Текущий шаг

ШАГ 07 — VAD и сегментация. **READY FOR STEP 08**.
Python 3.14.4, существующая .venv. ШАГ 08 не начат.

## Выполнено

- SpeechSegmenter Protocol, immutable SpeechChunk с source-ms и core ownership.
- Реальная локальная Silero v6 ONNX CPU, 512 samples/frame, stream h/c/context.
- threshold 0.5, min silence 500 ms, padding 200 ms; AppSettings и .env.example.
- Bypass без загрузки модели; короткая речь, тишина, multiple pauses, EOF.
- Длинная речь split 30 s с overlap; core intervals не пересекаются.
- Ограниченный буфер ~0.95 MiB PCM при defaults; блоки <=5 s.
- Документы, traceability и ADR-051–055 обновлены. Новых зависимостей нет.

## Проверки

По просьбе владельца выполнен один небольшой целевой suite, без полного
PostgreSQL/GPU регрессионного runner прошлых этапов.

| Проверка | Статус | Результат |
| --- | --- | --- |
| uv run pytest tests/test_segmentation.py tests/test_settings.py tests/test_transcription.py -q | PASS | 49 passed in 1.30s; 10 новых сценариев, реальные ONNX silence/Russian fixture, без SKIP. |
| Ручной local Russian smoke | PASS | 45 s, 10 участков; 39.384 s padded PCM; decode+VAD 0.875 s. |
| Source ms / STT первого участка | PASS | Первый 600000–602152 ms, последний 632632–645000 ms; STT вернул русскую речь. |
| Сохранность исходника | PASS | size/mtime_ns неизменны; PCM/текст не сохранялись. |
| uv run ruff check . | PASS | All checks passed. |
| uv run ruff format --check . | PASS | 54 files already formatted. |
| git diff --check | PASS | Whitespace ошибок нет. |
| Полный regression / PostgreSQL / long-file stress | NOT RUN | По просьбе пользователя ограничены проверки текущим этапом; schema/DB не менялись. |

Первый suite столкнулся с PermissionError старого Windows Temp (39 setup errors,
10 passed); тот же suite успешно повторён в новом tmp/step07-* с
PYTEST_DEBUG_TEMPROOT. Пользовательские временные каталоги не удалялись.

## Ограничения

- VAD не безошибочен; проверен один русский fixture, тихая речь/шум требуют
  дальнейшей калибровки. Покадровое сравнение с ручной эталонной разметкой не выполнено.
- На split PCM имеет intentional overlap, core — без дублей. Дедупликация текста
  по ownership относится к pipeline шага 08, здесь STT/persistence не связывались.
- Across working ranges segmenter требует один непрерывный iterable; отдельные
  независимые вызовы сбрасывают ONNX state. Gap/replay явно отклоняется.
- Для ручной приёмки: прослушать тихие ответы и места splits, подобрать threshold
  при необходимости; bypass позволяет повтор без VAD.

## Критерии готовности / следующий этап

- [x] Локальный Silero и обязательные параметры реализованы.
- [x] Buffer ограничен, source timestamps и межблочное состояние сохранены.
- [x] Bypass, silence, короткая/длинная речь и ошибки проверены.
- [x] Real Russian fixture и инспекция границ/STT выполнены без записи данных в Git.
- [x] Целевые pytest/Ruff/diff проходят.
- [ ] Владелец разрешил ШАГ 08.

Следующий шаг — 08: конвейер длинных файлов/чекпойнты, только после разрешения.

<details>
<summary>История шага 06</summary>

# Состояние проекта

Дата: 2026-10-09.

## Текущий шаг

ШАГ 06 V2 — STT contract и faster-whisper на RTX 4060 Ti.
Статус: **READY FOR STEP 07**. Код, зависимости, CUDA runtime и обязательный
offline GPU smoke на 45 секундах русского аудио проверены. ШАГ 07 не начат и
требует отдельного разрешения. Среда: .venv, CPython 3.14.4 x64 с GIL.

## Реализовано

- Immutable `TranscriptionSegment`/`TranscriptionWord`: относительные integer ms,
  текст, optional confidence/probability; `TranscriptionEngineInfo` фиксирует
  model/device/фактический compute type/language/beam.
- Application `TranscriptionEngine` Protocol и Infrastructure
  `FasterWhisperEngine` без зависимости Domain/Application от ML runtime.
- Default large-v3-turbo; допустимы medium/large-v3; ru, task=transcribe,
  beam_size=5, temperature=0, VAD off, optional word timestamps.
- Одна lazy model load на экземпляр/будущий worker. Lazy generator faster-whisper
  полностью потребляется внутри adapter и возвращается immutable tuple.
- Primary float16 и один явный fallback int8_float16 только при OOM или
  неподдерживаемом compute type. Missing CUDA DLL не запускает вторую модель.
- Offline-first: AppSettings задаёт локальный model_path, local_files_only=true и
  allow_download=false. После явного согласия модель загружена в LocalAppData;
  веса не входят в Git.
- Windows CUDA DLL loader использует локальные wheels, известные каталоги и
  удерживаемые WinDLL handles; системный PATH/toolkit/драйвер не меняются.
- Установлены: faster-whisper 1.2.1, CTranslate2 4.8.2, NumPy 2.5.3, PyAV 19.0.1,
  ONNX Runtime 1.31.0, cuBLAS 12.9.2.10, cuDNN 9.27.0.42 и NVRTC 12.9.86.
- README, архитектура, ADR-044–050, compatibility, tests docs и traceability
  обновлены. VAD, worker/IPC, pipeline и GUI не реализовывались.

## GPU smoke

С разрешения владельца использован 45-секундный фрагмент локального видео из
`C:\Users\hewle\Videos`, audio stream 1. FFmpeg выдал ровно 45 s PCM mono
16 kHz. Модель `mobiuslabsgmbh/faster-whisper-large-v3-turbo` работала offline,
language=ru, task=transcribe, beam=5, temperature=0, compute=float16.

- STT: 3.288 s; decode + STT: 3.664 s.
- Два сегмента: 0–20320 ms и 20320–45000 ms, без разрыва/выхода за диапазон.
- Наблюдаемая VRAM: 1441 MiB до процесса, 3710 MiB после inference; delta 2269 MiB.
- Получен связный русский текст; точность/WER не заявляется.
- Имя файла, PCM и распознанный текст не сохранены в репозитории.

## Выполненные проверки

Полный runner использовал настоящие RTX/CUDA runtime, FFmpeg 9.0.2 и собственный
временный PostgreSQL 18.3 cluster/test DB. PostgreSQL остановлен; рабочая БД и
системная служба не менялись.

| Команда / проверка | Статус | Фактический результат |
| --- | --- | --- |
| python --version | PASS | Python 3.14.4 из существующей .venv. |
| uv run pytest -q | PASS | 319 passed in 20.61s, без SKIP при строгих CUDA/PostgreSQL/FFmpeg gates. |
| tests/test_transcription.py | PASS | 16 unit: DTO/words, relative ms, generator, one load, offline, fallback, DLL order и ошибки. |
| tests/test_transcription_runtime.py | PASS | Реальные версии; CUDA device=1; float16/int8_float16 и NVIDIA runtime packages. |
| 45 s Russian large-v3-turbo inference | PASS | float16, beam 5, 2 segments, 3.288 s STT, observed +2269 MiB VRAM. |
| uv lock --check --offline; uv sync --locked --offline | PASS | Lock/runtime согласованы; модель не является Python package. |
| python -m pip check | PASS | No broken requirements found. |
| PostgreSQL integration | PASS | 24 passed in 7.35s на отдельной PostgreSQL 18.3. |
| Alembic upgrade/repeat/check/downgrade/upgrade/current | PASS | `0003_audio_timeline (head)`, schema diff отсутствует. |
| uv run ruff check . | PASS | All checks passed. |
| uv run ruff format --check . | PASS | 50 files already formatted. |
| git diff --check | PASS | Ошибок whitespace нет; только предупреждения core.autocrlf. |

## Обнаруженные и исправленные ошибки

1. CTranslate2 видел RTX и float16, но первый encoder падал: `cublas64_12.dll`
   отсутствовала. CUDA 12 cuBLAS/cuDNN runtime добавлен в project lock.
2. Одного `os.add_dll_directory` оказалось недостаточно для внутреннего loader
   CTranslate2. Adapter предзагружает cuBLAS Lt, затем cuBLAS и cuDNN по абсолютным
   локальным путям и удерживает handles.
3. Ошибка missing cuBLAS ошибочно считалась поводом для int8_float16 fallback.
   Это пыталось держать две модели на 8 GB VRAM и выглядело как зависание. Fallback
   ограничен OOM/compute-type failures; добавлен regression test `loads == 1`.
4. Первая попытка использовала неверный repository id и получила 401 без загрузки.
   Использовано точное mapping faster-whisper 1.2.1:
   `mobiuslabsgmbh/faster-whisper-large-v3-turbo`.

## Ограничения

- Оценка VRAM — наблюдаемая до/после, а не инструментированный абсолютный peak.
- Проверен один 45-секундный фрагмент и float16. Реальный OOM fallback на модели
  не провоцировался, чтобы не нарушать стабильность; его логика покрыта unit.
- Точность не гарантируется; WER/CER, разные микрофоны и длинные записи — шаг 15.
- Абсолютные chunk offsets/checkpoints/worker относятся к шагам 08–09.
- Блокирующих проблем для ШАГА 07 нет.

## Критерии готовности

- [x] STT Protocol/DTO, model info и relative integer-ms contract реализованы.
- [x] ru/transcribe/beam 5/temperature 0, optional word timestamps реализованы.
- [x] Offline model gate, одна загрузка и полное потребление generator проверены.
- [x] float16 -> int8_float16 fallback детерминирован и безопасен.
- [x] Python 3.14/CTranslate2/CUDA DLL runtime работает на RTX 4060 Ti.
- [x] 45 секунд русского аудио распознаны локально; runtime/VRAM/timestamps записаны.
- [x] Полный pytest, PostgreSQL/Alembic, Ruff и git diff --check проходят.
- [ ] Владелец принял ШАГ 06 и отдельно разрешил ШАГ 07.

## Следующий этап

Только после явного разрешения — ШАГ 07: Silero VAD и сегментация без потери слов.

<details>
<summary>История завершённых шагов 00–03</summary>

# История шага 03

Дата: 2026-10-08.

## Текущий шаг

ШАГ 03 V2 — PostgreSQL: схема, миграции и транзакционные репозитории.
Статус: **READY FOR STEP 04**. Шаг 02 принят новым запросом владельца.
Шаг 03 реализован; обязательные проверки выполнены на реальной изолированной
PostgreSQL 18.3 Windows x64. Блокеров для приёмки 03 нет.
ШАГ 04 не начат и требует отдельного разрешения.
Использована существующая .venv: CPython 3.14.4 x64 с GIL, >=3.14,<3.15.

## Реализовано

- Семь SQLAlchemy 2.1.4 моделей §7 ТЗ: media_files, audio_streams,
  transcription_jobs, processing_chunks, transcript_segments,
  transcript_versions, custom_terms. UUID/FK, TIMESTAMPTZ, JSONB, BIGINT ms.
- UNIQUE участков (job_id, stream_id, chunk_index), дорожек (media_file_id,
  stream_index), сегментов (chunk_id, segment_index), версий (job_id,
  version_number), canonical_form терминов. Индексы job/chunk/stream и
  (job_id, start_ms). CHECK времени, состояний, завершения, прогресса,
  положительных параметров аудио, JSON-типов, номера/типа версии, непустого термина.
- Составные FK исключают дорожку другого файла и сегмент чужого задания/чанка.
  Дополнительное processing_chunks.media_file_id обосновано ADR-029.
- Domain JobStatus: восемь состояний ТЗ и проверка переходов чистым Python.
- JobRepository: создание/переходы/прогресс из БД/явное DB-only удаление задания.
  ChunkRepository: регистрация незавершённых chunks; атомарное сохранение
  сегментов, COMPLETED, даты и счётчиков в одной транзакции. Любая ошибка — rollback.
  FOR UPDATE + ON CONFLICT защищают конкурентный повтор; идентичный результат
  не меняет БД, отличающийся RAW/интервал отвергается. Сегменты читаются пакетами
  с сортировкой по абсолютным ms; весь длинный транскрипт не загружается заранее.
- RAW сегменты/RAW версии защищены PostgreSQL UPDATE-триггерами. Каскадное
  удаление задания удаляет его результаты, сохраняет исходный файл, MediaFile
  и другое задание. READABLE/MANUAL не перезаписывают RAW.
- Engine/Session и Alembic используют только существующий AppSettings:
  DSN приоритетен, localhost only; echo=False/hide_parameters=True,
  безопасный PersistenceError без driver detail/секретов/текста.
- Alembic 1.20.0 и фиксированный DDL revision 0001_initial.
  Нет автозапуска миграций в CLI/import. Downgrade — только отдельная test DB.
- Защита test DB: отличается от фактической рабочей DB (в том числе DSN),
  имя *_test/test_*, запрет postgres/template*. На каждый тест — случайная
  lt_test_<uuid> схема, search_path без public, удаляется только собственная схема.
- scripts/check_postgresql.py: воспроизводимый реальный прогон с установленными
  binaries в отдельном временном процессе PostgreSQL, SCRAM/случайный пароль,
  loopback/свободный порт, только test DB; остановка в finally.
  Не устанавливает сервер и не меняет системную службу.
- psycopg[binary] 3.3.6 и зависимости установлены только в существующую .venv;
  pyproject/uv.lock согласованы (27 записей lock). CUDA/ML/GUI не устанавливались.
- 83 unit-проверки БД/Domain и 22 реальных PostgreSQL интеграционных случая;
  сохранены 167 тестов предыдущих этапов. Всего 272.
- Документация, README, матрица, совместимость Python и ADR-028–034 обновлены.
  Application pipeline, импорт, FFmpeg/VAD/STT/GUI/IPC не реализовывались.

## Выполненные проверки

Из корня Transcribation, установленный .venv Python 3.14.4.
Первый прогон без настроенного PostgreSQL: 250 passed, 15 skipped.
SKIP не был объявлен успешной интеграцией. Затем использованы уже установленные
binaries C:/Program Files/PostgreSQL/18/bin: собственный кластер в игнорируемом
tmp/step03-pg-<uuid>, отдельная local_transcriber_test, случайный порт/SCRAM пароль.
Рабочая local_transcriber не создавалась и не использовалась.
Реальное подключение подтвердило current_database и PostgreSQL 18.3.
Строгий runner PYTEST_REQUIRE_POSTGRES=1 запрещает подменить отсутствие БД SKIP.

Воспроизводимая команда:
```powershell
uv run python scripts/check_postgresql.py --postgres-bin 'C:/Program Files/PostgreSQL/18/bin'
```

| Команда / проверка | Статус | Фактический результат |
| --- | --- | --- |
| python --version | PASS | Python 3.14.4 из существующей .venv. |
| uv sync; TOML/импорты; uv lock --check --offline | PASS | SQLAlchemy 2.1.4, Alembic 1.20.0, psycopg/binary 3.3.6; 27 lock entries. |
| uv run pytest -q (с реальной test DB) | PASS | 272 passed, exit 0; без пропусков. В контрольном прогоне 23.15s. |
| uv run pytest tests/test_database_unit.py -q | PASS | 83 passed in 0.88s; все 64 пары статусов, URL/guard, ms, offline DDL и шаблон Alembic. Offline SQL не является PostgreSQL integration. |
| uv run pytest tests/test_postgresql.py -q | PASS | 22 passed in 9.15s на PostgreSQL 18.3; SQLite/mock не использованы. |
| uv run alembic -x test=true upgrade head (дважды) | PASS | Создана схема 0001_initial; повтор не меняет revision/не дублирует таблицы. |
| uv run alembic -x test=true check | PASS | No new upgrade operations detected. |
| uv run alembic -x test=true downgrade base; ... upgrade head | PASS | Реально выполнены только в disposable test DB; схема восстановлена. |
| uv run alembic -x test=true current | PASS | 0001_initial (head). |
| PostgreSQL constraints/rollback/idempotence | PASS | FK/CHECK/UNIQUE/NOT NULL; ошибка второго сегмента откатывает весь результат; подтверждённый RAW не меняется; конкурентный повтор без дублей. |
| Две дорожки / два задания / progress / сортировка ms | PASS | Изолированные результаты, 50% при одном из двух planned chunks; 100% после обоих, чтение batch_size=1 по абсолютному времени. |
| RAW UPDATE / каскадное удаление задания | PASS | Реальные SQL UPDATE отвергнуты триггерами; источник/другое задание сохранены. |
| python -m pip check | PASS | No broken requirements found, exit 0. |
| Финальный runner / остановка / secrets audit | PASS | Все команды exit 0; собственный postmaster.pid отсутствует, pwfile удалён; типовые private key/token patterns не найдены в changed/new файлах. |
| uv run ruff check . | PASS | All checks passed!, exit 0. |
| uv run ruff format --check . | PASS | 34 files already formatted, exit 0 после исправления формата миграции. |
| git diff --check | PASS | Exit 0; только core.autocrlf предупреждение LF/CRLF для uv.lock. |
| Документы/FR/NFR/локальные ссылки/.gitignore/.env.example/CLI | PASS | Сохранённые 167 тестов проходят; обязательные документы и новые ссылки доступны; secrets/local recordings/tmp исключаются. |
| Сохранность оригиналов/точек входа/индекса | PASS | ORIGINAL_TZ, промпты, AGENTS, main.py, __main__, settings/doctor и старые тесты сохранены; commit/push/staging отсутствуют. |
| Постоянная рабочая БД системной службы localhost:5432 | NOT RUN | Служба postgresql-x64-18 Running и порт доступны, но AppSettings не содержит credentials. Изменения рабочей БД/службы не выполнялись. Реальная persistence приёмка выполнена на отдельном кластере. |
| Реальный FFmpeg/VAD/Whisper/GPU/GUI | NOT RUN | За пределами 03; ничего не установлено или реализовано. |

## Обнаруженные и исправленные ошибки

1. Alembic test preflight SELECT открывал autobegin: без завершения этой
   транзакции CLI миграция могла откатиться при закрытии connection.
   Теперь preflight commit происходит до context.begin_transaction.
   CLI повторный upgrade/check/current и downgrade/upgrade реально проверены.
2. Alembic autogenerate с test_schema/search_path видел alembic_version как
   лишнюю предметную таблицу. Реальный regression test command.check выявил
   remove_table; исправлено исключением только служебного ledger.
3. Захват Windows pg_ctl через pipe удерживал EOF дочерним сервером.
   Runner использует файлы логов; остановка своего процесса проверена.
4. Ошибки Ruff/imports/переводов строк устранены, итоговые проверки PASS.

## Ограничения и известные вопросы

- Для постоянной рабочей БД нужно настроить роль/пароль и базы через user .env
  или окружение AppSettings. Пароль не требуется сообщать в чате.
  Для повторной приёмки 03 достаточно runner выше; это не блокер данного этапа.
- Обычный pytest без отдельной test DB честно пропустит PostgreSQL cases;
  strict runner превращает недоступность в FAIL. Test роль требует CONNECT/CREATE.
- Runner рассчитан на Windows и уже установленные binaries, оставляет свои
  остановленные кластеры/логи в tmp/. Пользовательские данные не удалялись;
  пароль bootstrap удалён, credentials не записаны в Git.
- ORM create_all не заменяет Alembic: RAW-триггеры создаёт миграция.
- Общий процент относится к зарегистрированному плану chunks, а не к ещё
  неизвестной продолжительности будущего pipeline. Resume/STT/словарные CRUD —
  соответствующие последующие шаги.
- Блокирующих проблем для приёмки ШАГА 03 нет.

## Критерии готовности / ручной чек-лист

- [x] Все семь таблиц §7, типы, индексы, FK, CHECK и уникальность реализованы.
- [x] Миграции применяются, повторяются и откатываются/восстанавливаются в test DB.
- [x] Атомарность/rollback, повтор и конкурентное сохранение подтверждены реальной PostgreSQL.
- [x] Прогресс считается из DB; две дорожки/два задания и ms сортировка проверены.
- [x] Test DB guard и отдельные схемы защищают рабочие данные; RAW/source сохранены.
- [x] Python 3.14/.venv, прежний CLI и точки входа сохранены; все обязательные проверки PASS.
- [x] Документы/матрица/решения обновлены; будущие этапы не начаты.
- [ ] Владелец принял 03 и отдельным заданием разрешил 04.
- [ ] Перед использованием постоянной БД настроить AppSettings credentials/роль/DB.

## Следующий этап

Только после разрешения — ШАГ 04: FFprobe, медиаинспекция и импорт.
[План](implementation_plan.md) и [матрица](requirements_traceability.md) сохранены;
этот шаг здесь не реализован.

<details>
<summary>История завершённых шагов 00–02 (прежние результаты и ограничения)</summary>

# История шага 02

Дата: 2026-10-08.

## Текущий шаг

ШАГ 02 V2 — настройки и диагностика Windows/инструментов.
Статус: **READY FOR STEP 03**. Предыдущий этап принят новым запросом владельца.
Шаг 02 реализован, обязательные проверки выполнены. Блокеров для приёмки 02 нет.
ШАГ 03 не начат и требует отдельного разрешения.
Использована существующая .venv: CPython 3.14.4 x64 с GIL, >=3.14,<3.15.
Оригинальное ТЗ и его полное содержимое в requirements.md сохранены.

## Реализовано

- AppSettings на Pydantic Settings в Infrastructure: environment выше
  явного/user .env, затем defaults; пустые значения используют defaults.
  LOCALAPPDATA → APPDATA → home/AppData/Local; data/cache/models/logs/temp.
  Абсолютные переопределения, Unicode/пробелы, UTF-8/BOM, воспроизводимость вне cwd.
- Default .env — стандартный user-data каталог LocalTranscriber/.env.
  Cwd .env не читается автоматически; CLI doctor --env-file задаёт явный файл.
  Проверены синтаксис и размер <=1 MiB; повреждённый конфиг не принимается частично.
- Настройки локальной PostgreSQL, executable paths/timeout, device/GPU index,
  model name/path и precision. Пароль и DSN — SecretStr без repr.
  Вывод ошибок не содержит input values, credentials, DSN или stderr инструментов.
- doctor с девятью независимыми результатами: Python, Windows, каталоги,
  ffmpeg, ffprobe, NVIDIA-драйвер, PostgreSQL, CUDA/CTranslate2, модель.
  Статусы OK/MISSING/ERROR/SKIP не смешивают driver, CUDA и inference.
- Subprocess без shell, timeout, скрытые окна Windows; аргументы не разбиваются
  по пробелам. Windows .bat/.cmd/.ps1 для инструментов отклоняются.
  PG/LOCAL_TRANSCRIBER env не передаются дочерним инструментам.
- PostgreSQL: реальная readiness-проверка pg_isready без SQL и credentials;
  localhost/loopback only. Ошибочный, внешний или многосерверный DSN даёт ERROR.
  Query/fragment/port=0 отвергаются. Authentication/БД/схема относятся к 03.
- При установленном CTranslate2 CUDA count проверяется отдельным Python -I -B
  с timeout. Модель проверяется только локально по непустым model.bin/config.json/
  tokenizer.json и синтаксису JSON; веса не читаются, inference не запускается.
- По умолчанию doctor не создаёт пользовательских каталогов/логов.
  --dry-run отключает все subprocess и создание. --create-dirs явно создаёт
  только настроенные каталоги; существующие файлы сохраняются, удалений нет.
- Существующие точки входа, --version/--help и ленивые импорты сохранены.
  Doctor exit 0 означает завершённый отчёт, даже с MISSING/ERROR.
  Ошибка загрузки настроек даёт exit 2 и безопасную диагностику без traceback.
- Прямые лёгкие runtime зависимости закреплены: pydantic 2.13.5,
  pydantic-settings 2.15.0, python-dotenv 1.2.4.
  uv.lock фиксирует 20 записей; pydantic-core 2.46.5 и остальные transitive
  установлены только в существующую .venv. Python 3.14 совместимость этих
  настроек подтверждена реальными импортами/тестами, не только metadata.
- Добавлены test_settings.py и test_doctor.py: 66 новых тестовых случаев;
  сохранённые тесты CLI адаптированы к doctor и runtime dependencies.
  Итого 167 тестов. Реальные subprocess/CLI, synthetic fixtures и mocks явно разделены.
- README, .env.example, архитектура, решения и матрица соответствия обновлены.
  Бизнес-логика, ORM/миграции/репозитории, GUI, STT и ML/CUDA установка не добавлялись.

## Выполненные проверки

Из корня проекта, PATH/VIRTUAL_ENV указывают на существующую .venv.
UV_CACHE_DIR=.cache/uv; UV_PYTHON_DOWNLOADS=never;
PYTEST_DEBUG_TEMPROOT — новый уникальный каталог tmp/step02-*.
Глобальный Python, пользовательский Temp и ACL не изменялись.

| Команда / проверка | Статус | Фактический результат |
| --- | --- | --- |
| python --version; executable/prefix/GIL/x64 | PASS | Python 3.14.4, проектная .venv. |
| uv sync; uv sync --offline после фиксации direct dependencies | PASS | 20 записей lock, установлены только лёгкие настройки и пакет проекта. |
| uv run pytest -q | PASS | 167 passed in 14.94s, exit 0; пропусков/предупреждений нет. |
| uv run ruff check . | PASS | All checks passed!, exit 0. |
| uv run ruff format --check . | PASS | 23 files already formatted, exit 0. |
| git diff --check | PASS | Exit 0; только существующие core.autocrlf предупреждения LF/CRLF. |
| uv lock --check --offline | PASS | Resolved 20 packages in 1ms; lock согласован. |
| python -m pip check | PASS | No broken requirements found. |
| uv run python -m local_transcriber --version / --help | PASS | Версия 0.0.1, справка с doctor; старые launcher также проверены pytest. |
| uv run python -m local_transcriber doctor --help | PASS | --env-file, --dry-run, --create-dirs; явные режимы, exit 0. |
| uv run python -m local_transcriber doctor | PASS | Все 9 результатов, exit 0; реальные статусы машины ниже. |
| uv run python -m local_transcriber doctor --env-file .env.example | PASS | Пример загружается; диагностика без паролей/traceback. |
| uv run python -m local_transcriber doctor --env-file .env.example --dry-run | PASS | Внешние проверки SKIP; чтение локальных путей/модели, без создания пользовательских данных. |
| Unit env/subprocess и ошибки | PASS | Missing tools/GPU/model; timeout/permissions/invalid response; malformed DSN/settings/env; UTF-8/BOM/Windows paths; credentials не выводятся. |
| Реальные CLI/subprocess интеграции | PASS | Unicode/пробелы, module/console/wrapper doctor; CLI без GPU, safe errors, сохранность sentinel файлов. |
| Dry-run и явное создание каталогов | PASS | Нулевой subprocess/нет новых data dirs; создание идемпотентно, отказ прав/путь-файл диагностируются без удаления. |
| Сохранность материалов и Git | PASS | HEAD 545d359 и индекс не менялись; src/main.py, init, тесты 00, AGENTS, .gitignore, ORIGINAL_TZ и исходник промптов не изменены. |
| Документы/ссылки/FR/NFR/.gitignore/.env.example | PASS | Сохранённые тесты аудита проходят; все новые ссылки на артефакты корректны, пример без credentials. |
| Реальная pg_isready readiness | NOT RUN | Инструмент не найден в PATH; doctor сообщает MISSING. Наличие самой службы/БД не установлено этим результатом. Коды/timeout/DSN проверены unit-тестами. |
| Реальный CUDA/CTranslate2 runtime / inference | NOT RUN | CTranslate2 не установлен; doctor сообщает MISSING. По заданию ML/CUDA не устанавливались. Проверки установленного backend смоделированы unit-тестами; inference — 06. |
| Реальная модель / STT | NOT RUN | Локальной модели нет. Диагностика MISSING реальная; synthetic файлы проверяют только инспекцию/повреждение manifest, не загрузку весов. |
| Реальные FFmpeg/ffprobe version probes | NOT RUN | Инструменты не найдены в PATH. Missing и контракты subprocess/ответов проверены; медиаобработка — 04–05. |

Отсутствующие зависимости на 02 явно необязательны по промпту: обязательная
проверка здесь — диагностика их отсутствия без crash. Эти NOT RUN не объявлены
успешными integration/hardware испытаниями и не блокируют завершение 02.

## Фактическая Windows-среда

- Python 3.14.4: OK.
- Windows: OK.
- NVIDIA-драйвер: OK, nvidia-smi сообщил 596.21; inference не проверялся.
- ffmpeg/ffprobe и pg_isready: MISSING в PATH.
- CTranslate2 и локальная модель: MISSING.
- Сетевых загрузок doctor не выполнял. Загружены только явно необходимые
  лёгкие Python-пакеты при uv sync; аудио/видео/транскрипты не передавались.

## Найденные ошибки и регрессии

1. Первый полный pytest: 149 passed, 1 failed. Double-quoted Windows .env
   преобразовал backslash sequences в управляющие символы пути. Валидация
   теперь отвергает такие пути; добавлены тесты / и single quotes, безопасного
   отказа и сохранности файла. Даны инструкции пользователю.
2. При проверке DSN обнаружен port=0, который выражение port or 5432 молча
   заменяло на default. Исправлена явная проверка диапазона; regression для
   port=0/fragment и отсутствие внешнего подключения.
3. Python-dotenv может пропустить malformed строку, приняв остальную часть.
   Добавлена предварительная syntax/UTF-8/size проверка и regression.
4. После прямой фиксации dependencies metadata сортировала Requires-Dist
   иначе pyproject: 166 passed, 1 failed. Исправлен тест: сравнивать множество
   зависимостей, а не порядок. Повторный полный прогон — 167 PASS.

## Критерии приёмки и ручной чек-лист

- [x] Python 3.14 и существующая .venv сохранены.
- [x] Настройки воспроизводимы и не зависят от cwd.
- [x] Конфиг-пример и диагностика не содержат паролей/DSN.
- [x] AppData/LOCALAPPDATA, папки и абсолютные пользовательские пути предусмотрены.
- [x] Doctor раздельно отражает все обязательные компоненты и отсутствие optional.
- [x] Unit env/subprocess, реальные CLI и Windows позитивные/негативные сценарии выполнены.
- [x] Dry-run не создаёт data dirs; явное создание не удаляет/не перезаписывает файлы.
- [x] CLI/точки входа этапа 01 работают; source media не обрабатываются.
- [x] pytest/Ruff/lock/pip/Git и документы проверены, выявленные ошибки исправлены.
- [x] Progress и матрица соответствия актуализированы; значимые решения записаны.
- [x] Следующий этап, commit и push не выполнялись.

## Ограничения и следующий шаг

Doctor — диагностика, не гарантия готовности всего desktop-приложения.
OK pg_isready не подтверждает пароль/наличие БД/схему. Model OK означает
локальную комплектность файлов/JSON; GPU count не заменяет inference.
Dry-run не проверяет права записи; --create-dirs проверяет их фактическим mkdir,
возможны частично созданные собственные пустые каталоги при отказе на одном из путей.
Автоматической очистки или скачивания нет.

Шаг 03 потребует доступной локальной PostgreSQL и отдельной test DB; настройки
их расположения будут проверены реальным подключением и миграциями только после
нового разрешения. **READY FOR STEP 03** относится к завершению 02.

## Архив предыдущих этапов

Исторические статусы и запреты ниже относятся к времени до разрешения ШАГА 02.
Актуальный статус указан выше.

<details>
<summary>Отчёты ШАГОВ 01 и 00</summary>

# История шага 02

Дата: 2026-10-08.

## Текущий шаг

ШАГ 01 V2 — минимальный Python-пакет и инструменты качества.
Статус: **READY FOR STEP 02**. ШАГ 00 принят новым запросом владельца,
ШАГ 01 реализован и проверен. Блокирующих проблем нет.
ШАГ 02 не начат; переход требует отдельного разрешения.
Использована существующая .venv: CPython 3.14.4 x64 с GIL, >=3.14,<3.15.

## Выполнено

- Единая типизированная функция local_transcriber.__main__:main.
  python -m local_transcriber, console script local-transcriber и сохранённый
  src/main.py обращаются к ней. Второго bootstrap нет.
- Реальные --version, --help/-h и справка при запуске без аргументов.
  Версия читается из установленной metadata, исходное значение — pyproject.toml.
- Неизвестный аргумент/команда и сокращение --vers дают exit 2, stderr и usage.
  Пользовательские файлы не читаются и не изменяются.
- Пакет устанавливается через uv sync, runtime dependencies пусты.
  Существующие .venv, pyproject.toml, uv.lock, .env.example и Git-структура сохранены;
  pyproject дополнен только записью console script. Переразрешение lock успешно,
  состав и байты uv.lock остались прежними: зависимости не изменились.
- Добавлены 28 тестов: unit main, installed metadata, изолированные импорты,
  настоящие дочерние процессы всех launcher, позитивные/негативные команды,
  Unicode/пробелы в пути и сохранность синтетического файла.
  73 теста аудита сохранены.
- Собран wheel; проверен его состав: только два Python-файла пакета и dist-info.
  Документы, .env, media, кэш и тесты не входят в wheel.
- Wheel установлен offline без зависимостей в отдельное чистое Python 3.14
  окружение внутри tmp/step01-clean-g6nw09ml/Чистое окружение с пробелами/окружение.
  В нём есть только local-transcriber; основная .venv не пересоздавалась.
- README с PowerShell-командами, архитектура, граница требований, план,
  решения и матрица требований синхронизированы. Матрица содержит артефакты
  и соответствующие проверки 01, не объявляет полный MVP готовым.

## Проверки и фактические результаты

Команды выполнялись из корня проекта, PATH/VIRTUAL_ENV направлены на существующую
.venv. UV_CACHE_DIR=.cache/uv, UV_PYTHON_DOWNLOADS=never;
PYTEST_DEBUG_TEMPROOT — новый уникальный tmp/step01-pytest-<UUID>.
Глобальный Python, ACL общего Temp и пользовательские материалы не изменялись.

| Команда / проверка | Статус | Результат |
| --- | --- | --- |
| python --version; путь/prefix/GIL/x64 | PASS | Python 3.14.4, существующая проектная .venv. |
| uv sync | PASS | Resolved 13 packages; установлен local-transcriber 0.0.1; runtime dependencies отсутствуют. |
| uv run python -m local_transcriber --version | PASS | local-transcriber 0.0.1, exit 0. |
| uv run python -m local_transcriber --help | PASS | Справка с доступными флагами и границей текущих возможностей, exit 0. |
| uv run pytest -q | PASS | 101 passed in 6.49s, exit 0, без пропусков и предупреждений. |
| uv run ruff check . | PASS | All checks passed!, exit 0. |
| uv run ruff format --check . | PASS | 18 files already formatted, exit 0. |
| uv lock --check --offline | PASS | Resolved 13 packages; существующий uv.lock соответствует pyproject. |
| uv build --wheel --offline --out-dir tmp/step01-wheel | PASS | Собран local_transcriber-0.0.1-py3-none-any.whl; состав проверен через zipfile. |
| uv venv --python .venv/Scripts/python.exe --offline <чистый каталог> | PASS | Отдельная Python 3.14.4 venv с кириллицей и пробелами в полном пути. |
| uv pip install --python <чистый venv>/Scripts/python.exe --offline --no-deps <wheel> | PASS | Установлен только wheel проекта. Реальные module/console/wrapper запускались с --version, --help, -h, без аргументов и ошибочными аргументами. |
| Изолированный import smoke и metadata | PASS | Без вывода, тяжёлых импортов и файлов в cwd; версия совпадает с pyproject. |
| Позитивные/негативные команды из Unicode cwd | PASS | Позитивные exit 0; --unknown-option/--vers/doctor — exit 2; нет traceback и потери контрольного файла. |
| git diff --check; git status; исходный и итоговый diff | PASS | Ошибок пробелов/удалений нет; индекс и HEAD не менялись. |
| Документы, ссылки, ТЗ, .gitignore и .env.example | PASS | Весь ORIGINAL_TZ сохранён в requirements; документы/ссылки и исключения проверяются сохранёнными тестами аудита. |
| GPU / PostgreSQL / FFmpeg / GUI / CUDA / STT | NOT RUN | Не требуются для 01, библиотеки/модели и реализации по заданию не добавляются. Hardware-gates остаются на соответствующих этапах. |

Дополнительный итоговый аудит: 23 проектных файла проверены на типичные секреты,
совпадений нет. Тяжёлые библиотеки отсутствуют. ORIGINAL_TZ.md, исходник
промптов, AGENTS.md, .env.example, .gitignore, uv.lock и тесты 00 не изменены.
Git HEAD остаётся e9d4f5c, индекс не менялся.

## Найденные ошибки и исправления

Первый pytest: 98 passed, 3 failed, 3 warnings. Изолированный Python -I игнорирует
PYTHONIOENCODING, русская справка была в Windows-кодировке, обвязка читала UTF-8.
Исправлена тестовая команда module на -I -X utf8; все три сценария справки
проверяют регрессию. Повторный полный pytest: 101 PASS.
Приложение не меняет глобальную кодировку или настройки Python.

uv sync автоматически повторил временно неудачное переименование в своём
локальном кэше и успешно завершился. Предупреждение uv build о кэше внутри
исходного дерева проверено инспекцией wheel: посторонние данные туда не попали.

## Критерии приёмки и ручной чек-лист

- [x] src-layout и существующий src/main.py сохранены; нет изменения sys.path.
- [x] Точка входа одна, все три launcher дают согласованные результаты.
- [x] Пакет запускается после установки в чистый Python 3.14 venv, без dev-пакетов.
- [x] --version/--help, import smoke, uv sync, pytest/Ruff и Git-проверка выполнены.
- [x] Запуск из корня и пути с кириллицей/пробелами реально проверен.
- [x] Негативные сценарии диагностируются, контрольные данные сохранены.
- [x] Нет GUI/БД/AI-заглушек и тяжёлых AI-зависимостей.
- [x] README, архитектура, решения, progress и матрица отражают границу этапа.
- [x] Оригинальное ТЗ и исходник промптов не изменены; commit/push не выполнялись.

## Известные ограничения и следующий шаг

CLI показывает информацию о пакете; транскрибация, GUI, БД, doctor и загрузка
настроек ещё не реализованы. Для запуска нужен установленный пакет (uv sync),
режим --only-dev устанавливает только инструменты и не заменяет установку пакета.
ML/CUDA-совместимость требует реальных будущих проверок из
[python314_compatibility.md](python314_compatibility.md).
Пропущенных обязательных проверок 01 и блокеров нет.

Следующий этап — 02: настройки и диагностика Windows/инструментов.
Только по новому разрешению владельца. **READY FOR STEP 02** относится
к минимальному пакету и инструментам, не к готовности desktop MVP.

## Архив ШАГА 00

Ниже сохранён отчёт предыдущего этапа. Его формулировки «01 не разрешён»
относятся к состоянию до нового задания владельца; текущий статус — выше.

<details>
<summary>Отчёт ШАГА 00 и предшествующая история</summary>

# История шага 02

Дата: 2026-10-08.

## Текущий шаг

ШАГ 00 V2 — завершение аудита и синхронизация полного ТЗ.
Статус: **READY к ШАГУ 01** — ШАГ 00 завершён, 73 теста и проверки качества прошли.
Блокер отсутствующего ТЗ и конфликт Python закрыты; переход требует нового запроса.
Оригинал предоставлен; выбор Python окончательно закрыт владельцем:
CPython 3.14 x64, >=3.14,<3.15. ШАГ 01 не начат и не разрешён.

## Выполнено в текущем продолжении

- Полностью изучен ORIGINAL_TZ.md 1.0 (1092 строки). Оригинал не изменяется.
- Все его разделы перенесены в requirements.md, включая 10 FR и 5 NFR;
  прежние F-/N- сохраняются как алиасы, пункты без ID не пропущены.
- Добавлена requirements_traceability.md: соответствие FR/NFR и прочих
  разделов шагам 00–17. План и архитектура синхронизированы с оригиналом.
- Python закреплён в pyproject.toml как >=3.14,<3.15 и .python-version=3.14.
  Исправлены два устаревших указания Python в исходных промптах.
- Создана локальная .venv на установленном Python 3.14.4 x64, global Python
  не менялся. Лёгкие dev-инструменты установлены, версии зафиксированы в uv.lock.
  Установка отдельно разрешена владельцем.
- Совместимость проверена по метаданным PyPI и wheel tags для CPython 3.14
  Windows x64; 20 пакетов допускают выбранную версию/имеют подходящие wheels.
  Отдельно проверена пара torch/torchaudio 2.9.1 для ограничения Silero audio.
- Источники, уровни подтверждения и риски ML/CUDA записаны в python314_compatibility.md.
- Код приложения, GUI, настройки, БД-репозитории, IPC, модели и CUDA не реализуются.
- Commit, push и изменение индекса не выполняются.

## Проверки текущего продолжения

Все команды ниже выполнены из корня в активированном локальном окружении.
Get-Command python/ruff указывал на .venv/Scripts; sys.prefix отличался от
sys.base_prefix, архитектура 64 bit и GIL=True.

| Команда / проверка | Результат | Фактические данные |
| --- | --- | --- |
| python --version | PASS | Python 3.14.4. |
| python -m pytest -q | PASS | 73 passed in 1.65s, exit 0; все негативные сценарии выполнены, пропусков нет. |
| ruff check . | PASS | All checks passed!, exit 0; Ruff 0.16.10. |
| ruff format --check . | PASS | 16 files already formatted, exit 0. |
| git diff --check | PASS | Код 0; предупреждения существующего core.autocrlf о LF/CRLF не являются ошибками пробелов. |
| uv sync --only-dev --python .venv/Scripts/python.exe | PASS | Локально установлены лёгкие dev-пакеты; 13 записей lock включая проект. Runtime dependencies пусты. |
| uv --cache-dir .cache/uv lock --check --offline | PASS | Resolved 13 packages in 1ms; lock соответствует pyproject.toml. |
| python -m pip check | PASS | No broken requirements found. |
| Полный оригинал / идентификаторы | PASS | Перенесено всё ТЗ 1.0; 15 тестов сравнивают все условия FR/NFR с оригиналом, отдельный тест проверяет полный текст оригинала в requirements.md. |
| Матрица требований и шагов | PASS | Все FR-01–FR-10 / NFR-01–NFR-05 сопоставлены шагам; пункты без ID также учтены, покрыты 00–17. |
| Внутренние ссылки / документы | PASS | 39 локальных ссылок корректны, обязательные документы читаются как UTF-8. |
| .gitignore / секреты | PASS | 19 локальных/приватных примеров исключены, 9 проектных разрешены; типичные ключи/токены/пароль в PostgreSQL URL не найдены в 21 проектном файле. .env.example без пароля. |
| Сохранность кода и оригинала | PASS | SHA-256 src/main.py, src/local_transcriber/__init__.py и ORIGINAL_TZ.md совпадают с исходными. |
| Python / dev-окружение / lock | PASS | >=3.14,<3.15 соответствует ==3.14.* в lock. Python 3.11/3.12/3.13/3.15 отклонены тестами. uv 0.12.23, pytest 9.1.1, Ruff 0.16.10, Hatchling 1.32.4 установлены только в .venv. |
| Глобальный Python | PASS | Остался исходный 3.14.4; глобальные uv/Ruff отсутствуют, никакой установки туда не было. |
| Планируемые зависимости (PyPI metadata/wheel tags) | PASS | Проверены 20 пакетов для обычного CPython 3.14 Windows x64 и дополнительная пара torch/torchaudio 2.9.1; источники и ограничения в python314_compatibility.md. |
| Импорт/runtime ML, VAD/GPU/CUDA/cuDNN | NOT RUN | По заданию тяжёлые библиотеки/модели не устанавливались. На 06–07 проверить импорты, DLL, локальную модель, VAD, GPU smoke, OOM и фиксировать реальные версии. |
| Реальные PostgreSQL/FFmpeg/GUI/packaged/E2E | SKIP | Вне 00; реализации и тестовые данные появятся на соответствующих шагах, см. план и матрицу. |

## Исправленные ошибки проверок и среда запуска

- Начальная Python-обвязка выбирала глобальный python из-за особенностей поиска
  subprocess executable на Windows. Этот запуск не использован как подтверждение
  .venv. Финальные команды выполнялись после настройки PATH/VIRTUAL_ENV в
  PowerShell; путь интерпретатора и prefix проверены явно, вывод настроен UTF-8.
- Первый корректный запуск .venv: 71 passed, 2 errors — PermissionError в общем
  Windows Temp/pytest-of-jke при создании tmp_path. Общий каталог не удалялся и
  его права не менялись. Для повторного запуска создан новый уникальный каталог
  tmp/pytest-<UUID> внутри проекта и задан PYTEST_DEBUG_TEMPROOT.
- Ruff format сначала сообщил 1 file would be reformatted. Отформатирован только
  tests/test_repository_audit.py; итоговый format --check успешен.
- Общий uv cache оказался недоступен в sandbox. Финальная offline-проверка
  использует игнорируемый локальный .cache/uv; права общего кэша не изменялись.
- Код приложения не менялся; исправления ограничены документацией, dev-конфигурацией,
  тестами и безопасным способом запуска проверок.

## Чек-лист завершения 00

- [x] Полное ТЗ прочитано, перенесено без потери идентификаторов и условий;
  оригинал сохранён.
- [x] Требования, архитектура, план и матрица 00–17 согласованы.
- [x] Python окончательно закреплён; конфликтующие указания в промптах исправлены.
- [x] Локальная Python 3.14 .venv и dev-инструменты подготовлены, lock согласован.
- [x] Все предусмотренные проверки 00 и негативные сценарии выполнены.
- [x] Неисполненные runtime/hardware проверки перечислены с планом, без заявления
  о проверенной работоспособности будущего приложения.
- [x] Исходники, данные, оригинальное ТЗ, Git HEAD и индекс сохранены.
- [ ] Владелец принял отчёт и отдельным запросом разрешил 01.

Блокирующих проблем для шага 00 нет. Вердикт: **READY к ШАГУ 01**.
Готовность относится к аудиту и среде разработки, не к MVP.


## Риски и проверки будущих шагов

- Наличие wheel не подтверждает import, inference или весь транзитивный граф.
- faster-whisper/CTranslate2: выбрать релиз, проверить VC++ Runtime, CUDA 12,
  cuDNN 9 и DLL, реальный GPU smoke и OOM fallback в 06.
- Silero: audio/all extras требуют torchaudio <2.10; подобрать пару torch/
  torchaudio либо минимальный backend и проверить VAD в 07.
- ONNX Runtime CPU проверен по метаданным; GPU provider отдельно не проверен
  и не нужен для проверки 00. PySide6/упаковка проверяются на 12–13/16.
- Производительность, WER/CER, память, возобновление и все критерии MVP — gates
  будущих шагов, успешный аудит не утверждает готовность desktop-приложения.

## Следующий шаг

Шаг 00 готов к приёмке. Только после нового задания — 01: единая точка входа,
--version/--help, smoke импорта и использования пакета. Уже подготовленное
dev-окружение не пересоздавать. Runtime-библиотеки добавляются по своим шагам.

## История до этого продолжения

Ниже сохранён прежний отчёт как историческая запись. Его BLOCKED/NOT RUN и
запрос выбора Python относятся к состоянию до предоставления ORIGINAL_TZ.md
и окончательного решения владельца; они не являются текущими статусами.

<details>
<summary>Предварительная подготовка и первая попытка аудита 00</summary>

# История шага 02

Дата: 2026-10-08.

## Текущий этап

Предварительная подготовка до V2 завершена и опубликована коммитом 0317329.
Текущий ШАГ 00 V2 — «Аудит текущего репозитория и закрепление ТЗ».
Статус: **BLOCKED FOR REQUIREMENTS** — полного оригинального ТЗ нет.
Доступная часть аудита выполнена, 46 проверок успешны. Приёмка шага
заблокирована отсутствием полного ТЗ; конфликт Python также остаётся открытым.
Реализация приложения не начата, шаг 01 не разрешён.

## Выполнено

- Изучено исходное состояние: пустой main.py, один коммит, отсутствие инфраструктуры.
- С явного разрешения пользователя .git перенесён из src/ в Transcribation/;
  история, remote и индекс сохранены. Исходный src/main.py остаётся пустым.
- Созданы AGENTS.md, README.md, четыре документа в docs/ и .gitignore.
- Добавлен pyproject.toml: метаданные, src-layout, Hatchling, dev-группа,
  настройки pytest и Ruff. Runtime-зависимости отсутствуют.
- Созданы минимальный пакет local_transcriber и tests/README.md.
- Описаны будущая единая точка входа, процессы и границы модулей.
- Начальные решения записаны в docs/decisions.md.
- Документы сверены: границы этапа, слой Domain, отдельный GPU worker,
  локальность данных, хранение медиа вне БД и статус точки входа согласованы.
- На момент завершения этапа подготовки commit и push не выполнялись.
  Установка зависимостей и следующий этап не выполнялись.

## Исторические проверки предварительной подготовки

Результаты ниже относятся к подготовке до V2; они не являются текущим
прогоном аудита. Новый набор проверок шага 00 приведён отдельно ниже.

## Что реально проверено при предварительной подготовке

Среда: Python 3.14.4, pytest 9.0.3, Git 2.53.0.windows.2.

| Проверка | Результат |
| --- | --- |
| git rev-parse --show-toplevel | Git-корень — Transcribation/. |
| git log -1 --oneline; git ls-files; git remote -v | Прежний коммит 9ee9b91 и origin сохранены; индекс содержит прежний main.py. |
| git fsck --full | Код 0, ошибок целостности Git нет. |
| git diff --check | Код 0. Дополнительно все созданные файлы проверены на завершающий LF и отсутствие пробелов в конце строк. |
| Python tomllib + packaging | TOML разобран; синтаксис зависимостей, requires-python, build backend, пути пакета/тестов и отсутствие runtime-зависимостей проверены. Это не проверка разрешения/сборки. |
| Проверка файлов и Python AST | Ровно 11 ожидаемых проектных файлов; main.py пуст; __init__.py содержит только docstring, исполняемой логики нет. |
| Проверка Markdown | UTF-8 корректен; все 7 внутренних ссылок существуют. Содержательная согласованность проверена отдельно. |
| git check-ignore --no-index | 56 примеров секретов, медиа, моделей, кэшей, транскриптов, логов и временных данных исключены; 18 примеров исходников, документов, uv.lock и .env.example разрешены. |
| python -m pytest --collect-only -p no:cacheprovider (из корня) | pyproject.toml принят, собрано 0 тестов, реальный код pytest — 5. Тесты не выполнялись; успешный прогон не заявляется. |
| Наличие uv, Ruff, Hatchling | Отсутствуют; uv sync/lock, Ruff и сборка пакета не запускались. |

Проверки выполнялись без создания моделей, медиа, БД и рабочих данных.
Временные файлы подготовки удалены; исходные пользовательские файлы сохранены.

## Известные проблемы и ограничения

- uv и Ruff не установлены; Hatchling отсутствует. Сборка и разрешение
  зависимостей не проверены. uv.lock не создан.
- Для шага 00 добавлены тесты структуры/Git, но они не заменяют полный оригинал ТЗ.
- Выбор Python 3.11 (V2) против >=3.14 (ADR-010) запрошен у владельца.
- Совместимость полного стека Python/Windows/CUDA/моделей не подтверждена.
  Минимум >=3.14 задаёт базу этапа 0, а не обещание совместимости будущих библиотек.
- Полное исходное ТЗ отсутствует; вопросы о форматах, качестве, дорожках,
  структурировании текста, экспорте и хранении собраны в docs/requirements.md.

## Передача подготовленного этапа в Git

2026-10-08 пользователь отдельно разрешил commit и push в свой репозиторий.
Целевая ветка — main, remote — origin (JustKillEnemies/LocalTranscribe).
Перед публикацией локальная и удалённая main указывали на 9ee9b91.
В коммит включается весь подготовленный набор документов и минимальная
структура; прежний main.py получает путь src/main.py, оставаясь пустым.
Для автора используются данные первого коммита, без изменения глобальных
настроек Git. Результат отправки проверяется сравнением локального HEAD
с удалённой refs/heads/main и сообщается пользователю после выполнения.

## ШАГ 00 V2: аудит и расхождения

Прочитаны AGENTS.md, требования, архитектура, progress, decisions и найденный
пользовательский LocalTranscribe_Codex_Prompts_V2.md. До аудита Git diff пуст;
единственный незакоммиченный файл — пользовательский файл промптов.
Он сохранён без изменений. Перечень расхождений находится в requirements.md.

- Отсутствующее имя CODEX_PROMPTS_V2.md исправлено указателем на исходник.
- Добавлен implementation_plan.md с шагами 00–17 и явными зависимостями.
- Установлены источники правды: requirements.md и progress.md.
- Создан .env.example без секретов и загрузчика настроек.
- Воспроизведён дефект Git-исключений: database.backup, dumps/database.sql и
  database.sql.gz не игнорировались (git check-ignore возвращал 1).
  Правила расширены без исключения SQL-миграций; добавлены регрессионные проверки.
- Добавлены и успешно выполнены негативные сценарии отсутствующего документа
  и повреждённого UTF-8 с проверкой неизменности данных.
- Все 46 тестов аудита прошли, включая регрессию Git-исключений дампов.
- Проверено 21 локальное Markdown-соединение; TOML разобран, дерево просмотрено.
- SHA-256 исходников, pyproject.toml и пользовательского файла промптов совпадают
  с контрольными суммами до правок; потери пользовательских материалов нет.
- Исходники приложения и pyproject.toml не меняются. Шаги 01–17 не реализуются.

## Результаты проверок ШАГА 00 V2

Команды выполнялись из корня Transcribation. PASS тестов структуры не снимает
блокер требований. Исходный сбой Git-исключений воспроизведён до исправления:
для database.backup, dumps/database.sql, database.sql.gz git check-ignore
возвращал 1; после исправления — 0. SQL-миграции и .env.example не игнорируются
(код 1, ожидаемо). Это регрессия правил Git, не испытание реальной PostgreSQL.

| Проверка / команда | Статус | Фактический результат |
| --- | --- | --- |
| python -B -m pytest -q -p no:cacheprovider | PASS | 46 passed in 1.41s, exit 0. |
| Негативные сценарии в том же pytest | PASS | Отсутствующий документ: Missing required document: docs/CODEX_PROMPTS_V2.md; повреждённый UTF-8: UnicodeDecodeError. Контрольные данные не изменены. |
| git check-ignore --no-index <путь> (тесты) | PASS | 19 локальных/приватных примеров исключены; 9 проектных примеров разрешены, включая миграции SQL. |
| git diff --check | PASS | Код 0. Git сообщает только предупреждения существующего core.autocrlf о LF/CRLF; ошибки пробелов отсутствуют. |
| git status --short --untracked-files=all; просмотр дерева | PASS | 8 отслеживаемых файлов изменены, 4 новых создано; пользовательский файл промптов остаётся untracked и не менялся. Удалений нет, индекс не изменён. |
| SHA-256 четырёх защищённых файлов (Python hashlib) | PASS | src/main.py, src/local_transcriber/__init__.py, pyproject.toml и пользовательские промпты идентичны исходным. |
| TOML (Python tomllib); локальные ссылки (Python pathlib/re) | PASS | TOML разобран; 21 локальная ссылка указывает на существующий файл. |
| Сравнение требований с полным оригинальным ТЗ | NOT RUN | Оригинал отсутствует, его путь/текст запрошены у пользователя. Соответствие ТЗ не подтверждено. |
| ruff check .; ruff format --check . | NOT RUN | Ruff отсутствует и как команда, и как Python-модуль. Установка инструментов относится к 01; проверять после отдельной подготовки среды. |
| uv sync / uv lock / сборка пакета | NOT RUN | uv и Hatchling отсутствуют; эти действия не входят в аудит 00 и не выполнялись. |
| GPU / PostgreSQL / FFmpeg / GUI / E2E | SKIP | Не применимы к 00: здесь только документы, структура и Git. Runtime-адаптеры не реализованы; план задаёт реальные проверки на своих шагах. |

Результаты команд и воспроизведения сохранены в этой таблице, diff доступен
через git diff; новые файлы показаны git status. Commit/push в этой задаче
не выполнялись: прежнее разрешение относилось к публикации предварительной подготовки.

## Ручной чек-лист аудита

- [x] Прочитаны заданные документы; отсутствующий путь промптов явно обнаружен
  и исправлен указателем без изменения исходника.
- [x] Дерево, Git-статус, исходный diff и итоговые изменения просмотрены.
- [x] Сохранены src-layout, src/main.py, пользовательские документы и отсутствие
  runtime-реализаций; не созданы лишние Python-модули приложения.
- [x] Требования и статусы имеют по одному источнику; прошлую подготовку
  отделили от шага 00 V2. Все расхождения перечислены в requirements.md.
- [x] Windows 11, RTX 4060 Ti 8 GB, русский язык и локальность обработки закреплены.
- [x] Проверен минимум один отказ и регрессия найденного дефекта.
- [ ] Получено и сопоставлено полное оригинальное ТЗ.
- [ ] Владелец разрешил конфликт Python 3.11 / >=3.14.
- [ ] Выполнены Ruff lint/format после появления инструмента.
- [ ] Владелец принял 00 и отдельным запросом разрешил 01.

Вердикт: **BLOCKED FOR REQUIREMENTS**. Документальная часть реализована,
но статус DONE/READY не заявляется; следующий шаг не начат.

## Следующий этап

Сначала завершить приёмку 00: получить оригинальное ТЗ, сопоставить требования,
разрешить конфликт Python и выполнить недостающие проверки качества.
Затем, только по новому явному заданию, шаг 01 — пакет/точка входа и инструменты.
Настройки относятся к 02. Полный план — implementation_plan.md.

## Исторические критерии предварительной подготовки

- [x] Все запрошенные документы и конфигурация существуют в проектном корне.
- [x] Документы согласованы и отличают планы от реализованного.
- [x] src/main.py сохранён; пакет расположен в src/, tests/ — в корне.
- [x] pyproject.toml корректно разобран, настройки доступного pytest проверены;
  недоступность остальных инструментов явно отражена.
- [x] .gitignore проверен на секретах, медиа, моделях и локальных артефактах.
- [x] Реальные результаты проверок и ограничения отражены в этом документе.
- [x] Бизнес-логика и будущие этапы не реализованы; на этапе подготовки
  commit и push не выполнялись. Разрешение на публикацию получено отдельно.

</details>

</details>

</details>

</details>

</details>

</details>

</details>

</details>

</details>

</details>

</details>

</details>

</details>
