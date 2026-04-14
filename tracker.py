"""
Coding Agent Heat Index Tracker
Pulls daily metrics from GitHub + npm for each AI coding agent.
"""

import json
import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
CONFIG_PATH = ROOT / "config.yaml"

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"


def gh_get(url, params=None):
    """GET GitHub API with simple retry on rate limit."""
    for attempt in range(3):
        r = requests.get(url, headers=HEADERS, params=params, timeout=30)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (403, 429):
            reset = int(r.headers.get("X-RateLimit-Reset", time.time() + 60))
            wait = max(5, min(60, reset - int(time.time())))
            print(f"   rate limited, sleeping {wait}s")
            time.sleep(wait)
            continue
        if r.status_code == 404:
            return None
        print(f"   HTTP {r.status_code} on {url}")
        return None
    return None


def fetch_repo(repo):
    """Fetch full repo metrics."""
    data = gh_get(f"https://api.github.com/repos/{repo}")
    if not data:
        return None
    return data


def fetch_contributors_count(repo):
    """Count contributors via per_page=1 pagination trick."""
    r = requests.get(
        f"https://api.github.com/repos/{repo}/contributors",
        headers=HEADERS,
        params={"per_page": 1, "anon": "true"},
        timeout=30,
    )
    if r.status_code != 200:
        return 0
    # Parse Link header for last page
    link = r.headers.get("Link", "")
    if 'rel="last"' in link:
        for part in link.split(","):
            if 'rel="last"' in part:
                url = part.split(";")[0].strip(" <>")
                if "page=" in url:
                    try:
                        return int(url.split("page=")[-1].split("&")[0])
                    except ValueError:
                        pass
    return len(r.json()) if isinstance(r.json(), list) else 0


def fetch_latest_release(repo):
    data = gh_get(f"https://api.github.com/repos/{repo}/releases/latest")
    if not data:
        return None
    return {
        "tag": data.get("tag_name"),
        "name": data.get("name"),
        "published_at": data.get("published_at"),
        "url": data.get("html_url"),
    }


def fetch_recent_commits(repo, since_days=28):
    since = (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat()
    r = requests.get(
        f"https://api.github.com/repos/{repo}/commits",
        headers=HEADERS,
        params={"since": since, "per_page": 1},
        timeout=30,
    )
    if r.status_code != 200:
        return 0
    link = r.headers.get("Link", "")
    if 'rel="last"' in link:
        for part in link.split(","):
            if 'rel="last"' in part:
                url = part.split(";")[0].strip(" <>")
                if "page=" in url:
                    try:
                        return int(url.split("page=")[-1].split("&")[0])
                    except ValueError:
                        pass
    data = r.json()
    return len(data) if isinstance(data, list) else 0


def fetch_star_history(repo):
    """Get stargazer count now and approximate 7d/30d ago via the
    stargazers endpoint (sampling via last pages)."""
    # We approximate recent velocity by checking how many stars were added
    # using the starred_at timestamps from the latest page of stargazers.
    r = requests.get(
        f"https://api.github.com/repos/{repo}/stargazers",
        headers={**HEADERS, "Accept": "application/vnd.github.star+json"},
        params={"per_page": 100, "page": 1},
        timeout=30,
    )
    if r.status_code != 200:
        return {"stars_7d": 0, "stars_30d": 0}

    # Find last page
    link = r.headers.get("Link", "")
    last_page = 1
    if 'rel="last"' in link:
        for part in link.split(","):
            if 'rel="last"' in part:
                url = part.split(";")[0].strip(" <>")
                if "page=" in url:
                    try:
                        last_page = int(url.split("page=")[-1].split("&")[0])
                    except ValueError:
                        pass

    # Fetch the last page for most recent stars
    if last_page > 1:
        r = requests.get(
            f"https://api.github.com/repos/{repo}/stargazers",
            headers={**HEADERS, "Accept": "application/vnd.github.star+json"},
            params={"per_page": 100, "page": last_page},
            timeout=30,
        )
        if r.status_code != 200:
            return {"stars_7d": 0, "stars_30d": 0}

    items = r.json() if isinstance(r.json(), list) else []
    now = datetime.now(timezone.utc)
    stars_7d = 0
    stars_30d = 0
    for item in items:
        ts = item.get("starred_at")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            delta = (now - dt).days
            if delta <= 7:
                stars_7d += 1
            if delta <= 30:
                stars_30d += 1
        except Exception:
            continue

    # If the last page was full of recent stars, we may be undercounting.
    # Heuristic: if all 100 were <7d old, project the velocity forward.
    if stars_7d == len(items) and len(items) == 100 and last_page > 1:
        stars_7d = int(stars_7d * 1.5)  # rough projection
        stars_30d = max(stars_30d, stars_7d * 2)

    return {"stars_7d": stars_7d, "stars_30d": stars_30d}


def fetch_closed_issues(repo):
    """Approximate closed issue count."""
    r = requests.get(
        f"https://api.github.com/search/issues",
        headers=HEADERS,
        params={"q": f"repo:{repo} is:issue is:closed"},
        timeout=30,
    )
    if r.status_code != 200:
        return 0
    data = r.json()
    return data.get("total_count", 0)


def fetch_npm_weekly(pkg):
    """Get last-week downloads from the npm registry."""
    if not pkg:
        return 0
    url = f"https://api.npmjs.org/downloads/point/last-week/{pkg}"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            return r.json().get("downloads", 0)
    except Exception as e:
        print(f"   npm fetch failed for {pkg}: {e}")
    return 0


def days_since(iso_date):
    if not iso_date:
        return 999
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).days
    except Exception:
        return 999


