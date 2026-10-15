"""Actual moved S3 offline controls cannot import the owner app/SDK or use network."""

import builtins
import socket

import pytest


@pytest.fixture(autouse=True)
def owner_and_network_blocked(monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in {"llm_router_eval", "openai", "typesafe", "anthropic"}:
            raise AssertionError("owner_app_or_sdk_import_forbidden")
        return original(name, *args, **kwargs)

    def denied(*args, **kwargs):
        raise AssertionError("network_forbidden")

    monkeypatch.setattr(builtins, "__import__", guarded)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
