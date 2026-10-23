import ast
import subprocess
import sys
from pathlib import Path


def test_domain_imports_with_only_standard_library_available():
    source = Path(__file__).resolve().parents[2] / "src"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-c",
            (
                "import sys; sys.path.insert(0, sys.argv[1]); "
                "from receipt_bot.domain.money import Money; print(Money(1).units)"
            ),
            str(source),
        ],
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "1"


def test_domain_has_no_imports_from_other_layers_or_external_packages():
    domain = Path(__file__).resolve().parents[2] / "src" / "receipt_bot" / "domain"
    for path in domain.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            for module in modules:
                assert (
                    module == "receipt_bot.domain"
                    or module.startswith("receipt_bot.domain.")
                    or module.split(".")[0] in sys.stdlib_module_names
                )
