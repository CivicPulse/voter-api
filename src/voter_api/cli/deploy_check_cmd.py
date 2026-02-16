"""Post-deploy functional test command.

Hits every public API endpoint on a running voter-api instance and reports
pass/fail status. Pure HTTP client — no database or internal service imports.
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import typer


class CheckStatus(enum.Enum):
    """Result status for a single endpoint check."""

    PASS = "pass"  # noqa: S105
    FAIL = "fail"
    SKIP = "skip"


@dataclass
class CheckResult:
    """Outcome of a single endpoint check."""

    name: str
    status: CheckStatus
    message: str
    endpoint: str
    response_time_ms: float = 0.0
    details: list[str] = field(default_factory=list)


_DEFAULT_URL = "https://voteapi.civpulse.org"


def _style_status(status: CheckStatus) -> str:
    """Return a colored, fixed-width status label."""
    if status is CheckStatus.PASS:
        return typer.style("PASS", fg=typer.colors.GREEN, bold=True)
    if status is CheckStatus.FAIL:
        return typer.style("FAIL", fg=typer.colors.RED, bold=True)
    return typer.style("SKIP", fg=typer.colors.YELLOW, bold=True)


def _request(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    follow_redirects: bool = True,
) -> tuple[httpx.Response | None, float, str | None]:
    """Issue one HTTP request and return (response, elapsed_ms, error_msg)."""
    start = time.monotonic()
    try:
        resp = client.request(method, url, follow_redirects=follow_redirects)
        elapsed = (time.monotonic() - start) * 1000
        return resp, elapsed, None
    except httpx.TimeoutException:
        elapsed = (time.monotonic() - start) * 1000
        return None, elapsed, "Request timed out"
    except httpx.ConnectError:
        elapsed = (time.monotonic() - start) * 1000
        return None, elapsed, "Connection refused"
    except httpx.HTTPError as exc:
        elapsed = (time.monotonic() - start) * 1000
        return None, elapsed, f"HTTP error: {exc}"


def _json_or_none(resp: httpx.Response) -> tuple[Any, str | None]:
    """Attempt to parse JSON; return (data, error_msg)."""
    try:
        return resp.json(), None
    except Exception:
        return None, "Response is not valid JSON"


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def _check_health(client: httpx.Client, base: str) -> CheckResult:
    endpoint = "/api/v1/health"
    resp, ms, err = _request(client, "GET", base + endpoint)
    if err:
        return CheckResult("health", CheckStatus.FAIL, err, endpoint, ms)
    assert resp is not None
    if resp.status_code != 200:
        return CheckResult("health", CheckStatus.FAIL, f"HTTP {resp.status_code}", endpoint, ms)
    data, jerr = _json_or_none(resp)
    if jerr:
        return CheckResult("health", CheckStatus.FAIL, jerr, endpoint, ms)
    if data.get("status") != "healthy":
        return CheckResult("health", CheckStatus.FAIL, f"status={data.get('status')!r}", endpoint, ms)
    return CheckResult("health", CheckStatus.PASS, "ok", endpoint, ms)


def _check_boundaries_list(client: httpx.Client, base: str) -> tuple[CheckResult, str | None]:
    """Returns (result, first_boundary_id_or_None)."""
    endpoint = "/api/v1/boundaries?page=1&page_size=1"
    resp, ms, err = _request(client, "GET", base + endpoint)
    if err:
        return CheckResult("boundaries_list", CheckStatus.FAIL, err, endpoint, ms), None
    assert resp is not None
    if resp.status_code != 200:
        return CheckResult("boundaries_list", CheckStatus.FAIL, f"HTTP {resp.status_code}", endpoint, ms), None
    data, jerr = _json_or_none(resp)
    if jerr:
        return CheckResult("boundaries_list", CheckStatus.FAIL, jerr, endpoint, ms), None

    details: list[str] = []
    items = data.get("items")
    pagination = data.get("pagination")
    if items is None or pagination is None:
        return CheckResult("boundaries_list", CheckStatus.FAIL, "missing items or pagination", endpoint, ms), None

    total = pagination.get("total", 0)
    details.append(f"total={total}")
    if total == 0:
        return CheckResult("boundaries_list", CheckStatus.FAIL, "total is 0", endpoint, ms, details), None

    first_id = items[0].get("id") if items else None
    return CheckResult("boundaries_list", CheckStatus.PASS, "ok", endpoint, ms, details), first_id


def _check_boundary_types(client: httpx.Client, base: str) -> CheckResult:
    endpoint = "/api/v1/boundaries/types"
    resp, ms, err = _request(client, "GET", base + endpoint)
    if err:
        return CheckResult("boundary_types", CheckStatus.FAIL, err, endpoint, ms)
    assert resp is not None
    if resp.status_code != 200:
        return CheckResult("boundary_types", CheckStatus.FAIL, f"HTTP {resp.status_code}", endpoint, ms)
    data, jerr = _json_or_none(resp)
    if jerr:
        return CheckResult("boundary_types", CheckStatus.FAIL, jerr, endpoint, ms)
    types = data.get("types")
    if not types:
        return CheckResult("boundary_types", CheckStatus.FAIL, "types list empty or missing", endpoint, ms)
    details = [f"types={types}"]
    return CheckResult("boundary_types", CheckStatus.PASS, "ok", endpoint, ms, details)


def _check_containing_point(client: httpx.Client, base: str) -> CheckResult:
    endpoint = "/api/v1/boundaries/containing-point?latitude=33.749&longitude=-84.388"
    resp, ms, err = _request(client, "GET", base + endpoint)
    if err:
        return CheckResult("containing_point", CheckStatus.FAIL, err, endpoint, ms)
    assert resp is not None
    if resp.status_code != 200:
        return CheckResult("containing_point", CheckStatus.FAIL, f"HTTP {resp.status_code}", endpoint, ms)
    data, jerr = _json_or_none(resp)
    if jerr:
        return CheckResult("containing_point", CheckStatus.FAIL, jerr, endpoint, ms)
    if not isinstance(data, list) or len(data) == 0:
        return CheckResult("containing_point", CheckStatus.FAIL, "expected non-empty list", endpoint, ms)
    details = [f"boundaries={len(data)}"]
    return CheckResult("containing_point", CheckStatus.PASS, "ok", endpoint, ms, details)


def _check_boundaries_geojson(client: httpx.Client, base: str) -> CheckResult:
    endpoint = "/api/v1/boundaries/geojson?boundary_type=county&page_size=1"
    resp, ms, err = _request(client, "GET", base + endpoint, follow_redirects=False)
    if err:
        return CheckResult("boundaries_geojson", CheckStatus.FAIL, err, endpoint, ms)
    assert resp is not None
    if resp.status_code == 302:
        details = [f"redirect to {resp.headers.get('location', '?')}"]
        return CheckResult("boundaries_geojson", CheckStatus.PASS, "302 redirect (R2)", endpoint, ms, details)
    if resp.status_code != 200:
        return CheckResult("boundaries_geojson", CheckStatus.FAIL, f"HTTP {resp.status_code}", endpoint, ms)
    data, jerr = _json_or_none(resp)
    if jerr:
        return CheckResult("boundaries_geojson", CheckStatus.FAIL, jerr, endpoint, ms)
    if data.get("type") != "FeatureCollection":
        return CheckResult("boundaries_geojson", CheckStatus.FAIL, "not a FeatureCollection", endpoint, ms)
    return CheckResult("boundaries_geojson", CheckStatus.PASS, "ok", endpoint, ms)


def _check_boundary_detail(client: httpx.Client, base: str, boundary_id: str | None) -> CheckResult:
    if not boundary_id:
        return CheckResult("boundary_detail", CheckStatus.SKIP, "no boundary ID available", "", 0)
    endpoint = f"/api/v1/boundaries/{boundary_id}?include_geometry=false"
    resp, ms, err = _request(client, "GET", base + endpoint)
    if err:
        return CheckResult("boundary_detail", CheckStatus.FAIL, err, endpoint, ms)
    assert resp is not None
    if resp.status_code != 200:
        return CheckResult("boundary_detail", CheckStatus.FAIL, f"HTTP {resp.status_code}", endpoint, ms)
    data, jerr = _json_or_none(resp)
    if jerr:
        return CheckResult("boundary_detail", CheckStatus.FAIL, jerr, endpoint, ms)
    required = {"id", "name", "boundary_type"}
    missing = required - set(data.keys())
    if missing:
        return CheckResult("boundary_detail", CheckStatus.FAIL, f"missing keys: {missing}", endpoint, ms)
    return CheckResult("boundary_detail", CheckStatus.PASS, "ok", endpoint, ms)


# --- Elections ---


def _check_elections_list(client: httpx.Client, base: str) -> tuple[CheckResult, str | None]:
    """Returns (result, first_election_id_or_None)."""
    endpoint = "/api/v1/elections?page=1&page_size=1"
    resp, ms, err = _request(client, "GET", base + endpoint)
    if err:
        return CheckResult("elections_list", CheckStatus.FAIL, err, endpoint, ms), None
    assert resp is not None
    if resp.status_code != 200:
        return CheckResult("elections_list", CheckStatus.FAIL, f"HTTP {resp.status_code}", endpoint, ms), None
    data, jerr = _json_or_none(resp)
    if jerr:
        return CheckResult("elections_list", CheckStatus.FAIL, jerr, endpoint, ms), None

    items = data.get("items")
    pagination = data.get("pagination")
    if items is None or pagination is None:
        return CheckResult("elections_list", CheckStatus.FAIL, "missing items or pagination", endpoint, ms), None

    total = pagination.get("total", 0)
    details = [f"total={total}"]
    first_id = items[0].get("id") if items else None
    return CheckResult("elections_list", CheckStatus.PASS, "ok", endpoint, ms, details), first_id


def _check_election_detail(client: httpx.Client, base: str, election_id: str | None) -> CheckResult:
    if not election_id:
        return CheckResult("election_detail", CheckStatus.SKIP, "no elections", "", 0)
    endpoint = f"/api/v1/elections/{election_id}"
    resp, ms, err = _request(client, "GET", base + endpoint)
    if err:
        return CheckResult("election_detail", CheckStatus.FAIL, err, endpoint, ms)
    assert resp is not None
    if resp.status_code != 200:
        return CheckResult("election_detail", CheckStatus.FAIL, f"HTTP {resp.status_code}", endpoint, ms)
    data, jerr = _json_or_none(resp)
    if jerr:
        return CheckResult("election_detail", CheckStatus.FAIL, jerr, endpoint, ms)
    required = {"id", "name", "election_date", "election_type"}
    missing = required - set(data.keys())
    if missing:
        return CheckResult("election_detail", CheckStatus.FAIL, f"missing keys: {missing}", endpoint, ms)
    return CheckResult("election_detail", CheckStatus.PASS, "ok", endpoint, ms)


def _check_election_results(client: httpx.Client, base: str, election_id: str | None) -> CheckResult:
    if not election_id:
        return CheckResult("election_results", CheckStatus.SKIP, "no elections", "", 0)
    endpoint = f"/api/v1/elections/{election_id}/results"
    resp, ms, err = _request(client, "GET", base + endpoint)
    if err:
        return CheckResult("election_results", CheckStatus.FAIL, err, endpoint, ms)
    assert resp is not None
    if resp.status_code != 200:
        return CheckResult("election_results", CheckStatus.FAIL, f"HTTP {resp.status_code}", endpoint, ms)
    return CheckResult("election_results", CheckStatus.PASS, "ok", endpoint, ms)


def _check_election_results_raw(client: httpx.Client, base: str, election_id: str | None) -> CheckResult:
    if not election_id:
        return CheckResult("election_results_raw", CheckStatus.SKIP, "no elections", "", 0)
    endpoint = f"/api/v1/elections/{election_id}/results/raw"
    resp, ms, err = _request(client, "GET", base + endpoint)
    if err:
        return CheckResult("election_results_raw", CheckStatus.FAIL, err, endpoint, ms)
    assert resp is not None
    if resp.status_code != 200:
        return CheckResult("election_results_raw", CheckStatus.FAIL, f"HTTP {resp.status_code}", endpoint, ms)
    return CheckResult("election_results_raw", CheckStatus.PASS, "ok", endpoint, ms)


def _check_election_geojson(client: httpx.Client, base: str, election_id: str | None) -> CheckResult:
    if not election_id:
        return CheckResult("election_geojson", CheckStatus.SKIP, "no elections", "", 0)
    endpoint = f"/api/v1/elections/{election_id}/results/geojson"
    resp, ms, err = _request(client, "GET", base + endpoint)
    if err:
        return CheckResult("election_geojson", CheckStatus.FAIL, err, endpoint, ms)
    assert resp is not None
    if resp.status_code != 200:
        return CheckResult("election_geojson", CheckStatus.FAIL, f"HTTP {resp.status_code}", endpoint, ms)
    data, jerr = _json_or_none(resp)
    if jerr:
        return CheckResult("election_geojson", CheckStatus.FAIL, jerr, endpoint, ms)
    if data.get("type") != "FeatureCollection":
        return CheckResult("election_geojson", CheckStatus.FAIL, "not a FeatureCollection", endpoint, ms)
    return CheckResult("election_geojson", CheckStatus.PASS, "ok", endpoint, ms)


def _check_election_precincts_geojson(client: httpx.Client, base: str, election_id: str | None) -> CheckResult:
    if not election_id:
        return CheckResult("election_precincts_geojson", CheckStatus.SKIP, "no elections", "", 0)
    endpoint = f"/api/v1/elections/{election_id}/results/geojson/precincts"
    resp, ms, err = _request(client, "GET", base + endpoint)
    if err:
        return CheckResult("election_precincts_geojson", CheckStatus.FAIL, err, endpoint, ms)
    assert resp is not None
    if resp.status_code != 200:
        return CheckResult("election_precincts_geojson", CheckStatus.FAIL, f"HTTP {resp.status_code}", endpoint, ms)
    data, jerr = _json_or_none(resp)
    if jerr:
        return CheckResult("election_precincts_geojson", CheckStatus.FAIL, jerr, endpoint, ms)
    if data.get("type") != "FeatureCollection":
        return CheckResult("election_precincts_geojson", CheckStatus.FAIL, "not a FeatureCollection", endpoint, ms)
    return CheckResult("election_precincts_geojson", CheckStatus.PASS, "ok", endpoint, ms)


# --- Elected Officials ---


def _check_officials_list(client: httpx.Client, base: str) -> tuple[CheckResult, str | None]:
    """Returns (result, first_official_id_or_None)."""
    endpoint = "/api/v1/elected-officials?page=1&page_size=1"
    resp, ms, err = _request(client, "GET", base + endpoint)
    if err:
        return CheckResult("officials_list", CheckStatus.FAIL, err, endpoint, ms), None
    assert resp is not None
    if resp.status_code != 200:
        return CheckResult("officials_list", CheckStatus.FAIL, f"HTTP {resp.status_code}", endpoint, ms), None
    data, jerr = _json_or_none(resp)
    if jerr:
        return CheckResult("officials_list", CheckStatus.FAIL, jerr, endpoint, ms), None

    items = data.get("items")
    pagination = data.get("pagination")
    if items is None or pagination is None:
        return CheckResult("officials_list", CheckStatus.FAIL, "missing items or pagination", endpoint, ms), None

    total = pagination.get("total", 0)
    details = [f"total={total}"]
    first_id = items[0].get("id") if items else None
    return CheckResult("officials_list", CheckStatus.PASS, "ok", endpoint, ms, details), first_id


def _check_officials_by_district(client: httpx.Client, base: str) -> CheckResult:
    endpoint = "/api/v1/elected-officials/by-district?boundary_type=state_senate&district_identifier=1"
    resp, ms, err = _request(client, "GET", base + endpoint)
    if err:
        return CheckResult("officials_by_district", CheckStatus.FAIL, err, endpoint, ms)
    assert resp is not None
    if resp.status_code != 200:
        return CheckResult("officials_by_district", CheckStatus.FAIL, f"HTTP {resp.status_code}", endpoint, ms)
    data, jerr = _json_or_none(resp)
    if jerr:
        return CheckResult("officials_by_district", CheckStatus.FAIL, jerr, endpoint, ms)
    if not isinstance(data, list):
        return CheckResult("officials_by_district", CheckStatus.FAIL, "expected list", endpoint, ms)
    details = [f"officials={len(data)}"]
    return CheckResult("officials_by_district", CheckStatus.PASS, "ok", endpoint, ms, details)


def _check_official_detail(client: httpx.Client, base: str, official_id: str | None) -> CheckResult:
    if not official_id:
        return CheckResult("official_detail", CheckStatus.SKIP, "no officials", "", 0)
    endpoint = f"/api/v1/elected-officials/{official_id}"
    resp, ms, err = _request(client, "GET", base + endpoint)
    if err:
        return CheckResult("official_detail", CheckStatus.FAIL, err, endpoint, ms)
    assert resp is not None
    if resp.status_code != 200:
        return CheckResult("official_detail", CheckStatus.FAIL, f"HTTP {resp.status_code}", endpoint, ms)
    return CheckResult("official_detail", CheckStatus.PASS, "ok", endpoint, ms)


def _check_official_sources(client: httpx.Client, base: str, official_id: str | None) -> CheckResult:
    if not official_id:
        return CheckResult("official_sources", CheckStatus.SKIP, "no officials", "", 0)
    endpoint = f"/api/v1/elected-officials/{official_id}/sources"
    resp, ms, err = _request(client, "GET", base + endpoint)
    if err:
        return CheckResult("official_sources", CheckStatus.FAIL, err, endpoint, ms)
    assert resp is not None
    if resp.status_code != 200:
        return CheckResult("official_sources", CheckStatus.FAIL, f"HTTP {resp.status_code}", endpoint, ms)
    return CheckResult("official_sources", CheckStatus.PASS, "ok", endpoint, ms)


# --- Datasets ---


def _check_datasets(client: httpx.Client, base: str) -> CheckResult:
    endpoint = "/api/v1/datasets"
    resp, ms, err = _request(client, "GET", base + endpoint)
    if err:
        return CheckResult("datasets", CheckStatus.FAIL, err, endpoint, ms)
    assert resp is not None
    if resp.status_code != 200:
        return CheckResult("datasets", CheckStatus.FAIL, f"HTTP {resp.status_code}", endpoint, ms)
    data, jerr = _json_or_none(resp)
    if jerr:
        return CheckResult("datasets", CheckStatus.FAIL, jerr, endpoint, ms)
    if "datasets" not in data:
        return CheckResult("datasets", CheckStatus.FAIL, "missing 'datasets' key", endpoint, ms)
    details = [f"datasets={len(data['datasets'])}"]
    return CheckResult("datasets", CheckStatus.PASS, "ok", endpoint, ms, details)


# --- Auth Gate ---


def _check_auth_gate(client: httpx.Client, base: str) -> CheckResult:
    endpoint = "/api/v1/voters"
    resp, ms, err = _request(client, "GET", base + endpoint)
    if err:
        return CheckResult("auth_gate", CheckStatus.FAIL, err, endpoint, ms)
    assert resp is not None
    if resp.status_code == 401:
        return CheckResult("auth_gate", CheckStatus.PASS, "401 as expected", endpoint, ms)
    return CheckResult("auth_gate", CheckStatus.FAIL, f"expected 401, got {resp.status_code}", endpoint, ms)


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

_SECTIONS: list[tuple[str, list[str]]] = [
    ("Health", ["health"]),
    (
        "Boundaries",
        [
            "boundaries_list",
            "boundary_types",
            "containing_point",
            "boundaries_geojson",
            "boundary_detail",
        ],
    ),
    (
        "Elections",
        [
            "elections_list",
            "election_detail",
            "election_results",
            "election_results_raw",
            "election_geojson",
            "election_precincts_geojson",
        ],
    ),
    (
        "Elected Officials",
        [
            "officials_list",
            "officials_by_district",
            "official_detail",
            "official_sources",
        ],
    ),
    ("Datasets", ["datasets"]),
    ("Auth Gate", ["auth_gate"]),
]


def _run_all_checks(client: httpx.Client, base: str) -> list[CheckResult]:
    """Execute all checks sequentially and return results in section order."""
    results: dict[str, CheckResult] = {}

    # Health
    results["health"] = _check_health(client, base)

    # Boundaries
    boundary_result, boundary_id = _check_boundaries_list(client, base)
    results["boundaries_list"] = boundary_result
    results["boundary_types"] = _check_boundary_types(client, base)
    results["containing_point"] = _check_containing_point(client, base)
    results["boundaries_geojson"] = _check_boundaries_geojson(client, base)
    results["boundary_detail"] = _check_boundary_detail(client, base, boundary_id)

    # Elections
    election_result, election_id = _check_elections_list(client, base)
    results["elections_list"] = election_result
    results["election_detail"] = _check_election_detail(client, base, election_id)
    results["election_results"] = _check_election_results(client, base, election_id)
    results["election_results_raw"] = _check_election_results_raw(client, base, election_id)
    results["election_geojson"] = _check_election_geojson(client, base, election_id)
    results["election_precincts_geojson"] = _check_election_precincts_geojson(client, base, election_id)

    # Elected Officials
    officials_result, official_id = _check_officials_list(client, base)
    results["officials_list"] = officials_result
    results["officials_by_district"] = _check_officials_by_district(client, base)
    results["official_detail"] = _check_official_detail(client, base, official_id)
    results["official_sources"] = _check_official_sources(client, base, official_id)

    # Datasets
    results["datasets"] = _check_datasets(client, base)

    # Auth Gate
    results["auth_gate"] = _check_auth_gate(client, base)

    # Return in section order
    ordered: list[CheckResult] = []
    for _section, names in _SECTIONS:
        for name in names:
            ordered.append(results[name])
    return ordered


def _print_results(results: list[CheckResult], *, verbose: bool) -> None:
    """Print formatted results grouped by section."""
    for section_name, check_names in _SECTIONS:
        typer.echo(section_name)
        for name in check_names:
            result = next(r for r in results if r.name == name)
            status_label = _style_status(result.status)
            time_str = f"({result.response_time_ms:.0f}ms)" if result.response_time_ms > 0 else ""
            typer.echo(f"  {status_label}  {result.name:<35s} {time_str}")
            if result.status is CheckStatus.FAIL:
                typer.echo(f"         {result.message}")
            if verbose and result.details:
                for detail in result.details:
                    typer.echo(f"         {detail}")


def deploy_check(
    url: str = typer.Option(_DEFAULT_URL, "--url", help="Base URL of the voter-api instance"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output per check"),
    timeout: int = typer.Option(10, "--timeout", help="Per-request timeout in seconds"),
) -> None:
    """Run post-deploy functional checks against a live voter-api instance."""
    base = url.rstrip("/")

    typer.echo(f"Voter API Deploy Check: {base}")
    typer.echo("=" * 56)

    start = time.monotonic()
    with httpx.Client(timeout=timeout) as client:
        results = _run_all_checks(client, base)
    total_time = time.monotonic() - start

    _print_results(results, verbose=verbose)

    passed = sum(1 for r in results if r.status is CheckStatus.PASS)
    failed = sum(1 for r in results if r.status is CheckStatus.FAIL)
    skipped = sum(1 for r in results if r.status is CheckStatus.SKIP)

    typer.echo("=" * 56)
    typer.echo(f"Results: {passed} passed, {failed} failed, {skipped} skipped ({total_time:.2f}s total)")

    if failed > 0:
        raise typer.Exit(code=1)
