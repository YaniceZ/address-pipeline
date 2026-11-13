-- One row per source: size, parse rate, extent and when it was last loaded.
CREATE OR REPLACE TABLE source_summary AS
WITH last_load AS (
    SELECT
        source,
        finished_at AS loaded_at,
        row_number() OVER (PARTITION BY source ORDER BY finished_at DESC) AS rn
    FROM run_log
    WHERE status = 'loaded'
)
SELECT
    a.source,
    any_value(a.province) AS province,
    count(*) AS addresses,
    round(100.0 * avg(CASE WHEN a.parsed THEN 1 ELSE 0 END), 2) AS parsed_pct,
    count(*) - count(DISTINCT a.full_address) AS repeated_addresses,
    min(a.lon) AS west,
    min(a.lat) AS south,
    max(a.lon) AS east,
    max(a.lat) AS north,
    any_value(l.loaded_at) AS loaded_at
FROM addresses a
LEFT JOIN last_load l ON l.source = a.source AND l.rn = 1
GROUP BY a.source
