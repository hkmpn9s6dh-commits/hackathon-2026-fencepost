from conftest import FIXTURES

from fencepost.detectors import load_repo
from fencepost.scan.code import collect_env_reads, collect_imports, collect_subcommands
from fencepost.scan.project import load_project, normalise_dist, version_floor


def test_version_floor_understands_the_common_operators():
    assert version_floor(">=3.11") == (3, 11)
    assert version_floor(">3.9") == (3, 10)
    assert version_floor("~=3.10") == (3, 10)
    assert version_floor("3.11") == (3, 11)
    assert version_floor(">=3.10,<4") == (3, 10)
    assert version_floor(None) is None


def test_distribution_names_normalise_like_pep_503():
    assert normalise_dist("PyYAML") == "pyyaml"
    assert normalise_dist("python_dateutil") == "python-dateutil"
    assert normalise_dist("ruamel.yaml") == "ruamel-yaml"


def test_project_reads_requires_python_and_dependencies():
    project = load_project(FIXTURES / "multi")
    assert project.requires_python == ">=3.12"
    assert [dep.name for dep in project.dependencies] == ["httpx"]
    assert project.requires_python_line >= 1


def test_imports_are_found_without_importing_the_project():
    imports = collect_imports(FIXTURES / "missing-dep")
    assert "yaml" in imports
    assert imports["yaml"].file.endswith("load.py")


def test_env_reads_cover_subscript_and_getenv(tmp_path):
    (tmp_path / "m.py").write_text(
        "import os\nA = os.environ['ONE_KEY']\nB = os.getenv('TWO_KEY')\n", encoding="utf-8"
    )
    reads = collect_env_reads(tmp_path)
    assert set(reads) == {"ONE_KEY", "TWO_KEY"}


def test_subcommands_are_read_from_add_parser():
    commands = collect_subcommands(FIXTURES / "phantom-command")
    assert set(commands) == {"audit"}


def test_stdlib_imports_are_not_reported():
    imports = collect_imports(FIXTURES / "multi")
    assert "tomllib" not in imports
    assert "yaml" in imports


def test_fencepostignore_excludes_paths(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "v.py").write_text("import yaml\n", encoding="utf-8")
    (tmp_path / ".fencepostignore").write_text("vendor/\n", encoding="utf-8")
    repo = load_repo(tmp_path)
    assert "yaml" not in repo.imports
