"""
Synthetic outbound-referral dataset for a fictional 5-building SNF operator.

Simulates the first 26 weeks after go-live on an outbound referral / discharge
coordination workflow: discharge plans, referrals to provider partners, partner
responses (read receipts, accept/decline), discharge-date changes, and 30-day
returns to the same building.

All names, numbers and behaviours are invented. Seeded for reproducibility.
Run:  python src/generate_data.py  -> writes CSVs to data/
"""
import json
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

import os
SEED = int(os.environ.get("SEED", 3))
rng = np.random.default_rng(SEED)
random.seed(SEED)

GO_LIVE = datetime(2026, 10, 12, 0, 0)          # Monday
WEEKS = 26
SNAPSHOT = datetime(2027, 4, 9, 17, 0)           # Friday of week 26, "now"
OUT = Path(__file__).resolve().parent.parent / "data"
OUT.mkdir(exist_ok=True)

# ----------------------------------------------------------------------------
# Calendars (business hours) and time helpers
# ----------------------------------------------------------------------------
CAL_STANDARD = ({0, 1, 2, 3, 4}, (8, 18))        # Mon-Fri 8-18
CAL_EXTENDED = ({0, 1, 2, 3, 4, 5, 6}, (8, 20))  # 7 days 8-20 (hospice)
CAL_STAFF = ({0, 1, 2, 3, 4}, (8, 17))           # facility social workers


