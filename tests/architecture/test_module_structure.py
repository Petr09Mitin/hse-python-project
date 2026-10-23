import ast
from graphlib import TopologicalSorter
from pathlib import Path


def test_local_modules_have_no_import_cycles():
    source = Path(__file__).resolve().parents[2] / "src"
    graph = {}
    for path in (source / "receipt_bot").rglob("*.py"):
        module = ".".join(path.relative_to(source).with_suffix("").parts)
        graph[module] = set()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                graph[module].update(alias.name for alias in node.names if alias.name.startswith("receipt_bot."))
            elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("receipt_bot."):
                graph[module].add(node.module)
    TopologicalSorter(graph).prepare()


def test_each_source_file_contains_at_most_one_class():
    source = Path(__file__).resolve().parents[2] / "src/receipt_bot"
    for path in source.rglob("*.py"):
        classes = [
            node for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))) if isinstance(node, ast.ClassDef)
        ]
        assert len(classes) <= 1, path
