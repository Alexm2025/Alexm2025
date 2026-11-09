"""Generate GitHub stats + top-language SVG cards for the profile README.

Runs in GitHub Actions with GITHUB_TOKEN. No third-party services, so the
cards never break because of someone else's rate limits.

Usage: python scripts/gen_stats.py <username> <output_dir>
"""
import json
import os
import sys
import urllib.request
from html import escape

USER = sys.argv[1]
OUT = sys.argv[2]
TOKEN = os.environ["GITHUB_TOKEN"]

QUERY = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    name
    followers { totalCount }
    pullRequests { totalCount }
    issues { totalCount }
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
      contributionCalendar { totalContributions }
    }
    repositoriesContributedTo(contributionTypes: [COMMIT, PULL_REQUEST, ISSUE]) { totalCount }
    repositories(first: 100, after: $cursor, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


def gql(variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        data = json.load(r)
    if "errors" in data:
        raise SystemExit(data["errors"])
    return data["data"]["user"]


def collect():
    cursor, repos, first = None, [], None
    while True:
        u = gql({"login": USER, "cursor": cursor})
        first = first or u
        repos += u["repositories"]["nodes"]
        page = u["repositories"]["pageInfo"]
        if not page["hasNextPage"]:
            break
        cursor = page["endCursor"]
    langs = {}
    for repo in repos:
        for e in repo["languages"]["edges"]:
            n = e["node"]["name"]
            if n in ("HTML", "CSS", "Jupyter Notebook", "Dockerfile", "Shell", "Makefile"):
                continue  # markup/config noise skews the chart
            size, color = langs.get(n, (0, e["node"]["color"] or "#8B949E"))
            langs[n] = (size + e["size"], color)
    cc = first["contributionsCollection"]
    stats = {
        "Total stars": sum(r["stargazerCount"] for r in repos),
        "Commits (this year)": cc["totalCommitContributions"] + cc["restrictedContributionsCount"],
        "Contributions (last year)": cc["contributionCalendar"]["totalContributions"],
        "Pull requests": first["pullRequests"]["totalCount"],
        "Public repositories": first["repositories"]["totalCount"],
        "Contributed to": first["repositoriesContributedTo"]["totalCount"],
    }
    return stats, langs


STYLE = """
<style>
.t{font:700 18px 'Segoe UI',Inter,Helvetica,Arial,sans-serif;fill:#E2E8F0}
.l{font:500 14px 'Segoe UI',Inter,Helvetica,Arial,sans-serif;fill:#94A3B8}
.v{font:700 15px 'Fira Code',Consolas,monospace;fill:#F8FAFC}
.fade{animation:in .6s ease both}
@keyframes in{from{opacity:0}to{opacity:1}}
</style>
<defs><linearGradient id="a" x1="0" x2="1"><stop offset="0" stop-color="#2DD4BF"/><stop offset=".5" stop-color="#38BDF8"/><stop offset="1" stop-color="#8B5CF6"/></linearGradient></defs>
"""


def card(w, h, title, body):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">{STYLE}'
        f'<rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="14" fill="#0B1324" stroke="#1E293B"/>'
        f'<rect x="24" y="52" width="40" height="3" rx="1.5" fill="url(#a)"/>'
        f'<text x="24" y="38" class="t">{escape(title)}</text>{body}</svg>'
    )


ICONS = ["★", "⎇", "▦", "⇄", "▣", "◎"]


def stats_svg(stats):
    rows = []
    for i, (k, v) in enumerate(stats.items()):
        y = 88 + i * 30
        rows.append(
            f'<g class="fade" style="animation-delay:{i*120}ms">'
            f'<text x="24" y="{y}" class="l" fill="url(#a)"><tspan fill="#38BDF8">{ICONS[i]}</tspan>  {escape(k)}</text>'
            f'<text x="406" y="{y}" class="v" text-anchor="end">{v:,}</text></g>'
        )
    return card(430, 270, "GitHub Stats", "".join(rows))


def langs_svg(langs):
    top = sorted(langs.items(), key=lambda kv: -kv[1][0])[:6]
    total = sum(s for _, (s, _) in top) or 1
    x, bar = 24.0, []
    for name, (size, color) in top:
        w = 382 * size / total
        bar.append(f'<rect x="{x:.1f}" y="74" width="{w:.1f}" height="10" fill="{color}"/>')
        x += w
    bar_svg = f'<clipPath id="c"><rect x="24" y="74" width="382" height="10" rx="5"/></clipPath><g clip-path="url(#c)">{"".join(bar)}</g>'
    items = []
    for i, (name, (size, color)) in enumerate(top):
        col, row = i % 2, i // 2
        cx, cy = 30 + col * 196, 122 + row * 34
        items.append(
            f'<g class="fade" style="animation-delay:{i*120}ms"><circle cx="{cx}" cy="{cy-5}" r="6" fill="{color}"/>'
            f'<text x="{cx+14}" y="{cy}" class="l"><tspan fill="#E2E8F0">{escape(name)}</tspan>  {100*size/total:.1f}%</text></g>'
        )
    return card(430, 270, "Most Used Languages", bar_svg + "".join(items))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    stats, langs = collect()
    with open(os.path.join(OUT, "stats.svg"), "w") as f:
        f.write(stats_svg(stats))
    with open(os.path.join(OUT, "languages.svg"), "w") as f:
        f.write(langs_svg(langs))
    print(json.dumps(stats, indent=2))
