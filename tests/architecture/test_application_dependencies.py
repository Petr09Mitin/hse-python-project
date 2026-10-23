import ast
import subprocess
import sys
from pathlib import Path


def test_application_imports_with_only_standard_library_available():
    source = Path(__file__).resolve().parents[2] / "src"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-c",
            (
                "import sys; sys.path.insert(0, sys.argv[1]); "
                "from receipt_bot.application.messaging.message_dispatcher import MessageDispatcher; "
                "print(MessageDispatcher.__name__)"
            ),
            str(source),
        ],
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "MessageDispatcher"


def test_application_imports_only_domain_application_and_standard_library():
    application = Path(__file__).resolve().parents[2] / "src/receipt_bot/application"
    for path in application.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            for module in modules:
                assert (
                    module in ("receipt_bot.domain", "receipt_bot.application")
                    or module.startswith(("receipt_bot.domain.", "receipt_bot.application."))
                    or module.split(".")[0] in sys.stdlib_module_names
                )
