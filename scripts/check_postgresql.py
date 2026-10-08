"""Run Step 03 on an owned temporary Windows PostgreSQL cluster.

Uses existing binaries only; does not install PostgreSQL or manage its service.
"""

import argparse
import json
import os
import secrets
import socket
import subprocess
from pathlib import Path
from uuid import uuid4


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--postgres-bin", type=Path, default=Path("C:/Program Files/PostgreSQL/18/bin")
    )
    args = parser.parse_args()
    binaries = args.postgres_bin.resolve()
    required = ("initdb.exe", "pg_ctl.exe", "createdb.exe", "psql.exe", "postgres.exe")
    if os.name != "nt" or not all((binaries / name).is_file() for name in required):
        parser.error("Requires Windows and existing PostgreSQL binaries; nothing installed")
    root = Path(__file__).resolve().parents[1]
    work = root / "tmp" / ("step03-pg-" + uuid4().hex)
    work.mkdir(parents=True)
    cluster = work / "cluster"
    pwfile = work / "bootstrap-password"
    password = secrets.token_urlsafe(32)
    pwfile.write_text(password + "\n", encoding="utf-8")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    environment = os.environ.copy()
    environment.update(
        LOCAL_TRANSCRIBER_POSTGRES_HOST="127.0.0.1",
        LOCAL_TRANSCRIBER_POSTGRES_PORT=str(port),
        LOCAL_TRANSCRIBER_POSTGRES_USER="localtranscriber_test",
        LOCAL_TRANSCRIBER_POSTGRES_PASSWORD=password,
        LOCAL_TRANSCRIBER_POSTGRES_DB="local_transcriber",
        LOCAL_TRANSCRIBER_POSTGRES_TEST_DB="local_transcriber_test",
        LOCAL_TRANSCRIBER_POSTGRES_DSN=(
            f"postgresql://localtranscriber_test:{password}@127.0.0.1:{port}/local_transcriber"
        ),
        PGPASSWORD=password,
        PGCONNECT_TIMEOUT="5",
        PYTEST_REQUIRE_POSTGRES="1",
        PATH=str(root / ".venv/Scripts") + os.pathsep + environment["PATH"],
        VIRTUAL_ENV=str(root / ".venv"),
        UV_CACHE_DIR=str(root / ".cache/uv"),
        UV_PYTHON_DOWNLOADS="never",
        PYTEST_DEBUG_TEMPROOT=str(work / "pytest"),
    )
    (work / "pytest").mkdir()
    results: list[dict[str, str | int]] = []

    def run(arguments: list[str | Path], label: str) -> None:
        print("CHECK:", label, flush=True)
        output_file = work / ("check-" + str(len(results)) + ".log")
        # File capture avoids Windows pg_ctl child holding a pipe open.
        with output_file.open("wb") as output:
            process = subprocess.run(
                [str(argument) for argument in arguments],
                cwd=root,
                env=environment,
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=output,
                stderr=subprocess.STDOUT,
            )
        output = output_file.read_text(encoding="utf-8", errors="replace")
        print(output.replace(password, "[REDACTED]"), flush=True)
        results.append({"check": label, "exit": process.returncode})
        if process.returncode:
            raise RuntimeError("Check failed: " + label)

    failed = False
    try:
        run(
            [
                binaries / "initdb.exe",
                "-D",
                cluster,
                "-U",
                "localtranscriber_test",
                "--pwfile",
                pwfile,
                "--auth-host=scram-sha-256",
                "--auth-local=scram-sha-256",
                "--encoding=UTF8",
                "--locale=C",
            ],
            "initdb",
        )
        pwfile.unlink()
        run(
            [
                binaries / "pg_ctl.exe",
                "-D",
                cluster,
                "-l",
                work / "server.log",
                "-o",
                f"-h 127.0.0.1 -p {port}",
                "-w",
                "start",
            ],
            "start owned PostgreSQL",
        )
        run(
            [
                binaries / "createdb.exe",
                "-h",
                "127.0.0.1",
                "-p",
                str(port),
                "-U",
                "localtranscriber_test",
                "local_transcriber_test",
            ],
            "create test DB",
        )
        run(
            [
                binaries / "psql.exe",
                "-h",
                "127.0.0.1",
                "-p",
                str(port),
                "-U",
                "localtranscriber_test",
                "-d",
                "local_transcriber_test",
                "-At",
                "-c",
                "SELECT current_database(), version();",
            ],
            "real PostgreSQL connection",
        )
        uv = root / ".venv/Scripts/uv.exe"
        run([uv, "run", "python", "--version"], "python --version")
        run([uv, "run", "pytest", "-q"], "uv run pytest -q")
        run([uv, "run", "pytest", "tests/test_database_unit.py", "-q"], "database unit tests")
        run([uv, "run", "pytest", "tests/test_postgresql.py", "-q"], "PostgreSQL integration tests")
        for operation in (
            ("upgrade", "head"),
            ("upgrade", "head"),
            ("check",),
            ("downgrade", "base"),
            ("upgrade", "head"),
            ("current",),
        ):
            run(
                [uv, "run", "alembic", "-x", "test=true", *operation],
                "alembic " + " ".join(operation),
            )
        run([uv, "run", "ruff", "check", "."], "uv run ruff check .")
        run([uv, "run", "ruff", "format", "--check", "."], "uv run ruff format --check .")
        run(["git", "diff", "--check"], "git diff --check")
    except (OSError, RuntimeError) as error:
        print(str(error).replace(password, "[REDACTED]"), flush=True)
        failed = True
    finally:
        if pwfile.exists():
            pwfile.unlink()
        # Even a partially failed pg_ctl start may leave our server running.
        if (cluster / "postmaster.pid").exists():
            try:
                run(
                    [binaries / "pg_ctl.exe", "-D", cluster, "-w", "stop", "-m", "fast"],
                    "stop owned PostgreSQL",
                )
            except OSError, RuntimeError:
                print("Owned PostgreSQL stop failed; inspect temporary cluster", flush=True)
                failed = True
        (work / "checks.json").write_text(
            json.dumps({"port": port, "results": results}, indent=2), encoding="utf-8"
        )
        print("ARTIFACT:", work / "checks.json", flush=True)
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
