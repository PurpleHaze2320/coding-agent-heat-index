"""
Dashboard Generator for Coding Agent Heat Index.
Produces a rich README.md leaderboard.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
README_PATH = ROOT / "README.md"


def load_latest():
    with open(DATA_DIR / "latest.json") as f:
        return json.load(f)


def load_history():
    path = DATA_DIR / "history.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def fmt_num(n):
    if n is None:
        return "—"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def heat_emoji(score):
    if score >= 75:
        return "🔥🔥🔥"
    if score >= 60:
        return "🔥🔥"
    if score >= 45:
        return "🔥"
    if score >= 30:
        return "🟡"
    if score >= 15:
        return "🟠"
    return "🔴"


def stars_arrow(stars_7d):
    if stars_7d >= 1000:
        return f"🚀 +{fmt_num(stars_7d)}"
    if stars_7d >= 200:
        return f"🚀 +{stars_7d}"
    if stars_7d >= 50:
        return f"📈 +{stars_7d}"
    if stars_7d >= 10:
        return f"↗️ +{stars_7d}"
    if stars_7d > 0:
        return f"→ +{stars_7d}"
    return "—"


def days_ago(iso_date):
    if not iso_date:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        days = (datetime.now(timezone.utc) - dt).days
        if days == 0:
            return "today"
        if days == 1:
            return "1 day ago"
        if days < 30:
            return f"{days} days ago"
        if days < 365:
            return f"{days // 30} mo ago"
        return f"{days // 365}y ago"
    except Exception:
        return "—"


def generate_readme(data, history):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    agents = [v for k, v in data.items() if not k.startswith("_")]
    agents.sort(key=lambda x: x.get("heat_score", 0), reverse=True)

    total = len(agents)
    total_stars = sum(a.get("metrics", {}).get("stars", 0) for a in agents)
    total_7d = sum(a.get("metrics", {}).get("stars_7d", 0) for a in agents)

    lines = [
        "# 🔥 Coding Agent Heat Index",
        "",
        "[![Daily Update](https://github.com/PurpleHaze2320/coding-agent-heat-index/actions/workflows/track.yml/badge.svg)](https://github.com/PurpleHaze2320/coding-agent-heat-index/actions/workflows/track.yml)",
        f"[![Agents Tracked](https://img.shields.io/badge/agents-{total}-blue)](https://github.com/PurpleHaze2320/coding-agent-heat-index)",
        "[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)",
        "[![GitHub stars](https://img.shields.io/github/stars/PurpleHaze2320/coding-agent-heat-index?style=social)](https://github.com/PurpleHaze2320/coding-agent-heat-index/stargazers)",
        "",
        "> The daily leaderboard for AI coding agents. Cursor, Claude Code, Cline, Aider, Codex, Gemini CLI and 6 more — ranked by real momentum, not marketing.",
        "",
        f"> Tracking **{total}** agents | **{fmt_num(total_stars)}** combined stars | **+{fmt_num(total_7d)}** stars this week | Updated **{now}**",
        "",
        "## Why This Exists",
        "",
        "Every week a new AI coding tool drops and claims to be the \"best.\" Developers are picking sides like sports fans —",
        "Cursor loyalists, Cline power users, Aider purists, Claude Code believers. But nobody is measuring who is actually",
        "winning based on real usage, velocity, and community momentum.",
        "",
        "This bot crawls GitHub and npm every day and calculates a **Heat Score (0–100)** for every major coding agent,",
        "based on seven weighted signals: star velocity, release cadence, commit activity, issue health, community size,",
        "fork ratio, and weekly npm downloads. No vibes, no vendor-picked benchmarks — just the data.",
        "",
        "---",
        "",
        "## 🏆 The Leaderboard",
        "",
        "| Rank | Agent | Heat | Stars | ⭐ 7d | Commits (4w) | Last Release | Category |",
        "|------|-------|:----:|------:|:-----:|:------------:|:------------:|----------|",
    ]

    for i, a in enumerate(agents, 1):
        m = a.get("metrics", {})
        rel = a.get("latest_release") or {}
        rel_days = days_ago(rel.get("published_at"))
        lines.append(
            f"| {i} | [{a['name']}](https://github.com/{a['repo']}) "
            f"| {heat_emoji(a.get('heat_score', 0))} **{a.get('heat_score', 0):.1f}** "
            f"| {fmt_num(m.get('stars', 0))} "
            f"| {stars_arrow(m.get('stars_7d', 0))} "
            f"| {m.get('commits_4w', 0)} "
            f"| {rel_days} "
            f"| `{a.get('category', '—')}` |"
        )

    lines += ["", "---", ""]

    # ─── Head-to-head ───
    if len(agents) >= 2:
        top = agents[0]
        runner_up = agents[1]
        lines += [
            "## 🥊 Today's Head-to-Head",
            "",
            f"**{top['name']}** vs **{runner_up['name']}** — the two hottest agents right now.",
            "",
            f"| Metric | {top['name']} | {runner_up['name']} | Winner |",
            f"|--------|:-:|:-:|:-:|",
        ]
        a, b = top.get("metrics", {}), runner_up.get("metrics", {})

        def row(label, av, bv, display_a=None, display_b=None, higher_better=True):
            """Compare numeric values, but allow pretty-formatted display strings."""
            if higher_better:
                winner = top["name"] if av > bv else (runner_up["name"] if bv > av else "tie")
            else:
                winner = top["name"] if av < bv else (runner_up["name"] if bv < av else "tie")
            da = display_a if display_a is not None else av
            db = display_b if display_b is not None else bv
            winner_cell = f"**{winner}**" if winner != "tie" else "—"
            return f"| {label} | {da} | {db} | {winner_cell} |"

        lines.append(row("Heat Score", top.get("heat_score", 0), runner_up.get("heat_score", 0)))
        lines.append(row("Stars", a.get("stars", 0), b.get("stars", 0),
                         display_a=fmt_num(a.get("stars", 0)), display_b=fmt_num(b.get("stars", 0))))
        lines.append(row("Stars (7d)", a.get("stars_7d", 0), b.get("stars_7d", 0)))
        lines.append(row("Commits (4w)", a.get("commits_4w", 0), b.get("commits_4w", 0)))
        lines.append(row("Contributors", a.get("contributors", 0), b.get("contributors", 0)))
        lines.append(row("Days since release", a.get("days_since_release", 999), b.get("days_since_release", 999), higher_better=False))
        lines += ["", "---", ""]

    # ─── By Vendor Tier ───
    big_tech = [a for a in agents if a.get("vendor") in ("Anthropic", "OpenAI", "Google", "Microsoft")]
    startups = [a for a in agents if a.get("vendor") not in ("Anthropic", "OpenAI", "Google", "Microsoft", "Block")]

    lines += [
        "## 🏢 Big Lab vs. Indie",
        "",
        "| Tier | Agents | Avg Heat | Total Stars |",
        "|------|--------|---------:|------------:|",
    ]
    for tier_name, tier_agents in [("Big Lab", big_tech), ("Indie / Open Source", startups)]:
        if tier_agents:
            avg = sum(a.get("heat_score", 0) for a in tier_agents) / len(tier_agents)
            stars = sum(a.get("metrics", {}).get("stars", 0) for a in tier_agents)
            lines.append(f"| {tier_name} | {len(tier_agents)} | {avg:.1f} | {fmt_num(stars)} |")

    lines += ["", "---", ""]

    # ─── Score breakdown for top 5 ───
    lines += [
        "## 🔍 Heat Score Breakdown — Top 5",
        "",
        "| Agent | Star Velocity | Release Freshness | Commit Activity | Issue Health | Community | Fork Ratio | npm |",
        "|-------|:-:|:-:|:-:|:-:|:-:|:-:|:-:|",
    ]
    for a in agents[:5]:
        c = a.get("score_components", {})
        npm_val = f"{c.get('npm_velocity', 0):.0f}" if a.get("npm") else "—"
        lines.append(
            f"| **{a['name']}** "
            f"| {c.get('star_velocity', 0):.0f} "
            f"| {c.get('release_freshness', 0):.0f} "
            f"| {c.get('commit_activity', 0):.0f} "
            f"| {c.get('issue_health', 0):.0f} "
            f"| {c.get('community', 0):.0f} "
            f"| {c.get('fork_ratio', 0):.0f} "
            f"| {npm_val} |"
        )

    lines += ["", "---", ""]

    # ─── Recent Releases ───
    rels = [a for a in agents if a.get("latest_release", {}).get("published_at")]
    rels.sort(key=lambda x: x["latest_release"]["published_at"], reverse=True)
    if rels:
        lines += ["## 📦 Recent Releases", ""]
        for a in rels[:10]:
            r = a["latest_release"]
            tag = r.get("tag") or "release"
            lines.append(
                f"- **{a['name']}** [`{tag}`]({r.get('url', '#')}) — {days_ago(r.get('published_at'))}"
            )
        lines += ["", "---", ""]

    # ─── Insights ───
    lines += ["## 💡 Today's Insights", ""]
    if agents:
        hottest = agents[0]
        lines.append(f"- **Hottest agent**: {hottest['name']} with a Heat Score of {hottest['heat_score']:.1f}")

        fastest_growing = max(agents, key=lambda x: x.get("metrics", {}).get("stars_7d", 0))
        lines.append(
            f"- **Fastest growing**: {fastest_growing['name']} gained **+{fastest_growing['metrics']['stars_7d']}** stars this week"
        )

        most_active = max(agents, key=lambda x: x.get("metrics", {}).get("commits_4w", 0))
        lines.append(
            f"- **Most active development**: {most_active['name']} with **{most_active['metrics']['commits_4w']}** commits in the last 4 weeks"
        )

        most_contributors = max(agents, key=lambda x: x.get("metrics", {}).get("contributors", 0))
        lines.append(
            f"- **Biggest community**: {most_contributors['name']} with **{most_contributors['metrics']['contributors']}** contributors"
        )

        npm_agents = [a for a in agents if a.get("metrics", {}).get("npm_weekly", 0) > 0]
        if npm_agents:
            top_npm = max(npm_agents, key=lambda x: x["metrics"]["npm_weekly"])
            lines.append(
                f"- **Most installed (npm, weekly)**: {top_npm['name']} with **{fmt_num(top_npm['metrics']['npm_weekly'])}** downloads"
            )

        stale = [a for a in agents if a.get("metrics", {}).get("days_since_release", 0) > 60]
        if stale:
            names = ", ".join(s["name"] for s in stale[:3])
            lines.append(f"- **Losing steam**: {names} haven't shipped a release in 60+ days")

    lines += ["", "---", ""]

    # ─── How the score works ───
    lines += [
        "## ⚙️ How the Heat Score Works",
        "",
        "A weighted composite of 7 signals, scored 0–100:",
        "",
        "| Signal | Weight | What It Measures |",
        "|--------|:------:|------------------|",
        "| Star Velocity | 25% | 7-day star growth (log-scaled) |",
        "| Commit Activity | 20% | Commits in the last 4 weeks |",
        "| Release Freshness | 15% | Days since last release |",
        "| npm Velocity | 15% | Weekly downloads (if published to npm) |",
        "| Issue Health | 10% | Closed issues / total issues |",
        "| Community | 10% | Total contributors (log-scaled) |",
        "| Fork Ratio | 5% | Forks relative to stars |",
        "",
        "Agents not published to npm have that weight redistributed to Star Velocity and Commit Activity.",
        "",
        "## 🚀 Running Locally",
        "",
        "```bash",
        "git clone https://github.com/PurpleHaze2320/coding-agent-heat-index.git",
        "cd coding-agent-heat-index",
        "pip install -r requirements.txt",
        "export GITHUB_TOKEN=ghp_your_token_here  # recommended",
        "python tracker.py",
        "python dashboard.py",
        "```",
        "",
        "## 📋 Adding an Agent",
        "",
        "Edit `config.yaml` and add an entry under `agents:`",
        "",
        "```yaml",
        "- name: MyAgent",
        "  repo: owner/repo-name",
        "  npm: \"@scope/package\"    # optional",
        "  category: cli-agent",
        "  vendor: MyCompany",
        "```",
        "",
        "---",
        "",
        f"*Powered by GitHub Actions • Data refreshed daily • Last run: {now}*",
        "",
        "*Built because developers deserve an unbiased leaderboard for the tools we use every day.*",
    ]

    return "\n".join(lines)


def main():
    data = load_latest()
    history = load_history()
    readme = generate_readme(data, history)
    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(readme)
    print(f"✅ Dashboard written to {README_PATH}")


if __name__ == "__main__":
    main()
