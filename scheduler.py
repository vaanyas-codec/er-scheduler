"""
scheduler.py  -  the heart of the project: the doctor-scheduling simulator.
==============================================================================
It simulates an emergency room one time unit ("tick") at a time and decides
which patient each doctor treats.  This is a CPU-scheduling simulator wearing
a hospital costume:

    Process  -> Patient          CPU    -> Doctor
    Priority -> Severity         Burst  -> Treatment time
    Shared resources -> Ventilator, ECG machine, X-ray unit (handed out by banker.py)

THE FOUR POLICIES (who gets treated next?)
    "fcfs"      First Come First Served: whoever arrived first.
    "sjf"       Shortest Job First (non-preemptive): shortest remaining treatment.
    "priority"  Most severe first. PREEMPTIVE (a critical patient can take a doctor
                away from a less urgent one), with AGING (long waits raise priority a
                little) and ESCALATION (after 20 units of waiting, treated as Critical)
                so nobody starves.
    "rr"        Round Robin: everyone gets a time slice of 3 units, then goes to the back.

EQUIPMENT RULE (two stages, both through Banker's algorithm)
    Stage 1: when treatment starts the patient asks for HALF of its declared claim.
    Stage 2: once half the treatment is done it asks for the rest.
    If Banker's algorithm says "unsafe", the patient is 'blocked' and skipped for now.

Everything in this file is deterministic: the same input always gives the same output.
"""
import banker

# ----------------------------------------------------------------- constants
MAX_PATIENTS = 32     # limit inherited from the C program
MAX_DOCTORS = 4
MAX_T = 2000          # safety stop: the simulation never runs past 2000 ticks
AGE_STEP = 4          # every 4 time units of waiting, a patient's priority improves by 1
RR_QUANTUM = 3        # Round Robin time slice
ESCALATE_WAIT = 20    # after waiting this long, a patient is treated as Critical

SEVERITY_NAMES = {1: "Critical", 2: "Urgent", 3: "Semi-urgent", 4: "Minor"}
# key = short code you pass to the functions, value = pretty name for display
POLICY_NAMES = {
    "fcfs": "FCFS",
    "sjf": "SJF (non-preemptive)",
    "priority": "Priority (preemptive+aging)",
    "rr": "Round Robin",
}

# The possible states of a patient (like process states in an OS):
NOT_ARRIVED, READY, RUNNING, DONE = range(4)   # = 0, 1, 2, 3


class Patient:
    """One patient, plus all the bookkeeping the simulator needs about them."""

    def __init__(self, name, arrival, burst, severity, claim=(0, 0, 0), pid=0, db_id=None):
        self.id = pid          # 1-based position in the list; 0 is reserved for "idle" in the timeline
        self.db_id = db_id     # primary key in the database (None if not from the DB)
        self.name = name
        self.arrival = arrival      # when the patient arrives
        self.burst = burst          # total treatment time needed
        self.severity = severity    # 1 (critical) .. 4 (minor)
        self.max = list(claim)      # declared maximum equipment claim [vent, ecg, xray]
        self.reset()                # set all the "live" fields to their starting values

    def reset(self):
        """Put the patient back to 'not yet simulated'. Called before every simulation."""
        self.alloc = [0] * banker.NRES   # equipment currently held
        self.remaining = self.burst      # treatment time still needed
        self.first_start = -1            # when a doctor first started on them (-1 = never)
        self.finish = 0                  # when treatment finished
        self.ready_since = 0             # since when they have been waiting in the ready queue
        self.quantum_used = 0            # Round Robin: time used in the current slice
        self.run_prio = 0                # priority frozen at the moment a doctor started on them
        self.active = False              # True while holding equipment (matters for Banker's)
        self.stage1_done = False         # has the first equipment request been granted?
        self.stage2_done = False         # has the second equipment request been granted?
        self.blocked = False             # currently refused equipment?
        self.denials = 0                 # how many times equipment was refused
        self.state = NOT_ARRIVED


