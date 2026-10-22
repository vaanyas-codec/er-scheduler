"""
test_backend.py  -  a quick self-check. Run it with:   python3 test_backend.py
==============================================================================
Prints PASS/FAIL for each check and stops at the first failure.  It uses a
TEMPORARY database, so it never touches your real er.db.
"""
import os, tempfile
# Point the database at a throw-away file BEFORE importing anything that uses it.
os.environ["ER_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

import os_demos, scheduler, service
from scenarios import SCENARIOS


def check(cond, msg):
    """Print PASS/FAIL for one check; exit with an error code on failure."""
    print(("PASS  " if cond else "FAIL  ") + msg)
    if not cond:
        raise SystemExit(1)


# This 'if' is REQUIRED: the pipeline demo starts a child process which re-imports this
# file (on macOS/Windows); without the guard it would run the tests again and again.
if __name__ == "__main__":
    service.init()

    # 1) Scheduler: all 4 built-in scenarios x all 4 policies must finish every patient
    #    and keep the Banker's invariants true on every tick.
    for k, sc in enumerate(SCENARIOS):
        for pol, r in scheduler.compare_all(sc["patients"], sc["doctors"], sc["equipment"]).items():
            check(r["metrics"]["invariants_ok"] and "warning" not in r, "scenario %d / %s" % (k + 1, pol))

    # 2) Service layer: database + scheduler working together.
    service.load_scenario(0)
    res = service.run_schedule("priority", on_duty_ids=[1, 2])
    check(len(res["patients"]) == 8 and res["doctor_names"] == ["Dr. Rao", "Dr. Iyer"], "run_schedule on scenario 1")
    check(len(service.list_runs()) == 1, "run saved to history")
    check(len(service.compare_policies(doctors=2)) == 4, "compare_policies")
    # Bad input must be rejected with ValueError (reaching check(False) would mean it was wrongly accepted).
    try:
        service.add_patient("X", 9, 0, 1); check(False, "bad severity rejected")
    except ValueError:
        check(True, "bad severity rejected")
    try:
        service.add_patient("Hog", 1, 0, 5, vent=5); service.run_schedule(doctors=1); check(False, "equipment overclaim rejected")
    except ValueError:
        check(True, "equipment overclaim rejected")

    # 3) The operating-system demos (delay=0 = no artificial pauses).
    b = os_demos.banker_demo()
    check(b["safe_sequence"] == ["P1", "P3", "P4", "P0", "P2"], "Banker safe sequence")   # the textbook answer
    check(os_demos.producer_consumer_demo(delay=0)["consistent"], "producer-consumer consistent")
    check(os_demos.readers_writers_demo(delay=0.2)["synchronized_ok"], "readers-writers synchronized run clean")
    p = os_demos.pipeline_demo(SCENARIOS[0]["patients"], delay=0)
    check(p["identical"], "pipeline data identical")
    print("\nAll checks passed.")
