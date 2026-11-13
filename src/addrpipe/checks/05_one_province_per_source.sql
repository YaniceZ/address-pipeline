-- description: each source belongs to exactly one province
-- severity: error
SELECT source, count(DISTINCT province) AS provinces
FROM addresses
GROUP BY source
HAVING count(DISTINCT province) > 1
