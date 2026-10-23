import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile


def test_wheel_imports_entire_application_and_resources_without_source_fallback(tmp_path):
    project = Path(__file__).resolve().parents[3]
    distribution = tmp_path / "distribution"
    subprocess.run(
        ["uv", "build", "--wheel", "--offline", "--out-dir", str(distribution)],
        cwd=project,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    installed = tmp_path / "installed"
    with ZipFile(next(distribution.glob("*.whl"))) as wheel:
        wheel.extractall(installed)
    script = (
        "import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); "
        "import receipt_bot; "
        "assert Path(receipt_bot.__file__).is_relative_to(sys.argv[1]); "
        "from receipt_bot.bootstrap.application_runner import ApplicationRunner; "
        "from receipt_bot.bootstrap.build_application import build_application; "
        "from receipt_bot.bootstrap.prepare_models import model_files; "
        "import receipt_bot.adapters.persistence.schema as schema; "
        "assert Path(schema.__file__).with_suffix('.sql').is_file(); "
        "assert model_files(); print('installed application and resources OK')"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", script, str(installed)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "installed application and resources OK"
