"""Moved S6 tests may not load its owner app or make a network connection."""

import builtins
import socket

import pytest


@pytest.fixture(autouse=True)
def no_owner_app_or_network(monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in {"issue_triage", "openai", "typesafe"}:
            raise AssertionError("owner_app_or_sdk_import_forbidden")
        return original(name, *args, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError("network_forbidden")

    monkeypatch.setattr(builtins, "__import__", guarded)
    monkeypatch.setattr(socket, "socket", forbidden)
