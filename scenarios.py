"""
scenarios.py  -  the four ready-made test cases from the original C project.
==============================================================================
Each scenario is a dict with:
    title      description shown to the user
    doctors    how many doctors (= CPUs) are working
    equipment  (ventilators, ECG machines, X-ray units) the hospital owns
    patients   list of patient dicts (see _p below)

Time is measured in abstract "time units" (like clock ticks in an OS simulation).
"""


def _p(name, arrival, burst, severity, claim=(0, 0, 0)):
    """Small helper that builds one patient dict.

    name      patient name
    arrival   time unit at which the patient arrives
    burst     treatment time needed (CPU burst in OS terms)
    severity  1 = Critical, 2 = Urgent, 3 = Semi-urgent, 4 = Minor (priority in OS terms)
    claim     MAXIMUM equipment the patient may need: (ventilators, ECG, X-ray)
    """
    return {"name": name, "arrival": arrival, "burst": burst, "severity": severity, "claim": claim}


SCENARIOS = [
    # Test 1: a normal mixed workload - good for comparing the 4 policies.
    {"title": "TEST 1: Mixed arrivals, 2 doctors (general workload)",
     "doctors": 2, "equipment": (2, 2, 1), "patients": [
        _p("Asha", 0, 8, 4), _p("Ravi", 1, 5, 3, (0, 2, 0)),
        _p("Meera", 2, 4, 1, (2, 0, 0)), _p("Karan", 3, 6, 2, (0, 0, 1)),
        _p("Sita", 4, 3, 4), _p("Imran", 5, 7, 1, (2, 0, 0)),
        _p("Neha", 6, 2, 3), _p("Vikram", 8, 5, 2, (0, 2, 1))]},

    # Test 2: one doctor, critical patients keep arriving -> shows preemption and aging.
    {"title": "TEST 2: Critical patients arrive mid-treatment, 1 doctor (preemption & aging)",
     "doctors": 1, "equipment": (1, 1, 1), "patients": [
        _p("Minor1", 0, 6, 4), _p("Minor2", 1, 4, 4), _p("Crit1", 2, 5, 1),
        _p("Crit2", 3, 3, 1), _p("Urg1", 4, 3, 2), _p("Crit3", 5, 2, 1)]},

    # Test 3: patients compete for scarce equipment -> Banker's algorithm must refuse unsafe requests.
    {"title": "TEST 3: Equipment contention, 3 doctors (Banker's must deny unsafe requests)",
     "doctors": 3, "equipment": (2, 1, 1), "patients": [
        _p("Pat1", 0, 6, 1, (2, 0, 0)), _p("Pat2", 0, 6, 1, (2, 0, 0)),
        _p("Pat3", 1, 4, 2, (0, 1, 1)), _p("Pat4", 2, 5, 3, (2, 0, 0)),
        _p("Pat5", 2, 3, 4)]},

    # Test 4: starvation - one Minor patient ("Lone") vs an endless stream of Urgent patients (U1..U14).
    # Without the escalation rule, "Lone" would wait for ever.
    {"title": "TEST 4: Continuous Urgent stream, 1 doctor (starvation & escalation)",
     "doctors": 1, "equipment": (1, 1, 1),
     "patients": [_p("U0", 0, 3, 2), _p("Lone", 1, 3, 4)]
                 + [_p("U%d" % i, 3 * i, 3, 2) for i in range(1, 15)]},   # U1 arrives at 3, U2 at 6, ...
]
