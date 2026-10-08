# Transcribation

Локальное desktop-приложение для преобразования длительных OBS-записей и
аудиофайлов в структурированный, читаемый русский текст.

Целевая среда: Windows 11, NVIDIA RTX 4060 Ti 8 GB и локальная PostgreSQL.
Обработка должна выполняться на компьютере пользователя без платных API и
облачной передачи медиа или транскриптов.

## Текущее состояние

Предварительная подготовка репозитория завершена и сохранена в Git.
Шаг 00 промптов V2 — аудит и среда разработки; отчёт о его завершении находится
в progress.md. Следующий шаг автоматически не начинается.
Единственный источник текущего статуса и результатов — [docs/progress.md](docs/progress.md).
Полное [исходное ТЗ](docs/ORIGINAL_TZ.md) предоставлено и синхронизировано с
[requirements.md](docs/requirements.md); [матрица этапов](docs/requirements_traceability.md)
показывает, где выполняется каждое требование.
Транскрибация, GUI, GPU worker, работа с PostgreSQL и экспорт **не реализованы**.
Пакет `local_transcriber` содержит только описание; `src/main.py` сохранён пустым.
Команды запуска приложения пока нет.

## Структура

```text
Transcribation/
├── AGENTS.md
├── README.md
├── .gitignore
├── .env.example
├── pyproject.toml
├── .python-version
├── uv.lock
├── docs/
│   ├── CODEX_PROMPTS_V2.md
│   ├── LocalTranscribe_Codex_Prompts_V2.md
│   ├── implementation_plan.md
│   ├── ORIGINAL_TZ.md
│   ├── requirements_traceability.md
│   ├── python314_compatibility.md
│   ├── requirements.md
│   ├── architecture.md
│   ├── progress.md
│   └── decisions.md
├── src/
│   ├── main.py
│   └── local_transcriber/
│       └── __init__.py
└── tests/
    ├── README.md
    └── test_repository_audit.py
```

Git-корень — `Transcribation/`. Каталог `.git` перенесён из `src/` с разрешения
пользователя, история и remote сохранены. В подготовленном коммите прежний
корневой `main.py` получил путь `src/main.py`; файл остаётся пустым.
Папка проекта называется Transcribation, GitHub-репозиторий — LocalTranscribe,
Python-пакет — local_transcriber. Переименование не требуется.

## Документация

- [Требования](docs/requirements.md): известный объём проекта и открытые вопросы.
- [Архитектура](docs/architecture.md): слои, модули, процессы и поток обработки.
- [Состояние](docs/progress.md): выполненные работы, проверки и следующий этап.
- [Решения](docs/decisions.md): принятые решения и их обоснование.
- [Правила агента](AGENTS.md): постоянные ограничения разработки.
- [Промпты V2](docs/CODEX_PROMPTS_V2.md): указатель на пользовательский исходник.
- [План 00–17](docs/implementation_plan.md): порядок и зависимости без статусов.

## Среда разработки

Python окончательно выбран: обычный CPython 3.14 x64 с GIL, >=3.14,<3.15.
Локальное dev-окружение — .venv на Python 3.14.4; глобальная установка не меняется.
[Совместимость ML-зависимостей](docs/python314_compatibility.md) проверяется
отдельно по wheels, импортам и реальному GPU inference. Модели и CUDA пока
не устанавливаются, транскрибация и CLI приложения ещё не реализованы.

`pyproject.toml` задаёт закреплённый Hatchling и группу dev: uv, pytest, Ruff
и Hatchling. Точные версии окружения зафиксированы в uv.lock.
Runtime-зависимости пока отсутствуют. PySide6, PostgreSQL-адаптеры, модели,
CUDA-библиотеки и движок распознавания на этом этапе не устанавливаются.

Из корня проекта после установки dev-зависимостей:

```powershell
.\.venv\Scripts\Activate.ps1
python --version
python -m pytest -q
ruff check .
ruff format --check .
git diff --check
```

Без активации можно вызывать .venv/Scripts/python.exe и ruff.exe напрямую.
Для воспроизведения только dev-окружения используется локальный uv:

```powershell
.\.venv\Scripts\uv.exe sync --locked --only-dev --python .\.venv\Scripts\python.exe
```

Если .venv отсутствует, создайте её уже установленным Python 3.14, затем
установите uv только внутрь неё (python -m venv .venv;
.venv/Scripts/python.exe -m pip install uv==0.12.23). Пакеты среды разработки
загружаются из PyPI; пользовательские медиа не отправляются.

Эти команды — инструкция для дальнейшей работы, а не отчёт об их выполнении.
Для шага 00 добавлены настоящие проверки структуры, документации, Git-исключений
и негативных сценариев; они не запускают GUI, GPU или БД. Их можно выполнить
доступным pytest без установки пакета:

```powershell
python -B -m pytest -q -p no:cacheprovider
```

Фактический результат — в progress.md. Успех аудита и инструментов разработки
не означает работоспособность будущего приложения.

uv.lock фиксирует лёгкие dev-зависимости для Python 3.14. ML/CUDA/GUI/БД
не добавлены в runtime-зависимости и не устанавливаются этим lock-файлом.

Единая будущая точка входа — `local_transcriber.__main__:main`. При реализации
bootstrap `python -m local_transcriber`, console script и совместимый
`src/main.py` должны делегировать ей; сейчас эти точки входа не реализуются.

## Локальные данные

Предусмотрены исключённые из Git каталоги `media/`, `recordings/`, `models/`,
`data/`, `transcripts/`, `exports/`, `logs/`, `tmp/`, `backups/` и `dumps/`.
Они пока не создаются. Секреты — в локальном окружении или `.env`, никогда в коде.
Фактические пользовательские пути будут определены при реализации настроек.
`.env.example` содержит только безопасные примеры и пустой пароль; значения
пока не читаются приложением. Загрузку конфигурации реализует шаг 02.
SQL-миграции можно хранить в Git; SQL-дампы помещайте в backups/ или dumps/.

Если pytest сообщает PermissionError для общего Windows Temp, используйте
новый уникальный корень временных данных, не удаляя старый каталог:

```powershell
$pytestTempRoot = Join-Path (Get-Location).Path ('tmp/pytest-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $pytestTempRoot | Out-Null
$env:PYTEST_DEBUG_TEMPROOT = $pytestTempRoot
python -m pytest -q
```

Для ограниченной среды uv можно явно задать локальный кэш:
`.venv/Scripts/uv.exe --cache-dir .cache/uv lock --check --offline`.
Эти настройки действуют только в текущем процессе и не меняют глобальный Python.
