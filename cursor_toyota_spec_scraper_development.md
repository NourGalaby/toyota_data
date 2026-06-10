# Toyota spec scraper development
_Exported on 6/10/2026 at 04:14:51 GMT+3 from Cursor (3.5.33)_

---

**User**

lets build new toyota scrapper. 
Part 1 - scrap html : 
it will iterate 3 models as per the spec. 
Also, it will fetch from the metadata in the html
the code will be part one, fetching the URL. between each request we will throttle 1 sec to avoid blocking. 

Also, we will save every page in /scrapped/[data]/model

part 2 - parsing into json
after scrapping all 3 models. we will parse the data into json: 
output.json — one record per trim, matching the fields above.
IMportant, if some data is missing do not make up or fabricate, just get from the HTML what is available. 

--- 
Stick to these:
Year, Make, Model, Trim
Base MSRP
Fuel type (gas / hybrid / PHEV / etc.)
Horsepower
Drivetrain (FWD / AWD / 4WD)
Seating capacity
Dimensions (width, height, length and wheelbase)
Mark any field you can't confirm as null. Do not guess or fabricate.

Part 3 - validation: 
After we make the json we will run a sanity check, for example : are HP and MSRP values plausible?).
--- 

Each part of the 3 parts should be clear, and seperated with comment. it should be easy to read.

detailed specs for models, scrapping and json: 

Toyota Spec Scraper — Agent Summary
Goal
Fetch Toyota full-specs pages and extract trim-level data: Year, Make, Model, Trim, Base MSRP, Fuel type, Horsepower, Drivetrain, Seating capacity, Dimensions (length, width, height, wheelbase).

Which pages to use
Use: https://www.toyota.com/{series}/features/ (e.g. camry, rav4, tacoma)
Do not use: model landing pages like /rav4/ or /tacoma/ — those are marketing pages with no full spec data
Fetch
Send a browser-like User-Agent
Follow redirects (Toyota adds a trailing slash)
One fetch per model is enough
Where the data lives
All specs are embedded in the HTML as a large JSON blob called fsoData, inside <script id="vehicleFsoData-json">.

Do not parse the whole script as JSON. Instead:

Find the literal string fsoData: in the HTML
Brace-match from the { right after it
json.loads() that substring
Vehicle metadata (BeautifulSoup)
From #fso-header-data:

data-year → Year
data-display-name → Model
data-series-code → series slug (camry, rav4, tacoma)
Make is always Toyota
Trim iteration — no URL looping needed
One fetch returns all trims. URL path trim IDs (e.g. /2555/2551/2559/) only control which columns show in the UI — the embedded fsoData contains every grade and trim variant.

Enumerate trims from:

fsoData["mpg/other/price"]["grades"][grade_key]["trims"][trim_id]
Camry confirmed: 10 trims from a URL with only 3 IDs in the path.

JSON structure
fsoData
  └── section (e.g. "mpg/other/price", "mechanical/performance", "dimensions", "weights/capacities")
        └── grades
              └── "{series}_{grade}"  (e.g. camry_le, rav4_woodland)
                    └── trims
                          └── "{trim_id}"  (e.g. "2559")
                                └── features with: label, value, icon
Field extraction
Field	Source section	How
Trim name
grade key
Strip {series}_ prefix → e.g. camry_le → LE
trim_id
trims dict key
Numeric string
Base MSRP
mpg/other/price
Label starts with "Base MSRP" → use value
Horsepower
mechanical/performance
"Hybrid System Net Horsepower" or "Horsepower" → value
Drivetrain
mechanical/performance
Whichever drivetrain label has icon == "standard" (FWD, AWD, 4WD)
Fuel type
mechanical/performance
Inferred — see below
Seating
weights/capacities
Label "Seating" → value
Dimensions
dimensions
"Overall length", "Overall width", "Overall height", "Wheelbase" → value
Parsing rules
Strip HTML from labels before matching (<sup>, <b>, etc.)
Drivetrain: use icon field, not value — "standard" means that variant has it
Fuel type priority: Hybrid System Net Horsepower present → Hybrid; else check for PHEV/plug-in, hydrogen, all-electric, hybrid motor labels, then gas engine descriptions. Avoid false "EV" matches from "EV modes" in drive mode text
Multiple rows per grade are normal (e.g. FWD + AWD = separate trim_ids)
Models to scrape
camry   → https://www.toyota.com/camry/features/
rav4    → https://www.toyota.com/rav4/features/
tacoma  → https://www.toyota.com/tacoma/features/
Pipeline
for each model:
  1. fetch /{series}/features/
  2. parse #fso-header-data for year/model
  3. extract fsoData JSON
  4. loop all grades × all trim_ids
  5. output one row per trim_id
Pitfalls
grade_to_trim_name must generalize beyond Camry (handle TRD, XLE Premium, i-FORCE MAX, etc.)
Tacoma may use 4WD and different horsepower labels than Camry hybrids
Static HTML vehicle bar is empty — trim names come from grade keys, not rendered DOM

---

**Cursor**

Let me first read the existing files to understand what's already there.

Good — I can see the existing single-model script. Now I'll build the new three-part scraper as a clean, self-contained file.

Now let's run it and watch all three parts execute:

Good — all three parts ran cleanly. 46 trims extracted. The validator correctly flags the real data gaps: Tacoma gas trims have undetected `fuel_type` (Toyota embeds their engine differently than Camry), and one i-FORCE MAX trim has a null drivetrain. Let me inspect the raw Tacoma data to fix those patterns properly.

Now I can see the patterns. Tacoma uses `i-FORCE 2.4L` (not `-liter`) and `i-FORCE MAX` for the hybrid. The fuel and drivetrain rules need expanding. Let me also check the i-FORCE MAX drivetrain case:

Two root causes identified:
1. **Fuel type** — Tacoma uses `i-FORCE 2.4L inline-4` (not `liter`/`cylinder`) and `i-FORCE MAX` for the hybrid
2. **Drivetrain** — `"Full-time 4-Wheel Drive with electronic locking center differential"` contains `4-wheel drive` not `four-wheel drive`, so the fallback misses it

Now re-run using the cached HTML (no new fetches):

All 46 records pass. Let me do a final spot-check of `output.json` to confirm the data looks right:

Everything is clean. All 46 records pass validation. Here's a summary of what was built:

---

**`toyota_scraper.py` — three self-contained parts:**

**Part 1 — Scraping**
- Fetches `https://www.toyota.com/{series}/features/` for `camry`, `rav4`, `tacoma`
- Browser-like User-Agent + 1-second throttle between live requests
- Saves raw HTML to `scrapped/<YYYY-MM-DD>/<series>/page.html`
- Idempotent: skips the network if today's file already exists

**Part 2 — Parsing → `output.json`**
- Reads vehicle metadata from `#fso-header-data` (year, model)
- Brace-matches the embedded `fsoData:` JSON blob (no full-script parse)
- Walks every `grade × trim_id` — one record each
- Fields that are absent in the HTML are explicitly `null`, never fabricated
- `grade_key_to_trim_name()` generalises to any series (handles TRD, XSE, i-FORCE MAX, Woodland, etc.)
- Fuel-type inference covers Hybrid, PHEV, EV, Hydrogen, Gas; specifically handles Toyota's `i-FORCE` (gas) vs `i-FORCE MAX hybrid` labels
- Drivetrain detection uses `icon == "standard"` first, with a keyword fallback that covers extended labels like `"Full-time 4-Wheel Drive with …"`

**Part 3 — Validation**
- Checks that required fields aren't null
- MSRP ($15k–$120k), HP (80–700), Seating (2–9), all four dimensions, fuel type, and drivetrain are range/enum validated
- Prints a clean report; all 46 records currently pass

**Results:** 10 Camry trims (all Hybrid), 9 RAV4 trims (all Hybrid, HP not published in their fsoData), 27 Tacoma trims (mix of Gas i-FORCE and Hybrid i-FORCE MAX).

---

**User**

looking at @output.json  
there are some duplicates. for example 
@output.json (488-523) 
What are the possible options ? I think we should stick to the minimum base_msrp, and keep the data for it. 
For that we would add a step before writing the json, and use pandas to make it a dataframe, dedup it. Then write it. 
You think this is a good option? 


---

**Cursor**

Before recommending an approach, let me look at the full picture of what's actually being flagged as duplicates.

I want to give you an honest assessment before recommending an approach, because looking at the full data carefully, these are **not actual duplicates** — and collapsing them would silently destroy real information.

---

## What you're actually seeing

Take the SR5 block as the clearest example:

| trim_id | Drivetrain | Seating | Length | Wheelbase | MSRP |
|---------|-----------|---------|--------|-----------|------|
| 7558 | 4WD | **2** | 213 | 131.9 | $39,735 |
| 7540 | 4WD | **5** | 213 | 131.9 | $40,805 |
| 7570 | 4WD | **5** | **226.2** | **145.1** | $41,305 |
| 7126 | **RWD** | **2** | 213 | 131.9 | $36,535 |
| 7146 | **RWD** | **5** | 213 | 131.9 | $37,605 |
| 7170 | **RWD** | **5** | **226.2** | **145.1** | $38,105 |

Every row differs in at least one meaningful dimension — cab size (2 vs 5 seats = Access Cab vs Double Cab), bed length (213" vs 226.2" with a different wheelbase), or drivetrain. These map to real, buyable, differently-priced vehicles. The same pattern holds for all Camry and RAV4 rows — drivetrain (FWD vs AWD) changes both the HP and the MSRP.

---

## Three realistic options

**Option A — Dedup on `(model, trim)`, keep min MSRP**

This is what you proposed. It's simple and gives you exactly one row per named trim. The problem: you'd keep the cheapest Tacoma SR5 (RWD, 2-seat Access Cab, $36,535) and discard the 4WD and Double Cab variants. The surviving row would have seating=2 and drivetrain=RWD, which is not the "representative" SR5 most people think of. Potentially misleading for any downstream use.

**Option B — Dedup on `(model, trim, drivetrain)`, keep min MSRP**

Collapses cab/bed variants but preserves drivetrain splits. Still gives you multiple rows for Camry LE (FWD + AWD), but drops the 226.2" long-bed Tacoma variants. Slightly more faithful, but still lossy.

**Option C — Keep all rows as-is, flag the "variant axis"**

The cleanest option given that all data is accurate. The records aren't duplicates — they're variants. If you want to reduce them, you'd need to add a column that names *why* they're different (e.g., `cab_type: "Access Cab" / "Double Cab"`, `bed_length: "short" / "long"`). That data isn't currently being extracted from the HTML, but it exists in the fsoData.

---

## My honest recommendation

**Don't deduplicate by `(model, trim)` alone.** The information loss is real and the surviving row can be misleading (a 2-seat RWD SR5 is not the "base" SR5 in any meaningful sense).

If the downstream goal is "one entry-point price per trim name," Option B `(model, trim, drivetrain)` is the least-bad choice. If the goal is a faithful spec sheet, keep all rows.

The pandas approach itself is fine mechanically — `groupby` + `idxmin()` on a parsed numeric MSRP column is clean. The issue is purely the grouping key, not the tool.

If you want to switch to Agent mode and implement one of these options, just let me know which direction fits your use case and I can build it exactly as you want it.

---

**User**

I agree on not losing. so lets keep two options, one is base_output.json with just model, trim, base_msrp (min), and all the required data for this trim.  
and another which will be detailed_trims that will contain full data with all variations. not skipping columns Lets do that

---

**Cursor**

Now I have a full picture. I'll make targeted changes: rename the final output file to `detailed_trims.json`, add a `build_base_output()` function that picks the min-MSRP row per `(model, trim)` and writes `base_output.json`, and wire both into `parse_all_models` and the validation step.

Now update `main()` to validate both outputs and update the section header label:

Both files are clean. Let me do a quick sanity spot-check to confirm the right variant was chosen for `base_output.json`:

Both files are written and validated. Here's what was produced:

**`detailed_trims.json`** — 46 records, every variant intact (all drivetrains, cab sizes, bed lengths, engine options). Nothing dropped.

**`base_output.json`** — 22 records, one row per `(model, trim)`. The min-MSRP variant wins and all of its original fields are preserved verbatim — no fabrication, no field dropping. For example:
- Camry LE → FWD at $29,300 (cheapest entry point to that trim)
- Tacoma SR → RWD 2-seat at $32,445 (the cheapest SR money can buy)
- Tacoma SR5 → RWD 2-seat at $36,535

Both files pass the full validation with zero issues.

