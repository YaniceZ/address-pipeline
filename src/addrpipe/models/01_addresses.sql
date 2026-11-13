-- One table over every source in the lake. The geometry is kept in the parquet files as WKB;
-- the warehouse works from the lon and lat columns written at ingest.
CREATE OR REPLACE TABLE addresses AS
SELECT
    source,
    source_id,
    house_number,
    try_cast(house_number AS INTEGER) AS house_number_int,
    number_suffix,
    unit,
    street_name,
    street_type,
    street_dir,
    full_address,
    city,
    province,
    parsed,
    raw_street_type,
    lon,
    lat
FROM read_parquet('{lake_glob}', union_by_name = true)