def add_bh(t, hours, cal):
    """Add `hours` of working time to t on calendar `cal`."""
    days, (sh, eh) = cal
    remaining = max(hours, 0.0)
    while True:
        if t.weekday() in days:
            open_t = t.replace(hour=sh, minute=0, second=0, microsecond=0)
            close_t = t.replace(hour=eh, minute=0, second=0, microsecond=0)
            if t < open_t:
                t = open_t
            if t < close_t:
                avail = (close_t - t).total_seconds() / 3600
                if remaining <= avail:
                    return t + timedelta(hours=remaining)
                remaining -= avail
        t = (t + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def lognormal(median, sigma=0.75):
    return float(rng.lognormal(math.log(median), sigma))


# ----------------------------------------------------------------------------
# Facilities
# ----------------------------------------------------------------------------
FACILITIES = [
    # id, name, beds, hh_shotgun_prob, staff_patience_bh, lead_days_probs(1..6), incomplete_packet_rate
    ("F01", "Cedar",  120, 0.15, 10, [.03, .08, .22, .28, .22, .17], 0.04),
    ("F02", "Harbor",  90, 0.60, 5,  [.03, .09, .22, .27, .22, .17], 0.04),
    ("F03", "Maple",  150, 0.25, 11, [.02, .05, .17, .30, .26, .20], 0.03),
    ("F04", "Willow", 100, 0.10, 16, [.22, .28, .22, .14, .08, .06], 0.05),
    ("F05", "Summit",  80, 0.35, 10, [.04, .09, .22, .27, .22, .16], 0.16),
]
FAC = {f[0]: dict(zip(["id", "name", "beds", "shotgun", "patience", "lead", "incomplete"], f)) for f in FACILITIES}
ALL_F = [f[0] for f in FACILITIES]

# ----------------------------------------------------------------------------
# Provider directory (partners)
# ----------------------------------------------------------------------------
# open/resp medians are in partner business hours. weight = staff habit (how often chosen first).
# reasons = typical decline reasons when declining for "base" reasons.
P = []


def partner(pid, name, ptype, on, open_m, resp_m, p_acc, weight, coverage=None,
            ghost=None, payer_decl=None, reasons=None, ret30=None, lead_bh=None, cal=None):
    P.append(dict(
        partner_id=pid, partner_name=name, provider_type=ptype, on_exacare=on,
        open_m=open_m, resp_m=resp_m * (1.0 if on else 0.7), p_acc=p_acc, weight=weight,
        coverage=coverage or ALL_F, ghost=ghost if ghost is not None else (0.02 if on else 0.07),
        payer_decl=payer_decl or {}, reasons=reasons or {"No staff capacity": 1.0},
        ret30=ret30, lead_bh=lead_bh, cal=cal or (CAL_EXTENDED if ptype == "Hospice" else CAL_STANDARD),
    ))


HH_R = {"No staff capacity": .7, "Clinical needs exceed capability": .3}
partner("P01", "BrightPath Home Health",   "Home Health", True,  0.4, 1.8, .84, 1.30, ret30=.09)
partner("P02", "Riverbend Home Care",      "Home Health", False, 5.0, 11., .44, 1.75, ghost=.12,
        payer_decl={"Medicare Advantage": .30}, reasons=HH_R, ret30=.17)
partner("P03", "Comfort First Home Health", "Home Health", False, 1.6, 4.5, .74, 1.00,
        coverage=["F01", "F02", "F03"], reasons=HH_R, ret30=.11)
partner("P04", "Unity Home Health",        "Home Health", True,  0.5, 2.2, .78, 0.80, ret30=.10)
partner("P05", "Evergreen Home Health",    "Home Health", False, 2.5, 6.0, .68, 0.80, reasons=HH_R, ret30=.13)
partner("P06", "Northstar Home Health",    "Home Health", False, 6.0, 14., .58, 0.55, ghost=.14, reasons=HH_R, ret30=.18)
partner("P07", "Keystone Home Care",       "Home Health", False, 1.2, 3.0, .80, 0.95,
        coverage=["F03", "F04"], reasons=HH_R, ret30=.10)
partner("P08", "Lighthouse Home Health",   "Home Health", True,  0.3, 1.5, .80, 0.65, ret30=.16)
partner("P09", "Sunrise Home Health",      "Home Health", False, 3.0, 8.0, .64, 0.45, reasons=HH_R, ret30=.12)
partner("P10", "Oakwood Home Health",      "Home Health", False, 3.5, 9.0, .70, 0.50,
        payer_decl={"Medicaid": .75, "Medicare Advantage": .45}, reasons=HH_R, ret30=.12)
partner("P11", "Pinnacle Home Health",     "Home Health", False, 2.0, 5.0, .74, 0.40, reasons=HH_R, ret30=.10)
partner("P12", "Meadowlark Home Health",   "Home Health", False, 8.0, 20., .45, 0.30, ghost=.18, reasons=HH_R, ret30=.15)

HO_R = {"No staff capacity": .6, "Clinical needs exceed capability": .4}
partner("P13", "Serenity Hospice",         "Hospice", True,  0.4, 1.5, .90, 1.2, reasons=HO_R, ret30=.02)
partner("P14", "Harborlight Hospice",      "Hospice", False, 2.0, 5.0, .82, 1.0, reasons=HO_R, ret30=.03)
partner("P15", "Compass Hospice",          "Hospice", False, 1.5, 4.0, .86, 0.8, reasons=HO_R, ret30=.02)
partner("P16", "Tranquil Pines Hospice",   "Hospice", False, 4.0, 10., .72, 0.5, reasons=HO_R, ret30=.04)
partner("P17", "Haven Hospice Care",       "Hospice", False, 3.0, 8.0, .78, 0.5, reasons=HO_R, ret30=.03)

DME_R = {"Item backordered": .65, "Payer not accepted": .35}
partner("P18", "MedSupply Direct",         "DME", True,  0.6, 2.0, .93, 1.2, reasons=DME_R, lead_bh=4)
partner("P19", "HomeEquip Medical",        "DME", False, 2.0, 6.0, .86, 1.1, reasons=DME_R, lead_bh=8)
partner("P20", "CareGear DME",             "DME", False, 3.0, 8.0, .82, 0.9, reasons=DME_R, lead_bh=16)
partner("P21", "Apex Medical Equipment",   "DME", False, 1.5, 4.0, .88, 0.7, reasons=DME_R, lead_bh=6)
partner("P22", "ReliaMed Supply",          "DME", False, 5.0, 13., .72, 0.5, ghost=.12, reasons=DME_R, lead_bh=14)
partner("P23", "Prime Mobility DME",       "DME", False, 2.5, 6.0, .84, 0.5, reasons=DME_R, lead_bh=8)

DI_R = {"No bed or chair available": .75, "Clinical needs exceed capability": .25}
partner("P24", "RenalCare Dialysis East",  "Dialysis", False, 3.0, 12., .64, 1.1, reasons=DI_R)
partner("P25", "Kidney Health Partners",   "Dialysis", True,  0.8, 4.0, .76, 1.0, reasons=DI_R)
partner("P26", "ClearFlow Dialysis",       "Dialysis", False, 5.0, 16., .55, 0.6, ghost=.12,
        coverage=["F01", "F02", "F05"], reasons=DI_R)
partner("P27", "Westside Dialysis",        "Dialysis", False, 2.5, 9.0, .62, 0.6, reasons=DI_R)

SN_R = {"No bed or chair available": .6, "Clinical needs exceed capability": .25, "Payer not accepted": .15}
partner("P28", "Oak Terrace Nursing",      "Skilled Nursing", True,  0.8, 5.0, .55, 1.0, reasons=SN_R)
partner("P29", "Brookside Long-Term Care", "Skilled Nursing", False, 5.0, 18., .42, 0.9, reasons=SN_R)
partner("P30", "Valley Manor",             "Skilled Nursing", False, 3.0, 12., .48, 0.7, reasons=SN_R,
        payer_decl={"Medicaid": .4})
partner("P31", "Rosewood Care Center",     "Skilled Nursing", False, 4.0, 14., .50, 0.6, reasons=SN_R)

LT_R = {"Clinical needs exceed capability": .6, "No bed or chair available": .4}
partner("P32", "Regional Specialty LTACH", "LTACH", False, 2.0, 8.0, .62, 1.0, reasons=LT_R)
partner("P33", "Continuum Specialty Hospital", "LTACH", True, 0.8, 4.0, .70, 0.9, reasons=LT_R)

PART = {p["partner_id"]: p for p in P}
BY_TYPE = {}
for p in P:
    BY_TYPE.setdefault(p["provider_type"], []).append(p)

# ----------------------------------------------------------------------------
# Discharge plans
# ----------------------------------------------------------------------------
PLANS = [
    # plan name, prob, list of (service, prob needed)
    ("Home with home health",            .50, [("Home Health", 1.0), ("DME", .40)]),
    ("Home with hospice",                .08, [("Hospice", 1.0), ("DME", .55)]),
    ("Assisted living with home health", .08, [("Home Health", 1.0)]),
    ("Home with DME only",               .15, [("DME", 1.0)]),
    ("Home, outpatient dialysis",        .07, [("Dialysis", 1.0), ("Home Health", .45)]),
    ("Transfer to long-term care",       .09, [("Skilled Nursing", 1.0)]),
    ("Transfer to LTACH",                .03, [("LTACH", 1.0)]),
]
PLAN_P = np.array([p[1] for p in PLANS]); PLAN_P /= PLAN_P.sum()
PAYERS = ["Medicare Part A", "Medicare Advantage", "Medicaid", "Commercial / other"]
PAYER_P = [.42, .33, .15, .10]
AUTH_SLIP_P = {"Medicare Part A": .03, "Medicare Advantage": .16, "Medicaid": .08, "Commercial / other": .06}
DOW_P = [.15, .17, .17, .18, .22, .07, .04]  # discharge day-of-week weights

PREP_BH = {"Home Health": 1, "Hospice": 1, "Dialysis": 6, "Skilled Nursing": 4, "LTACH": 4}

# staff: 2 social workers per building, one replaced mid-period (turnover)
STAFF = {}
for f in ALL_F:
    STAFF[f] = {"early": [f"{f}-SW1", f"{f}-SW2"], "late": [f"{f}-SW1", f"{f}-SW3"]}

discharges, referrals, events, date_changes = [], [], [], []
rid_counter = 0
eid_counter = 0


def ev(ref_id, etype, at, actor):
    global eid_counter
    if at is None or at > SNAPSHOT:
        return
    eid_counter += 1
    events.append(dict(event_id=f"E{eid_counter:06d}", referral_id=ref_id, event_type=etype,
                       event_at=at, actor=actor))


def pick_partners(ptype, k, exclude):
    pool = [p for p in BY_TYPE[ptype] if p["partner_id"] not in exclude]
    if not pool:
        return []
    w = np.array([p["weight"] for p in pool]); w = w / w.sum()
    k = min(k, len(pool))
    idx = rng.choice(len(pool), size=k, replace=False, p=w)
    return [pool[i] for i in idx]


def simulate_referral(fac, p, payer, sent_at):
    """Return dict with opened_at, response_at, decision, reason, info_requested."""
    cal = p["cal"]
    ghost = rng.random() < p["ghost"]
    opened = add_bh(sent_at, lognormal(p["open_m"], 0.9), cal)
    if ghost:
        never_open = rng.random() < 0.55
        return dict(opened_at=None if never_open else opened, response_at=None,
                    decision=None, reason=None, info_requested=False)
    info_requested = False
    resp_med = p["resp_m"]
    # decision logic
    if fac["id"] not in p["coverage"] and rng.random() < 0.92:
        decision, reason = "declined", "Outside service area"
        resp_med *= 0.4
    elif payer in p["payer_decl"] and rng.random() < p["payer_decl"][payer]:
        decision, reason = "declined", "Payer not accepted"
        resp_med *= 0.7
    else:
        decision, reason = None, None
        if rng.random() < fac["incomplete"] * (0.7 if p["on_exacare"] else 1.3):
            if rng.random() < 0.45:
                decision, reason = "declined", "Incomplete referral packet"
            else:
                info_requested = True
                resp_med += 4
        if decision is None:
            if rng.random() < p["p_acc"]:
                decision = "accepted"
            else:
                decision = "declined"
                rs = list(p["reasons"].keys()); rw = np.array(list(p["reasons"].values()))
                reason = rs[rng.choice(len(rs), p=rw / rw.sum())]
    response = add_bh(opened, lognormal(resp_med, 0.7), cal)
    return dict(opened_at=opened, response_at=response, decision=decision, reason=reason,
                info_requested=info_requested)


def next_staff_time(t):
    return add_bh(t, 0.0, CAL_STAFF)


did = 0
for f in ALL_F:
    fac = FAC[f]
    weekly_rate = fac["beds"] * 0.072
    day = GO_LIVE + timedelta(days=3)
    end_day = SNAPSHOT + timedelta(days=8)
    while day <= end_day:
        n = rng.poisson(weekly_rate / 7 * DOW_P[day.weekday()] * 7)
        for _ in range(n):
            did += 1
            disch_id = f"D{did:05d}"
            plan_i = rng.choice(len(PLANS), p=PLAN_P)
            plan_name, _, svc = PLANS[plan_i]
            payer = PAYERS[rng.choice(4, p=PAYER_P)]
            planned = day.replace(hour=11)
            lead = int(rng.choice(np.arange(1, 7), p=fac["lead"]))
            start = planned - timedelta(days=lead)
            start = start.replace(hour=int(rng.integers(8, 16)), minute=int(rng.integers(0, 60)))
            start = next_staff_time(start)
            if start < GO_LIVE:
                continue
            if start > SNAPSHOT:
                continue
            period = "early" if start < GO_LIVE + timedelta(weeks=13) else "late"
            staff = random.choice(STAFF[f][period])
            needs = [s for s, pr in svc if rng.random() < pr]

            cancelled = rng.random() < 0.05
            cancel_at = start + (planned - start) * float(rng.uniform(0.2, 0.9)) if cancelled else None

            ready_times, delay_reason, unplaced = [], None, False
            need_results = []
            for ptype in needs:
                sent_refs = []          # list of (ref dict)
                used = set()
                t_batch = start
                chosen = None
                attempts = 0
                while chosen is None and attempts < 6:
                    if cancelled and t_batch > cancel_at:
                        break
                    if t_batch > SNAPSHOT:
                        break
                    if ptype == "Home Health":
                        k = (2 if rng.random() < .6 else 3) if rng.random() < fac["shotgun"] else 1
                    elif ptype == "DME":
                        k = 1
                    else:
                        k = 2 if rng.random() < 0.15 else 1
                    batch = pick_partners(ptype, k, used)
                    if not batch:
                        break
                    attempts += 1
                    for p in batch:
                        used.add(p["partner_id"])
                        r = simulate_referral(fac, p, payer, t_batch)
                        r.update(partner=p, sent_at=t_batch, attempt=attempts)
                        sent_refs.append(r)
                    deadline = add_bh(t_batch, fac["patience"], CAL_STAFF)
                    accepts = [r for r in sent_refs if r["decision"] == "accepted"]
                    first_acc = min(accepts, key=lambda r: r["response_at"]) if accepts else None
                    if first_acc and first_acc["response_at"] <= deadline:
                        chosen = first_acc
                        break
                    resolved = all(r["decision"] == "declined" and r["response_at"] <= deadline for r in sent_refs)
                    if resolved:
                        last = max(r["response_at"] for r in sent_refs)
                        t_batch = add_bh(last, float(rng.uniform(0.3, 2.0)), CAL_STAFF)
                    else:
                        t_batch = deadline
                if chosen is None:
                    accepts = [r for r in sent_refs if r["decision"] == "accepted"]
                    if accepts:
                        chosen = min(accepts, key=lambda r: r["response_at"])
                need_results.append((ptype, sent_refs, chosen))

            # ---------------- discharge date logic ----------------
            new_date = planned
            changes = []
            primary_reason = None
            if not cancelled:
                partner_ready = planned
                partner_reason = None
                for ptype, sent_refs, chosen in need_results:
                    if chosen is None:
                        unplaced = True
                        if not sent_refs:
                            continue
                        last = max((r["response_at"] or r["sent_at"]) for r in sent_refs)
                        ready = last + timedelta(days=int(rng.integers(1, 4)))
                        rsn = "No partner accepted"
                    else:
                        p = chosen["partner"]
                        if ptype == "DME":
                            ready = add_bh(chosen["response_at"], p["lead_bh"], CAL_STANDARD)
                            rsn = "Awaiting DME delivery" if chosen["response_at"] <= planned - timedelta(hours=8) else "Awaiting partner acceptance"
                        else:
                            ready = add_bh(chosen["response_at"], PREP_BH[ptype], p["cal"])
                            rsn = "Awaiting partner acceptance"
                    if ready > partner_ready:
                        partner_ready, partner_reason = ready, rsn
                if partner_ready > planned:
                    d = partner_ready.replace(hour=11, minute=0, second=0, microsecond=0)
                    if partner_ready.hour >= 11:
                        d += timedelta(days=1)
                    changes.append((d, partner_reason))
                    new_date = d
                # non-partner causes
                for rsn, prob, (lo, hi) in [
                    ("Payer authorization pending", AUTH_SLIP_P[payer], (1, 3)),
                    ("Resident / family not ready", 0.06, (1, 2)),
                    ("Clinical status change", 0.05, (1, 4)),
                ]:
                    if rng.random() < prob:
                        new_date = new_date + timedelta(days=int(rng.integers(lo, hi + 1)))
                        changes.append((new_date, rsn))
                if changes:
                    primary_reason = changes[0][1]

            final_date = new_date
            if cancelled:
                status = "Cancelled (hospital transfer)"
            elif final_date > SNAPSHOT:
                status = "Upcoming"
            else:
                status = "Discharged"
            if cancelled and cancel_at > SNAPSHOT:
                status = "Upcoming"
                cancelled = False  # not yet known at snapshot

            # selected partners per need
            placed_partner = {}
            for ptype, sent_refs, chosen in need_results:
                if chosen and chosen["response_at"] <= SNAPSHOT and not cancelled:
                    placed_partner[ptype] = chosen["partner"]["partner_id"]

            # 30-day return to same building (only visible returns)
            returned = None
            if status == "Discharged" and plan_name not in ("Transfer to long-term care", "Transfer to LTACH"):
                if final_date + timedelta(days=30) <= SNAPSHOT:
                    hh = placed_partner.get("Home Health") or placed_partner.get("Hospice")
                    base = PART[hh]["ret30"] if hh else (0.12 if not unplaced else 0.17)
                    if unplaced:
                        base += 0.05
                    returned = bool(rng.random() < base)

            # change log rows
            prev = planned
            for i, (d, rsn) in enumerate(changes):
                changed_at = min(d, prev) - timedelta(hours=float(rng.uniform(2, 20)))
                if changed_at <= SNAPSHOT:
                    date_changes.append(dict(discharge_id=disch_id, change_no=i + 1,
                                             changed_at=changed_at, old_date=prev.date(),
                                             new_date=d.date(), reason=rsn))
                prev = d

            visible_changes = [c for c in changes if True]
            slip_days = (final_date.date() - planned.date()).days if status != "Cancelled (hospital transfer)" else None
            discharges.append(dict(
                discharge_id=disch_id, facility_id=f, resident_id=f"R{did:05d}", payer_type=payer,
                discharge_plan=plan_name, services_needed="; ".join(needs),
                planning_started_at=start, original_planned_date=planned.date(),
                current_discharge_date=final_date.date(), status=status,
                date_changes=len(changes) if status != "Cancelled (hospital transfer)" else 0,
                slip_days=slip_days, primary_delay_reason=primary_reason,
                all_services_placed=not unplaced if needs else True,
                returned_within_30d=returned,
            ))

            # ---------------- referral rows + events ----------------
            discharge_time = final_date
            for ptype, sent_refs, chosen in need_results:
                for r in sent_refs:
                    rid_counter += 1
                    ref_id = f"OR{rid_counter:06d}"
                    p = r["partner"]
                    sent_at = r["sent_at"]
                    opened, resp = r["opened_at"], r["response_at"]
                    # facility closes outstanding referrals when the need is resolved / resident leaves
                    close_at = discharge_time if not cancelled else cancel_at
                    if chosen is not None and r is not chosen:
                        close_at = min(close_at, chosen["response_at"] + timedelta(hours=float(rng.uniform(4, 30))))
                    if cancelled:
                        if resp is not None and resp <= cancel_at:
                            pass
                        else:
                            resp_eff = None
                    resp_eff = resp if (resp is not None and resp <= close_at and resp <= SNAPSHOT) else None
                    open_eff = opened if (opened is not None and opened <= SNAPSHOT and opened <= close_at) else None
                    if r is chosen and not cancelled and chosen["response_at"] <= SNAPSHOT:
                        final = "Placed"
                    elif resp_eff is not None and r["decision"] == "accepted":
                        final = "Accepted, not selected" if not cancelled else "Withdrawn"
                    elif resp_eff is not None and r["decision"] == "declined":
                        final = "Declined"
                    elif close_at <= SNAPSHOT:
                        final = "Withdrawn" if cancelled else "No response (closed)"
                    else:
                        final = "Pending"
                    if final == "Withdrawn" and resp_eff is not None and r["decision"] == "declined":
                        final = "Declined"
                    referrals.append(dict(
                        referral_id=ref_id, discharge_id=disch_id, facility_id=f,
                        partner_id=p["partner_id"], provider_type=ptype, payer_type=payer,
                        sent_by=staff, attempt_no=r["attempt"], sent_at=sent_at,
                        opened_at=open_eff, first_response_at=resp_eff,
                        decision=r["decision"] if resp_eff is not None else None,
                        decline_reason=r["reason"] if (resp_eff is not None and r["decision"] == "declined") else None,
                        info_requested=r["info_requested"] and open_eff is not None,
                        final_status=final,
                    ))
                    ev(ref_id, "SENT", sent_at, staff)
                    ev(ref_id, "OPENED", open_eff, p["partner_id"])
                    if r["info_requested"] and open_eff is not None:
                        t_req = open_eff + timedelta(hours=float(rng.uniform(0.5, 3)))
                        ev(ref_id, "INFO_REQUESTED", t_req, p["partner_id"])
                        ev(ref_id, "DOCUMENT_UPLOADED", add_bh(t_req, float(rng.uniform(0.5, 4)), CAL_STAFF), staff)
                    if resp_eff is not None:
                        ev(ref_id, "ACCEPTED" if r["decision"] == "accepted" else "DECLINED", resp_eff, p["partner_id"])
                    if final == "Placed":
                        ev(ref_id, "SELECTED", chosen["response_at"] + timedelta(minutes=int(rng.integers(10, 240))), staff)
                    if final in ("No response (closed)", "Withdrawn", "Accepted, not selected"):
                        ev(ref_id, "CLOSED", close_at, staff)
        day += timedelta(days=1)

# ----------------------------------------------------------------------------
# Write tables
# ----------------------------------------------------------------------------
fac_df = pd.DataFrame([{"facility_id": f["id"], "facility_name": f["name"], "licensed_beds": f["beds"]}
                       for f in FAC.values()])
par_df = pd.DataFrame([{"partner_id": p["partner_id"], "partner_name": p["partner_name"],
                        "provider_type": p["provider_type"], "on_exacare": p["on_exacare"],
                        "service_area_facilities": "; ".join(p["coverage"])} for p in P])
dis_df = pd.DataFrame(discharges)
dis_df["slip_days"] = dis_df.slip_days.astype("Int64")
ref_df = pd.DataFrame(referrals)
evt_df = pd.DataFrame(events).sort_values("event_at")
chg_df = pd.DataFrame(date_changes)

for name, df in [("facilities", fac_df), ("provider_directory", par_df), ("discharge_plans", dis_df),
                 ("outbound_referrals", ref_df), ("referral_events", evt_df),
                 ("discharge_date_changes", chg_df)]:
    df.to_csv(OUT / f"{name}.csv", index=False)
    print(f"{name:24s} {len(df):6d} rows")

meta = dict(go_live=GO_LIVE.isoformat(), snapshot=SNAPSHOT.isoformat(), weeks=WEEKS, seed=SEED)
(OUT / "meta.json").write_text(json.dumps(meta, indent=2))
