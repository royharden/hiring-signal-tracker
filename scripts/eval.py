"""Explicit offline synthetic DEV rules evaluation; no implicit corpus or heldout run."""

from _bootstrap import run

if __name__ == "__main__":
    raise SystemExit(run("eval"))
