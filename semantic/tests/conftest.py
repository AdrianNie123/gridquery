# Shared fixtures for the semantic-layer verification suite.
# Every governed Cube metric is checked against independently computed
# DuckDB SQL over the marts. Cube must be running locally (make cube-up).

import json
import time
from pathlib import Path

import duckdb
import pytest
import requests

CUBE_BASE_URL = "http://localhost:4000"
CUBE_LOAD_URL = CUBE_BASE_URL + "/cubejs-api/v1/load"
CUBE_META_URL = CUBE_BASE_URL + "/cubejs-api/v1/meta"

REPO_ROOT = Path(__file__).resolve().parents[2]
DUCKDB_PATH = REPO_ROOT / "data" / "gridquery.duckdb"


def to_float(value):
    """Cube returns numbers as strings or numbers, nulls as None."""
    if value is None:
        return None
    return float(value)


@pytest.fixture(scope="session")
def cube_available():
    """Fail the session early with a clear message if Cube is not running."""
    try:
        resp = requests.get(CUBE_META_URL, timeout=5)
        resp.raise_for_status()
    except requests.RequestException as exc:
        pytest.fail(
            f"Cube is not reachable at {CUBE_BASE_URL} ({exc}). "
            "Start it with `make cube-up` and re-run the suite."
        )


@pytest.fixture(scope="session")
def cube_query(cube_available):
    """Return a helper that runs a Cube REST query dict and returns row dicts."""

    def _query(query_dict):
        params = {"query": json.dumps(query_dict)}
        for _ in range(60):
            resp = requests.get(CUBE_LOAD_URL, params=params, timeout=60)
            try:
                body = resp.json()
            except ValueError:
                raise AssertionError(
                    f"Cube returned non-JSON (HTTP {resp.status_code}): {resp.text[:500]}"
                )
            if body.get("error") == "Continue wait":
                time.sleep(1)
                continue
            if resp.status_code != 200 or "error" in body:
                raise AssertionError(
                    f"Cube query failed: {body.get('error', resp.text[:500])}\n"
                    f"query: {json.dumps(query_dict)}"
                )
            return body["data"]
        raise AssertionError(
            f"Cube kept returning 'Continue wait' for query: {json.dumps(query_dict)}"
        )

    return _query


@pytest.fixture(scope="session")
def cube_meta(cube_available):
    """Raw /v1/meta payload for governance checks."""
    return requests.get(CUBE_META_URL, timeout=10).json()


@pytest.fixture(scope="session")
def db():
    """Read-only DuckDB connection to the warehouse, path resolved from repo root."""
    if not DUCKDB_PATH.exists():
        pytest.fail(
            f"DuckDB warehouse not found at {DUCKDB_PATH}. "
            "Build it first (dbt build in transform/)."
        )
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    yield con
    con.close()
