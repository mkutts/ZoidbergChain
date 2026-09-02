"""Regression checks for the removed unused legacy embedding load."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ZOIDBERG_COIN = ROOT / "zoidbergCoin.py"
ORIGINALITY_REQUIREMENTS = ROOT / "requirements-originality.txt"
ML_MODULES = {"sentence_transformers", "transformers", "torch"}


def _imported_modules(source_path):
    tree = ast.parse(source_path.read_text(encoding="utf-8-sig"), filename=str(source_path))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[0])
    return modules


def _assigned_names(source_path):
    tree = ast.parse(source_path.read_text(encoding="utf-8-sig"), filename=str(source_path))
    return {
        target.id
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        for target in ([*node.targets] if isinstance(node, ast.Assign) else [node.target])
        if isinstance(target, ast.Name)
    }


def test_legacy_script_has_no_sentence_transformer_model_load():
    source = ZOIDBERG_COIN.read_text(encoding="utf-8")

    assert "sentence_transformers" not in source
    assert "SentenceTransformer" not in source
    assert "all-MiniLM-L6-v2" not in source
    assert "model" not in _assigned_names(ZOIDBERG_COIN)


def test_supported_production_sources_have_no_ml_stack_imports():
    production_sources = sorted([*ROOT.glob("*.py"), *(ROOT / "scripts").rglob("*.py")])

    for source_path in production_sources:
        assert not (_imported_modules(source_path) & ML_MODULES), source_path.name


def test_supported_originality_dependencies_remain_declared():
    declarations = set(ORIGINALITY_REQUIREMENTS.read_text(encoding="utf-8").splitlines())

    assert {"ImageHash==4.3.1", "pillow==12.3.0", "pytesseract==0.3.13"} <= declarations
