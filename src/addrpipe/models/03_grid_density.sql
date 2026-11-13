-- Address counts on a 0.01 degree grid (roughly 1 km tall and 0.7 km wide at Canadian latitudes).
-- cell_lon and cell_lat are the south-west corner of each cell.
CREATE OR REPLACE TABLE grid_density AS
SELECT
    source,
    round(floor(lon / 0.01) * 0.01, 2) AS cell_lon,
    round(floor(lat / 0.01) * 0.01, 2) AS cell_lat,
    count(*) AS addresses
FROM addresses
GROUP BY ALL
