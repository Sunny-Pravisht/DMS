"""Rate limiter behaviour.

The end-to-end suite disables rate limiting (its counters are process-wide and
would trip on repeated logins), so the limits are pinned down here instead.
"""
from threading import Lock

import pytest

from app.middleware.rate_limit_middleware import RateLimitMiddleware


def make_middleware(**overrides):
    """Build a middleware instance without running __init__ (it starts a task)."""
    from collections import defaultdict

    middleware = RateLimitMiddleware.__new__(RateLimitMiddleware)
    middleware.default_limit = overrides.get("default_limit", 100)
    middleware.window_seconds = overrides.get("window_seconds", 60)
    middleware.login_limit = overrides.get("login_limit", 5)
    middleware.login_window_seconds = overrides.get("login_window_seconds", 300)
    middleware.trusted_proxy_ips = set(overrides.get("trusted_proxy_ips", ()))
    middleware.request_counts = defaultdict(lambda: defaultdict(list))
    middleware.lock = Lock()
    middleware.endpoint_limits = {
        "/api/auth/login": (middleware.login_limit, middleware.login_window_seconds),
        "/api/auth/setup/initial-user": (
            middleware.login_limit,
            middleware.login_window_seconds,
        ),
        "/api/documents/upload": (20, 60),
        "/api/ai/chat": (30, 60),
        "/api/ai/extract": (20, 60),
    }
    return middleware


def test_login_endpoint_uses_the_strict_limit():
    middleware = make_middleware()

    limit, window = middleware.get_rate_limit("/api/auth/login")

    assert (limit, window) == (5, 300)


def test_default_limit_applies_to_other_endpoints():
    middleware = make_middleware()

    assert middleware.get_rate_limit("/api/documents/") == (100, 60)


def test_sixth_login_attempt_is_blocked():
    middleware = make_middleware()
    limit, window = middleware.get_rate_limit("/api/auth/login")

    for attempt in range(limit):
        blocked, _ = middleware.is_rate_limited("1.2.3.4", "/api/auth/login", limit, window)
        assert blocked is False, f"attempt {attempt + 1} should be allowed"

    blocked, retry_after = middleware.is_rate_limited(
        "1.2.3.4", "/api/auth/login", limit, window
    )

    assert blocked is True
    assert 0 < retry_after <= window + 1


def test_limits_are_tracked_per_ip():
    middleware = make_middleware()
    limit, window = 2, 60

    for _ in range(limit):
        middleware.is_rate_limited("10.0.0.1", "/api/documents/", limit, window)

    blocked_first, _ = middleware.is_rate_limited("10.0.0.1", "/api/documents/", limit, window)
    blocked_other, _ = middleware.is_rate_limited("10.0.0.2", "/api/documents/", limit, window)

    assert blocked_first is True
    assert blocked_other is False


def test_limits_are_tracked_per_endpoint():
    middleware = make_middleware()
    limit, window = 2, 60

    for _ in range(limit):
        middleware.is_rate_limited("10.0.0.1", "/api/documents/", limit, window)

    blocked_same, _ = middleware.is_rate_limited("10.0.0.1", "/api/documents/", limit, window)
    blocked_other, _ = middleware.is_rate_limited("10.0.0.1", "/api/tags/", limit, window)

    assert blocked_same is True
    assert blocked_other is False


def test_auth_endpoints_are_marked_for_failure_only_counting():
    middleware = make_middleware()

    assert middleware.is_auth_endpoint("/api/auth/login") is True
    assert middleware.is_auth_endpoint("/api/auth/setup/initial-user") is True
    assert middleware.is_auth_endpoint("/api/documents/") is False


def test_check_rate_limit_does_not_consume_budget():
    """Checking must be side-effect free so successful logins stay free."""
    middleware = make_middleware()
    limit, window = 2, 60

    for _ in range(10):
        blocked, _ = middleware.check_rate_limit("1.1.1.1", "/api/auth/login", limit, window)
        assert blocked is False


def test_record_request_consumes_budget():
    middleware = make_middleware()
    limit, window = 2, 60

    middleware.record_request("1.1.1.1", "/api/auth/login")
    middleware.record_request("1.1.1.1", "/api/auth/login")

    blocked, _ = middleware.check_rate_limit("1.1.1.1", "/api/auth/login", limit, window)
    assert blocked is True


def test_clear_endpoint_resets_only_that_endpoint():
    middleware = make_middleware()

    middleware.record_request("1.1.1.1", "/api/auth/login")
    middleware.record_request("1.1.1.1", "/api/documents/")

    middleware.clear_endpoint("1.1.1.1", "/api/auth/login")

    assert middleware.check_rate_limit("1.1.1.1", "/api/auth/login", 1, 60)[0] is False
    assert middleware.check_rate_limit("1.1.1.1", "/api/documents/", 1, 60)[0] is True


def test_successful_logins_never_lock_the_user_out():
    """Regression: five successful sign-ins used to trigger 'Rate limit exceeded'."""
    middleware = make_middleware()
    limit, window = middleware.get_rate_limit("/api/auth/login")

    for attempt in range(limit * 3):
        blocked, _ = middleware.check_rate_limit("1.1.1.1", "/api/auth/login", limit, window)
        assert blocked is False, f"successful login {attempt + 1} was throttled"
        # Simulates the dispatch path for a 200 response.
        middleware.clear_endpoint("1.1.1.1", "/api/auth/login")


def test_failed_logins_still_lock_out():
    middleware = make_middleware()
    limit, window = middleware.get_rate_limit("/api/auth/login")

    for _ in range(limit):
        assert middleware.check_rate_limit("1.1.1.1", "/api/auth/login", limit, window)[0] is False
        middleware.record_request("1.1.1.1", "/api/auth/login")  # 401 path

    blocked, retry_after = middleware.check_rate_limit(
        "1.1.1.1", "/api/auth/login", limit, window
    )
    assert blocked is True
    assert retry_after > 0


def test_a_success_after_failures_clears_the_slate():
    """Mistyping the password twice must not haunt you after signing in."""
    middleware = make_middleware()
    limit, window = middleware.get_rate_limit("/api/auth/login")

    middleware.record_request("1.1.1.1", "/api/auth/login")
    middleware.record_request("1.1.1.1", "/api/auth/login")

    middleware.clear_endpoint("1.1.1.1", "/api/auth/login")  # successful login

    for _ in range(limit):
        assert middleware.check_rate_limit("1.1.1.1", "/api/auth/login", limit, window)[0] is False
        middleware.record_request("1.1.1.1", "/api/auth/login")


@pytest.mark.parametrize(
    "direct_ip,trusted,expected",
    [
        ("127.0.0.1", ["127.0.0.1"], "198.51.100.7"),  # trusted proxy: header wins
        ("203.0.113.10", ["127.0.0.1"], "203.0.113.10"),  # untrusted: header ignored
    ],
)
def test_forwarded_header_is_only_trusted_from_a_configured_proxy(
    direct_ip, trusted, expected
):
    from types import SimpleNamespace

    middleware = make_middleware(trusted_proxy_ips=trusted)
    request = SimpleNamespace(
        client=SimpleNamespace(host=direct_ip),
        headers={"X-Forwarded-For": "198.51.100.7"},
    )

    assert middleware.get_client_ip(request) == expected
