"""
service.py  -  the BACKEND API. This is the file your GUI talks to.
==============================================================================
It sits between the GUI and everything else:

      GUI  ->  service.py  ->  database.py (stores data)
                           ->  scheduler.py (runs the simulation)

Rules that make it easy to use from a GUI:
  * every function takes and returns plain Python data (numbers, strings, lists, dicts);
  * bad input raises ValueError with a readable message, so the GUI can do
        try:    service.add_patient(...)
        except ValueError as e:    show_message(str(e))

Overview of the functions
    init()                                  call once at start-up
    add_patient / list_patients / delete_patient / clear_patients
    get_config / set_config                 doctors on duty + equipment totals
    run_schedule(...)                       run ONE policy and save it to history
    compare_policies(...)                   run ALL four policies (not saved)
    list_runs()                             history of saved runs
    load_scenario(k)                        fill the database with a built-in test case
"""
import json

import database
import scheduler
from scenarios import SCENARIOS

# Order matters: it matches the order (ventilator, ECG, X-ray) used everywhere else.
EQUIPMENT_CODES = ("vent", "ecg", "xray")


def init():
    """Create the database file/tables if needed. Call this once when the program starts."""
    database.init_db()


def _num(v, lo, hi, what="value"):
    """Convert v to an int and check lo <= v <= hi, otherwise raise a friendly ValueError.
    (A GUI text box always gives strings like "5", so conversion is needed.)"""
    try:
        v = int(v)
    except (TypeError, ValueError):
        raise ValueError("%s must be a whole number" % what)
    if not lo <= v <= hi:
        raise ValueError("%s must be between %d and %d" % (what, lo, hi))
    return v


# ============================================================== patients
def list_patients():
    """All patients as a list of dicts: id, name, severity, arrival, burst, vent, ecg, xray, created."""
    with database.connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM patients ORDER BY id")]


def add_patient(name, severity, arrival, burst, vent=0, ecg=0, xray=0):
    """Register a patient. Returns the new patient's id.

    severity  1 = Critical ... 4 = Minor      arrival  time unit of arrival (0-500)
    burst     treatment time (1-60)           vent/ecg/xray  maximum equipment needed
    """
    name = str(name).strip()[:40]        # tidy the name, cap at 40 characters
    if not name:
        raise ValueError("name required")
    # Validate every number BEFORE touching the database.
    vals = (name, _num(severity, 1, 4, "severity"), _num(arrival, 0, 500, "arrival"),
            _num(burst, 1, 60, "treatment time"), _num(vent, 0, 20, "ventilators"),
            _num(ecg, 0, 20, "ECG machines"), _num(xray, 0, 20, "X-ray units"))
    with database.connect() as c:
        if c.execute("SELECT COUNT(*) FROM patients").fetchone()[0] >= scheduler.MAX_PATIENTS:
            raise ValueError("limit: %d patients" % scheduler.MAX_PATIENTS)
        # The '?' placeholders stop SQL-injection: values are never pasted into the SQL text.
        cur = c.execute("INSERT INTO patients(name,severity,arrival,burst,vent,ecg,xray) "
                        "VALUES(?,?,?,?,?,?,?)", vals)
        return cur.lastrowid             # id the database gave the new row


def delete_patient(patient_id):
    """Remove one patient by id."""
    with database.connect() as c:
        c.execute("DELETE FROM patients WHERE id=?", (int(patient_id),))


def clear_patients():
    """Remove ALL patients."""
    with database.connect() as c:
        c.execute("DELETE FROM patients")


# =============================================================== config
def get_config():
    """Current setup: {'doctors': [{id, name, on_duty}...], 'equipment': [{code, name, total}...]}"""
    with database.connect() as c:
        return {"doctors": [dict(r) for r in c.execute("SELECT id,name,on_duty FROM doctors ORDER BY id")],
                "equipment": [dict(r) for r in c.execute("SELECT code,name,total FROM equipment ORDER BY rowid")]}


def set_config(on_duty_ids, equipment):
    """Choose which doctors are on duty and how much equipment exists.

    on_duty_ids  list of doctor ids, 1 to 4 of them, e.g. [1, 2]
    equipment    dict such as {'vent': 2, 'ecg': 2, 'xray': 1}
    """
    ids = [int(i) for i in on_duty_ids]
    if not 1 <= len(ids) <= scheduler.MAX_DOCTORS:
        raise ValueError("choose between 1 and %d doctors on duty" % scheduler.MAX_DOCTORS)
    # Validate the equipment numbers before changing anything.
    totals = {code: _num(equipment[code], 0, 20, code) for code in EQUIPMENT_CODES}
    with database.connect() as c:
        c.execute("UPDATE doctors SET on_duty=0")         # everyone off duty...
        for i in ids:
            c.execute("UPDATE doctors SET on_duty=1 WHERE id=?", (i,))   # ...then switch on the chosen ones
        for code, total in totals.items():
            c.execute("UPDATE equipment SET total=? WHERE code=?", (total, code))


