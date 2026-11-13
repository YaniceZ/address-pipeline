-- description: the same address text appears more than once in a source without a unit number
-- severity: warn
SELECT source, city, full_address, count(*) AS copies
FROM addresses
WHERE full_address IS NOT NULL AND unit IS NULL
GROUP BY source, city, full_address
HAVING count(*) > 1
