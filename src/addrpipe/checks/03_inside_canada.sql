-- description: every point falls inside a bounding box around Canada
-- severity: error
SELECT source, source_id, lon, lat
FROM addresses
WHERE lon NOT BETWEEN -141.1 AND -52.5
   OR lat NOT BETWEEN 41.6 AND 83.2
