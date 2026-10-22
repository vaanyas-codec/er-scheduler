"""
main.py  -  command-line runner (for trying the backend WITHOUT a GUI).
==============================================================================
Usage (type these in a terminal, in this folder):
  python3 main.py                  run the 4 built-in scheduling tests + all demos
  python3 main.py sim 1            just test case 1 (use 1, 2, 3 or 4)
  python3 main.py banker           Banker's algorithm demo
  python3 main.py intake           producer-consumer demo
  python3 main.py rw               readers-writers demo
  python3 main.py pipeline [1-4]   process + pipe + threads pipeline demo
  python3 main.py file patients.txt <doctors> <vent> <ecg> <xray>
        reads patients from a text file, one per line ('#' starts a comment):
        name arrival burst severity max_vent max_ecg max_xray

This file only PRINTS results. The real work is done by scheduler.py / os_demos.py,
which is exactly what your GUI will call instead of these print statements.
"""
import sys

import os_demos
import scheduler
from scenarios import SCENARIOS

LINE = "=" * 78   # divider used for headings


def print_case(title, specs, doctors, total, detail=True):
    """Run all 4 policies on one set of patients and print a comparison table.
    With detail=True also prints a step-by-step trace, a Gantt chart and a per-patient table
    for the Priority policy."""
    print("\n%s\n %s\n Doctors: %d | Equipment: Ventilator=%d ECG=%d X-Ray=%d | Patients: %d\n%s"
          % (LINE, title, doctors, *total, len(specs), LINE))
    results = scheduler.compare_all(specs, doctors, total)     # {policy_key: result}
    print("\n Policy comparison (times in time units):")
    print("  %-30s %8s %8s %8s %10s %6s %5s %6s" % ("Policy", "AvgWait", "AvgTAT", "AvgResp", "CritWait", "Util%", "Ctx", "Denied"))
    for r in results.values():
        m = r["metrics"]
        print("  %-30s %8.2f %8.2f %8.2f %10.2f %6.1f %5d %6d" % (r["policy"], m["avg_wait"], m["avg_tat"],
              m["avg_resp"], m["avg_wait_critical"], m["utilisation"], m["switches"], m["denials"]))
    ok = all(r["metrics"]["invariants_ok"] for r in results.values())
    print("\n Invariant check (resources conserved + state safe, every tick, all policies): %s" % ("PASS" if ok else "FAIL"))
    if not detail:
        return

    # Detailed view for one policy: re-run with verbose=True to get the text log.
    r = scheduler.simulate(specs, doctors, total, "priority", verbose=True)
    print("\n Detailed trace: %s" % r["policy"])
    for line in r["log"]:
        print("  " + line)
    print("\n  Gantt chart ([start-end) per doctor):")
    for d in range(1, doctors + 1):
        print("  Doctor %d: %s" % (d, " ".join("[%d-%d %s]" % (g["start"], g["end"], g["patient"])
                                              for g in r["gantt"] if g["doctor"] == d)))
    print("\n  %-3s %-7s %-12s %4s %5s %5s %6s %5s %4s %5s %6s" % ("ID", "Name", "Severity", "Arr", "Burst", "Start", "Finish", "Wait", "TAT", "Resp", "Denied"))
    for p in r["patients"]:
        print("  %-3d %-7s %-12s %4d %5d %5d %6d %5d %4d %5d %6d" % (p["id"], p["name"], p["severity_name"],
              p["arrival"], p["burst"], p["start"], p["finish"], p["wait"], p["tat"], p["resp"], p["denied"]))


def run_scenario(k):
    """Run built-in test case k (0-3)."""
    sc = SCENARIOS[k]
    print_case(sc["title"], sc["patients"], sc["doctors"], sc["equipment"])
    if k == 3:
        # Starvation demo: run Priority with escalation OFF and then ON and compare the
        # longest wait of the lone Minor patient.
        print("\n Starvation check (Priority policy, one Minor patient vs a continuous Urgent stream):")
        for esc in (0, scheduler.ESCALATE_WAIT):
            r = scheduler.simulate(sc["patients"], sc["doctors"], sc["equipment"], "priority", escalate=esc)
            minor = max([p["wait"] for p in r["patients"] if p["severity"] == 4] + [0])
            other = max([p["wait"] for p in r["patients"] if p["severity"] != 4] + [0])
            print("  Escalation %-8s: longest Minor wait = %3d | longest wait of others = %3d | makespan = %d"
                  % ("OFF" if esc == 0 else "ON (%d)" % esc, minor, other, r["metrics"]["makespan"]))


def run_file(path, doctors, total):
    """Read patients from a text file and run print_case on them."""
    specs = []
    with open(path) as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue                                    # skip comments and blank lines
            w = line.split()                                # split on spaces
            try:
                assert len(w) >= 7                          # need all 7 columns
                specs.append({"name": w[0][:15], "arrival": int(w[1]), "burst": int(w[2]),
                              "severity": int(w[3]), "claim": tuple(int(x) for x in w[4:7])})
            except (ValueError, IndexError, AssertionError):
                print("Skipping malformed line:", line.strip())
    print_case("CUSTOM INPUT FILE", specs[:scheduler.MAX_PATIENTS], doctors, total)


def show(title, result):
    """Print a demo's log lines under a heading."""
    print("\n%s\n %s\n%s" % (LINE, title, LINE))
    for line in result["log"]:
        print("  " + line)


def main(argv):
    """Look at the command-line words and decide what to run."""
    cmd = argv[1] if len(argv) > 1 else "all"      # no argument = everything
    if cmd == "all":
        for k in range(len(SCENARIOS)):
            run_scenario(k)
        show("BANKER'S ALGORITHM DEMO", os_demos.banker_demo())
        show("PRODUCER-CONSUMER DEMO", os_demos.producer_consumer_demo())
        show("READERS-WRITERS DEMO", os_demos.readers_writers_demo())
    elif cmd == "sim" and len(argv) > 2 and argv[2] in "1234" and len(argv[2]) == 1:
        run_scenario(int(argv[2]) - 1)             # user says 1-4, the list index is 0-3
    elif cmd == "banker":
        show("BANKER'S ALGORITHM DEMO", os_demos.banker_demo())
    elif cmd == "intake":
        show("PRODUCER-CONSUMER DEMO", os_demos.producer_consumer_demo())
    elif cmd == "rw":
        show("READERS-WRITERS DEMO", os_demos.readers_writers_demo())
    elif cmd == "pipeline":
        k = int(argv[2]) - 1 if len(argv) > 2 and argv[2] in "1234" else 0
        sc = SCENARIOS[k]
        r = os_demos.pipeline_demo(sc["patients"])
        show("PIPELINE: reception process -> pipe -> intake thread -> buffer -> triage threads", r)
        if r["identical"]:                         # only schedule if the data arrived intact
            print_case("SCHEDULING THE PATIENTS THAT ARRIVED THROUGH THE PIPELINE",
                       r["patients"], sc["doctors"], sc["equipment"], detail=False)
    elif cmd == "file" and len(argv) == 7:
        run_file(argv[2], int(argv[3]), [int(x) for x in argv[4:7]])
    else:
        print(__doc__)                             # unknown command -> show the help text above


# Required guard: the pipeline demo starts a child process, and on macOS/Windows that child
# re-imports this file. Without the guard it would run main() again inside the child.
if __name__ == "__main__":
    main(sys.argv)
