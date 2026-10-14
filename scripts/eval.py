"""Refuse unimplemented evaluation rather than manufacture result rows."""

from _bootstrap import run

if __name__ == "__main__":
    raise SystemExit(run("eval"))
