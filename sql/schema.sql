-- ============================================================================
-- Outbound referral analytics: proposed reporting data model
-- Concept by Hanna Maliarchuk. Runs on PostgreSQL or DuckDB.
-- The CSVs in data/ follow these tables exactly (all values simulated).
-- ============================================================================

-- One row per building.
CREATE TABLE facilities (
    facility_id      TEXT PRIMARY KEY,
    facility_name    TEXT NOT NULL,
    licensed_beds    INTEGER
);

-- The Provider Directory: every partner a building can refer to.
-- service_area_facilities is a ';'-separated list here for simplicity;
-- in production it would be a facility_partner_coverage bridge table.
CREATE TABLE provider_directory (
    partner_id               TEXT PRIMARY KEY,
    partner_name             TEXT NOT NULL,
    provider_type            TEXT NOT NULL,   -- Home Health, Hospice, DME, Dialysis, Skilled Nursing, LTACH
    on_exacare               BOOLEAN NOT NULL,-- receives referrals in-platform (TRUE) or via secure email link (FALSE)
    service_area_facilities  TEXT
);

-- One row per planned discharge (the unit that bed-days and returns hang off).
CREATE TABLE discharge_plans (
    discharge_id            TEXT PRIMARY KEY,
    facility_id             TEXT REFERENCES facilities,
    resident_id             TEXT,
    payer_type              TEXT,
    discharge_plan          TEXT,             -- e.g. Home with home health
    services_needed         TEXT,             -- ';'-separated provider types
    planning_started_at     TIMESTAMP,        -- first outbound referral sent
    original_planned_date   DATE,
    current_discharge_date  DATE,
    status                  TEXT,             -- Discharged / Upcoming / Cancelled (hospital transfer)
    date_changes            INTEGER,
    slip_days               INTEGER,
    primary_delay_reason    TEXT,             -- reason on the first date change
    all_services_placed     BOOLEAN,
    returned_within_30d     BOOLEAN           -- NULL while the 30-day window is still open
);

-- One row per referral sent to one partner (a discharge can have several).
CREATE TABLE outbound_referrals (
    referral_id        TEXT PRIMARY KEY,
    discharge_id       TEXT REFERENCES discharge_plans,
    facility_id        TEXT REFERENCES facilities,
    partner_id         TEXT REFERENCES provider_directory,
    provider_type      TEXT,
    payer_type         TEXT,
    sent_by            TEXT,                  -- staff member
    attempt_no         INTEGER,               -- 1 = first round of referrals for that service
    sent_at            TIMESTAMP,
    opened_at          TIMESTAMP,             -- read receipt / secure link opened
    first_response_at  TIMESTAMP,             -- accept or decline
    decision           TEXT,                  -- accepted / declined / NULL
    decline_reason     TEXT,
    info_requested     BOOLEAN,
    final_status       TEXT                   -- Placed, Accepted not selected, Declined, No response (closed), Withdrawn, Pending
);

-- The timestamped activity log behind each referral.
CREATE TABLE referral_events (
    event_id     TEXT PRIMARY KEY,
    referral_id  TEXT REFERENCES outbound_referrals,
    event_type   TEXT,                        -- SENT, OPENED, INFO_REQUESTED, DOCUMENT_UPLOADED, ACCEPTED, DECLINED, SELECTED, CLOSED
    event_at     TIMESTAMP,
    actor        TEXT                         -- staff id or partner id
);

-- Every change to a discharge date, with its reason.
CREATE TABLE discharge_date_changes (
    discharge_id  TEXT REFERENCES discharge_plans,
    change_no     INTEGER,
    changed_at    TIMESTAMP,
    old_date      DATE,
    new_date      DATE,
    reason        TEXT,
    PRIMARY KEY (discharge_id, change_no)
);
