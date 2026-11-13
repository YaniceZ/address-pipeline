-- description: no more than 1% of a source's addresses are unparsed
-- severity: error
SELECT
    source,
    count(*) AS addresses,
    count(*) FILTER (WHERE NOT parsed) AS unparsed,
    round(100.0 * count(*) FILTER (WHERE NOT parsed) / count(*), 2) AS unparsed_pct
FROM addresses
GROUP BY source
HAVING count(*) FILTER (WHERE NOT parsed) > 0.01 * count(*)