# ─── Score computation ───

def score_star_velocity(stars_7d, stars_30d):
    """Log-scaled velocity score."""
    weekly = stars_7d
    if weekly <= 0:
        return 0
    # 1000+ stars/week = 100 (Claude Code tier)
    return min(100, (math.log10(weekly + 1) / math.log10(1001)) * 100)


def score_release_freshness(days):
    if days <= 7:
        return 100
    if days <= 30:
        return 90 - (days - 7) * 1.5
    if days <= 90:
        return 60 - (days - 30) * 0.5
    if days <= 365:
        return max(0, 30 - (days - 90) * 0.1)
    return 0


def score_commit_activity(commits_4w):
    if commits_4w <= 0:
        return 0
    # 300+ commits/month = 100
    return min(100, (math.log10(commits_4w + 1) / math.log10(301)) * 100)


def score_issue_health(open_issues, closed_issues):
    total = open_issues + closed_issues
    if total == 0:
        return 50
    return (closed_issues / total) * 100


def score_community(contributors):
    if contributors <= 0:
        return 0
    # 500+ contributors = 100
    return min(100, (math.log10(contributors + 1) / math.log10(501)) * 100)


def score_fork_ratio(forks, stars):
    if stars == 0:
        return 0
    ratio = forks / stars
    # 10-15% is healthy; above that bonus, below that penalty
    return min(100, ratio * 1000)


def score_npm_velocity(weekly_downloads):
    if weekly_downloads <= 0:
        return 0
    # 100k/week = 100
    return min(100, (math.log10(weekly_downloads + 1) / math.log10(100001)) * 100)


