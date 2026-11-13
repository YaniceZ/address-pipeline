-- description: a reload did not shrink a source by more than 10% against its previous load
-- severity: warn
WITH loads AS (
    SELECT
        source,
        rows,
        row_number() OVER (PARTITION BY source ORDER BY finished_at DESC) AS rn
    FROM run_log
    WHERE status = 'loaded'
)
SELECT
    cur.source,
    prev.rows AS previous_rows,
    cur.rows AS current_rows
FROM loads cur
JOIN loads prev ON prev.source = cur.source AND prev.rn = 2
WHERE cur.rn = 1 AND cur.rows < 0.9 * prev.rows