# ============================================================ scheduling
def _prepare(c, on_duty_ids, doctors, equipment):
    """Gather and validate everything a simulation needs.
    Returns (patient_specs, number_of_doctors, doctor_names, equipment_totals)."""
    # Equipment: use what the caller passed, otherwise what is stored in the database.
    if equipment is None:
        equipment = {r["code"]: r["total"] for r in c.execute("SELECT code,total FROM equipment")}
    total = [_num(equipment.get(code, 0), 0, 20, code) for code in EQUIPMENT_CODES]

    # Doctors: either a list of doctor ids (we then know their names) or just a count.
    if on_duty_ids is not None:
        names = []
        for i in on_duty_ids:
            row = c.execute("SELECT name FROM doctors WHERE id=?", (int(i),)).fetchone()
            if row is None:
                raise ValueError("choose at least one doctor on duty")
            names.append(row["name"])
        if not names:
            raise ValueError("choose at least one doctor on duty")
        ndoc = _num(len(names), 1, scheduler.MAX_DOCTORS, "doctors on duty")
    else:
        ndoc = _num(doctors, 1, scheduler.MAX_DOCTORS, "doctors")
        names = []

    # Patients (oldest first, at most 32).
    rows = c.execute("SELECT * FROM patients ORDER BY id LIMIT ?", (scheduler.MAX_PATIENTS,)).fetchall()
    if not rows:
        raise ValueError("no patients registered")
    specs = []
    for r in rows:
        claim = (r["vent"], r["ecg"], r["xray"])
        # Refuse early (with a clear message) if someone needs more equipment than exists.
        for k, need, have in zip(EQUIPMENT_CODES, claim, total):
            if need > have:
                raise ValueError("%s needs %d %s but the hospital has %d - remove or edit this patient"
                                 % (r["name"], need, k, have))
        specs.append({"name": r["name"], "arrival": r["arrival"], "burst": r["burst"],
                      "severity": r["severity"], "claim": claim, "db_id": r["id"]})
    return specs, ndoc, names, total


def run_schedule(policy="priority", on_duty_ids=None, doctors=2, equipment=None, verbose=False):
    """Schedule ALL stored patients with ONE policy and save the run in the history.

    policy       'fcfs' | 'sjf' | 'priority' | 'rr'
    on_duty_ids  list of doctor ids on duty (or None to use the plain number `doctors`)
    equipment    {'vent':..,'ecg':..,'xray':..} or None to use the stored totals
    verbose      True adds a step-by-step text log under result['log']

    Returns a dict: policy, metrics, patients, gantt, doctor_names, run_id (and maybe log).
    """
    with database.connect() as c:
        specs, ndoc, names, total = _prepare(c, on_duty_ids, doctors, equipment)
        res = scheduler.simulate(specs, ndoc, total, policy, verbose=verbose)   # <- the actual simulation
        res["doctor_names"] = names
        # Save the whole result as JSON text in the 'runs' table...
        cur = c.execute("INSERT INTO runs(policy,doctors,vent,ecg,xray,result) VALUES(?,?,?,?,?,?)",
                        (policy, ndoc, *total, json.dumps(res)))
        res["run_id"] = cur.lastrowid
        # ...and one row per patient in 'outcomes' (handy for reports).
        c.executemany(
            "INSERT INTO outcomes(run_id,patient_id,patient_name,started,finished,waited,equipment_holds) "
            "VALUES(?,?,?,?,?,?,?)",
            [(cur.lastrowid, p["db_id"], p["name"], p["start"], p["finish"], p["wait"], p["denied"])
             for p in res["patients"]])
    return res


def compare_policies(on_duty_ids=None, doctors=2, equipment=None):
    """Run all four policies on the stored patients (nothing is saved).
    Returns {'fcfs': result, 'sjf': result, 'priority': result, 'rr': result}."""
    with database.connect() as c:
        specs, ndoc, names, total = _prepare(c, on_duty_ids, doctors, equipment)
    out = scheduler.compare_all(specs, ndoc, total)
    for r in out.values():
        r["doctor_names"] = names
    return out


def list_runs(limit=10):
    """The most recent saved runs (newest first), each with its full result decoded back into a dict."""
    with database.connect() as c:
        return [{**dict(r), "result": json.loads(r["result"])} for r in
                c.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (int(limit),))]


# ============================================================ scenarios
def load_scenario(k):
    """Replace the stored patients with built-in test case k (0-3) and set the number of
    doctors and equipment totals to match it. Returns the scenario title."""
    if not 0 <= k < len(SCENARIOS):
        raise ValueError("scenario must be 0-%d" % (len(SCENARIOS) - 1))
    sc = SCENARIOS[k]
    clear_patients()
    for p in sc["patients"]:
        add_patient(p["name"], p["severity"], p["arrival"], p["burst"], *p["claim"])
    # Put the first N doctors on duty, N = what the scenario wants.
    doctor_ids = [d["id"] for d in get_config()["doctors"]][:sc["doctors"]]
    set_config(doctor_ids, dict(zip(EQUIPMENT_CODES, sc["equipment"])))
    return sc["title"]
