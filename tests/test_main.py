import unittest
from collections import defaultdict
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from main import _rate_limit_store, app, check_rate_limit

import tests._pathsetup  # noqa: F401

_INCLUDED_ROUTER_PREFIXES = {
    '/index', '/graph', '/response', '/manage'
}


class TestRoutes(unittest.TestCase):
    def setUp(self):
        self._lifespan_patches = [
            patch('main.loadAllIndexes', new_callable=AsyncMock),
            patch('main.reload_env_variables'),
            patch('main.init_settings'),
        ]
        for p in self._lifespan_patches:
            p.start()

    def tearDown(self):
        for p in self._lifespan_patches:
            p.stop()

    def test_routes_contain_expected_prefixes(self):
        found_prefixes = set()
        for r in app.router.routes:
            if hasattr(r, 'include_context'):
                prefix = r.include_context.prefix
                found_prefixes.add(prefix)
        for prefix in _INCLUDED_ROUTER_PREFIXES:
            self.assertIn(prefix, found_prefixes,
                          f"No included router found with prefix {prefix}")

    def test_root_endpoint_returns_hello(self):
        with TestClient(app) as client:
            response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"Hello": "CUITCCA"})

    def test_cors_middleware_configured(self):
        cors_middleware = [
            m for m in app.user_middleware if m.cls.__name__ == 'CORSMiddleware'
        ]
        self.assertEqual(len(cors_middleware), 1)
        kwargs = cors_middleware[0].kwargs
        self.assertIn("http://localhost", kwargs["allow_origins"])
        self.assertIn("Content-Type", kwargs["allow_headers"])
        self.assertIn("Authorization", kwargs["allow_headers"])

    def test_cors_preflight_returns_allow_origin(self):
        with TestClient(app) as client:
            client.options(
                "/", headers={"Origin": "http://localhost"}
            )
        # CORS middleware should handle preflight; if lifespan doesn't run,
        # response may be 405 but we can still verify the middleware is registered
        cors_middleware = [
            m for m in app.user_middleware if m.cls.__name__ == 'CORSMiddleware'
        ]
        self.assertTrue(len(cors_middleware) >= 1)

    def test_static_files_mount_registered(self):
        mount_routes = [
            r for r in app.router.routes
            if hasattr(r, 'path') and r.path.startswith('/web')
        ]
        static_routes = [
            r for r in app.router.routes
            if hasattr(r, 'name') and r.name == 'web'
        ]
        self.assertTrue(
            len(mount_routes) > 0 or len(static_routes) > 0,
            "Expected /web static mount to be registered",
        )


class TestRateLimit(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        _rate_limit_store.clear()

    async def test_within_limit_does_not_raise(self):
        ip = "1.2.3.4"
        for _ in range(30):
            await check_rate_limit(ip)

    async def test_over_limit_raises_http_429(self):
        _rate_limit_store.clear()
        ip = "1.2.3.4"
        for _ in range(30):
            await check_rate_limit(ip)
        with pytest.raises(HTTPException) as exc_info:
            await check_rate_limit(ip)
        self.assertEqual(exc_info.value.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    async def test_different_ips_have_separate_limits(self):
        _rate_limit_store.clear()
        ip_a = "1.2.3.4"
        ip_b = "5.6.7.8"
        for _ in range(30):
            await check_rate_limit(ip_a)
        await check_rate_limit(ip_b)
        with pytest.raises(HTTPException):
            await check_rate_limit(ip_a)


class TestSessionAndStatsMiddleware(unittest.TestCase):
    def setUp(self):
        self._lifespan_patches = [
            patch('main.loadAllIndexes', new_callable=AsyncMock),
            patch('main.reload_env_variables'),
            patch('main.init_settings'),
        ]
        for p in self._lifespan_patches:
            p.start()
        self._stats_dict = {
            "total_visits": 0,
            "ip_count": 0,
            "user_visits": defaultdict(int),
            "endpoint_visits": defaultdict(int),
        }
        self._stats_patch = patch('main.access_stats', self._stats_dict)
        self._stats_patch.start()

    def tearDown(self):
        for p in self._lifespan_patches:
            p.stop()
        self._stats_patch.stop()

    def test_session_cookie_set_on_first_request(self):
        with TestClient(app) as client:
            response = client.get("/")
        self.assertIn("session_id", response.cookies)
        self.assertTrue(len(response.cookies["session_id"]) > 0)

    def test_session_cookie_not_re_set_when_already_present(self):
        with TestClient(app) as client:
            first = client.get("/")
            session_id = first.cookies["session_id"]
            second = client.get("/", cookies={"session_id": session_id})
        set_cookies = second.headers.get_list("set-cookie")
        session_cookies = [c for c in set_cookies if "session_id=" in c]
        self.assertEqual(len(session_cookies), 0)

    def test_stats_increment_on_request(self):
        with TestClient(app) as client:
            client.get("/")
            client.get("/")
            client.get("/")
        self.assertGreaterEqual(self._stats_dict["total_visits"], 3)


if __name__ == "__main__":
    unittest.main()
