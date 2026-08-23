import json

import pytest
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from app.core.exception_handlers import http_exception_handler, unhandled_exception_handler

pytestmark = pytest.mark.unit


def _make_request(path: str = "/test") -> Request:
    scope = {
        "type": "http",
        "path": path,
        "headers": [],
        "method": "GET",
        "query_string": b"",
    }
    request = Request(scope)
    request.state.request_id = "test-trace-id"
    return request


async def test_unhandled_exception_handler_hides_internal_details() -> None:
    request = _make_request("/boom")
    response = await unhandled_exception_handler(request, ValueError("db password is hunter2"))

    assert response.status_code == 500
    body = json.loads(response.body)
    assert body["detail"] == "An unexpected error occurred."
    assert body["trace_id"] == "test-trace-id"
    assert "hunter2" not in response.body.decode()


async def test_http_exception_handler_uses_problem_json_shape() -> None:
    request = _make_request("/missing")
    exc = StarletteHTTPException(status_code=404, detail="Not Found")

    response = await http_exception_handler(request, exc)

    assert response.status_code == 404
    assert response.media_type == "application/problem+json"
    body = json.loads(response.body)
    assert body == {
        "type": "about:blank",
        "title": "Not Found",
        "status": 404,
        "detail": "Not Found",
        "instance": "/missing",
        "trace_id": "test-trace-id",
    }
