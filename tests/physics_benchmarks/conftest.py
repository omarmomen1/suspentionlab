"""Benchmark recorder.

Each benchmark test calls record(...) with measured values and tolerances. When
BENCH_RECORD_PATH is set (scripts/generate_benchmark_status.py does this), the
recorded values and each test's pass/fail outcome are written there. A failing
test therefore becomes a red tile with no manual step.
"""
import json
import os

import pytest

_RECORDS: dict = {}
_OUTCOMES: dict = {}


@pytest.fixture
def record(request):
    def _record(**fields):
        _RECORDS.setdefault(request.node.nodeid, {}).update(fields)
    return _record


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when == "call":
        _OUTCOMES[item.nodeid] = "PASS" if rep.passed else "FAIL"
    elif rep.when == "setup" and not rep.passed:
        _OUTCOMES[item.nodeid] = "FAIL"


def pytest_sessionfinish(session, exitstatus):
    path = os.environ.get("BENCH_RECORD_PATH")
    if not path:
        return
    out = {
        nodeid: {"verdict": _OUTCOMES.get(nodeid, "FAIL"), **_RECORDS.get(nodeid, {})}
        for nodeid in set(_OUTCOMES) | set(_RECORDS)
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, sort_keys=True)
