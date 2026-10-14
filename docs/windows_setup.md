# Установка и Windows onedir build

CPython 3.14 x64 с GIL остаётся единственной версией для разработки. Target —
Windows 10/11 x64; фактическая сборка/испытания выполнялись на Windows 11.
Вердикт, реальные проверки и оставшиеся ограничения — [progress.md](progress.md).

## Готовый комплект

Текущий локальный artifact: `dist/LocalTranscribe Windows x64/LocalTranscribe/`.
Переносите папку целиком: LocalTranscribe.exe + _internal + dist-inventory.json.
Это onedir, не установщик. Python/uv для запуска готового exe не требуются;
NVIDIA CUDA/cuDNN DLL уже входят в _internal/nvidia, модель вынесена отдельно.
Не переносите только exe и не записывайте данные в _internal.

Двойной щелчок exe открывает GUI; `--help`/`--version` доступны из PowerShell.
Это console build: при GUI может оставаться консоль. Source launchers
`python -m local_transcriber` и src/main.py сохраняют прежний CLI.

Внешние компоненты подготавливаются пользователем:

1. NVIDIA-драйвер для RTX 4060 Ti. В испытаниях driver 596.21, GPU 8 GB.
2. Локальная PostgreSQL 17+; проверена 18.3. Служба/роль/БД устанавливаются и
   создаются отдельно, приложение не устанавливает и не управляет службой.
