-- ============================================================================
-- Outbound referral analytics: metric definitions as SQL
-- Concept by Hanna Maliarchuk. Runs on PostgreSQL or DuckDB against schema.sql.
-- Each query is one report on the dashboard. Data is simulated.
-- ============================================================================


-- M1. Outbound status: funnel, acceptance and speed, by building (+ total row)
--     Acceptance rate      = accepted / answered (unanswered referrals excluded)
--     Referrals/placement  = referrals sent / partners actually used
WITH r AS (
    SELECT o.*, f.facility_name,
           EXTRACT(EPOCH FROM (o.first_response_at - o.sent_at)) / 3600.0 AS hours_to_response
    FROM outbound_referrals o
    JOIN facilities f USING (facility_id)
)
SELECT COALESCE(facility_name, 'All buildings')                    AS building,
       COUNT(*)                                                      AS sent,
       COUNT(opened_at)                                              AS opened,
       COUNT(*) FILTER (WHERE decision IS NOT NULL)                  AS answered,
       COUNT(*) FILTER (WHERE decision = 'accepted')                 AS accepted,
       COUNT(*) FILTER (WHERE final_status = 'Placed')               AS placed,
       ROUND(COUNT(*) FILTER (WHERE decision = 'accepted')::NUMERIC
             / NULLIF(COUNT(*) FILTER (WHERE decision IS NOT NULL), 0), 3)              AS acceptance_rate,
       ROUND(COUNT(*)::NUMERIC / NULLIF(COUNT(*) FILTER (WHERE final_status = 'Placed'), 0), 2) AS referrals_per_placement,
       ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY hours_to_response))::NUMERIC, 1)    AS median_hours_to_response
FROM r
GROUP BY ROLLUP (facility_name)
ORDER BY facility_name NULLS LAST;


-- M2. Partner scorecard: volume, speed, acceptance, placements, top decline
--     reason, and 30-day returns for home health / hospice placements
WITH r AS (
    SELECT o.*, EXTRACT(EPOCH FROM (o.first_response_at - o.sent_at)) / 3600.0 AS hours_to_response
    FROM outbound_referrals o
),
top_decline AS (
    SELECT partner_id, decline_reason,
           ROW_NUMBER() OVER (PARTITION BY partner_id ORDER BY COUNT(*) DESC, decline_reason) AS rk
    FROM outbound_referrals
    WHERE decision = 'declined'
    GROUP BY partner_id, decline_reason
),
returns AS (
    SELECT o.partner_id,
           COUNT(*)                                        AS placements_tracked,
           COUNT(*) FILTER (WHERE d.returned_within_30d)   AS returned
    FROM outbound_referrals o
    JOIN discharge_plans d USING (discharge_id)
    WHERE o.final_status = 'Placed'
      AND o.provider_type IN ('Home Health', 'Hospice')
      AND d.returned_within_30d IS NOT NULL
    GROUP BY o.partner_id
)
SELECT p.partner_name,
       p.provider_type,
       p.on_exacare,
       COUNT(*)                                                                         AS referrals,
       ROUND(COUNT(*)::NUMERIC / SUM(COUNT(*)) OVER (PARTITION BY p.provider_type), 3) AS share_of_type,
       ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY r.hours_to_response))::NUMERIC, 1) AS median_hours_to_response,
       ROUND(COUNT(*) FILTER (WHERE r.decision = 'accepted')::NUMERIC
             / NULLIF(COUNT(*) FILTER (WHERE r.decision IS NOT NULL), 0), 3)            AS acceptance_rate,
       COUNT(*) FILTER (WHERE r.final_status = 'Placed')                               AS placed,
       MAX(t.decline_reason)                                                            AS top_decline_reason,
       MAX(x.placements_tracked)                                                        AS placements_tracked,
       ROUND(MAX(x.returned)::NUMERIC / NULLIF(MAX(x.placements_tracked), 0), 3)        AS return_rate_30d
FROM r
JOIN provider_directory p USING (partner_id)
LEFT JOIN top_decline t ON t.partner_id = r.partner_id AND t.rk = 1
LEFT JOIN returns x     ON x.partner_id = r.partner_id
GROUP BY p.partner_name, p.provider_type, p.on_exacare
ORDER BY p.provider_type, referrals DESC;


