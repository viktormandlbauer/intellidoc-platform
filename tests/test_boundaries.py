"""Package dependencies: service -> contracts <- worker -> engine -> contracts."""
import ast
import subprocess
import sys
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1] / "src" / "intellidoc"

# what each package may import from intellidoc, besides itself
ALLOWED = {
    "contracts": set(),
    "engine": {"contracts"},
    "worker": {"engine", "contracts"},
    "service": {"contracts"},
}


def _imports(path: Path) -> set[str]:
    """intellidoc-internal modules imported by a file, as dotted paths below `intellidoc`."""
    rel = path.relative_to(PKG).with_suffix("").parts
    package = rel[:-1]  # the package a relative import starts from
    out = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                base = list(package[: len(package) - node.level + 1])
                mod = ".".join(base + ([node.module] if node.module else []))
            elif (node.module or "").startswith("intellidoc."):
                mod = node.module.removeprefix("intellidoc.")
            else:
                continue
            out.add(mod)
        elif isinstance(node, ast.Import):
            out |= {a.name.removeprefix("intellidoc.") for a in node.names if a.name.startswith("intellidoc.")}
    return out


@pytest.mark.parametrize("pkg", sorted(ALLOWED))
def test_imports_respect_the_layering(pkg):
    bad = []
    for f in sorted((PKG / pkg).rglob("*.py")):
        for mod in _imports(f):
            if mod == "" or mod == pkg or mod.startswith(pkg + "."):
                continue  # the top-level package (__version__) or itself
            if not any(mod == a or mod.startswith(a + ".") for a in ALLOWED[pkg]):
                bad.append(f"{f.relative_to(PKG)} imports intellidoc.{mod}")
    assert not bad, "\n".join(bad)


def test_service_runs_without_engine_dependencies():
    """Importing the service must not load the engine or its heavy dependencies, so the API image
    can be installed with `intellidoc[api]` alone."""
    code = (
        "import sys, intellidoc.service, intellidoc.contracts; "
        "heavy = ('intellidoc.engine', 'intellidoc.worker', 'docling', 'sklearn', 'yaml', 'psycopg', 'laya', 'torch'); "
        "print(sorted({m.split('.')[0] if not m.startswith('intellidoc') else '.'.join(m.split('.')[:2]) "
        "for m in sys.modules if m.startswith(heavy)}))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
    assert out.strip() == "[]"
