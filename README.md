# Toyota Trim Scraper

Scrapes trim-level specs for **Camry, RAV4, and Tacoma** from Toyota.com and outputs structured JSON.

---

## How to run

```bash
pip install beautifulsoup4
python toyota_scraper.py
```

The script runs in three sequential steps and prints progress for each:

1. **Scrape** — fetches the `/features/` page for each model, saves raw HTML under `scrapped/<YYYY-MM-DD>/<model>/page.html`. Re-runs on the same day reuse the cached HTML (no re-fetch).
2. **Parse** — extracts the embedded `fsoData` JSON blob from each page and writes:
   - `detailed_trims.json` — every variant (46 records across 3 models)
   - `base_output.json` — one record per (model, trim), lowest MSRP variant
3. **Validate** — sanity-checks both files (MSRP range, HP range, known drivetrains/fuel types, dimension bounds).

---

## Sources

I used **toyota.com** because I found it contains all the data, and it is the most reliable for Toyota data. I would trust the official source always more than 3rd parties.

I started by making a simple request to the toyota page to test what data it gets and whether it will have the data I needed. I found that a simple request returns all metadata for trims embedded in the HTML. Specifically, every `/features/` page embeds a large JSON blob called `fsoData` inside a `<script id="vehicleFsoData-json">` tag. One fetch per model returns every grade and trim variant at once; no pagination or extra requests needed. I utilised that. to save every HTML, then parse it into json,csv -> later into our database

---

## How missing data and duplicate trims are handled

**Missing data** — if a field is absent from the HTML, it is written as `null`. Nothing is inferred. The validator flags any required field that comes back null so gaps are visible rather than silent.

**Duplicate trims** —

I was not sure on whether to keep all variations even in one trim ( for example Tacoma Fs4 have different variations with different base_msrp) or to choose one trim as requested in the requirment. So I did both. 

1- I chose one (model, trim) and kept the minimum MSRP as the main one. That selection is written to `base_output.json`. 

2-The full set of variants (different drivetrains, cab sizes, bed lengths) is kept in `detailed_trims.json` for reference.

---

## Known gaps
- Not much I think we pretty much cover all what is required. I think there are few cases that may not work for other models, and are coded just for those models. For example for Rav4 the HP was written in the title it self not in the fsoData similar to all other models.

- I added few fields that are thought are important. I am not sure if our schema would allow that, if it does not I can drop them

- With more time I could generalize this to work on all models, and get more data. Also, it will be hosted as a serverless job on the cloud or as an Airflow dag. I will delete the saved HTML and save the data to a database instead of json. 

---

## Scheduling and catching new model years

To keep the data current I would deploy the script as a scheduled job — a weekly cron or a cloud scheduler task (e.g. AWS EventBridge, GitHub Actions on a schedule). The scraper is already idempotent within a day and organises output by date under `scrapped/<YYYY-MM-DD>/`, so each run naturally produces a versioned snapshot.

To detect new model years automatically I would compare the `year` field parsed from `#fso-header-data` against the most recently stored year for each model. If the year increments, the pipeline would send an alert (email or Slack) and write the new data into a fresh dated folder. A lightweight diff step — comparing trim names and MSRP values between the previous and current snapshots — would surface new trims, discontinued trims, and price changes without manual review.
# toyota_data
# toyota_data