3. FFmpeg/ffprobe x64; проверен FFmpeg 9.0.2 essentials. Укажите абсолютные пути.
   Источники: [FFmpeg](https://ffmpeg.org/download.html),
   [Windows builds Gyan](https://www.gyan.dev/ffmpeg/builds/).
   Эти executables в комплект приложения не входят; их лицензии сохраняйте
   вместе с выбранной внешней поставкой.
4. Локальная CTranslate2-модель large-v3-turbo: весь каталог model.bin,
   config.json, tokenizer.json и остальные файлы исходной поставки. Существующая
   модель находится в `%LOCALAPPDATA%/LocalTranscriber/models/large-v3-turbo`.
5. Для чистой ОС подготовьте Microsoft Visual C++ x64 Redistributable по
   [официальной инструкции Microsoft](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist).

Официальные инструкции: [PostgreSQL Windows](https://www.postgresql.org/download/windows/),
[CTranslate2 installation](https://opennmt.net/CTranslate2/installation.html),
[faster-whisper](https://github.com/SYSTRAN/faster-whisper),
[PyInstaller deployment](https://pyinstaller.org/en/stable/).

## Конфигурация и первый запуск

Файл `.env` хранится вне dist/Git. По умолчанию используется
`%LOCALAPPDATA%/LocalTranscriber/.env`; другой файл задаётся `--env-file`.
Взять основу можно из [корневого примера](../.env.example) или
`_internal/examples/.env.example`. Заполните локальные PostgreSQL host/port/db/
user/password и пути ffmpeg/ffprobe/pg_isready/model. Environment выше .env.
Пути абсолютные, в .env используйте `/` или одинарные кавычки.

В psql, от имени администратора своей PostgreSQL, можно подготовить отдельную
роль и БД приложения (не выполнять на чужом сервере):

```sql
CREATE ROLE local_transcriber LOGIN;
\password local_transcriber
CREATE DATABASE local_transcriber OWNER local_transcriber;
```

Пароль вводится интерактивно, а затем сохраняется только в локальной конфигурации.
Миграции применяются явно к настроенной существующей БД; автоматического создания
DB/role/service нет. `--test` у db-upgrade выбирает только отдельную *_test/test_*
БД через тот же AppSettings и отказывает, если она совпадает с рабочей.

```powershell
$app = '.\dist\LocalTranscribe Windows x64\LocalTranscribe\LocalTranscribe.exe'
$config = Join-Path $env:LOCALAPPDATA 'LocalTranscriber/.env'
& $app --version
& $app doctor --env-file $config --create-dirs
& $app db-upgrade --env-file $config
& $app doctor --env-file $config
& $app gui --env-file $config
```

doctor проверяет readiness, но не создаёт схему и не подтверждает успешный
inference. Повторный db-upgrade head идемпотентен. Не запускайте автоматические
integration tests с рабочей БД; используйте owned-cluster runner.

## Совместимость GPU и модели

Проверенный комплект из lock: faster-whisper 1.2.1 / CTranslate2 4.8.2 /
cuBLAS wheel 12.9.2.10 / cuDNN wheel 9.27.0.42 / ONNX Runtime 1.31.0,
PySide6 6.12.0, CPython 3.14.4. Точные build/dependency versions и лицензии
записаны в `_internal/build-manifest.json`; SHA-256 файлов — dist-inventory.json.
Системный CUDA Toolkit для этой сборки отдельно не устанавливался: runtime DLL
включены из locked NVIDIA wheels. Драйвер остаётся внешним компонентом.
Не подменяйте отдельные DLL случайными версиями и не понижайте Python.

Основная Whisper-модель не входит в dist. На этом ПК можно использовать уже
скачанную модель, либо осознанно загрузить её в dev-среде с интернетом:

```powershell
@'
from faster_whisper.utils import download_model
from pathlib import Path
import os
download_model("large-v3-turbo", output_dir=str(Path(os.environ["LOCALAPPDATA"]) / "LocalTranscriber/models/large-v3-turbo"))
'@ | uv run python -
```

Это отдельная подготовка, не автоматическое действие приложения. Сохраняйте
лицензию поставщика модели. При offline старте отсутствующая модель вызывает
понятную ошибку, не загрузку. Модель/GUI/GPU worker — разные владельцы ресурсов;
процесс inference отделён от интерфейса, один активный GPU worker.

## Offline и пользовательские данные

После подготовки модели, драйвера, FFmpeg и PostgreSQL соединение с интернетом
для обработки не нужно. Для дополнительного offline режима библиотек:

```powershell
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
& $app gui --env-file $config
```

По умолчанию кэш/логи/temp — под LocalTranscriber user-data; это не dist и не
Program Files. Исходники media не копируются в PostgreSQL и не удаляются при
удалении истории. Runtime лог исключает текст/пароли; явное обслуживание — через
maintenance с подтверждением для destructive actions.

Автотест packaged mode использует isolated AppSettings/profile directories,
read-only ACL только собственного artifact, PATH без dev .venv и запрещает
Python non-loopback socket attempts audit hook. Это не отключение ОС от сети:
native network firewall test и отдельный новый Windows account/VM оцениваются
отдельно. Для ручной приёмки на чистой ОС отключите внешний интернет, оставив
loopback PostgreSQL, и выполните doctor → import → transcribe → export/GUI.

## Воспроизводимая сборка разработчика

Из корня существующего проекта, в Python 3.14 .venv:

```powershell
uv sync --locked
uv run python --version
uv run python scripts/build_windows.py --output 'dist/My fresh Windows build'
```

Закреплены PyInstaller 6.22.3 и hooks-contrib 2026.8 в uv.lock. Входы —
[spec](../bundling/LocalTranscribe.spec), [entry](../bundling/entry.py),
[builder/audit](../scripts/build_windows.py), src и migrations. Build работает
на Windows x64, не cross-compiles. SOURCE_DATE_EPOCH берётся из Git HEAD,
PYTHONHASHSEED=0; manifest фиксирует версии и input hashes. Побайтовая идентичность
двух builds не заявляется; воспроизводится процедура из locked inputs.
Выходной каталог должен быть новым: существующие файлы/сборки не перезаписываются.

Bundle inputs заданы явно; веса Whisper/.env/медиа/SQL dumps/пользовательские
transcripts/репозиторий целиком не собираются. Маленький Silero VAD ONNX,
поставляемый faster-whisper, включён как runtime asset. Python DLL, Qt plugins,
PyAV/ORT/SQLAlchemy/psycopg, CUDA DLL и dependency notices включены.

Для повторения реальной packaged проверки (нужен уже подготовленный local
FLEURS fixture по [benchmark.md](benchmark.md) и model path):

```powershell
.venv/Scripts/python.exe scripts/check_postgresql.py --pytest-target tests/test_packaging.py --packaged-exe 'dist/My fresh Windows build/LocalTranscribe/LocalTranscribe.exe'
```

Runner использует собственный loopback PostgreSQL cluster, останавливает его в
finally, не трогает системную службу. Обычный pytest без --packaged-exe пропускает
только opt-in packaged integration; unit regressions выполняются всегда.

Установка в настоящее чистое окружение/VM и Windows 10 пока требуют отдельных
фактических проверок. Проблемы запуска: [руководство пользователя](user_guide.md),
[компоненты и лицензии](third_party_notices.md).
