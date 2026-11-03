# Compat impact of <change> (<org/repo#issue>)

<!-- Fill in or delete every comment and placeholder. Take each number from a committed file and
     say which. No billing project, account, job IDs, or costs; bytes processed only. -->

Proposed change: <what changes, in one or two sentences; which cases differ and which don't>.

## Summary

<!-- Real cases, not argument structure. Typically: exposure (pages using the feature, % of the
     denominator); sample results by rating; extrapolated broken/worse with the denominator;
     what's behind broken and worse (sites, libraries, patterns, and fixes shipped upstream);
     how the field rate (use counters) compares with the crawl rate; anything the crawl can't size. -->

## 1. HTTP Archive

<!-- If a Common Crawl corpus was used too: crawl, seed, WARC count, HTML responses, and which
     numbers come from it (cc.py pick/download). Its pages aren't only root pages. -->

<!-- Crawl date, table, clients, root and/or non-root pages. Each query file, what it selects
     (use counters with where they're incremented, or custom metric fields with a link to the
     metric's source at a commit), and its output file. -->

| | desktop | mobile |
|---|---|---|
| Pages crawled | | |
| <condition> | | |

## 2. Live comparison on a sample

<!-- sample.py's strata, seed, and size (sample.jsonl). The browser and version; the before and
     after setups (flags, build, or emulation, from change.py); the sanity check. compare.py's
     visits: A and A2 before, B after, crawl-like viewports, waits, what's recorded (scrubbed at capture); output
     in out/results.jsonl. analyze.py's auto-ratings and how many pages were reviewed by hand
     (out/review/, out/review.csv); rechecks with recheck.py. -->

<!-- extrapolate.py output (out/summary.md): -->

| Stratum | Pages | Sampled | Broken | Worse | No visible change | Not assessable |
|---|---|---|---|---|---|---|

| Group | Broken | Worse | No visible change | Not assessable |
|---|---|---|---|---|

What's behind the ratings:

<!-- One bullet per stratum group and rating that matters: the pattern, named sites or
     libraries, the cause, and the review image (out/review/NNN.png) for the clearest case. -->

## 3. Top-ranked pages

<!-- If the sample has few or no pages in the top rank buckets, run every top-ranked hit through
     the same steps (out-top<N>/) and report the results here. Otherwise delete this section. -->

## Not covered

<!-- What the crawl and this method can't see: pages the crawl doesn't visit, interaction,
     logged-in state, special cases in the change, other engines. -->

## Query bytes

All on the <crawl date> crawl, run on <date>:

| Query | Bytes processed |
|---|---|

## Reproduce

```sh
bq query --use_legacy_sql=false --format=csv --max_rows=1000000 < hits.sql > hits.csv
python3 sample.py hits.csv sample.jsonl <seed> <n> <stratum-columns...>
python3 -m venv .venv && .venv/bin/pip install playwright pillow pyobjc-framework-Vision  # Vision for ocr_check.py on macOS; elsewhere install tesseract
.venv/bin/python compare.py "$CHROME" sample.jsonl out
.venv/bin/python analyze.py out
# review out/review/*.png by hand and fill in the empty ratings in out/review.csv
python3 extrapolate.py out/review.csv sample.jsonl > out/summary.md
.venv/bin/python recheck.py "$CHROME" <url> <desktop|mobile> <out.png>
```

<!-- Browser, Playwright, and Pillow versions; anything that changed during the run (run.log);
     that live pages change, so a rerun won't match exactly; that screenshots (out*/shots/)
     aren't committed and compare.py regenerates them. -->
