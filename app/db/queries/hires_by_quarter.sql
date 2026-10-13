-- Section 2, requirement 1: hires per department and job in a year, pivoted by quarter.
--
-- * Half-open UTC range on the indexed `datetime` column (no function on the column).
-- * Quarters computed in UTC, independent of the session time zone.
-- * Linguistic ordering (ICU) so "Geologist" sorts before "GIS Analyst" on every platform.
SELECT d.department,
       j.job,
       COUNT(*) FILTER (WHERE EXTRACT(QUARTER FROM e.datetime AT TIME ZONE 'UTC') = 1) AS "Q1",
       COUNT(*) FILTER (WHERE EXTRACT(QUARTER FROM e.datetime AT TIME ZONE 'UTC') = 2) AS "Q2",
       COUNT(*) FILTER (WHERE EXTRACT(QUARTER FROM e.datetime AT TIME ZONE 'UTC') = 3) AS "Q3",
       COUNT(*) FILTER (WHERE EXTRACT(QUARTER FROM e.datetime AT TIME ZONE 'UTC') = 4) AS "Q4"
FROM hired_employees AS e
JOIN departments AS d ON d.id = e.department_id
JOIN jobs AS j ON j.id = e.job_id
WHERE e.datetime >= :year_start
  AND e.datetime < :next_year_start
GROUP BY d.department, j.job
ORDER BY d.department COLLATE "und-x-icu",
         j.job COLLATE "und-x-icu";
