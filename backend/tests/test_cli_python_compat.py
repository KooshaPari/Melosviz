"""Keep CLI syntax compatible with the package's declared Python minimum."""
import ast
from pathlib import Path

import pytest


@pytest.mark.parametrize("version", [(3, 10), (3, 11)])
def test_cli_parses_on_supported_python_versions(version):
    source = Path(__file__).parents[1] / "src/melosviz/cli/main.py"
    ast.parse(source.read_text(), filename=str(source), feature_version=version)
