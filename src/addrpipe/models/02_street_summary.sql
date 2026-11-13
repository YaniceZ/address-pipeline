-- Addresses per street, with the lowest and highest house number seen.
CREATE OR REPLACE TABLE street_summary AS
SELECT
    source,
    city,
    street_name,
    street_type,
    street_dir,
    count(*) AS addresses,
    min(house_number_int) AS lowest_number,
    max(house_number_int) AS highest_number
FROM addresses
WHERE street_name IS NOT NULL
GROUP BY ALL
