# Manual imports

Sources that only publish files (no API) are imported from CSVs in this folder.

## `dosm_jmi.csv` — DOSM Job Market Insights (rung 3)

Build it from the data file attached to each quarterly release
("Big Data Analytics: Job Market Insights", dosm.gov.my). One row per occupation per quarter:

```
period,release_date,masco_code,occupation,offerings,source_url
2026Q2,2026-08-14,2411,Accountants,22067,https://www.dosm.gov.my/portal-main/release-content/big-data-analytics-job-market-insights-q22026
```

- `release_date` is the day the release went public, not the end of the quarter. Snapshots dated
  before it will not see the row (no look-ahead).
- `masco_code` must appear in `pipeline/curated/occupation_code_map.csv` to count toward a skill.
  Unmapped codes still count toward the quarter's total.
- Use real figures from the release only. Never type in estimates.

Then run `kompas fetch dosm_jmi`.
