-- Scripts defining a `then` accessor (getter), on a prototype or in an object
-- literal / class. Prototype on the 10k sample.
SELECT
  client,
  page,
  url,
  FARM_FINGERPRINT(response_body) AS body_fp,
  ARRAY_TO_STRING(
    ARRAY(SELECT SUBSTR(m, 1, 300) FROM UNNEST(REGEXP_EXTRACT_ALL(response_body,
      r'.{0,120}(?:(?:defineProperty|__defineGetter__)\(\s*[\w$.]+\s*,\s*["\x27]then["\x27]|\bget\s+then\s*\().{0,120}')) AS m LIMIT 5),
    '\n---\n') AS snippets
FROM `httparchive.sample_data.requests_10k`
WHERE REGEXP_CONTAINS(response_body,
  r'(?:defineProperty|__defineGetter__)\(\s*[\w$.]+\s*,\s*["\x27]then["\x27]|\bget\s+then\s*\(')
