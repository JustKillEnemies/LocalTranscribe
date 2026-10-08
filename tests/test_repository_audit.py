"""Step 00: document, structure and Git checks; no application implementation."""

import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest
from packaging.specifiers import SpecifierSet

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read_required_document(root: Path, relative: str) -> str:
    path = root / relative
    if not path.is_file():
        raise AssertionError(f"Missing required document: {relative}")
    return path.read_text(encoding="utf-8")


def _git(*arguments: str) -> subprocess.CompletedProcess[str]:
    assert shutil.which("git"), "Git is required for the step 00 audit"
    return subprocess.run(
        ["git", *arguments],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


@pytest.mark.parametrize(
    "relative",
    [
        "AGENTS.md",
        "README.md",
        "docs/CODEX_PROMPTS_V2.md",
        "docs/LocalTranscribe_Codex_Prompts_V2.md",
        "docs/requirements.md",
        "docs/ORIGINAL_TZ.md",
        "docs/requirements_traceability.md",
        "docs/python314_compatibility.md",
        "docs/architecture.md",
        "docs/decisions.md",
        "docs/progress.md",
        "docs/implementation_plan.md",
        ".env.example",
    ],
)
def test_required_documents_exist_and_are_readable(relative: str) -> None:
    assert _read_required_document(PROJECT_ROOT, relative).strip()


def test_canonical_prompt_path_resolves_to_preserved_source() -> None:
    pointer = _read_required_document(PROJECT_ROOT, "docs/CODEX_PROMPTS_V2.md")
    targets = re.findall(r"\[[^\]]+\]\(([^)]+)\)", pointer)
    assert "LocalTranscribe_Codex_Prompts_V2.md" in targets
    source = _read_required_document(PROJECT_ROOT, "docs/LocalTranscribe_Codex_Prompts_V2.md")
    assert re.search(r"^## [^\n]+? 00\.", source, flags=re.MULTILINE)


def test_missing_prompt_file_reports_path_without_data_loss(tmp_path: Path) -> None:
    user_file = tmp_path / "recording.mkv"
    user_file.write_bytes(b"synthetic preservation sentinel")
    original = user_file.read_bytes()
    relative = "docs/CODEX_PROMPTS_V2.md"

    with pytest.raises(AssertionError, match=re.escape(f"Missing required document: {relative}")):
        _read_required_document(tmp_path, relative)

    assert user_file.read_bytes() == original
    assert sorted(path.name for path in tmp_path.iterdir()) == ["recording.mkv"]


def test_corrupt_document_is_not_silently_accepted(tmp_path: Path) -> None:
    document = tmp_path / "requirements.md"
    document.write_bytes(b"\xff\xfe\x00")
    original = document.read_bytes()

    with pytest.raises(UnicodeDecodeError):
        _read_required_document(tmp_path, "requirements.md")

    assert document.read_bytes() == original


def test_main_file_is_present_in_src_layout() -> None:
    assert (PROJECT_ROOT / "src/main.py").is_file()
    assert not (PROJECT_ROOT / "main.py").exists()


def test_git_root_and_agents_scope() -> None:
    result = _git("rev-parse", "--show-toplevel")
    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()).resolve() == PROJECT_ROOT
    assert not (PROJECT_ROOT / "src/.git").exists()
    agents = _read_required_document(PROJECT_ROOT, "AGENTS.md")
    for scope in ("Transcribation", "src/local_transcriber", "tests/", "Windows", "4060 Ti"):
        assert scope in agents


@pytest.mark.parametrize(
    "relative",
    [
        ".env",
        ".env.production",
        "recordings/obs.mkv",
        "source.mp4",
        "audio.wav",
        "exports/result.txt",
        "exports/result.json",
        "transcripts/result.md",
        "models/model/config.json",
        "model.safetensors",
        "tmp/decoded.raw",
        "logs/app.log",
        "backups/database.sql",
        "database.dump",
        "database.backup",
        "dumps/database.sql",
        "database.sql.gz",
        "database.sql.bz2",
        "database.sql.xz",
    ],
)
def test_gitignore_protects_local_and_private_data(relative: str) -> None:
    result = _git("check-ignore", "--no-index", relative)
    assert result.returncode == 0, f"Not ignored: {relative}; {result.stderr}"


@pytest.mark.parametrize(
    "relative",
    [
        ".env.example",
        "AGENTS.md",
        "docs/CODEX_PROMPTS_V2.md",
        "docs/implementation_plan.md",
        "src/main.py",
        "src/local_transcriber/__init__.py",
        "tests/test_repository_audit.py",
        "migrations/versions/example.sql",
        "uv.lock",
    ],
)
def test_gitignore_allows_project_materials(relative: str) -> None:
    result = _git("check-ignore", "--no-index", relative)
    assert result.returncode == 1, f"Unexpected ignore: {relative}; {result.stderr}"


