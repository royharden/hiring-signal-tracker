"""Resolve the same committed product assets in a source checkout or installed wheel."""

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = PACKAGE_ROOT.parent.parent
SOURCE_CHECKOUT = PACKAGE_ROOT.parent.name == "src" and (_REPO_ROOT / "pyproject.toml").is_file()
PRODUCT_ROOT = _REPO_ROOT if SOURCE_CHECKOUT else PACKAGE_ROOT
RUBRIC_PATH = (
    PRODUCT_ROOT / "docs/annotation-guide.md"
    if SOURCE_CHECKOUT
    else PACKAGE_ROOT / "data/annotation-guide.md"
)