def compute_heat_score(metrics, weights, has_npm):
    """Weighted composite score 0-100."""
    components = {
        "star_velocity": score_star_velocity(metrics["stars_7d"], metrics["stars_30d"]),
        "release_freshness": score_release_freshness(metrics["days_since_release"]),
        "commit_activity": score_commit_activity(metrics["commits_4w"]),
        "issue_health": score_issue_health(metrics["open_issues"], metrics["closed_issues"]),
        "community": score_community(metrics["contributors"]),
        "fork_ratio": score_fork_ratio(metrics["forks"], metrics["stars"]),
        "npm_velocity": score_npm_velocity(metrics["npm_weekly"]) if has_npm else 0,
    }

    # If no npm, redistribute that weight to star velocity + commits
    active_weights = dict(weights)
    if not has_npm:
        npm_w = active_weights.pop("npm_velocity", 0)
        active_weights["star_velocity"] += npm_w * 0.5
        active_weights["commit_activity"] += npm_w * 0.5

    total = sum(active_weights.values())
    score = sum(components[k] * active_weights[k] for k in active_weights) / total
    return round(score, 1), components


# ─── Main ───

def track_agent(agent):
    repo = agent["repo"]
    print(f"📡 Tracking {agent['name']} ({repo})")

    repo_data = fetch_repo(repo)
    if not repo_data:
        print(f"   ⚠️ could not fetch repo")
        return None

    stars = repo_data.get("stargazers_count", 0)
    forks = repo_data.get("forks_count", 0)
    open_issues = repo_data.get("open_issues_count", 0)

    release = fetch_latest_release(repo) or {}
    commits_4w = fetch_recent_commits(repo, 28)
    star_hist = fetch_star_history(repo)
    closed_issues = fetch_closed_issues(repo)
    contributors = fetch_contributors_count(repo)
    npm_weekly = fetch_npm_weekly(agent.get("npm"))

    metrics = {
        "stars": stars,
        "forks": forks,
        "open_issues": open_issues,
        "closed_issues": closed_issues,
        "contributors": contributors,
        "stars_7d": star_hist["stars_7d"],
        "stars_30d": star_hist["stars_30d"],
        "commits_4w": commits_4w,
        "days_since_release": days_since(release.get("published_at")),
        "npm_weekly": npm_weekly,
    }

    return {
        "name": agent["name"],
        "repo": repo,
        "category": agent.get("category"),
        "vendor": agent.get("vendor"),
        "pricing": agent.get("pricing"),
        "description": agent.get("description"),
        "npm": agent.get("npm"),
        "vscode_extension": agent.get("vscode_extension"),
        "metrics": metrics,
        "latest_release": release,
        "pushed_at": repo_data.get("pushed_at"),
        "language": repo_data.get("language"),
        "license": (repo_data.get("license") or {}).get("spdx_id"),
        "html_url": repo_data.get("html_url"),
    }


def main():
    DATA_DIR.mkdir(exist_ok=True)
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    weights = config["weights"]
    results = {}

    for agent in config["agents"]:
        try:
            data = track_agent(agent)
            if data:
                has_npm = bool(agent.get("npm"))
                score, components = compute_heat_score(data["metrics"], weights, has_npm)
                data["heat_score"] = score
                data["score_components"] = {k: round(v, 1) for k, v in components.items()}
                results[agent["name"]] = data
        except Exception as e:
            print(f"   ⚠️ error tracking {agent['name']}: {e}")
            continue

    results["_meta"] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "agent_count": len([k for k in results if not k.startswith("_")]),
    }

    # Write latest snapshot
    with open(DATA_DIR / "latest.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    # Append to history
    history_path = DATA_DIR / "history.json"
    history = {}
    if history_path.exists():
        try:
            with open(history_path) as f:
                history = json.load(f)
        except Exception:
            history = {}

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    history[today] = {
        name: {
            "heat_score": r.get("heat_score"),
            "stars": r.get("metrics", {}).get("stars"),
            "stars_7d": r.get("metrics", {}).get("stars_7d"),
        }
        for name, r in results.items()
        if not name.startswith("_")
    }

    with open(history_path, "w") as f:
        json.dump(history, f, indent=2)

    print(f"\n✅ Tracked {results['_meta']['agent_count']} agents")
    print(f"   → {DATA_DIR / 'latest.json'}")


if __name__ == "__main__":
    main()
