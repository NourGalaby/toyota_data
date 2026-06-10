# Python script for fetching HTML
_Exported on 6/10/2026 at 04:15:01 GMT+3 from Cursor (3.5.33)_

---

**User**

lets write a python script to get 
https://www.toyota.com/camry/features/mpg_other_price/2555/2551/2559 

and save it as html 

---

**Cursor**

I'll check the workspace and fetch that Toyota page to see what headers or setup the script needs.


The page loads with a browser User-Agent. I'll add a small Python script and verify it saves the HTML.


Created `fetch_toyota.py` in your Toyota folder. It fetches the page and saves the raw HTML.

**Run it:**
```bash
python3 fetch_toyota.py
```

That writes `camry_mpg_other_price.html` (~1 MB). I verified it works against the live page.

**Options:**
```bash
python3 fetch_toyota.py --url "https://www.toyota.com/camry/features/mpg_other_price/2555/2551/2559" -o output.html
```

The script uses Python’s standard library only (no extra packages). It sends a browser-like User-Agent and follows redirects (Toyota adds a trailing slash).

---

**User**

lets extract the following for each trim available in the html, in the same script: it should read from the html using BeautifulSoup

Year, Make, Model, Trim
Base MSRP
Fuel type (gas / hybrid / PHEV / etc.)
Horsepower
Drivetrain (FWD / AWD / 4WD)
Seating capacity
Dimensions (width, height, length and wheelbase)

---

**Cursor**

I'll inspect the saved HTML structure first so we can map where trim specs live before extending the script with BeautifulSoup parsing.


I have the data layout: trim specs live in embedded `fsoData` JSON. I'll extend the script with BeautifulSoup parsing and add a requirements file.


Fuel type was misclassified because "EV modes" matched the EV check — I'll tighten that logic.


Updated `fetch_toyota.py` to fetch the page, parse it with BeautifulSoup, and extract trim specs from the embedded `fsoData` JSON in the HTML.

**How it works**

Toyota embeds all trim specs in a large `fsoData` JSON blob inside the page. The script:

1. Uses BeautifulSoup to read vehicle metadata (`year`, `make`, `model`) from `#fso-header-data`
2. Extracts and parses the `fsoData` JSON
3. Loops over every grade/trim and pulls the requested fields
4. Writes results to `camry_trims.csv` and prints JSON to stdout

**Run it**

```bash
pip install -r requirements.txt

# Fetch fresh HTML + extract
python3 fetch_toyota.py

# Or parse the saved HTML only
python3 fetch_toyota.py --parse-only
```

**Extracted fields (10 trims found)**

| Field | Source |
|---|---|
| Year, Make, Model | `#fso-header-data` attributes |
| Trim | Grade key (LE, SE, XLE, XSE, Nightshade) |
| Base MSRP | `mpg/other/price` section |
| Fuel type | Inferred from mechanical specs (all 2026 Camry trims → Hybrid) |
| Horsepower | `Hybrid System Net Horsepower` |
| Drivetrain | FWD or AWD based on which drivetrain is marked `standard` |
| Seating capacity | `weights/capacities` → Seating |
| Dimensions | `dimensions` → length, width, height, wheelbase |

Example output for LE FWD:

```json
{
  "year": "2026",
  "make": "Toyota",
  "model": "Camry",
  "trim": "LE",
  "base_msrp": "$29,300",
  "fuel_type": "Hybrid",
  "horsepower": "225",
  "drivetrain": "FWD",
  "seating_capacity": "5",
  "overall_length": "193.5",
  "overall_width": "72.4",
  "overall_height": "56.9",
  "wheelbase": "111.2"
}
```

Each grade has two variants (FWD and AWD), so you get 10 rows total. Results are saved to `camry_trims.csv`.

---

**User**

now that we confirmed it is working, please write down the patterns you learned to extract. 
Also, we need to iterate over all trims. The current url have 3 trims. so we need to do at least 6 trims per each model. 

for example https://www.toyota.com/camry/features/mpg_other_price/2555/2551/2559/ 
have the trims 2555/2551/2559
we can also try to get 2552/2553/2554. 
We keep trying till we get at least 6. if we get more we also keep them. 


also, we will iterate over 2 more models rav4, and tacoma which are at: 
https://www.toyota.com/rav4/ 
https://www.toyota.com/tacoma/ 

now lets paste all patterns learned. which will be used by another agent to build the system 

---

**Cursor**

