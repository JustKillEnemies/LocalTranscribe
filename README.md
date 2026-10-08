# Transcribation

Локальное desktop-приложение для преобразования длительных OBS-записей и
аудиофайлов в структурированный, читаемый русский текст.

Целевая среда: Windows 11, NVIDIA RTX 4060 Ti 8 GB и локальная PostgreSQL.
Обработка должна выполняться на компьютере пользователя без платных API и
облачной передачи медиа или транскриптов.

## Текущее состояние

Пакет поддерживает запуск, справку и вывод версии. Транскрибация, GUI,
GPU worker, PostgreSQL и экспорт пока не реализованы.
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
│       └── __main__.py
└── tests/
    ├── README.md
    ├── test_repository_audit.py
    └── test_cli.py
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
Runtime-зависимостей сейчас нет; тяжёлые AI/CUDA/GUI/БД библиотеки не устанавливаются.
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
код 0. Неизвестные аргументы, включая ещё не реализованный doctor, дают код 2
и диагностику в stderr. Сокращения вроде --vers не поддерживаются.
CLI не загружает модели, не создаёт worker и не читает .env.

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
Загрузка настроек и выбор пользовательских путей относятся к шагу 02.
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
