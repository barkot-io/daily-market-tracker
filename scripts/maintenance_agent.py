#!/usr/bin/env python3
"""
maintenance_agent.py
────────────────────
Repository Health & Metrics Audit Agent

Collects live data from the GitHub REST API and writes a structured
Markdown report to .github/repo-health-report.md.

The surrounding workflow only commits when this file's content actually
changes (git diff --staged --quiet guard), so no meaningless commits
are ever created.

Environment variables (injected by the workflow):
  GITHUB_TOKEN  – ephemeral GitHub App installation token
  REPO          – "owner/repo" string
  DRY_RUN       – "true" to skip writing the output file
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

# ── Configuration ──────────────────────────────────────────────────────────────

TOKEN   = os.environ["GITHUB_TOKEN"]
REPO    = os.environ["REPO"]
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept":        "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
BASE = "https://api.github.com"

OUTPUT_FILE = Path(".github/repo-health-report.md")

NOW = datetime.now(timezone.utc)

# Thresholds for "stale" classification
STALE_ISSUE_DAYS = 30
STALE_PR_DAYS    = 14
OLD_BRANCH_DAYS  = 90


# ── HTTP helper ────────────────────────────────────────────────────────────────

def gh(path: str, params: dict | None = None) -> dict | list:
    """
    Authenticated GitHub API GET request with automatic pagination.
    Returns a list for paginated endpoints, a dict for single-object endpoints.
    Raises requests.HTTPError on API errors.
    """
    url: str | None = f"{BASE}{path}"
    results: list = []

    while url:
        response = requests.get(url, headers=HEADERS, params=params, timeout=30)

        if response.status_code == 204:   # No Content
            return {}

        response.raise_for_status()
        data = response.json()

        if isinstance(data, list):
            results.extend(data)
            url    = response.links.get("next", {}).get("url")
            params = None          # only the first page uses query params
        else:
            return data            # single-object response — return immediately

    return results


def safe_gh(path: str, params: dict | None = None, default=None):
    """gh() wrapper that swallows HTTP errors and returns `default` instead."""
    try:
        return gh(path, params)
    except requests.HTTPError as exc:
        print(f"  ⚠️  API call skipped ({exc.response.status_code}): {path}")
        return default if default is not None else {}


# ── Utilities ──────────────────────────────────────────────────────────────────

def days_since(iso: str | None) -> int | None:
    """Return the number of whole days between an ISO-8601 timestamp and now."""
    if not iso:
        return None
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (NOW - dt).days


def badge(value: int, warn: int, crit: int, higher_is_better: bool = False) -> str:
    """Return a colour-coded emoji based on value thresholds."""
    if higher_is_better:
        return "🟢" if value >= warn else ("🟡" if value >= crit else "🔴")
    return "🟢" if value <= warn else ("🟡" if value <= crit else "🔴")


# ── Data collectors ────────────────────────────────────────────────────────────

def collect_meta() -> dict:
    data = gh(f"/repos/{REPO}")
    return {
        "stars":          data.get("stargazers_count", 0),
        "forks":          data.get("forks_count", 0),
        "watchers":       data.get("subscribers_count", 0),
        "open_issues":    data.get("open_issues_count", 0),
        "default_branch": data.get("default_branch", "main"),
        "visibility":     data.get("visibility", "unknown"),
        "language":       data.get("language") or "N/A",
        "size_kb":        data.get("size", 0),
        "created_at":     data.get("created_at"),
        "pushed_at":      data.get("pushed_at"),
        "days_since_push": days_since(data.get("pushed_at")),
        "description":    data.get("description") or "",
    }


def collect_issues() -> dict:
    items = gh(f"/repos/{REPO}/issues", {"state": "open", "per_page": 100})
    real  = [i for i in items if "pull_request" not in i]
    stale = [
        i for i in real
        if (days_since(i.get("updated_at")) or 0) >= STALE_ISSUE_DAYS
    ]
    return {
        "open_count":  len(real),
        "stale_count": len(stale),
        "stale": [
            {
                "number": i["number"],
                "title":  i["title"][:60],
                "days":   days_since(i["updated_at"]),
            }
            for i in stale[:5]
        ],
    }


def collect_prs() -> dict:
    prs   = gh(f"/repos/{REPO}/pulls", {"state": "open", "per_page": 100})
    stale = [
        p for p in prs
        if (days_since(p.get("updated_at")) or 0) >= STALE_PR_DAYS
    ]
    return {
        "open_count":  len(prs),
        "stale_count": len(stale),
        "stale": [
            {
                "number": p["number"],
                "title":  p["title"][:60],
                "days":   days_since(p["updated_at"]),
            }
            for p in stale[:5]
        ],
    }


def collect_branches(default_branch: str) -> dict:
    branches    = gh(f"/repos/{REPO}/branches", {"per_page": 100})
    non_default = [b for b in branches if b["name"] != default_branch]

    old: list[dict] = []
    for b in non_default:
        commit = safe_gh(f"/repos/{REPO}/commits/{b['commit']['sha']}")
        date   = (
            commit.get("commit", {}).get("committer", {}).get("date")
            if commit else None
        )
        age = days_since(date)
        if age is not None and age >= OLD_BRANCH_DAYS:
            old.append({"name": b["name"], "days": age})

    return {
        "total_count":       len(branches),
        "non_default_count": len(non_default),
        "old_count":         len(old),
        "old":               old[:5],
    }


def collect_traffic() -> dict:
    """Requires push/admin access; returns a note dict if unavailable."""
    views  = safe_gh(f"/repos/{REPO}/traffic/views",  default=None)
    clones = safe_gh(f"/repos/{REPO}/traffic/clones", default=None)

    if views is None or clones is None:
        return {"unavailable": True}

    return {
        "views_14d":           views.get("count", 0),
        "unique_visitors_14d": views.get("uniques", 0),
        "clones_14d":          clones.get("count", 0),
        "unique_cloners_14d":  clones.get("uniques", 0),
    }


def collect_contributors() -> int:
    data = safe_gh(
        f"/repos/{REPO}/contributors",
        {"per_page": 100, "anon": "true"},
        default=[],
    )
    return len(data) if isinstance(data, list) else -1


def collect_ci() -> dict:
    data = safe_gh(f"/repos/{REPO}/actions/runs", {"per_page": 10}, default={})
    runs = data.get("workflow_runs", []) if isinstance(data, dict) else []
    conclusions = [r.get("conclusion") for r in runs[:10]]
    return {
        "recent_success": conclusions.count("success"),
        "recent_failure": conclusions.count("failure"),
        "last_conclusion": conclusions[0] if conclusions else "N/A",
    }


def collect_protection(branch: str) -> dict:
    data = safe_gh(f"/repos/{REPO}/branches/{branch}/protection", default=None)
    if not data:
        return {"enabled": False}
    return {
        "enabled": True,
        "required_reviews": (
            data.get("required_pull_request_reviews", {})
                .get("required_approving_review_count", 0)
        ),
        "status_checks": bool(data.get("required_status_checks")),
        "enforce_admins": data.get("enforce_admins", {}).get("enabled", False),
    }


# ── Report renderer ────────────────────────────────────────────────────────────

def render(meta, issues, prs, branches, traffic, contributors, ci, protection) -> str:
    ts = NOW.strftime("%Y-%m-%d %H:%M UTC")

    def _stale_rows(items: list, prefix: str) -> list[str]:
        if not items:
            return []
        return (
            ["", f"**Top stale {prefix}s:**", ""]
            + [
                f"- #{i['number']} — {i['title']} _(inactive {i['days']}d)_"
                for i in items
            ]
            + [""]
        )

    p = protection
    prot_rows: list[str]
    if p["enabled"]:
        prot_rows = [
            f"| Protection Enabled | ✅ Yes |",
            f"| Required Approving Reviews | {p.get('required_reviews', 0)} |",
            f"| Required Status Checks | {'✅ Yes' if p.get('status_checks') else '⚠️ No'} |",
            f"| Enforce Admins | {'✅ Yes' if p.get('enforce_admins') else '⚠️ No'} |",
        ]
    else:
        prot_rows = [
            f"| Protection Enabled | ❌ No — **add branch protection rules** |",
        ]

    traffic_rows: list[str]
    if traffic.get("unavailable"):
        traffic_rows = ["_Traffic data unavailable (requires admin/push access)._"]
    else:
        traffic_rows = [
            "| Metric | Count |",
            "|--------|-------|",
            f"| Page Views (14d) | {traffic.get('views_14d', 0):,} |",
            f"| Unique Visitors (14d) | {traffic.get('unique_visitors_14d', 0):,} |",
            f"| Clones (14d) | {traffic.get('clones_14d', 0):,} |",
            f"| Unique Cloners (14d) | {traffic.get('unique_cloners_14d', 0):,} |",
        ]

    lines = [
        "# 🏥 Repository Health Report",
        "",
        f"> **Repo:** [{REPO}](https://github.com/{REPO})  ",
        f"> **Generated:** {ts} by `project-maintenance-agent[bot]`  ",
        f"> **Schedule:** Daily automated audit (random window 02:00–08:00 UTC)",
        "",
        "---",
        "",
        "## 📊 Repository Overview",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| ⭐ Stars | {meta['stars']:,} |",
        f"| 🍴 Forks | {meta['forks']:,} |",
        f"| 👁 Watchers | {meta['watchers']:,} |",
        f"| 💾 Disk Size | {meta['size_kb']:,} KB |",
        f"| 🌐 Visibility | {meta['visibility'].capitalize()} |",
        f"| 💻 Primary Language | {meta['language']} |",
        f"| 👥 Contributors | {contributors if contributors >= 0 else 'N/A'} |",
        f"| 📅 Last Push | {meta['days_since_push']} days ago |",
        "",
        "---",
        "",
        "## 🐛 Issues",
        "",
        "| Metric | Count | Health |",
        "|--------|-------|--------|",
        f"| Open Issues | {issues['open_count']} | {badge(issues['open_count'], 10, 30)} |",
        f"| Stale (>{STALE_ISSUE_DAYS}d inactive) | {issues['stale_count']} | {badge(issues['stale_count'], 3, 10)} |",
        *_stale_rows(issues["stale"], "issue"),
        "---",
        "",
        "## 🔀 Pull Requests",
        "",
        "| Metric | Count | Health |",
        "|--------|-------|--------|",
        f"| Open PRs | {prs['open_count']} | {badge(prs['open_count'], 5, 15)} |",
        f"| Stale (>{STALE_PR_DAYS}d inactive) | {prs['stale_count']} | {badge(prs['stale_count'], 2, 5)} |",
        *_stale_rows(prs["stale"], "PR"),
        "---",
        "",
        "## 🌿 Branches",
        "",
        "| Metric | Count | Health |",
        "|--------|-------|--------|",
        f"| Total Branches | {branches['total_count']} | {badge(branches['total_count'], 10, 25)} |",
        f"| Old Branches (>{OLD_BRANCH_DAYS}d) | {branches['old_count']} | {badge(branches['old_count'], 2, 5)} |",
        *(
            ["", "**Branches to consider pruning:**", ""]
            + [f"- `{b['name']}` — {b['days']}d since last commit" for b in branches["old"]]
            + [""]
            if branches["old"] else []
        ),
        "---",
        "",
        f"## 🔒 Branch Protection (`{meta['default_branch']}`)",
        "",
        "| Setting | Status |",
        "|---------|--------|",
        *prot_rows,
        "",
        "---",
        "",
        "## ⚙️ CI/CD (Last 10 Runs)",
        "",
        "| Outcome | Count |",
        "|---------|-------|",
        f"| ✅ Success | {ci.get('recent_success', 'N/A')} |",
        f"| ❌ Failure | {ci.get('recent_failure', 'N/A')} |",
        f"| Last conclusion | `{ci.get('last_conclusion', 'N/A')}` |",
        "",
        "---",
        "",
        "## 📈 Traffic (Last 14 Days)",
        "",
        *traffic_rows,
        "",
        "---",
        "",
        "<sub>🤖 Auto-generated by `project-maintenance-agent[bot]`"
        " · [Workflow](.github/workflows/agent-scheduler.yml)"
        " · Do not edit manually — changes will be overwritten</sub>",
        "",
    ]

    return "\n".join(lines)


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"🔍 Auditing: {REPO}")
    print(f"🕐 Timestamp: {NOW.isoformat()}")
    if DRY_RUN:
        print("⚠️  DRY RUN — no files will be written.\n")

    print("  → Collecting repository metadata …")
    meta = collect_meta()

    print("  → Collecting issues …")
    issues = collect_issues()

    print("  → Collecting pull requests …")
    prs = collect_prs()

    print(f"  → Analysing branches (threshold: {OLD_BRANCH_DAYS}d) …")
    branches = collect_branches(meta["default_branch"])

    print("  → Fetching traffic …")
    traffic = collect_traffic()

    print("  → Counting contributors …")
    contributors = collect_contributors()

    print("  → Fetching CI run history …")
    ci = collect_ci()

    print(f"  → Checking branch protection ({meta['default_branch']}) …")
    protection = collect_protection(meta["default_branch"])

    report = render(meta, issues, prs, branches, traffic, contributors, ci, protection)

    # ── Console summary ───────────────────────────────────────────────────────
    print()
    print("── Audit Summary " + "─" * 40)
    print(f"  Stars / Forks   : {meta['stars']:,} / {meta['forks']:,}")
    print(f"  Open Issues     : {issues['open_count']}  (stale: {issues['stale_count']})")
    print(f"  Open PRs        : {prs['open_count']}  (stale: {prs['stale_count']})")
    print(f"  Branches        : {branches['total_count']}  (old: {branches['old_count']})")
    print(f"  Contributors    : {contributors}")
    print(f"  Last push       : {meta['days_since_push']}d ago")
    print(f"  Branch protect  : {'✅ enabled' if protection['enabled'] else '❌ DISABLED'}")
    print(f"  Last CI run     : {ci.get('last_conclusion', 'N/A')}")
    print("─" * 56)

    if DRY_RUN:
        print("\n── Report Preview (first 40 lines) " + "─" * 20)
        print("\n".join(report.splitlines()[:40]))
        return

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(report, encoding="utf-8")
    print(f"\n✅ Report written → {OUTPUT_FILE}")


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as exc:
        print(f"\n❌ GitHub API error: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyError as exc:
        print(f"\n❌ Missing required env var: {exc}", file=sys.stderr)
        sys.exit(1)
