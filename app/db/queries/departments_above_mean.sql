-- Section 2, requirement 2: departments that hired more employees in a year than the mean of
-- employees hired that year across all departments, ordered by hires (descending).
--
-- * LEFT JOIN from departments: departments without hires count as 0 in the mean
--   ("the mean ... for all the departments").
-- * `hired` counts only the hires of the year, the same measure the mean is computed on.
-- * Strictly greater than the mean; ties broken alphabetically for a deterministic order.
WITH hires_per_department AS (
    SELECT d.id,
           d.department,
           COUNT(e.id) AS hired
    FROM departments AS d
    LEFT JOIN hired_employees AS e
           ON e.department_id = d.id
          AND e.datetime >= :year_start
          AND e.datetime < :next_year_start
    GROUP BY d.id, d.department
)
SELECT id,
       department,
       hired
FROM hires_per_department
WHERE hired > (SELECT AVG(hired) FROM hires_per_department)
ORDER BY hired DESC,
         department COLLATE "und-x-icu";
