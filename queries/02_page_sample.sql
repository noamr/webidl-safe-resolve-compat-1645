-- Root pages in the Oct 2026 crawl, with rank, for drawing a stratified random sample.
-- Takes the first 300 per (rank, client) stratum by a seeded hash.
SELECT client, page, rank
FROM (
  SELECT client, page, rank,
    ROW_NUMBER() OVER (PARTITION BY client, rank ORDER BY FARM_FINGERPRINT(CONCAT(page, 'webidl1645'))) AS n,
    COUNT(*) OVER (PARTITION BY client, rank) AS stratum_size
  FROM `httparchive.crawl.pages`
  WHERE date = '2026-10-01' AND is_root_page
)
WHERE n <= 300
