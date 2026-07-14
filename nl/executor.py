"""Execute a validated QueryPlan against Cube's REST API.

Only /cubejs-api/v1/load is touched, only with plans that passed the
validator. Cube errors surface as CubeQueryError; nothing is retried
except Cube's own "Continue wait" long-query handshake.
"""

import json
import time

import requests

from nl.catalog import CUBE_LOAD_URL
from nl.schema import QueryPlan


class CubeQueryError(RuntimeError):
    pass


def to_cube_query(plan: QueryPlan) -> dict:
    """Translate the QueryPlan into Cube's REST query dict."""
    query: dict = {"measures": plan.measures}
    if plan.dimensions:
        query["dimensions"] = plan.dimensions
    if plan.filters:
        query["filters"] = [
            {"member": f.member, "operator": f.operator}
            | ({"values": f.values} if f.values else {})
            for f in plan.filters
        ]
    if plan.time_dimension is not None:
        td: dict = {"dimension": plan.time_dimension.dimension}
        if plan.time_dimension.granularity is not None:
            td["granularity"] = plan.time_dimension.granularity
        if plan.time_dimension.date_range is not None:
            td["dateRange"] = plan.time_dimension.date_range
        query["timeDimensions"] = [td]
    if plan.order:
        query["order"] = {o.member: o.direction for o in plan.order}
    if plan.limit is not None:
        query["limit"] = plan.limit
    return query


def execute_plan(plan: QueryPlan, load_url: str = CUBE_LOAD_URL) -> list[dict]:
    """Run the plan and return Cube's result rows."""
    params = {"query": json.dumps(to_cube_query(plan))}
    for _ in range(60):
        resp = requests.get(load_url, params=params, timeout=60)
        try:
            body = resp.json()
        except ValueError:
            raise CubeQueryError(
                f"Cube returned non-JSON (HTTP {resp.status_code}): {resp.text[:500]}"
            )
        if body.get("error") == "Continue wait":
            time.sleep(1)
            continue
        if resp.status_code != 200 or "error" in body:
            raise CubeQueryError(f"Cube query failed: {body.get('error', resp.text[:500])}")
        return body["data"]
    raise CubeQueryError("Cube kept returning 'Continue wait'")
