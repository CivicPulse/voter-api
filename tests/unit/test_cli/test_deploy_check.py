"""Unit tests for the deploy-check CLI command."""

from __future__ import annotations

import re
from unittest.mock import patch

import httpx
import pytest
from typer.testing import CliRunner

from voter_api.cli.app import app
from voter_api.cli.deploy_check_cmd import CheckStatus, _run_all_checks

runner = CliRunner()


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


BASE = "http://test-api:8000"


def _make_response(
    status_code: int = 200,
    json_data: object | None = None,
    *,
    text: str = "",
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """Build a fake httpx.Response."""
    if json_data is not None:
        import json

        content = json.dumps(json_data).encode()
        resp_headers = {"content-type": "application/json"}
    else:
        content = text.encode()
        resp_headers = {"content-type": "text/plain"}
    if headers:
        resp_headers.update(headers)
    return httpx.Response(
        status_code=status_code,
        content=content,
        headers=resp_headers,
        request=httpx.Request("GET", BASE),
    )


# --- Healthy response fixtures ---

_HEALTHY_RESPONSES = {
    "/api/v1/health": _make_response(json_data={"status": "healthy"}),
    "/api/v1/boundaries?page=1&page_size=1": _make_response(
        json_data={
            "items": [{"id": "b-1", "name": "Fulton", "boundary_type": "county"}],
            "pagination": {"total": 159, "page": 1, "page_size": 1, "total_pages": 159},
        }
    ),
    "/api/v1/boundaries/types": _make_response(json_data={"types": ["county", "state_senate"]}),
    "/api/v1/boundaries/containing-point?latitude=33.749&longitude=-84.388": _make_response(
        json_data=[{"id": "b-1", "name": "Fulton", "boundary_type": "county"}]
    ),
    "/api/v1/boundaries/geojson?boundary_type=county&page_size=1": _make_response(
        json_data={"type": "FeatureCollection", "features": []}
    ),
    "/api/v1/boundaries/b-1?include_geometry=false": _make_response(
        json_data={"id": "b-1", "name": "Fulton", "boundary_type": "county"}
    ),
    "/api/v1/elections?page=1&page_size=1": _make_response(
        json_data={
            "items": [{"id": "e-1", "name": "General 2024", "election_date": "2024-11-05", "election_type": "general"}],
            "pagination": {"total": 1, "page": 1, "page_size": 1, "total_pages": 1},
        }
    ),
    "/api/v1/elections/e-1": _make_response(
        json_data={"id": "e-1", "name": "General 2024", "election_date": "2024-11-05", "election_type": "general"}
    ),
    "/api/v1/elections/e-1/results": _make_response(json_data={"election_id": "e-1"}),
    "/api/v1/elections/e-1/results/raw": _make_response(json_data={"election_id": "e-1"}),
    "/api/v1/elections/e-1/results/geojson": _make_response(json_data={"type": "FeatureCollection", "features": []}),
    "/api/v1/elections/e-1/results/geojson/precincts": _make_response(
        json_data={"type": "FeatureCollection", "features": []}
    ),
    "/api/v1/elected-officials?page=1&page_size=1": _make_response(
        json_data={
            "items": [{"id": "o-1", "full_name": "John Doe"}],
            "pagination": {"total": 5, "page": 1, "page_size": 1, "total_pages": 5},
        }
    ),
    "/api/v1/elected-officials/by-district?boundary_type=state_senate&district_identifier=1": _make_response(
        json_data=[{"id": "o-1", "full_name": "John Doe"}]
    ),
    "/api/v1/elected-officials/o-1": _make_response(json_data={"id": "o-1", "full_name": "John Doe"}),
    "/api/v1/elected-officials/o-1/sources": _make_response(json_data=[]),
    "/api/v1/datasets": _make_response(json_data={"base_url": None, "datasets": []}),
    "/api/v1/voters": _make_response(status_code=401, json_data={"detail": "Not authenticated"}),
    "/api/v1/info": _make_response(json_data={"version": "0.1.0", "git_commit": "abc123", "environment": "test"}),
}


def _mock_client_all_pass(method: str, url: str, **kwargs: object) -> httpx.Response:
    """Route mock requests to canned healthy responses."""
    path = url.replace(BASE, "")
    if path in _HEALTHY_RESPONSES:
        return _HEALTHY_RESPONSES[path]
    return _make_response(status_code=404, json_data={"detail": "not found"})


class TestHelpText:
    def test_help_renders(self) -> None:
        result = runner.invoke(app, ["deploy-check", "--help"])
        output = _strip_ansi(result.output)
        assert result.exit_code == 0
        assert "deploy" in output.lower()
        assert "--url" in output
        assert "--verbose" in output
        assert "--timeout" in output


class TestAllPass:
    def test_all_checks_pass(self) -> None:
        with patch("voter_api.cli.deploy_check_cmd.httpx.Client") as mock_cls:
            mock_instance = mock_cls.return_value.__enter__.return_value
            mock_instance.request.side_effect = lambda method, url, **kw: _mock_client_all_pass(method, url, **kw)

            result = runner.invoke(app, ["deploy-check", "--url", BASE])

        assert result.exit_code == 0
        assert "passed" in result.output
        assert "0 failed" in result.output

    def test_all_checks_pass_verbose(self) -> None:
        with patch("voter_api.cli.deploy_check_cmd.httpx.Client") as mock_cls:
            mock_instance = mock_cls.return_value.__enter__.return_value
            mock_instance.request.side_effect = lambda method, url, **kw: _mock_client_all_pass(method, url, **kw)

            result = runner.invoke(app, ["deploy-check", "--url", BASE, "--verbose"])

        assert result.exit_code == 0
        # Verbose shows detail lines like total=159
        assert "total=159" in result.output


class TestFailureScenarios:
    def test_health_failure_exits_1(self) -> None:
        def _mock_request(method: str, url: str, **kwargs: object) -> httpx.Response:
            path = url.replace(BASE, "")
            if path == "/api/v1/health":
                return _make_response(status_code=500, text="error")
            return _mock_client_all_pass(method, url, **kwargs)

        with patch("voter_api.cli.deploy_check_cmd.httpx.Client") as mock_cls:
            mock_instance = mock_cls.return_value.__enter__.return_value
            mock_instance.request.side_effect = _mock_request

            result = runner.invoke(app, ["deploy-check", "--url", BASE])

        assert result.exit_code == 1
        assert "1 failed" in result.output

    def test_invalid_json_response(self) -> None:
        def _mock_request(method: str, url: str, **kwargs: object) -> httpx.Response:
            path = url.replace(BASE, "")
            if path == "/api/v1/health":
                return _make_response(text="not json at all")
            return _mock_client_all_pass(method, url, **kwargs)

        with patch("voter_api.cli.deploy_check_cmd.httpx.Client") as mock_cls:
            mock_instance = mock_cls.return_value.__enter__.return_value
            mock_instance.request.side_effect = _mock_request

            result = runner.invoke(app, ["deploy-check", "--url", BASE])

        assert result.exit_code == 1
        assert "not valid JSON" in result.output


class TestSkipScenarios:
    def test_empty_data_skips_not_fails(self) -> None:
        """When elections/officials lists are empty, dependent checks skip."""
        empty_responses = dict(_HEALTHY_RESPONSES)
        empty_responses["/api/v1/elections?page=1&page_size=1"] = _make_response(
            json_data={
                "items": [],
                "pagination": {"total": 0, "page": 1, "page_size": 1, "total_pages": 0},
            }
        )
        empty_responses["/api/v1/elected-officials?page=1&page_size=1"] = _make_response(
            json_data={
                "items": [],
                "pagination": {"total": 0, "page": 1, "page_size": 1, "total_pages": 0},
            }
        )

        def _mock_request(method: str, url: str, **kwargs: object) -> httpx.Response:
            path = url.replace(BASE, "")
            if path in empty_responses:
                return empty_responses[path]
            return _make_response(status_code=404, json_data={"detail": "not found"})

        with patch("voter_api.cli.deploy_check_cmd.httpx.Client") as mock_cls:
            mock_instance = mock_cls.return_value.__enter__.return_value
            mock_instance.request.side_effect = _mock_request

            result = runner.invoke(app, ["deploy-check", "--url", BASE])

        assert result.exit_code == 0
        assert "0 failed" in result.output
        # Should have skipped election detail, results, geojson, precincts, official detail, sources
        assert "skipped" in result.output


class TestTimeoutHandling:
    def test_timeout_produces_fail_not_crash(self) -> None:
        def _mock_request(method: str, url: str, **kwargs: object) -> httpx.Response:
            path = url.replace(BASE, "")
            if path == "/api/v1/health":
                raise httpx.TimeoutException("timed out")
            return _mock_client_all_pass(method, url, **kwargs)

        with patch("voter_api.cli.deploy_check_cmd.httpx.Client") as mock_cls:
            mock_instance = mock_cls.return_value.__enter__.return_value
            mock_instance.request.side_effect = _mock_request

            result = runner.invoke(app, ["deploy-check", "--url", BASE])

        assert result.exit_code == 1
        assert "timed out" in result.output.lower()

    def test_connection_error_produces_fail(self) -> None:
        def _mock_request(method: str, url: str, **kwargs: object) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        with patch("voter_api.cli.deploy_check_cmd.httpx.Client") as mock_cls:
            mock_instance = mock_cls.return_value.__enter__.return_value
            mock_instance.request.side_effect = _mock_request

            result = runner.invoke(app, ["deploy-check", "--url", BASE])

        assert result.exit_code == 1
        assert "Connection refused" in result.output


class TestAuthGate:
    def test_401_is_pass(self) -> None:
        """Auth gate check passes when voters endpoint returns 401."""
        with patch("voter_api.cli.deploy_check_cmd.httpx.Client") as mock_cls:
            mock_instance = mock_cls.return_value.__enter__.return_value
            mock_instance.request.side_effect = lambda method, url, **kw: _mock_client_all_pass(method, url, **kw)

            result = runner.invoke(app, ["deploy-check", "--url", BASE])

        assert result.exit_code == 0

    def test_200_on_voters_is_fail(self) -> None:
        """If voters endpoint returns 200 without auth, auth gate is broken."""
        broken_auth_responses = dict(_HEALTHY_RESPONSES)
        broken_auth_responses["/api/v1/voters"] = _make_response(json_data={"items": [], "pagination": {"total": 0}})

        def _mock_request(method: str, url: str, **kwargs: object) -> httpx.Response:
            path = url.replace(BASE, "")
            if path in broken_auth_responses:
                return broken_auth_responses[path]
            return _make_response(status_code=404, json_data={"detail": "not found"})

        with patch("voter_api.cli.deploy_check_cmd.httpx.Client") as mock_cls:
            mock_instance = mock_cls.return_value.__enter__.return_value
            mock_instance.request.side_effect = _mock_request

            result = runner.invoke(app, ["deploy-check", "--url", BASE])

        assert result.exit_code == 1
        assert "expected 401" in result.output


class TestGeoJsonRedirect:
    def test_302_redirect_is_pass(self) -> None:
        """GeoJSON endpoint returning 302 (R2 redirect) is a pass."""
        redirect_responses = dict(_HEALTHY_RESPONSES)
        redirect_responses["/api/v1/boundaries/geojson?boundary_type=county&page_size=1"] = _make_response(
            status_code=302,
            text="",
            headers={"location": "https://r2.example.com/county.geojson"},
        )

        def _mock_request(method: str, url: str, **kwargs: object) -> httpx.Response:
            path = url.replace(BASE, "")
            if path in redirect_responses:
                return redirect_responses[path]
            return _make_response(status_code=404, json_data={"detail": "not found"})

        with patch("voter_api.cli.deploy_check_cmd.httpx.Client") as mock_cls:
            mock_instance = mock_cls.return_value.__enter__.return_value
            mock_instance.request.side_effect = _mock_request

            result = runner.invoke(app, ["deploy-check", "--url", BASE])

        assert result.exit_code == 0


class TestRunAllChecks:
    def test_returns_19_results(self) -> None:
        """The orchestrator returns exactly 19 check results."""
        client = httpx.Client()
        client.request = lambda method, url, **kw: _mock_client_all_pass(method, url, **kw)  # type: ignore[method-assign]

        results = _run_all_checks(client, BASE)
        assert len(results) == 19

    def test_all_statuses_are_check_status(self) -> None:
        client = httpx.Client()
        client.request = lambda method, url, **kw: _mock_client_all_pass(method, url, **kw)  # type: ignore[method-assign]

        results = _run_all_checks(client, BASE)
        for r in results:
            assert isinstance(r.status, CheckStatus)


@pytest.fixture
def _suppress_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """Suppress typer output for focused unit tests."""
    monkeypatch.setattr("typer.echo", lambda *a, **kw: None)