Reviewing the script and HTML structure to document extraction patterns and trim-iteration logic for the other agent.


# Toyota.com Trim Spec Extraction — Patterns & System Design Notes

Documentation for building a multi-model scraper (Camry, RAV4, Tacoma). Based on confirmed working extraction from [2026 Camry specs](https://www.toyota.com/camry/features/mpg_other_price/2555/2551/2559/).

---

## 1. Page Types (Critical Distinction)

| Page type | Example URL | Has extractable `fsoData`? |
|---|---|---|
| **Marketing / MLP** | `https://www.toyota.com/rav4/` | **No** — trim cards are static HTML, no full spec matrix |
| **Full Specs (FSO)** | `https://www.toyota.com/camry/features/mpg_other_price/2555/2551/2559/` | **Yes** — all spec data lives here |

**Rule:** Always target `/{series}/features/...`, never the model landing page.

---

## 2. URL Patterns

### Base specs URL
```
https://www.toyota.com/{series}/features/
```

### Deep-link with comparison trim IDs (optional path segments)
```
https://www.toyota.com/{series}/features/mpg_other_price/{trim_id_1}/{trim_id_2}/{trim_id_3}/
```

**Examples:**
- Camry: `https://www.toyota.com/camry/features/mpg_other_price/2555/2551/2559/`
- RAV4 (expected): `https://www.toyota.com/rav4/features/mpg_other_price/{ids}/`
- Tacoma (expected): `https://www.toyota.com/tacoma/features/mpg_other_price/{ids}/`

### URL behavior
- Server **301-redirects** to add trailing slash — follow redirects.
- Requires a **browser User-Agent** or the response may be blocked/empty.
- Response size ~1 MB HTML.

### What URL trim IDs actually control
From confirmed Camry extraction:

| Source | Value | Meaning |
|---|---|---|
| URL path | `2555/2551/2559` | 3 trims selected for the **comparison UI columns** |
| `#fso-header-data` → `data-default-trims` | `2555,2551,2556` | Default comparison trim set (may differ slightly from URL) |
| `#fso-header-data` → `data-trims` | `17` | Total trim configurations in Toyota's system for this model |
| **`fsoData` JSON embedded in HTML** | **10 trim IDs** | **Complete spec data for all grades/variants** |

**Key finding:** A single fetch of the Camry URL with 3 trim IDs in the path still returned **all 10 trims** inside `fsoData`. URL trim IDs appear to control UI column selection, not what data is embedded.

**Confirmed Camry trim IDs (all found in one page):**
```
2551, 2552, 2553, 2555, 2556, 2557, 2558, 2559, 2560, 2561
```

Grades × drivetrain variants:
| Grade | FWD trim_id | AWD trim_id |
|---|---|---|
| LE | 2559 | 2552 |
| Nightshade | 2558 | 2551 |
| SE | 2561 | 2553 |
| XLE | 2560 | 2555 |
| XSE | 2557 | 2556 |

---

## 3. HTTP Fetch Pattern

```python
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ...",
    "Accept": "text/html,application/xhtml+xml,...",
    "Accept-Language": "en-US,en;q=0.9",
}
# Follow redirects, timeout ~30s
```

---

## 4. HTML Parsing Entry Points (BeautifulSoup)

### 4a. Vehicle metadata — `#fso-header-data`

```html
<div id="fso-header-data"
     data-series-code="camry"
     data-series-name="camry"
     data-year="2026"
     data-display-name="Camry"
     data-default-trims="2555,2551,2556"
     data-trims="17"
     ...>
```

| Attribute | Use |
|---|---|
| `data-year` | Year (e.g. `2026`) |
| `data-display-name` | Model name (e.g. `Camry`) |
| `data-series-code` | URL slug (e.g. `camry`, `rav4`, `tacoma`) |
| `data-default-trims` | Comma-separated trim IDs — good **seed list** for URL construction |
| `data-trims` | Total trim count hint |

Make is always **Toyota**. Fallback: parse `<title>` with regex `(\d{4})\s+Toyota\s+(\w+)`.

### 4b. Spec data — `fsoData` inside `script#vehicleFsoData-json`

Located inside:
```html
<script id="vehicleFsoData-json">
window.__PRELOADED_STATE__ = JSON.stringify({
   ...
   fsoData:{ ... massive JSON ... },
   nextsteps: { ... },
   ...
});
</script>
```

**Important:** `fsoData` is **raw JSON embedded directly** in the JS object — it is NOT a quoted/escaped string. Do not parse the whole `__PRELOADED_STATE__` as JSON; instead:

1. Find the literal marker `fsoData:` in the HTML string.
2. Start at the `{` immediately after it.
3. Use **brace-depth counting** to find the matching closing `}`.
4. `json.loads()` that substring.

---

## 5. `fsoData` JSON Structure

```
fsoData
├── "mpg/other/price"              ← MSRP, mileage
├── "safety/convenience"
├── "exterior"
├── "interior"
├── "audio_multimedia"
├── "connected_services"
├── "mechanical/performance"       ← drivetrain, engine, horsepower
├── "dimensions"                   ← length, width, height, wheelbase
├── "weights/capacities"           ← seating capacity
├── "tires"
├── "packages"
├── "options"
└── "warranty_information [warranty_general]"
```

Each section:
```json
{
  "grades": {
    "{series}_{grade_key}": {
      "image": "/content/common/img/jellies/fso/2026/camry/camry_xle.png",
      "trims": {
        "{trim_id}": {
          "{feature_key}": {
            "featureCode": "...",
            "label": "Base MSRP <sup ...>",
            "value": "$34,500",
            "icon": "false",
            "labeldescription": "",
            "valuedescription": ""
          }
        }
      }
    }
  }
}
```

### Grade keys (Camry confirmed)
```
camry_le, camry_se, camry_xle, camry_xse, camry_nightshade
```

**Generalization pattern:** `{series_code}_{grade_slug}` — strip the `{series_code}_` prefix to get the trim/grade display name.

Expected RAV4 grades (from marketing page): LE, SE, XLE Premium, Woodland, XSE, Limited  
Expected Tacoma grades: SR, SR5, TRD PreRunner, TRD Sport, TRD Off-Road, Limited, TRD Sport i-FORCE MAX, TRD Off-Road i-FORCE MAX, Limited i-FORCE MAX, Trailhunter, TRD Pro

---

## 6. Feature Object Semantics

Each feature has:

| Field | Meaning |
|---|---|
| `label` | Display name — often contains HTML (`<sup>`, `<b>`) — **strip tags before matching** |
| `value` | Text value when present (e.g. `"$29,300"`, `"225"`, `"193.5"`) |
| `icon` | Availability flag for checkbox-style features |

### `icon` values (critical for drivetrain)
| `icon` value | Meaning |
|---|---|
| `"standard"` | Standard on **this specific trim variant** |
| `"available"` | Optional / package |
| `"not-available"` | Not on this variant |
| `"false"` | Section header or plain text field (use `value` instead) |

**Drivetrain extraction:** Find which drivetrain label has `icon == "standard"`.

---

## 7. Field → Source Mapping

| Output field | Section | Label match | Extraction logic |
|---|---|---|---|
| **Year** | `#fso-header-data` | `data-year` | Direct attribute |
| **Make** | — | — | Always `"Toyota"` |
| **Model** | `#fso-header-data` | `data-display-name` | Direct attribute |
| **Trim** | grade key | — | Strip `{series}_` prefix from grade key; title-case (see naming rules below) |
| **trim_id** | grade → trims | dict key | The numeric trim ID string (e.g. `"2559"`) |
| **Base MSRP** | `mpg/other/price` | label starts with `"Base MSRP"` | Use `value` (e.g. `"$29,300"`) |
| **Horsepower** | `mechanical/performance` | `"Hybrid System Net Horsepower"`, `"Net Horsepower"`, or `"Horsepower"` | Use `value` |
| **Drivetrain** | `mechanical/performance` | See drivetrain labels below | Whichever has `icon == "standard"` |
| **Fuel type** | `mechanical/performance` | Inferred | See fuel type rules below |
| **Seating capacity** | `weights/capacities` | `"Seating"` | Use `value` |
| **Overall length** | `dimensions` | `"Overall length"` | Use `value` |
| **Overall width** | `dimensions` | `"Overall width"` | Use `value` |
| **Overall height** | `dimensions` | `"Overall height"` | Use `value` |
| **Wheelbase** | `dimensions` | `"Wheelbase"` | Use `value` |

### Drivetrain label → abbreviation map
```
"Front-Wheel Drive (FWD)"                          → FWD
"Electronic On-Demand All-Wheel Drive (AWD)"       → AWD
"All-Wheel Drive (AWD)"                            → AWD
"Four-Wheel Drive (4WD)"                           → 4WD
"Rear-Wheel Drive (RWD)"                           → RWD
```

### Fuel type inference (priority order)
1. If `"Hybrid System Net Horsepower"` has a `value` → **Hybrid**
2. If any standard feature label contains `"plug-in"` or `"phev"` → **PHEV**
3. If label contains `"fuel cell"` or `"hydrogen"` → **Hydrogen**
4. If label contains `"battery electric"` or `"all-electric"` → **EV**
5. If label contains `"hybrid"`, `"electric motor"`, or `"permanent magnet"` + `"motor"` → **Hybrid**
6. If standard feature matches `\d+-liter` or `\d+-cylinder` engine description → **Gas**
7. Else → empty string

**Pitfall:** Do NOT match `\bev\b` broadly — `"Drive Mode Select ... EV modes"` is not an EV powertrain.

### Trim name formatting rules
```
camry_le         → LE
camry_se         → SE
camry_xle        → XLE
camry_xse        → XSE
camry_nightshade → Nightshade
rav4_xle_premium → XLE Premium   (generalize: split on _, title-case)
tacoma_trd_pro   → TRD Pro
```

Special-case known acronyms: LE, SE, XLE, XSE, TRD, SR, SR5 → preserve casing.

---

## 8. Iteration Strategy — Getting All Trims (≥ 6 per model)

### Primary strategy (recommended — confirmed working)
```
1. Fetch  /{series}/features/  OR  /{series}/features/mpg_other_price/{default_trim_ids}/
2. Parse fsoData
3. Enumerate ALL trim IDs from:
     fsoData["mpg/other/price"]["grades"][*]["trims"].keys()
4. For each (grade_key, trim_id) pair, extract specs from all 4 sections
5. Deduplicate by trim_id
```

This alone gave **10 trims for Camry** from a URL with only 3 IDs in the path.

### Fallback / expansion strategy (if primary returns < 6)
Use when `fsoData` appears filtered by URL (not yet confirmed for RAV4/Tacoma):

```
1. Parse data-default-trims from #fso-header-data → seed_ids
2. Fetch page with seed_ids in URL path
3. Collect trim_ids found in fsoData
4. If count < 6:
     a. Generate candidate ID sets (e.g. seed ± nearby IDs like 2552/2553/2554)
     b. Fetch each candidate URL
     c. Merge all discovered trim_ids (union)
     d. Stop when unique trim_id count >= 6 OR no new IDs found after N attempts
5. Keep all trims found, not just 6
```

### URL construction for candidate attempts
```python
# Template
base = f"https://www.toyota.com/{series}/features/mpg_other_price"
url  = f"{base}/{'/'.join(trim_id_group)}/"

# Example progression for Camry
attempt_1 = [2555, 2551, 2559]   # default from URL
attempt_2 = [2552, 2553, 2554]     # user-suggested expansion
attempt_3 = data_default_trims   # from HTML header
```

### Trim discovery without guessing IDs
After any successful fetch, **mine all trim IDs directly from `fsoData`** — this is the authoritative source. URL IDs are only needed if the embedded JSON is incomplete.

---

## 9. Multi-Model Loop

```python
MODELS = [
    {"series": "camry",   "seed_url": "https://www.toyota.com/camry/features/mpg_other_price/2555/2551/2559/"},
    {"series": "rav4",    "seed_url": "https://www.toyota.com/rav4/features/"},
    {"series": "tacoma",  "seed_url": "https://www.toyota.com/tacoma/features/"},
]

for model in MODELS:
    html = fetch(model["seed_url"])
    records = parse_html_specs(html)
    if len(records) < 6:
        # run fallback trim ID expansion (section 8)
        ...
    all_records.extend(records)
```

**Do not scrape** `https://www.toyota.com/rav4/` or `https://www.toyota.com/tacoma/` directly for specs — those are marketing pages. Navigate to `/features/` from there or construct the FSO URL directly.

---

## 10. Output Record Schema

```json
{
  "year": "2026",
  "make": "Toyota",
  "model": "Camry",
  "trim": "LE",
  "trim_id": "2559",
  "base_msrp": "$29,300",
  "fuel_type": "Hybrid",
  "horsepower": "225",
  "drivetrain": "FWD",
  "seating_capacity": "5",
  "overall_length": "193.5",
  "overall_width": "72.4",
  "overall_height": "56.9",
  "wheelbase": "111.2"
}
```

Note: Each **grade** may produce **multiple rows** (FWD + AWD variants = separate trim_ids). Camry: 5 grades × 2 drivetrains = 10 rows.

---

## 11. Known Pitfalls

| Issue | Detail |
|---|---|
| `grade_to_trim_name` is Camry-hardcoded | Must generalize to `{series}_` prefix stripping for RAV4/Tacoma |
| Labels contain HTML | Always `re.sub(r'<[^>]+>', '', label)` before matching |
| MSRP label has disclaimer markup | Match by prefix `"Base MSRP"`, not exact string |
| `"EV modes"` false positive | Don't use broad `\bev\b` regex for fuel type |
| `fsoData` is not valid standalone page JSON | Must brace-match from `fsoData:` marker |
| Static HTML vehicle bar is empty | Trim names are NOT in rendered HTML — derive from grade keys |
| Dimensions units not in value | Values are bare numbers (inches, implied) |
| Tacoma may use 4WD not AWD | Include both in drivetrain label map |
| Tacoma hybrid trims | Horsepower label may differ — also check for `"i-FORCE MAX"` patterns and non-hybrid HP labels |

---

## 12. Pseudocode for Extraction Pipeline

```python
def extract_from_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")

    # 1. Metadata
    header = soup.find(id="fso-header-data")
    year   = header["data-year"]
    model  = header["data-display-name"]
    series = header["data-series-code"]
    default_trims = header["data-default-trims"].split(",")

    # 2. fsoData
    fso_data = extract_fso_data(html)  # brace-match after "fsoData:"

    # 3. Iterate all trims
    records = []
    for grade_key, grade_data in fso_data["mpg/other/price"]["grades"].items():
        trim_name = grade_to_trim_name(grade_key, series)
        for trim_id in grade_data["trims"]:
            records.append({
                "year": year, "make": "Toyota", "model": model,
                "trim": trim_name, "trim_id": trim_id,
                "base_msrp":       get_value(fso_data, "mpg/other/price",       grade_key, trim_id, "Base MSRP"),
                "horsepower":      get_value(fso_data, "mechanical/performance", grade_key, trim_id, "Hybrid System Net Horsepower", "Horsepower"),
                "drivetrain":      get_standard_drivetrain(fso_data, grade_key, trim_id),
                "fuel_type":       infer_fuel_type(fso_data, grade_key, trim_id),
                "seating_capacity":get_value(fso_data, "weights/capacities",    grade_key, trim_id, "Seating"),
                "overall_length":  get_value(fso_data, "dimensions",           grade_key, trim_id, "Overall length"),
                "overall_width":   get_value(fso_data, "dimensions",           grade_key, trim_id, "Overall width"),
                "overall_height":  get_value(fso_data, "dimensions",           grade_key, trim_id, "Overall height"),
                "wheelbase":       get_value(fso_data, "dimensions",           grade_key, trim_id, "Wheelbase"),
            })
    return records
```

---

## 13. Validation Checklist for New Models

- [ ] Fetch returns HTTP 200 with ~500KB–1.5MB HTML
- [ ] `fsoData:` marker present in HTML
- [ ] `#fso-header-data` has `data-year`, `data-display-name`, `data-series-code`
- [ ] `fso_data["mpg/other/price"]["grades"]` is non-empty
- [ ] Unique `trim_id` count ≥ 6 (or matches expected model trim count)
- [ ] Each record has non-empty: `base_msrp`, `drivetrain`, `seating_capacity`
- [ ] No fuel_type = `"EV"` on known hybrid-only models (sanity check)

---

## 14. Reference — Confirmed Camry Output (10 trims)

| trim | trim_id | MSRP | HP | drivetrain |
|---|---|---|---|---|
| LE | 2559 | $29,300 | 225 | FWD |
| LE | 2552 | $30,825 | 232 | AWD |
| Nightshade | 2558 | $32,800 | 225 | FWD |
| Nightshade | 2551 | $34,325 | 232 | AWD |
| SE | 2561 | $31,800 | 225 | FWD |
| SE | 2553 | $33,325 | 232 | AWD |
| XLE | 2560 | $34,500 | 225 | FWD |
| XLE | 2555 | $36,025 | 232 | AWD |
| XSE | 2557 | $35,700 | 225 | FWD |
| XSE | 2556 | $37,225 | 232 | AWD |

---

This is the full pattern set. The highest-leverage insight for the next agent: **parse `fsoData` for all trim IDs after one fetch before brute-forcing URL combinations** — Camry already returned 10/10 trims from a 3-ID URL. RAV4 (6 grades) and Tacoma (11 grades) will likely need only one `/features/` fetch each, with Tacoma potentially having more rows due to gas + hybrid variants per grade.

Switch to **Agent mode** if you want this implemented as a multi-model scraper with the ≥6 trim fallback logic built in.

---

**User**

lets summerize this for the agent. since we get all the trims data no need to iterate. 

just AI summery 

---

**Cursor**

# Toyota Spec Scraper — Agent Summary

## Goal
Fetch Toyota full-specs pages and extract trim-level data: Year, Make, Model, Trim, Base MSRP, Fuel type, Horsepower, Drivetrain, Seating capacity, Dimensions (length, width, height, wheelbase).

## Which pages to use
- **Use:** `https://www.toyota.com/{series}/features/` (e.g. camry, rav4, tacoma)
- **Do not use:** model landing pages like `/rav4/` or `/tacoma/` — those are marketing pages with no full spec data

## Fetch
- Send a browser-like User-Agent
- Follow redirects (Toyota adds a trailing slash)
- One fetch per model is enough

## Where the data lives
All specs are embedded in the HTML as a large JSON blob called **`fsoData`**, inside `<script id="vehicleFsoData-json">`.

**Do not** parse the whole script as JSON. Instead:
1. Find the literal string `fsoData:` in the HTML
2. Brace-match from the `{` right after it
3. `json.loads()` that substring

## Vehicle metadata (BeautifulSoup)
From `#fso-header-data`:
- `data-year` → Year
- `data-display-name` → Model
- `data-series-code` → series slug (camry, rav4, tacoma)
- Make is always **Toyota**

## Trim iteration — no URL looping needed
**One fetch returns all trims.** URL path trim IDs (e.g. `/2555/2551/2559/`) only control which columns show in the UI — the embedded `fsoData` contains every grade and trim variant.

Enumerate trims from:
```
fsoData["mpg/other/price"]["grades"][grade_key]["trims"][trim_id]
```

Camry confirmed: **10 trims** from a URL with only 3 IDs in the path.

## JSON structure
```
fsoData
  └── section (e.g. "mpg/other/price", "mechanical/performance", "dimensions", "weights/capacities")
        └── grades
              └── "{series}_{grade}"  (e.g. camry_le, rav4_woodland)
                    └── trims
                          └── "{trim_id}"  (e.g. "2559")
                                └── features with: label, value, icon
```

## Field extraction

| Field | Source section | How |
|---|---|---|
| Trim name | grade key | Strip `{series}_` prefix → e.g. `camry_le` → `LE` |
| trim_id | trims dict key | Numeric string |
| Base MSRP | `mpg/other/price` | Label starts with `"Base MSRP"` → use `value` |
| Horsepower | `mechanical/performance` | `"Hybrid System Net Horsepower"` or `"Horsepower"` → `value` |
| Drivetrain | `mechanical/performance` | Whichever drivetrain label has `icon == "standard"` (FWD, AWD, 4WD) |
| Fuel type | `mechanical/performance` | Inferred — see below |
| Seating | `weights/capacities` | Label `"Seating"` → `value` |
| Dimensions | `dimensions` | `"Overall length"`, `"Overall width"`, `"Overall height"`, `"Wheelbase"` → `value` |

## Parsing rules
- **Strip HTML from labels** before matching (`<sup>`, `<b>`, etc.)
- **Drivetrain:** use `icon` field, not `value` — `"standard"` means that variant has it
- **Fuel type priority:** Hybrid System Net Horsepower present → Hybrid; else check for PHEV/plug-in, hydrogen, all-electric, hybrid motor labels, then gas engine descriptions. Avoid false `"EV"` matches from `"EV modes"` in drive mode text
- **Multiple rows per grade** are normal (e.g. FWD + AWD = separate trim_ids)

## Models to scrape
```
camry   → https://www.toyota.com/camry/features/
rav4    → https://www.toyota.com/rav4/features/
tacoma  → https://www.toyota.com/tacoma/features/
```

## Pipeline
```
for each model:
  1. fetch /{series}/features/
  2. parse #fso-header-data for year/model
  3. extract fsoData JSON
  4. loop all grades × all trim_ids
  5. output one row per trim_id
```

## Pitfalls
- `grade_to_trim_name` must generalize beyond Camry (handle TRD, XLE Premium, i-FORCE MAX, etc.)
- Tacoma may use 4WD and different horsepower labels than Camry hybrids
- Static HTML vehicle bar is empty — trim names come from grade keys, not rendered DOM

