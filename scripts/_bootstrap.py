"""Resolve the package from this checkout, including after it is moved."""

import importlib
import sys
from pathlib import Path


def load(module: str):
    source = Path(__file__).resolve().parents[1] / "src"
    sys.path.insert(0, str(source))
    return importlib.import_module(f"hiring_signals.{module}")


def run(command: str) -> int:
    return load("cli").main([command, *sys.argv[1:]])
