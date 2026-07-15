"""Shared fixtures for the eval-harness tests (offline, no API key).

The governed surface comes from the same /v1/meta fixture the nl tests
use, so golden plans are validated against the real governed shape."""

import json
from pathlib import Path

import pytest

from nl.catalog import governed_views

FIXTURE_META = (
    Path(__file__).resolve().parents[2] / "nl" / "tests" / "fixtures" / "meta.json"
)


@pytest.fixture(scope="session")
def meta():
    return json.loads(FIXTURE_META.read_text())


@pytest.fixture(scope="session")
def views(meta):
    return governed_views(meta)
