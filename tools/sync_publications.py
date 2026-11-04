#!/usr/bin/env python3
"""
Find new A2M2 papers on OpenAlex and put them in front of a human to review.

Nothing is published automatically. `fetch` only reports. The two commands that
change files, `approve` and `reject`, are run by a person, one paper at a time.

Why OpenAlex and not Google Scholar: Scholar has no public API, blocks scripted
access, and mixes in duplicates and unrelated work. OpenAlex is free and has a
real API. It is queried by each co-director's ORCID iD, which is more precise
than matching on a name. No API key is needed: OpenAlex only asks for one when
using cursor paging, and this script uses plain page numbers.

    python3 tools/sync_publications.py fetch [--since 2025]
        Report works that are not on the site and have not been rejected.
        Defaults to the previous calendar year onwards, so a first run does not
        bury you in a decade of history. Use --since 2018 to backfill.

    python3 tools/sync_publications.py approve <id-or-doi> --programme <tag>
        Add one paper to assets/data/publications.json. --programme is
        required, and "none" is a valid answer. Use --dry-run to preview.

    python3 tools/sync_publications.py reject <id-or-doi> [--reason "..."]
        Remember that a paper is out of scope so it is never suggested again.

Known blind spot: arXiv-only preprints are often missing from OpenAlex, so add
those by hand (the DRBD-Mamba preprint is one).
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "assets" / "data" / "publications.json"
DEFAULT_REJECTED = ROOT / "tools" / "rejected_publications.json"

API = "https://api.openalex.org"
CONTACT = "a2m2.uwa@gmail.com"  # OpenAlex's "polite pool" asks for a contact
USER_AGENT = f"a2m2-website-sync (mailto:{CONTACT})"
SELECT = "id,doi,title,publication_year,type,authorships,primary_location,best_oa_location,locations"

# Confirmed by checking that each ORCID returns that person's known papers.
AUTHORS = [
    {"name": "Ghulam Mubashar Hassan", "orcid": "0000-0002-6636-8807"},
    {"name": "Naeha Sharif", "orcid": "0000-0001-8351-6288"},
]
ORCIDS = {a["orcid"] for a in AUTHORS}
AUTHOR_NAMES = {a["name"].lower() for a in AUTHORS}

# Must stay in step with PROGRAMMES in assets/js/main.js; a unit test checks it.
PROGRAMMES = (
    "brain-cognition",
    "vision-eye-health-oculomics",
    "cancer-imaging-precision-oncology",
    "vascular-health-healthy-ageing",
)
SITE_TYPES = ("journal", "conference", "preprint", "book")

# Starting suggestions only. The reviewer always chooses the final tag.
# Matched at the start of a word, so "eye" does not fire inside "they".
KEYWORDS = {
    "cancer-imaging-precision-oncology": [
        "tumor", "tumour", "glioblastoma", "glioma", "cancer", "oncolog",
        "radiomic", "psma", "metasta", "segmentation of", "pancrea", "prostate",
        "radiotherap", "radiation therap", "lesion",
    ],
    "vascular-health-healthy-ageing": [
        "coronary", "vascular", "aortic", "calcification", "cardio", "ageing", "aging",
    ],
    "vision-eye-health-oculomics": [
        "visual field", "glaucoma", "ophthalm", "retina", "oculomic", "fundus", "optic nerve", "eye",
    ],
    "brain-cognition": [
        "alzheimer", "dementia", "cognit", "neuroimag", "brain", "mci", "eeg", "neuro",
    ],
}
# A brain tumour paper is oncology, not cognition, unless it also says so.
COGNITION_STRONG = ("alzheimer", "dementia", "cognit", "neuroimag", "mci")

# OpenAlex work types that are never a publication worth listing.
SKIP_TYPES = {
    "peer-review", "paratext", "erratum", "retraction", "editorial", "dataset",
    "grant", "libguides", "supplementary-materials", "standard", "dissertation", "report",
}
# DOI prefixes of preprint servers: arXiv, Research Square, bio/medRxiv,
# Preprints.org, SSRN, TechRxiv.
PREPRINT_PREFIXES = ("10.48550/", "10.21203/", "10.1101/", "10.20944/", "10.2139/", "10.36227/")
CONFERENCE_WORDS = re.compile(
    r"\b(conference|workshop|proceedings|symposium|lecture notes|miccai|cvpr|iccv|eccv|"
    r"neurips|icml|aaai|wacv|isbi)\b",
    re.IGNORECASE,
)
STOPWORDS = {"a", "an", "and", "the", "of", "for", "in", "on", "with", "to", "using", "by", "from", "via"}


# ---------------------------------------------------------------- text helpers


def clean_title(title: str | None) -> str:
    """OpenAlex titles can carry markup such as <i> and HTML entities."""
    return html.unescape(re.sub(r"<[^>]+>", "", title or "")).strip()


def normalise_title(title: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean_title(title).lower()).strip()


def same_work(a: str, b: str) -> bool:
    """Same paper, allowing for a prefix such as 'MNA-net:' on one version."""
    if not a or not b:
        return False
    if a == b:
        return True
    return min(len(a), len(b)) >= 30 and (a in b or b in a)


def norm_doi(value: str | None) -> str | None:
    match = re.search(r"10\.\d{4,9}/[^\s?#\"<>]+", value or "", re.IGNORECASE)
    return match.group(0).lower().rstrip("/.") if match else None


def short_id(openalex_id: str | None) -> str:
    match = re.search(r"W\d+", openalex_id or "")
    return match.group(0) if match else ""


def make_slug(title: str, year: int, taken: set[str]) -> str:
    words = [w for w in re.findall(r"[a-z0-9]+", clean_title(title).lower()) if w not in STOPWORDS]
    base = "-".join(words[:5]) or "publication"
    slug = f"{base}-{year}"[:70].rstrip("-")
    candidate, n = slug, 2
    while candidate in taken:
        candidate, n = f"{slug}-{n}", n + 1
    return candidate


def year_group(year: int, today_year: int) -> str:
    """Recent years get their own heading, older ones share 'earlier'."""
    return str(year) if year >= today_year - 3 else "earlier"


# ------------------------------------------------------------------- classify


def suggest_programmes(title: str) -> list[str]:
    lowered = clean_title(title).lower()

    def hit(words) -> bool:
        return any(re.search(r"\b" + re.escape(w), lowered) for w in words)

    tags = [tag for tag, words in KEYWORDS.items() if hit(words)]
    if "cancer-imaging-precision-oncology" in tags and "brain-cognition" in tags:
        if not hit(COGNITION_STRONG):
            tags.remove("brain-cognition")
    return [t for t in PROGRAMMES if t in tags]


def venue_name(work: dict) -> str:
    """Prefer a real journal or conference over an institutional repository."""
    for location in work.get("locations") or []:
        source = location.get("source") or {}
        if source.get("type") in {"journal", "conference", "book series", "ebook platform"} and source.get("display_name"):
            return _dedupe_venue(source["display_name"])
    source = (work.get("primary_location") or {}).get("source") or {}
    return _dedupe_venue(source.get("display_name") or "")


def _dedupe_venue(name: str) -> str:
    """OpenAlex sometimes lists a venue's full name and its '.../Proceedings' alias
    joined by '/'; when the parts overlap heavily, keep only the first."""
    for separator in (" - ", "/"):
        parts = [p.strip() for p in name.split(separator) if p.strip()]
        if len(parts) > 1 and all(_similar(parts[0], p) for p in parts[1:]):
            return _dedupe_venue(parts[0]) if separator == " - " else parts[0]
    return name


def _similar(a: str, b: str) -> bool:
    a_words, b_words = set(a.lower().split()), set(b.lower().split())
    if not a_words or not b_words:
        return False
    overlap = len(a_words & b_words) / min(len(a_words), len(b_words))
    return overlap >= 0.6


def guess_type(work: dict) -> str:
    doi = norm_doi(work.get("doi")) or ""
    if work.get("type") == "preprint" or doi.startswith(PREPRINT_PREFIXES):
        return "preprint"
    name = venue_name(work)
    source_type = ((work.get("primary_location") or {}).get("source") or {}).get("type")
    if source_type == "conference" or CONFERENCE_WORDS.search(name):
        return "conference"  # LNCS chapters are 'book-chapter' in OpenAlex
    if work.get("type") in {"book", "book-chapter"}:
        return "book"
    return "journal"


def venue_string(work: dict, site_type: str, year: int) -> str:
    doi = norm_doi(work.get("doi")) or ""
    arxiv = re.match(r"10\.48550/arxiv\.(.+)", doi)
    if arxiv:
        return f"arXiv preprint arXiv:{arxiv.group(1)}, {year}"
    name = venue_name(work) or ("Preprint" if site_type == "preprint" else "")
    return f"{name}, {year}" if name else str(year)


def build_authors(work: dict) -> list[dict]:
    people = []
    for authorship in work.get("authorships") or []:
        author = authorship.get("author") or {}
        name = (author.get("display_name") or "").strip()
        if not name:
            continue
        orcid = (author.get("orcid") or "").rsplit("/", 1)[-1]
        member = orcid in ORCIDS or name.lower() in AUTHOR_NAMES
        people.append({"name": name, "groupMember": True} if member else {"name": name})
    if len(people) > 8:  # long consortium lists: first few, then our authors
        head = people[:3]
        members = [p for p in people[3:] if p.get("groupMember")]
        people = head + members + [{"name": "et al."}]
    return people


def build_links(work: dict, doi: str | None, site_type: str) -> list[dict]:
    links: list[dict] = []
    seen: set[str] = set()

    def add(label: str, url: str | None) -> None:
        if url and url.startswith(("http://", "https://")) and url not in seen:
            seen.add(url)
            links.append({"label": label, "url": url})

    if doi:
        add("DOI", f"https://doi.org/{doi}")
    open_access = work.get("best_oa_location") or {}
    add("Preprint" if site_type == "preprint" else "Open access",
        open_access.get("landing_page_url") or open_access.get("pdf_url"))
    if not links:
        add("View record", (work.get("primary_location") or {}).get("landing_page_url"))
    return links


def build_record(work: dict, taken_ids: set[str], today_year: int) -> dict:
    title = clean_title(work.get("title"))
    year = int(work["publication_year"])
    doi = norm_doi(work.get("doi"))
    site_type = guess_type(work)
    links = build_links(work, doi, site_type)
    url = links[0]["url"] if links else (work.get("id") or "")
    return {
        "id": make_slug(title, year, taken_ids),
        "title": title,
        "year": year,
        "yearGroup": year_group(year, today_year),
        "type": site_type,
        "authors": build_authors(work),
        "venue": venue_string(work, site_type, year),
        "url": url,
        "links": links,
        "programmeTags": suggest_programmes(title),
    }


# ------------------------------------------------------------------------ I/O


def api_get(path: str, params: dict | None = None) -> dict:
    url = f"{API}{path}?{urllib.parse.urlencode({**(params or {}), 'mailto': CONTACT})}"
    last = ""
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=40) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            body = error.read()[:300].decode("utf-8", "replace")
            if error.code != 429 and error.code < 500:
                raise RuntimeError(f"OpenAlex returned HTTP {error.code} for {url}: {body}") from None
            last = f"HTTP {error.code}"
        except (urllib.error.URLError, TimeoutError) as error:
            last = str(error)
        time.sleep(2 ** (attempt + 1))
    raise RuntimeError(f"OpenAlex unreachable after 3 attempts ({last}): {url}")


def fetch_author_works(orcid: str) -> list[dict]:
    works: list[dict] = []
    for page in range(1, 21):
        data = api_get("/works", {"filter": f"author.orcid:{orcid}", "per-page": 100, "page": page, "select": SELECT})
        results = data.get("results", [])
        works.extend(results)
        if len(results) < 100:
            break
        time.sleep(0.2)
    return works


def fetch_one(ref: str) -> dict:
    wid = short_id(ref)
    if wid:
        return api_get(f"/works/{wid}", {"select": SELECT})
    doi = norm_doi(ref)
    if doi:
        return api_get(f"/works/doi:{doi}", {"select": SELECT})
    raise SystemExit(f"'{ref}' is neither an OpenAlex id (W123...) nor a DOI.")


def load_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


# Mirrors the hand-written layout of publications.json (authors and links one
# object per line, tag lists inline) so approving a paper adds a clean diff
# instead of re-wrapping the whole file. A test checks it round-trips exactly.


def _s(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _inline(value) -> str:
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{_s(k)}: {_inline(v)}" for k, v in value.items()) + " }"
    if isinstance(value, list):
        return "[" + ", ".join(_inline(v) for v in value) + "]"
    return _s(value)


def _field(key: str, value, indent: int) -> str:
    pad = " " * indent
    if isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
        body = ",\n".join(f"{pad}  {_inline(v)}" for v in value)
        return f"{pad}{_s(key)}: [\n{body}\n{pad}]"
    return f"{pad}{_s(key)}: {_inline(value)}"


def dumps_publications(data: dict) -> str:
    lines = ["{"]
    for key, value in data.items():
        if key != "publications":
            lines.append(f"  {_s(key)}: {_inline(value)},")
    lines.append('  "publications": [')
    records = [
        "    {\n" + ",\n".join(_field(k, v, 6) for k, v in record.items()) + "\n    }"
        for record in data["publications"]
    ]
    lines.append(",\n".join(records))
    lines += ["  ]", "}"]
    return "\n".join(lines) + "\n"


def validate_publications(data: dict) -> list[str]:
    """The same rules assets/js/main.js applies; a record failing these is silently dropped there."""
    problems, seen = [], set()
    for i, r in enumerate(data.get("publications", [])):
        label = r.get("id") or f"#{i}"
        if not isinstance(r.get("id"), str) or not r["id"]:
            problems.append(f"{label}: missing id")
        elif r["id"] in seen:
            problems.append(f"{label}: duplicate id")
        seen.add(r.get("id"))
        for field in ("title", "venue"):
            if not isinstance(r.get(field), str) or not r[field]:
                problems.append(f"{label}: missing {field}")
        if not isinstance(r.get("year"), int):
            problems.append(f"{label}: year must be a number")
        if r.get("type") not in SITE_TYPES:
            problems.append(f"{label}: type must be one of {SITE_TYPES}")
        if not r.get("authors") or not all(a.get("name") for a in r["authors"]):
            problems.append(f"{label}: needs at least one named author")
        if not str(r.get("url", "")).startswith(("http://", "https://")):
            problems.append(f"{label}: url must be http(s)")
        for link in r.get("links", []):
            if not str(link.get("url", "")).startswith(("http://", "https://")):
                problems.append(f"{label}: link url must be http(s)")
        bad = [t for t in r.get("programmeTags", []) if t not in PROGRAMMES]
        if bad:
            problems.append(f"{label}: unknown programme tag(s) {bad}")
    return problems


# ------------------------------------------------------------------- commands


def site_keys(data: dict) -> tuple[set[str], list[str], set[str]]:
    dois, titles, ids = set(), [], set()
    for record in data.get("publications", []):
        ids.add(record["id"])
        titles.append(normalise_title(record["title"]))
        for url in [record.get("url", "")] + [l.get("url", "") for l in record.get("links", [])]:
            doi = norm_doi(url)
            if doi:
                dois.add(doi)
    return dois, titles, ids


def collect_candidates(args) -> list[dict]:
    today_year = dt.date.today().year
    since = args.since or today_year - 1
    site = load_json(args.data, {"publications": []})
    known_dois, known_titles, known_ids = site_keys(site)

    rejected = load_json(args.rejected, {"rejected": []})["rejected"]
    skip_ids = {r.get("openalexId") for r in rejected}
    skip_dois = {norm_doi(r.get("doi")) for r in rejected if r.get("doi")}
    skip_titles = [normalise_title(r.get("title")) for r in rejected]

    found: dict[str, dict] = {}
    reached = 0
    for author in AUTHORS:
        works = fetch_author_works(author["orcid"])
        print(f"  {author['name']}: {len(works)} works", file=sys.stderr)
        reached += bool(works)
        for work in works:
            entry = found.setdefault(short_id(work.get("id")), {"work": work, "via": []})
            entry["via"].append(author["name"])
    if not reached:
        # An outage must not read as "no new papers".
        raise SystemExit("OpenAlex returned no works for either author; refusing to report 'no candidates'.")

    pool = []
    for wid, entry in found.items():
        work = entry["work"]
        year = work.get("publication_year")
        title_key = normalise_title(work.get("title"))
        doi = norm_doi(work.get("doi"))
        if not wid or not title_key or not year or year < since or work.get("type") in SKIP_TYPES:
            continue
        if (doi and doi in known_dois) or any(same_work(title_key, k) for k in known_titles):
            continue
        if wid in skip_ids or (doi and doi in skip_dois) or any(same_work(title_key, k) for k in skip_titles):
            continue
        pool.append({"wid": wid, "work": work, "via": entry["via"], "key": title_key, "also": []})

    # One entry per paper: prefer the published version over its preprint.
    pool.sort(key=lambda c: (guess_type(c["work"]) == "preprint", -c["work"]["publication_year"]))
    kept: list[dict] = []
    for candidate in pool:
        twin = next((k for k in kept if same_work(candidate["key"], k["key"])), None)
        if twin:
            twin["also"].append(candidate["wid"])
            twin["via"] += [v for v in candidate["via"] if v not in twin["via"]]
        else:
            kept.append(candidate)

    taken = set(known_ids)
    for candidate in kept:
        record = build_record(candidate["work"], taken, today_year)
        taken.add(record["id"])
        candidate["record"] = record
        candidate["relevant"] = bool(record["programmeTags"])
    kept.sort(key=lambda c: (not c["relevant"], -c["record"]["year"], c["record"]["title"]))
    return kept


def render_markdown(candidates: list[dict], since: int) -> str:
    if not candidates:
        return f"No new publication candidates since {since}.\n"
    cmd = "python3 tools/sync_publications.py"
    out = [f"{len(candidates)} paper(s) on OpenAlex are not on the site yet (published {since} or later).",
           "Nothing has been published. Review each one and run the command shown.", ""]

    def entry(c: dict) -> list[str]:
        r = c["record"]
        names = ", ".join(a["name"] for a in r["authors"][:4]) + (", et al." if len(r["authors"]) > 4 else "")
        lines = [f"- **[{r['title']}]({r['url']})**  ",
                 f"  {r['year']} · {r['type']} · {r['venue']}  ",
                 f"  {names}  ",
                 f"  Found via {', '.join(c['via'])}"]
        if c["also"]:
            lines[-1] += f" · also listed as {', '.join(c['also'])}"
        return lines

    relevant = [c for c in candidates if c["relevant"]]
    other = [c for c in candidates if not c["relevant"]]
    if relevant:
        out += ["## Likely relevant", ""]
        for c in relevant:
            out += entry(c)
            tags = " ".join(f"--programme {t}" for t in c["record"]["programmeTags"])
            out += ["", "  ```", f"  {cmd} approve {c['wid']} {tags}", f"  {cmd} reject {c['wid']}", "  ```", ""]
    if other:
        out += ["## No programme keyword matched (probably outside A²M²)", ""]
        for c in other:
            out += entry(c)
            out += ["", "  ```", f"  {cmd} reject {c['wid']} --reason \"out of scope\"",
                    f"  {cmd} approve {c['wid']} --programme none", "  ```", ""]
    return "\n".join(out) + "\n"


def command_fetch(args) -> None:
    since = args.since or dt.date.today().year - 1
    candidates = collect_candidates(args)
    markdown = render_markdown(candidates, since)
    print(markdown)
    if args.markdown:
        Path(args.markdown).write_text(markdown, encoding="utf-8")
    if args.json:
        summary = [{"openalexId": c["wid"], "title": c["record"]["title"], "year": c["record"]["year"],
                    "relevant": c["relevant"], "suggested": c["record"]["programmeTags"]} for c in candidates]
        Path(args.json).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def command_approve(args) -> None:
    today_year = dt.date.today().year
    work = fetch_one(args.ref)
    if not work.get("title") or not work.get("publication_year"):
        raise SystemExit("OpenAlex has no title or year for that work; add it by hand instead.")
    site = load_json(args.data, {"schemaVersion": 1, "publications": []})
    dois, titles, ids = site_keys(site)
    title_key = normalise_title(work["title"])
    doi = norm_doi(work.get("doi"))
    if (doi and doi in dois) or any(same_work(title_key, k) for k in titles):
        raise SystemExit("That paper is already on the site.")

    record = build_record(work, ids, today_year)
    record["programmeTags"] = [] if "none" in args.programme else list(dict.fromkeys(args.programme))
    if args.type:
        record["type"] = args.type
        record["venue"] = venue_string(work, args.type, record["year"])

    index = next((i for i, r in enumerate(site["publications"]) if r["year"] <= record["year"]), len(site["publications"]))
    site["publications"].insert(index, record)
    problems = validate_publications(site)
    if problems:
        raise SystemExit("Refusing to write; the result would be invalid:\n  " + "\n  ".join(problems))

    if args.dry_run:
        print(json.dumps(record, indent=2, ensure_ascii=False))
        print("\n(dry run, nothing written)")
        return
    args.data.write_text(dumps_publications(site), encoding="utf-8")
    print(f"Added \"{record['title']}\" ({record['type']}, {record['year']}).")
    print("Check the authors, venue and links before committing: OpenAlex metadata is not always complete.")


def command_reject(args) -> None:
    work = fetch_one(args.ref)
    data = load_json(args.rejected, {"rejected": []})
    wid = short_id(work.get("id"))
    if any(r.get("openalexId") == wid for r in data["rejected"]):
        print("Already rejected.")
        return
    data["rejected"].append({
        "openalexId": wid,
        "doi": norm_doi(work.get("doi")),
        "title": clean_title(work.get("title")),
        "reason": args.reason or "",
        "date": dt.date.today().isoformat(),
    })
    args.rejected.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Rejected \"{clean_title(work.get('title'))}\". It will not be suggested again.")


def main(argv: list[str] | None = None) -> None:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--data", type=Path, default=DEFAULT_DATA, help=argparse.SUPPRESS)
    common.add_argument("--rejected", type=Path, default=DEFAULT_REJECTED, help=argparse.SUPPRESS)

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", parents=[common], help="Report papers not yet on the site.")
    fetch.add_argument("--since", type=int, help="Earliest publication year (default: last year).")
    fetch.add_argument("--markdown", help="Also write the report to this file.")
    fetch.add_argument("--json", help="Also write a machine-readable summary to this file.")
    fetch.set_defaults(run=command_fetch)

    approve = sub.add_parser("approve", parents=[common], help="Add one paper to publications.json.")
    approve.add_argument("ref", help="OpenAlex id (W123...) or DOI.")
    approve.add_argument("--programme", action="append", required=True, choices=[*PROGRAMMES, "none"],
                         help="Programme tag; repeat for several, or 'none'.")
    approve.add_argument("--type", choices=SITE_TYPES, help="Override the guessed type.")
    approve.add_argument("--dry-run", action="store_true")
    approve.set_defaults(run=command_approve)

    reject = sub.add_parser("reject", parents=[common], help="Never suggest this paper again.")
    reject.add_argument("ref", help="OpenAlex id (W123...) or DOI.")
    reject.add_argument("--reason")
    reject.set_defaults(run=command_reject)

    args = parser.parse_args(argv)
    try:
        args.run(args)
    except RuntimeError as error:
        raise SystemExit(f"error: {error}") from None


if __name__ == "__main__":
    main()