def validate(patients, doctors, total):
    """Raise ValueError with a readable message if the input can't be simulated."""
    if not 1 <= len(patients) <= MAX_PATIENTS:
        raise ValueError("need between 1 and %d patients" % MAX_PATIENTS)
    if not 1 <= doctors <= MAX_DOCTORS:
        raise ValueError("need between 1 and %d doctors" % MAX_DOCTORS)
    for p in patients:
        if p.burst < 1 or p.arrival < 0 or not 1 <= p.severity <= 4:
            raise ValueError("invalid data for patient %s" % p.name)
        for r in range(banker.NRES):
            # a patient can't claim more equipment than the hospital owns - it could never be served
            if not 0 <= p.max[r] <= total[r]:
                raise ValueError("%s claims more %s than the hospital owns"
                                 % (p.name, banker.RES_NAMES[r]))


class Simulation:
    """Runs ONE simulation: one policy, one set of patients, one set of doctors."""

    def __init__(self, patients, doctors, total, policy="priority",
                 escalate=ESCALATE_WAIT, verbose=False):
        if policy not in POLICY_NAMES:
            raise ValueError("unknown policy: %s" % policy)
        validate(patients, doctors, total)
        self.ps = patients            # NOTE: these objects get modified, so give each run fresh ones
        self.n = len(patients)
        self.ndoc = doctors
        self.total = list(total)      # equipment the hospital owns
        self.avail = list(total)      # equipment currently free (starts as everything)
        self.policy = policy
        self.escalate = escalate      # 0 switches escalation off (used for the starvation demo)
        self.verbose = verbose        # if True, keep a text log of what happens each tick
        self.log_lines = []
        self.t = 0                    # the simulation clock
        self.ctx = 0                  # context switches: times a doctor changed to a different patient
        self.inv_fail = 0             # how many ticks broke the safety invariants (should stay 0)
        self.running = [None] * doctors   # which patient each doctor is treating right now
        self.last = [None] * doctors      # which patient each doctor treated most recently
        # timeline[d][t] = id of the patient doctor d treated at tick t (0 = idle) -> used for the Gantt chart
        self.timeline = [[] for _ in range(doctors)]
        for p in self.ps:
            p.reset()

    # ================================================================ helpers
    def _log(self, msg, t=None):
        """Add a line to the text log (only when verbose=True)."""
        if self.verbose:
            self.log_lines.append("[t=%3d] %s" % (self.t if t is None else t, msg))

    def eff_prio(self, p, t):
        """Effective priority of patient p at time t. LOWER NUMBER = MORE URGENT."""
        # Escalation: waited too long -> treat as Critical (priority 1).
        if self.escalate > 0 and t - p.ready_since >= self.escalate:
            return 1
        # Aging: every AGE_STEP units of waiting improves priority by 1.
        e = p.severity - (t - p.ready_since) // AGE_STEP
        # ...but aging can lift a patient by at most ONE level and never up to Critical,
        # so a long-waiting Minor patient can reach Semi-urgent but not overtake Urgent ones.
        floor_ = 1 if p.severity == 1 else max(2, p.severity - 1)
        return max(e, floor_)

    def better(self, a, b, t):
        """True if patient a should be treated BEFORE patient b under the current policy."""
        pol = self.policy
        if pol == "fcfs":
            if a.arrival != b.arrival:
                return a.arrival < b.arrival            # earlier arrival wins
        elif pol == "sjf":
            if a.remaining != b.remaining:
                return a.remaining < b.remaining        # shorter remaining time wins
            if a.arrival != b.arrival:
                return a.arrival < b.arrival            # tie -> earlier arrival
        elif pol == "priority":
            ea, eb = self.eff_prio(a, t), self.eff_prio(b, t)
            if ea != eb:
                return ea < eb                          # more urgent wins
            if a.ready_since != b.ready_since:
                return a.ready_since < b.ready_since    # tie -> waiting longer
        elif pol == "rr":
            if a.ready_since != b.ready_since:
                return a.ready_since < b.ready_since    # whoever joined the queue first
        return a.id < b.id                              # final tie-break: list order (keeps results deterministic)

    def _deny(self, p, stage, rc):
        """Record that p's equipment request was refused (counted once per blocked period)."""
        if not p.blocked:
            p.blocked = True
            p.denials += 1
            why = "unsafe state (deadlock risk)" if rc == banker.UNSAFE else "not enough free equipment"
            self._log("%-6s equipment request (stage %d) DENIED - %s" % (p.name, stage, why))

    def try_stages(self, p):
        """Try to get patient p the equipment it needs RIGHT NOW. True = patient can be treated.

        Stage 1 = half the claim at first dispatch, stage 2 = the rest once half the
        treatment is done. Refusal comes from Banker's algorithm (banker.request).
        """
        if not p.stage1_done:
            # A 1-unit treatment has no 'halfway', so it asks for everything at once.
            whole = p.burst < 2
            req = [m if whole else m // 2 for m in p.max]
            rc = banker.request(self.ps, p, req, self.avail)
            if rc != banker.GRANTED:
                self._deny(p, 1, rc)
                return False
            p.stage1_done = True
            if whole:
                p.stage2_done = True
        # Stage 2 is requested once at least half of the treatment has been done.
        if not p.stage2_done and p.remaining * 2 <= p.burst:
            req = [p.max[r] - p.alloc[r] for r in range(banker.NRES)]   # the rest of the claim
            rc = banker.request(self.ps, p, req, self.avail)
            if rc != banker.GRANTED:
                self._deny(p, 2, rc)
                return False
            p.stage2_done = True
        if p.blocked:
            self._log("%-6s equipment request now granted" % p.name)
        p.blocked = False
        return True

    def invariants_broken(self):
        """Self-check run after every tick. Returns True if something is WRONG:
        - free equipment is negative, or
        - equipment was created/lost (free + held must always equal the total), or
        - the allocation is no longer a safe state (Banker's guarantee violated)."""
        for r in range(banker.NRES):
            if self.avail[r] < 0:
                return True
            if self.avail[r] + sum(p.alloc[r] for p in self.ps) != self.total[r]:
                return True
        return not banker.is_safe(self.ps, self.avail)[0]

    def _dispatch(self, d, p):
        """Doctor d starts treating patient p."""
        p.state = RUNNING
        p.quantum_used = 0
        # Remember the priority p had when it got the doctor; preemption compares against this.
        p.run_prio = self.eff_prio(p, self.t) if self.policy == "priority" else p.severity
        if p.first_start < 0:
            p.first_start = self.t        # first time ever on a doctor -> used for response time
        self.running[d] = p
        if self.last[d] is not p:         # doctor switched to a different patient
            self.ctx += 1
        self.last[d] = p
        self._log("Doctor %d starts %-6s (%s, remaining %d)"
                  % (d + 1, p.name, SEVERITY_NAMES[p.severity], p.remaining))

    def _unassign(self, d, why):
        """Doctor d stops treating its current patient; the patient goes back to the ready queue."""
        p = self.running[d]
        self._log("Doctor %d stops %-6s (%s)" % (d + 1, p.name, why))
        p.state = READY
        p.ready_since = self.t            # waiting starts again from now
        p.quantum_used = 0
        self.running[d] = None

    def _best_ready(self, tried):
        """The best READY patient (by the policy) that we haven't already tried this tick."""
        best = None
        for p in self.ps:
            if p.state == READY and p.id not in tried:
                if best is None or self.better(p, best, self.t):
                    best = p
        return best

    def _pick(self, tried):
        """Choose the best READY patient whose equipment request also succeeds.
        Patients that get refused are remembered in 'tried' so we move on to the next best."""
        while True:
            best = self._best_ready(tried)
            if best is None:
                return None               # nobody suitable
            tried.add(best.id)
            if self.try_stages(best):
                return best

    # ================================================================== run
    def run(self):
        """The main simulation loop. One loop pass = one time unit. Returns the result dict."""
        ps, nd, pol = self.ps, self.ndoc, self.policy
        done = busy = 0   # done = patients finished; busy = total doctor-ticks spent treating
        while done < self.n and self.t < MAX_T:
            t = self.t
            tried = set()     # patients already tried this tick (so refused ones aren't retried endlessly)

            # ---- Step 1: arrivals - patients whose arrival time has come join the ready queue
            for p in ps:
                if p.state == NOT_ARRIVED and p.arrival <= t:
                    p.state = READY
                    p.ready_since = t
                    self._log("%-6s arrives (%s, treatment %d)"
                              % (p.name, SEVERITY_NAMES[p.severity], p.burst))

            # ---- Step 2: a patient already being treated may need its stage-2 equipment;
            #              if that is refused the doctor must put the patient aside
            for d in range(nd):
                if self.running[d] is not None and not self.try_stages(self.running[d]):
                    self._unassign(d, "waiting for equipment")

            # ---- Step 3: Round Robin only - a patient whose time slice is used up goes to the back
            if pol == "rr":
                for d in range(nd):
                    p = self.running[d]
                    if p is None or p.quantum_used < RR_QUANTUM:
                        continue
                    if any(q.state == READY for q in ps):
                        self._unassign(d, "quantum expired")     # somebody else is waiting
                    else:
                        p.quantum_used = 0                       # nobody waiting: carry on

            # ---- Step 4: every idle doctor takes the best waiting patient
            for d in range(nd):
                if self.running[d] is None:
                    p = self._pick(tried)
                    if p is not None:
                        self._dispatch(d, p)

            # ---- Step 5: Priority policy only - PREEMPTION.
            #      If all doctors are busy but a waiting patient is MORE urgent than the least
            #      urgent patient being treated, swap them.
            if pol == "priority":
                while True:
                    worst, idle = None, False        # worst = doctor treating the least urgent patient
                    for d in range(nd):
                        if self.running[d] is None:
                            idle = True              # a free doctor exists -> no need to preempt
                            break
                        if worst is None or self.running[d].run_prio > self.running[worst].run_prio:
                            worst = d
                    if idle or worst is None:
                        break
                    best = self._best_ready(tried)
                    if best is None:
                        break
                    if self.eff_prio(best, t) >= self.running[worst].run_prio:
                        break                        # waiting patient is not more urgent -> stop
                    tried.add(best.id)
                    if self.try_stages(best):        # only preempt if the newcomer can get its equipment
                        self._unassign(worst, "preempted by more urgent patient")
                        self._dispatch(worst, best)

            # ---- Step 6: execute ONE time unit of treatment for every busy doctor
            for d in range(nd):
                p = self.running[d]
                if p is None:
                    self.timeline[d].append(0)       # idle doctor
                    continue
                self.timeline[d].append(p.id)
                p.remaining -= 1
                p.quantum_used += 1
                busy += 1
                if p.remaining == 0:                 # treatment finished -> discharge
                    p.state = DONE
                    p.finish = t + 1
                    for r in range(banker.NRES):     # give all equipment back
                        self.avail[r] += p.alloc[r]
                        p.alloc[r] = 0
                    p.active = False
                    self.running[d] = None
                    done += 1
                    self._log("%-6s discharged, equipment released" % p.name, t + 1)

            # ---- Step 7: sanity check, then advance the clock
            if self.invariants_broken():
                self.inv_fail += 1
            self.t += 1

        self.busy = busy
        self.all_done = done == self.n   # False only if we hit MAX_T with patients unfinished
        return self.result()

    # ============================================================== results
    def gantt(self):
        """Turn the tick-by-tick timeline into treatment blocks for a Gantt chart.

        Consecutive ticks with the same patient are merged, e.g. [3,3,3,0,0,5] becomes
        patient 3 from 0 to 3, then patient 5 from 5 to 6 (idle time is left out).
        Returns a list of {doctor, patient_id, patient, start, end}; 'end' is exclusive.
        """
        blocks = []
        for d in range(self.ndoc):
            t0 = 0
            row = self.timeline[d]
            while t0 < self.t:
                pid, t1 = row[t0], t0
                while t1 < self.t and row[t1] == pid:     # extend the block while the patient stays the same
                    t1 += 1
                if pid:                                   # 0 = idle -> no block
                    blocks.append({"doctor": d + 1, "patient_id": pid,
                                   "patient": self.ps[pid - 1].name, "start": t0, "end": t1})
                t0 = t1
        return blocks

    def result(self):
        """Compute the final statistics. Definitions used (standard OS-scheduling ones):
            TAT  (turnaround) = finish - arrival
            wait              = TAT - treatment time
            resp (response)   = first_start - arrival
        """
        n = self.n
        wait = tat = resp = crit_wait = 0
        denials = crit = 0
        rows = []
        for p in self.ps:
            p_tat = p.finish - p.arrival
            p_wait = p_tat - p.burst
            p_resp = p.first_start - p.arrival
            wait += p_wait; tat += p_tat; resp += p_resp; denials += p.denials
            if p.severity == 1:                 # track waiting time of Critical patients separately
                crit_wait += p_wait; crit += 1
            rows.append({"id": p.id, "db_id": p.db_id, "name": p.name,
                         "severity": p.severity, "severity_name": SEVERITY_NAMES[p.severity],
                         "arrival": p.arrival, "burst": p.burst,
                         "start": p.first_start, "finish": p.finish,
                         "wait": p_wait, "tat": p_tat, "resp": p_resp, "denied": p.denials})
        res = {
            "policy": POLICY_NAMES[self.policy],
            "policy_key": self.policy,
            "metrics": {
                "avg_wait": round(wait / n, 2),
                "avg_tat": round(tat / n, 2),
                "avg_resp": round(resp / n, 2),
                "avg_wait_critical": round(crit_wait / crit, 2) if crit else 0.0,
                # utilisation = % of doctor-time spent treating (busy ticks / all doctor ticks)
                "utilisation": round(100.0 * self.busy / (self.ndoc * self.t), 1),
                "makespan": self.t,             # time at which the last patient left
                "switches": self.ctx,
                "denials": denials,             # total refused equipment requests
                "invariants_ok": self.inv_fail == 0,
            },
            "patients": rows,
            "gantt": self.gantt(),
        }
        if not self.all_done:
            res["warning"] = "simulation stopped at MAX_T with unfinished patients"
        if self.verbose:
            res["log"] = self.log_lines
        return res


# ================================================== convenience functions
def simulate(specs, doctors, total, policy="priority", escalate=ESCALATE_WAIT, verbose=False):
    """Easiest way to run a simulation from plain data.

    specs   list of dicts: name, arrival, burst, severity, claim=(vent, ecg, xray)
            (an optional db_id is carried through to the result)
    doctors number of doctors, total = (vent, ecg, xray) the hospital owns.
    Returns the result dict described in Simulation.result().
    """
    patients = [Patient(s["name"], s["arrival"], s["burst"], s["severity"],
                        s.get("claim", (0, 0, 0)), pid=i + 1, db_id=s.get("db_id"))
                for i, s in enumerate(specs)]       # fresh Patient objects every call
    return Simulation(patients, doctors, total, policy, escalate, verbose).run()


def compare_all(specs, doctors, total, escalate=ESCALATE_WAIT):
    """Run all four policies on the same patients. Returns {policy_key: result}."""
    return {k: simulate(specs, doctors, total, k, escalate) for k in POLICY_NAMES}
