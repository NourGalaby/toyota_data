#!/usr/bin/env python3
"""
Toyota Trim-Level Spec Scraper
==============================
Part 1 — Fetch HTML for each model and save to disk
Part 2 — Parse fsoData JSON embedded in each page → output.json
Part 3 — Sanity-check every record in output.json
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

# ──────────────────────────────────────────────────────────────────────────────
# SHARED CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────

MODELS = ["camry", "rav4", "tacoma"]

FEATURES_URL_TEMPLATE = "https://www.toyota.com/{series}/features/"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)

SECTION_PRICE      = "mpg/other/price"
SECTION_MECHANICAL = "mechanical/performance"
SECTION_DIMENSIONS = "dimensions"
SECTION_WEIGHTS    = "weights/capacities"

# Maps every known full-length drivetrain label to its abbreviation.
# icon == "standard" means this trim ships with that drivetrain.
DRIVETRAIN_LABEL_MAP: dict[str, str] = {
    "Front-Wheel Drive (FWD)":                              "FWD",
    "Electronic On-Demand All-Wheel Drive (AWD)":           "AWD",
    "All-Wheel Drive (AWD)":                                "AWD",
    "Four-Wheel Drive (4WD)":                               "4WD",
    "Part-Time Four-Wheel Drive (4WD)":                     "4WD",
    "Rear-Wheel Drive (RWD)":                               "RWD",
}

DETAILED_JSON = Path("detailed_trims.json")   # every variant, nothing dropped
BASE_JSON     = Path("base_output.json")       # one row per (model, trim) — min MSRP variant


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  PART 1 — FETCH HTML                                                        ║
# ║  Iterates over MODELS, fetches each /features/ page, throttles 1 s between  ║
# ║  requests, and saves raw HTML under scrapped/<today>/<series>/page.html      ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def build_save_path(series: str) -> Path:
    """Return scrapped/<YYYY-MM-DD>/<series>/page.html, creating dirs as needed."""
    today = date.today().isoformat()          # e.g. 2026-06-10
    path  = Path("scrapped") / today / series / "page.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def fetch_html(url: str, timeout: int = 30) -> bytes:
    """Send a browser-like GET request and return raw bytes."""
    request = Request(
        url,
        headers={
            "User-Agent":      USER_AGENT,
            "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def scrape_all_models(throttle_seconds: float = 1.0) -> dict[str, Path]:
    """
    Fetch every model's /features/ page and persist the HTML.

    Returns a mapping of {series: saved_html_path}.
    Already-saved pages are re-used so the scraper is idempotent within one day.
    """
    saved: dict[str, Path] = {}

    for index, series in enumerate(MODELS):
        url       = FEATURES_URL_TEMPLATE.format(series=series)
        save_path = build_save_path(series)

        if save_path.exists():
            print(f"[Part 1] {series}: cached → {save_path}")
            saved[series] = save_path
            continue

        # Throttle between live requests (skip before the very first one)
        if index > 0 and saved:
            print(f"[Part 1] Throttling {throttle_seconds}s …")
            time.sleep(throttle_seconds)

        print(f"[Part 1] Fetching {url} …", end=" ", flush=True)
        try:
            html_bytes = fetch_html(url)
        except HTTPError as exc:
            print(f"FAILED — HTTP {exc.code}: {exc.reason}", file=sys.stderr)
            continue
        except URLError as exc:
            print(f"FAILED — {exc.reason}", file=sys.stderr)
            continue

        save_path.write_bytes(html_bytes)
        print(f"saved {len(html_bytes):,} bytes → {save_path}")
        saved[series] = save_path

    return saved


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  PART 2 — PARSE HTML INTO JSON                                               ║
# ║  Reads saved HTML files, extracts the embedded fsoData JSON blob, walks      ║
# ║  every grade × trim_id, and writes output.json (one object per trim).        ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# ── Helpers ───────────────────────────────────────────────────────────────────

def clean_label(raw: str) -> str:
    """Strip HTML tags (<sup>, <b>, etc.) and surrounding whitespace."""
    return re.sub(r"<[^>]+>", "", raw).strip()


def brace_match(text: str, start: int) -> str:
    """
    Return the JSON object substring starting at text[start] by counting braces.
    Raises ValueError if braces are unbalanced.
    """
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValueError("Unbalanced braces — could not extract JSON object.")


def extract_fso_data(html: str) -> dict:
    """
    Locate the literal string 'fsoData:' in the page source, then brace-match
    the object that follows and parse it as JSON.
    """
    marker = "fsoData:"
    pos    = html.find(marker)
    if pos == -1:
        raise ValueError("fsoData marker not found in HTML.")
    json_text = brace_match(html, pos + len(marker))
    return json.loads(json_text)


def parse_vehicle_metadata(soup: BeautifulSoup) -> tuple[str, str, str]:
    """
    Read year, make, model from the #fso-header-data element.
    Falls back to the <title> tag if the element is absent.
    Returns (year, make, model); any missing piece is an empty string.
    """
    header = soup.find(id="fso-header-data")
    if header:
        year  = header.get("data-year", "") or ""
        model = header.get("data-display-name", "") or ""
        if year and model:
            return year, "Toyota", model

    # Fallback: parse "2026 Toyota Camry" from <title>
    title = (soup.title.string or "") if soup.title else ""
    m = re.search(r"(\d{4})\s+Toyota\s+([\w ]+)", title)
    if m:
        return m.group(1), "Toyota", m.group(2).strip()

    return "", "Toyota", ""


def grade_key_to_trim_name(grade_key: str, series: str) -> str:
    """
    Convert a grade key like 'camry_xle', 'rav4_woodland', or
    'tacoma_trd_pro' into a human-readable trim name.

    Rules:
    - Strip the leading '{series}_' prefix (case-insensitive)
    - Upper-case common acronyms (TRD, XLE, XSE, LE, SE, SR, SR5, AWD, …)
    - Join remaining words with spaces in title-case
    """
    ACRONYMS = {
        "trd", "xle", "xse", "le", "se", "sr", "sr5", "awd", "fwd",
        "4wd", "rwd", "phev", "ev", "xl", "xr", "ltz", "ls",
    }

    name = re.sub(rf"^{re.escape(series)}_", "", grade_key, flags=re.IGNORECASE)
    parts = name.split("_")
    formatted = []
    for part in parts:
        if part.lower() in ACRONYMS:
            formatted.append(part.upper())
        else:
            formatted.append(part.capitalize())
    return " ".join(formatted)


# ── Feature extraction ────────────────────────────────────────────────────────

def build_feature_map(trim_features: dict | None) -> dict[str, dict]:
    """
    Given the raw features dict for a single trim_id, return a lookup keyed by
    the cleaned label string.
    """
    if not trim_features:
        return {}
    result: dict[str, dict] = {}
    for feature in trim_features.values():
        label = clean_label(feature.get("label", ""))
        if label:
            result[label] = feature
    return result


def _get_feature_value(features: dict[str, dict], *prefixes: str) -> str | None:
    """
    Return the first non-empty value whose label starts with (or equals) any
    of the given prefixes.  Returns None if nothing matches.
    """
    for prefix in prefixes:
        for label, feature in features.items():
            if label == prefix or label.startswith(prefix):
                value = feature.get("value", "")
                if isinstance(value, str):
                    value = value.strip()
                if value:
                    return value
    return None


def get_hp_from_label(features: dict[str, dict]) -> str | None:
    """
    Some models (e.g. RAV4) embed horsepower inside the label itself rather than
    in the value field, e.g.:
      "Hybrid powertrain: 2.5-Liter … ; 226 net combined hp"  (value == "")

    Scan standard-icon features for a label containing "N net combined hp" and
    return the number as a plain string, or None if not found.
    """
    for label, feature in features.items():
        if feature.get("icon") != "standard":
            continue
        match = re.search(r"(\d+)\s+net combined hp", label, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def get_standard_drivetrain(features: dict[str, dict]) -> str | None:
    """
    Walk the mechanical features; return the abbreviation for the first
    drivetrain label whose icon field equals 'standard'.
    """
    for full_label, abbreviation in DRIVETRAIN_LABEL_MAP.items():
        feature = features.get(full_label)
        if feature and feature.get("icon") == "standard":
            return abbreviation

    # Fallback: scan all labels for drivetrain keywords marked standard.
    # Covers labels with extra text like "Full-time 4-Wheel Drive with …"
    for label, feature in features.items():
        if feature.get("icon") != "standard":
            continue
        lower = label.lower()
        if "front-wheel drive" in lower or "(fwd)" in lower:
            return "FWD"
        if "all-wheel drive" in lower or "(awd)" in lower:
            return "AWD"
        if "four-wheel drive" in lower or "4-wheel drive" in lower or "(4wd)" in lower:
            return "4WD"
        if "rear-wheel drive" in lower or "(rwd)" in lower:
            return "RWD"

    return None


def infer_fuel_type(features: dict[str, dict]) -> str | None:
    """
    Determine fuel type from the mechanical/performance features.

    Priority order (highest specificity first):
    1. Hybrid System Net Horsepower present → Hybrid
    2. Standard label mentioning plug-in / PHEV → PHEV
    3. Standard label mentioning fuel cell / hydrogen → Hydrogen
    4. Standard label mentioning battery electric / all-electric → EV
    5. Standard label mentioning i-FORCE MAX hybrid powertrain → Hybrid
    6. Standard label mentioning hybrid or electric motor → Hybrid
    7. Standard label matching an engine displacement / powertrain pattern → Gas
       (covers "2.4L", "inline-4", "V6", "-liter", "-cylinder", "i-FORCE …engine")
    8. Cannot determine → None
    """
    if _get_feature_value(features, "Hybrid System Net Horsepower"):
        return "Hybrid"

    for label, feature in features.items():
        if feature.get("icon") != "standard":
            continue
        lower = label.lower()
        if "plug-in" in lower or "phev" in lower:
            return "PHEV"
        if "fuel cell" in lower or "hydrogen" in lower:
            return "Hydrogen"
        if "battery electric" in lower or "all-electric" in lower:
            return "EV"
        # i-FORCE MAX is Toyota's hybrid truck powertrain
        if "i-force max" in lower and "hybrid" in lower:
            return "Hybrid"
        if "hybrid" in lower or ("electric motor" in lower and "ev mode" not in lower):
            return "Hybrid"
        if re.search(r"permanent.magnet.*motor", lower):
            return "Hybrid"

    for label, feature in features.items():
        if feature.get("icon") != "standard":
            continue
        lower = label.lower()
        # Standard displacement patterns: "2.4L", "2.4-liter", "4-cylinder",
        # "inline-4", "V6", "i-FORCE …engine" (gas variant without MAX)
        if re.search(
            r"\d+\.\d+l\b"                   # 2.4L, 3.5L …
            r"|\d+\.\d+-liter"               # 2.4-liter …
            r"|\d+-cylinder"                 # 4-cylinder …
            r"|inline-\d"                    # inline-4, inline-6 …
            r"|\bv\d\b"                      # V6, V8 …
            r"|i-force\b.*engine"            # i-FORCE … engine (gas)
            r"|turbocharged.*engine",        # turbocharged … engine
            lower,
        ):
            return "Gas"

    return None


def or_null(value: str | None) -> str | None:
    """Return the value if it is a non-empty string, else None."""
    if not value:
        return None
    return value


# ── Core extraction ────────────────────────────────────────────────────────────

def extract_trim_records(
    fso_data: dict,
    year: str,
    make: str,
    model: str,
    series: str,
) -> list[dict]:
    """
    Walk every grade × trim_id in fsoData and return a list of record dicts.
    Missing fields are explicitly set to null (None) — never fabricated.
    """
    price_grades = fso_data.get(SECTION_PRICE, {}).get("grades", {})
    records: list[dict] = []

    for grade_key, grade_data in price_grades.items():
        trim_name = grade_key_to_trim_name(grade_key, series)
        trims     = grade_data.get("trims", {})

        for trim_id in trims:
            def section_features(section: str) -> dict[str, dict]:
                return build_feature_map(
                    fso_data
                    .get(section, {})
                    .get("grades", {})
                    .get(grade_key, {})
                    .get("trims", {})
                    .get(trim_id)
                )

            price_f  = section_features(SECTION_PRICE)
            mech_f   = section_features(SECTION_MECHANICAL)
            dim_f    = section_features(SECTION_DIMENSIONS)
            weight_f = section_features(SECTION_WEIGHTS)

            hp = or_null(
                _get_feature_value(
                    mech_f,
                    "Hybrid System Net Horsepower",
                    "Net Horsepower",
                    "Horsepower",
                    "i-FORCE MAX Horsepower",
                )
                or get_hp_from_label(mech_f)
            )

            record: dict = {
                "year":             or_null(year),
                "make":             make,
                "model":            or_null(model),
                "trim":             trim_name,
                "trim_id":          trim_id,
                "base_msrp":        or_null(_get_feature_value(price_f,  "Base MSRP")),
                "fuel_type":        infer_fuel_type(mech_f),
                "horsepower":       hp,
                "drivetrain":       get_standard_drivetrain(mech_f),
                "seating_capacity": or_null(_get_feature_value(weight_f, "Seating")),
                "dimensions": {
                    "overall_length": or_null(_get_feature_value(dim_f, "Overall length")),
                    "overall_width":  or_null(_get_feature_value(dim_f, "Overall width")),
                    "overall_height": or_null(_get_feature_value(dim_f, "Overall height")),
                    "wheelbase":      or_null(_get_feature_value(dim_f, "Wheelbase")),
                },
            }
            records.append(record)

    records.sort(key=lambda r: (r["trim"], r["drivetrain"] or "", r["trim_id"]))
    return records


def parse_html_file(html_path: Path, series: str) -> list[dict]:
    """Read a saved HTML file and return its list of trim records."""
    html = html_path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")

    year, make, model = parse_vehicle_metadata(soup)
    fso_data          = extract_fso_data(html)

    return extract_trim_records(fso_data, year, make, model, series)


def _msrp_as_float(record: dict) -> float:
    """
    Parse base_msrp to a float for comparison.
    Records with a null or unparseable MSRP sort to the end (infinity).
    """
    raw = record.get("base_msrp")
    if not raw:
        return float("inf")
    try:
        return float(raw.replace("$", "").replace(",", "").strip())
    except ValueError:
        return float("inf")


def build_base_output(all_records: list[dict]) -> list[dict]:
    """
    Collapse all_records to one row per (model, trim) by keeping whichever
    variant has the lowest base_msrp.  All fields of that winning row are
    preserved in full — nothing is dropped or fabricated.
    """
    best: dict[tuple, dict] = {}

    for record in all_records:
        key = (record.get("model"), record.get("trim"))
        if key not in best or _msrp_as_float(record) < _msrp_as_float(best[key]):
            best[key] = record

    # Restore the same sort order as the detailed output
    result = list(best.values())
    result.sort(key=lambda r: (r.get("model") or "", r.get("trim") or ""))
    return result


def parse_all_models(saved_paths: dict[str, Path]) -> list[dict]:
    """
    Parse every saved HTML file, aggregate all records, and write both outputs:
      - detailed_trims.json  — every variant, nothing dropped
      - base_output.json     — one row per (model, trim) using the min-MSRP variant
    """
    all_records: list[dict] = []

    for series, html_path in saved_paths.items():
        print(f"[Part 2] Parsing {series} …", end=" ", flush=True)
        try:
            records = parse_html_file(html_path, series)
            print(f"{len(records)} trims extracted.")
            all_records.extend(records)
        except (ValueError, KeyError) as exc:
            print(f"ERROR — {exc}", file=sys.stderr)

    # Write detailed output (all variants)
    DETAILED_JSON.write_text(json.dumps(all_records, indent=2), encoding="utf-8")
    print(f"\n[Part 2] detailed_trims.json → {len(all_records)} records → {DETAILED_JSON.resolve()}")

    # Write base output (one row per model+trim, lowest MSRP wins)
    base_records = build_base_output(all_records)
    BASE_JSON.write_text(json.dumps(base_records, indent=2), encoding="utf-8")
    print(f"[Part 2] base_output.json   → {len(base_records)} records → {BASE_JSON.resolve()}\n")

    return all_records


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  PART 3 — VALIDATION                                                         ║
# ║  Runs plausibility checks on every record and prints a report.               ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# Plausible ranges (inclusive) for numeric fields
MSRP_MIN       =  15_000   # USD
MSRP_MAX       = 120_000
HP_MIN         =      80   # hp
HP_MAX         =     700
SEATING_MIN    =       2
SEATING_MAX    =       9
LENGTH_MIN     =   150.0   # inches
LENGTH_MAX     =   280.0
WIDTH_MIN      =    60.0
WIDTH_MAX      =    90.0
HEIGHT_MIN     =    48.0
HEIGHT_MAX     =     90.0
WHEELBASE_MIN  =    90.0
WHEELBASE_MAX  =   160.0

VALID_FUEL_TYPES  = {"Gas", "Hybrid", "PHEV", "EV", "Hydrogen"}
VALID_DRIVETRAINS = {"FWD", "AWD", "4WD", "RWD"}


def _parse_msrp(value: str) -> float | None:
    """Strip '$' and commas, return float or None."""
    try:
        return float(value.replace("$", "").replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def _parse_numeric(value: str | None) -> float | None:
    """Extract the first numeric token from a value string."""
    if value is None:
        return None
    match = re.search(r"[\d,]+\.?\d*", value.replace(",", ""))
    if match:
        try:
            return float(match.group().replace(",", ""))
        except ValueError:
            return None
    return None


def validate_records(records: list[dict]) -> None:
    """
    Run sanity checks on every record and print a summary.
    Checks:
      - Required fields are not null
      - MSRP and HP are within plausible ranges
      - Fuel type and drivetrain are known values
      - Dimensions fall within plausible ranges
    """
    print("=" * 70)
    print("[Part 3] VALIDATION REPORT")
    print("=" * 70)

    issues_found = 0

    for rec in records:
        label = f"{rec.get('year')} Toyota {rec.get('model')} {rec.get('trim')} (id={rec.get('trim_id')})"
        rec_issues: list[str] = []

        # ── Required fields presence ─────────────────────────────────────────
        for field in ("year", "model", "trim", "base_msrp", "fuel_type", "drivetrain"):
            if rec.get(field) is None:
                rec_issues.append(f"'{field}' is null")

        # ── MSRP range ───────────────────────────────────────────────────────
        msrp_raw = rec.get("base_msrp")
        if msrp_raw is not None:
            msrp = _parse_msrp(msrp_raw)
            if msrp is None:
                rec_issues.append(f"base_msrp not parseable: {msrp_raw!r}")
            elif not (MSRP_MIN <= msrp <= MSRP_MAX):
                rec_issues.append(f"base_msrp out of range: ${msrp:,.0f}")

        # ── Horsepower range ─────────────────────────────────────────────────
        hp_raw = rec.get("horsepower")
        if hp_raw is not None:
            hp = _parse_numeric(hp_raw)
            if hp is None:
                rec_issues.append(f"horsepower not parseable: {hp_raw!r}")
            elif not (HP_MIN <= hp <= HP_MAX):
                rec_issues.append(f"horsepower out of range: {hp}")

        # ── Fuel type ────────────────────────────────────────────────────────
        fuel = rec.get("fuel_type")
        if fuel is not None and fuel not in VALID_FUEL_TYPES:
            rec_issues.append(f"unknown fuel_type: {fuel!r}")

        # ── Drivetrain ───────────────────────────────────────────────────────
        dt = rec.get("drivetrain")
        if dt is not None and dt not in VALID_DRIVETRAINS:
            rec_issues.append(f"unknown drivetrain: {dt!r}")

        # ── Seating ──────────────────────────────────────────────────────────
        seat_raw = rec.get("seating_capacity")
        if seat_raw is not None:
            seat = _parse_numeric(seat_raw)
            if seat is not None and not (SEATING_MIN <= seat <= SEATING_MAX):
                rec_issues.append(f"seating_capacity out of range: {seat}")

        # ── Dimensions ───────────────────────────────────────────────────────
        dims = rec.get("dimensions", {})
        dim_checks = [
            ("overall_length", LENGTH_MIN,    LENGTH_MAX),
            ("overall_width",  WIDTH_MIN,     WIDTH_MAX),
            ("overall_height", HEIGHT_MIN,    HEIGHT_MAX),
            ("wheelbase",      WHEELBASE_MIN, WHEELBASE_MAX),
        ]
        for dim_key, lo, hi in dim_checks:
            raw = dims.get(dim_key)
            if raw is not None:
                val = _parse_numeric(raw)
                if val is not None and not (lo <= val <= hi):
                    rec_issues.append(f"{dim_key} out of range: {val}")

        if rec_issues:
            issues_found += len(rec_issues)
            print(f"\n  ✗ {label}")
            for issue in rec_issues:
                print(f"      • {issue}")

    print()
    if issues_found == 0:
        print(f"  All {len(records)} records passed validation. No issues found.")
    else:
        print(f"  {issues_found} issue(s) found across {len(records)} records.")
    print("=" * 70)


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  ENTRY POINT                                                                 ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def main() -> int:
    print("\n── PART 1: Scraping HTML ──────────────────────────────────────────────\n")
    saved_paths = scrape_all_models(throttle_seconds=1.0)

    if not saved_paths:
        print("No HTML pages were fetched or cached. Aborting.", file=sys.stderr)
        return 1

    print("\n── PART 2: Parsing into JSON (detailed_trims + base_output) ──────────\n")
    all_records  = parse_all_models(saved_paths)
    base_records = build_base_output(all_records)

    print("── PART 3: Validation ─────────────────────────────────────────────────\n")
    print("Validating detailed_trims.json …")
    validate_records(all_records)
    print("\nValidating base_output.json …")
    validate_records(base_records)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
