import os
import re
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest

for _name, _value in {
    "CHAT_MODEL": "test/chat-model",
    "CHAT_MODEL_API_KEY": "test-key",
    "JUDGE_CHAT_MODEL": "test/judge-model",
    "JUDGE_CHAT_MODEL_API_KEY": "test-key",
}.items():
    os.environ.setdefault(_name, _value)

_LINE = re.compile(r"^(?P<key>\S+::\S+)\s+(?P<tags>(?:@\w+:[A-Z]+-\d+\s*)+)$")


def _load_trace() -> dict[str, str]:
    path = os.environ.get("TEST_TRACE_FILE")
    if not path or not Path(path).is_file():
        return {}
    trace: dict[str, str] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        match = _LINE.match(line.strip())
        if match:
            trace[match["key"]] = match["tags"].strip()
    return trace


_TRACE = _load_trace()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, Any, None]:
    outcome = yield
    report = outcome.get_result()
    path, line, name = report.location
    base = name.split("[")[0]
    tags = _TRACE.get(f"{path}::{name}") or _TRACE.get(f"{path}::{base}")
    if tags:
        report.location = (path, line, f"{name} {tags}")