-- M3. Discharge timeliness by building: how often dates move, bed-days lost,
--     and how much of it was waiting on a partner. Days are attributed to the
--     first reason in the date-change log. Planned discharge time assumed 11:00.
WITH first_reason AS (
    SELECT discharge_id, reason FROM discharge_date_changes WHERE change_no = 1
),
d AS (
    SELECT dp.*, f.facility_name, fr.reason AS first_reason,
           (dp.current_discharge_date - dp.original_planned_date) AS days_moved,
           EXTRACT(EPOCH FROM (dp.original_planned_date + INTERVAL '11 hours' - dp.planning_started_at)) / 86400.0 AS notice_days
    FROM discharge_plans dp
    JOIN facilities f USING (facility_id)
    LEFT JOIN first_reason fr USING (discharge_id)
    WHERE dp.status = 'Discharged'
)
SELECT COALESCE(facility_name, 'All buildings')                                   AS building,
       COUNT(*)                                                                     AS discharged,
       COUNT(*) FILTER (WHERE days_moved > 0)                                       AS date_moved,
       ROUND(COUNT(*) FILTER (WHERE days_moved > 0)::NUMERIC / COUNT(*), 3)         AS date_moved_rate,
       SUM(days_moved)                                                              AS bed_days_lost,
       SUM(days_moved) FILTER (WHERE first_reason IN
           ('Awaiting partner acceptance', 'Awaiting DME delivery', 'No partner accepted')) AS bed_days_waiting_on_partner,
       ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY notice_days))::NUMERIC, 1) AS median_notice_days
FROM d
GROUP BY ROLLUP (facility_name)
ORDER BY facility_name NULLS LAST;


-- M4. Date moved, by planning notice (how far ahead referrals started)
WITH d AS (
    SELECT dp.*,
           EXTRACT(EPOCH FROM (dp.original_planned_date + INTERVAL '11 hours' - dp.planning_started_at)) / 86400.0 AS notice_days
    FROM discharge_plans dp
    WHERE dp.status = 'Discharged'
)
SELECT CASE WHEN notice_days <= 2   THEN '1. Under 2 days'
            WHEN notice_days <= 3.5 THEN '2. 2 to 3.5 days'
            ELSE                         '3. Over 3.5 days' END                     AS planning_notice,
       COUNT(*)                                                                     AS discharged,
       ROUND(COUNT(*) FILTER (WHERE date_changes > 0)::NUMERIC / COUNT(*), 3)       AS date_moved_rate
FROM d
GROUP BY 1
ORDER BY 1;


-- M5. First-answer time by send window (DOW: 0 = Sunday ... 6 = Saturday)
SELECT CASE WHEN EXTRACT(DOW FROM sent_at) IN (0, 6)                              THEN 'Weekend'
            WHEN EXTRACT(DOW FROM sent_at) = 5 AND EXTRACT(HOUR FROM sent_at) >= 12 THEN 'Fri after noon'
            WHEN EXTRACT(DOW FROM sent_at) = 5                                    THEN 'Fri before noon'
            WHEN EXTRACT(HOUR FROM sent_at) >= 12                                 THEN 'Mon-Thu after noon'
            ELSE                                                                       'Mon-Thu before noon' END AS send_window,
       COUNT(*)                                                                    AS referrals,
       ROUND((percentile_cont(0.5) WITHIN GROUP (
           ORDER BY EXTRACT(EPOCH FROM (first_response_at - sent_at)) / 3600.0))::NUMERIC, 1) AS median_hours_to_response
FROM outbound_referrals
GROUP BY 1
ORDER BY median_hours_to_response DESC;


-- M6. Routing check: referrals sent to partners whose service area excludes the building
SELECT p.partner_name,
       f.facility_name                                                      AS building_outside_area,
       COUNT(*)                                                             AS referrals_sent,
       COUNT(*) FILTER (WHERE o.decline_reason = 'Outside service area')    AS declined_outside_area
FROM outbound_referrals o
JOIN provider_directory p USING (partner_id)
JOIN facilities f         USING (facility_id)
WHERE POSITION(o.facility_id IN p.service_area_facilities) = 0
GROUP BY p.partner_name, f.facility_name
ORDER BY referrals_sent DESC;


-- M7. Network growth: most-referred partners not yet on exacare (invite list)
SELECT p.partner_name,
       p.provider_type,
       COUNT(*)                                                                    AS referrals_received,
       COUNT(DISTINCT o.facility_id)                                               AS buildings_referring,
       ROUND((percentile_cont(0.5) WITHIN GROUP (
           ORDER BY EXTRACT(EPOCH FROM (o.first_response_at - o.sent_at)) / 3600.0))::NUMERIC, 1) AS median_hours_to_response
FROM outbound_referrals o
JOIN provider_directory p USING (partner_id)
WHERE NOT p.on_exacare
GROUP BY p.partner_name, p.provider_type
ORDER BY referrals_received DESC
LIMIT 10;


-- M8. Production sketch (not run here): in the live product there is no
--     returned_within_30d flag. A return is an inbound referral for the same
--     resident to the same building within 30 days of discharge, which exacare
--     can see because inbound and outbound live in one system. Needs reliable
--     resident matching across referrals (an MPI or name + DOB + payer ID).
--
-- SELECT d.discharge_id,
--        MIN(i.received_at) AS returned_at
-- FROM discharge_plans d
-- LEFT JOIN inbound_referrals i
--        ON i.resident_id = d.resident_id
--       AND i.facility_id = d.facility_id
--       AND i.received_at >  d.current_discharge_date
--       AND i.received_at <= d.current_discharge_date + INTERVAL '30 days'
-- WHERE d.status = 'Discharged'
-- GROUP BY d.discharge_id;