def test_plan_covers_source_steps_in_order() -> None:
    source = _read_required_document(PROJECT_ROOT, "docs/LocalTranscribe_Codex_Prompts_V2.md")
    plan = _read_required_document(PROJECT_ROOT, "docs/implementation_plan.md")
    headings = re.findall(r"^## [^\n]+? (\d{2})\. (.+)$", source, flags=re.MULTILINE)
    rows = re.findall(r"^\| (\d{2}) \| ([^|]+) \| ([^|]+) \|", plan, flags=re.MULTILINE)
    assert [number for number, _ in headings] == [f"{number:02d}" for number in range(18)]
    assert [(number, title.strip()) for number, title, _ in rows] == headings
    for number, _, dependencies in rows[1:]:
        assert f"{int(number) - 1:02d}" in dependencies


def test_example_has_no_embedded_credentials() -> None:
    example = _read_required_document(PROJECT_ROOT, ".env.example")
    values = {}
    for line in example.splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, separator, value = line.partition("=")
            assert separator, f"Invalid environment line: {line}"
            values[key] = value
    assert values["LOCAL_TRANSCRIBER_POSTGRES_PASSWORD"] == ""
    assert values["LOCAL_TRANSCRIBER_POSTGRES_TEST_DB"] != values["LOCAL_TRANSCRIBER_POSTGRES_DB"]
    assert not any("API_KEY" in key or "TOKEN" in key for key in values)


def _requirement_sections(content: str) -> dict[str, str]:
    pattern = r"^## ((?:FR|NFR)-\d{2})\. .*?(?=^#{1,2} |\Z)"
    return {
        match.group(1): match.group(0).strip()
        for match in re.finditer(pattern, content, flags=re.MULTILINE | re.DOTALL)
    }


@pytest.mark.parametrize(
    "identifier",
    [f"FR-{number:02d}" for number in range(1, 11)]
    + [f"NFR-{number:02d}" for number in range(1, 6)],
)
def test_original_requirement_clauses_and_ids_are_preserved(identifier: str) -> None:
    original = _read_required_document(PROJECT_ROOT, "docs/ORIGINAL_TZ.md")
    normalized = _read_required_document(PROJECT_ROOT, "docs/requirements.md")
    assert (
        _requirement_sections(normalized)[identifier] == _requirement_sections(original)[identifier]
    )


def test_traceability_covers_all_original_requirements_and_steps() -> None:
    original = _read_required_document(PROJECT_ROOT, "docs/ORIGINAL_TZ.md")
    trace = _read_required_document(PROJECT_ROOT, "docs/requirements_traceability.md")
    identifiers = set(_requirement_sections(original))
    rows = re.findall(r"^\| ((?:FR|NFR)-\d{2}) \| ([^|]+) \| ([^|]+) \|", trace, re.MULTILINE)
    assert {identifier for identifier, _, _ in rows} == identifiers
    for identifier, implementation, acceptance in rows:
        assert re.findall(r"\b(?:0\d|1[0-7])\b", implementation), identifier
        assert re.findall(r"\b(?:0\d|1[0-7])\b", acceptance), identifier
    assert set(re.findall(r"\b(?:0\d|1[0-7])\b", trace)) == {
        f"{number:02d}" for number in range(18)
    }


@pytest.mark.parametrize(
    ("version", "accepted"),
    [
        ("3.11.9", False),
        ("3.12.0", False),
        ("3.13.9", False),
        ("3.14.0", True),
        ("3.14.4", True),
        ("3.15.0", False),
    ],
)
def test_python_minor_version_is_fixed(version: str, accepted: bool) -> None:
    config = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert config["project"]["requires-python"] == ">=3.14,<3.15"
    assert (version in SpecifierSet(config["project"]["requires-python"])) is accepted
    assert (PROJECT_ROOT / ".python-version").read_text(encoding="utf-8").strip() == "3.14"


def test_original_tz_is_available_and_linked_as_source() -> None:
    original = _read_required_document(PROJECT_ROOT, "docs/ORIGINAL_TZ.md")
    requirements = _read_required_document(PROJECT_ROOT, "docs/requirements.md")
    assert len(_requirement_sections(original)) == 15
    assert "(ORIGINAL_TZ.md)" in requirements
    assert original.strip() in requirements


def test_prompt_python_policy_is_current() -> None:
    prompts = _read_required_document(PROJECT_ROOT, "docs/LocalTranscribe_Codex_Prompts_V2.md")
    assert "Python 3.14" in prompts
    assert "Python 3.11" not in prompts
    assert "Python 3.12" not in prompts


def test_all_internal_document_links_resolve() -> None:
    for document in [PROJECT_ROOT / "README.md", *sorted((PROJECT_ROOT / "docs").glob("*.md"))]:
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
            if "://" not in target:
                assert (document.parent / target.split("#")[0]).is_file(), (document.name, target)
