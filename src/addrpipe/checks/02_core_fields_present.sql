-- description: rows marked as parsed have a house number and a street name
-- severity: error
SELECT source, source_id, full_address
FROM addresses
WHERE parsed AND (house_number IS NULL OR street_name IS NULL)
