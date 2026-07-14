# Shared fixtures for the NL-interface tests.
# Offline tests run against a checked-in /v1/meta snapshot so they need
# neither a running Cube nor an API key. Live tests (marked) verify the
# snapshot still matches the serving surface and exercise the real stack.

import json
import os
from pathlib import Path

import pytest

from nl.catalog import governed_views

FIXTURE_META = Path(__file__).parent / "fixtures" / "meta.json"


@pytest.fixture(scope="session")
def meta():
    return json.loads(FIXTURE_META.read_text())


@pytest.fixture(scope="session")
def views(meta):
    return governed_views(meta)


def require_api_key():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set; live NL tests skipped")
