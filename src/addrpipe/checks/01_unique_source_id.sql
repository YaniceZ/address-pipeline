-- description: source_id is unique within each source
-- severity: error
SELECT source, source_id, count(*) AS copies
FROM addresses
GROUP BY source, source_id
HAVING count(*) > 1
