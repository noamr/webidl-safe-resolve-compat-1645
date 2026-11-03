-- Root pages per (rank, client) stratum in the Oct 2026 crawl (denominators for extrapolation).
SELECT client, rank, COUNT(*) AS pages
FROM `httparchive.crawl.pages`
WHERE date = '2026-10-01' AND is_root_page
GROUP BY client, rank
ORDER BY client, rank
