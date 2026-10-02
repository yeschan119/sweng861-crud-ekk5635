"""The JSON log formatter: one parseable object per record, core fields protected.

AI use: drafting and test-case enumeration.
"""

import json
import logging
import sys

from logging_setup import JsonFormatter, configure_logging, request_id_var


def _record(message="hello", level=logging.INFO, exc_info=None, **extra):
    record = logging.LogRecord("sweng861.test", level, __file__, 1, message, None, exc_info)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def _format(record):
    return json.loads(JsonFormatter().format(record))


def test_a_record_becomes_one_json_object_with_the_core_fields():
    entry = _format(_record())

    assert entry["level"] == "INFO"
    assert entry["logger"] == "sweng861.test"
    assert entry["message"] == "hello"
    assert entry["timestamp"].endswith("+00:00")
    assert entry["request_id"] is None


def test_the_request_id_comes_from_the_context():
    token = request_id_var.set("req-123")
    try:
        entry = _format(_record())
    finally:
        request_id_var.reset(token)

    assert entry["request_id"] == "req-123"


def test_extra_fields_are_included():
    entry = _format(_record(event="coverage_created", coverage_id=7))

    assert entry["event"] == "coverage_created"
    assert entry["coverage_id"] == 7


def test_an_extra_cannot_overwrite_a_core_field():
    token = request_id_var.set("real-id")
    try:
        entry = _format(_record(level=logging.ERROR, request_id="forged", logger="x"))
    finally:
        request_id_var.reset(token)

    assert entry["level"] == "ERROR"
    assert entry["request_id"] == "real-id"
    assert entry["logger"] == "sweng861.test"


def test_an_unserialisable_extra_does_not_lose_the_line():
    entry = _format(_record(when=object()))

    assert entry["message"] == "hello"
    assert entry["when"].startswith("<object object")


def test_an_exception_is_kept_with_its_traceback():
    try:
        raise ValueError("boom")
    except ValueError:
        entry = _format(_record(level=logging.ERROR, exc_info=sys.exc_info()))

    assert "ValueError: boom" in entry["exception"]


def test_configure_logging_writes_json_to_stdout_and_is_idempotent(capsys):
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    try:
        configure_logging()
        configure_logging()
        logging.getLogger("sweng861.test").info("configured")

        lines = capsys.readouterr().out.strip().splitlines()
        assert len(root.handlers) == 1
        assert [json.loads(line)["message"] for line in lines] == ["configured"]
    finally:
        root.handlers, root.level = saved_handlers, saved_level


def test_configure_logging_keeps_httpx_from_logging_urls():
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    try:
        configure_logging()
        assert logging.getLogger("httpx").getEffectiveLevel() == logging.WARNING
    finally:
        root.handlers, root.level = saved_handlers, saved_level
