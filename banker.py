"""
banker.py  -  Banker's algorithm (deadlock AVOIDANCE) for hospital equipment.
==============================================================================
THE PROBLEM
    Patients need shared equipment (ventilator, ECG machine, X-ray unit).
    If two patients each hold half of what they need and both wait for the
    other's equipment, nobody can ever finish: that is a DEADLOCK.

THE IDEA (Dijkstra's Banker's algorithm)
    Before giving equipment to a patient, pretend to give it, then ask:
    "Is there still SOME order in which every patient could finish?"
        - yes -> the state is SAFE   -> really give the equipment
        - no  -> the state is UNSAFE -> refuse, make the patient wait

OS word      ->  our meaning
    process      patient
    resource     equipment type (index 0 = ventilator, 1 = ECG, 2 = X-ray)
    max          the most equipment the patient may ever ask for (declared upfront)
    alloc        equipment the patient holds right now
    need         max - alloc  (what they might still ask for)
    avail        equipment currently free in the hospital

Any object that has the attributes  .max  .alloc  .active  can be used here.
(scheduler.Patient has them.)
"""

NRES = 3                                   # number of resource types
RES_NAMES = ("Ventilator", "ECG", "X-Ray")  # human-readable names, same order as the lists

# Result codes returned by request():
EXCEEDS = -1   # patient asked for more than its declared maximum (a bug / invalid request)
WAIT = 0       # not enough equipment free right now -> just wait
GRANTED = 1    # request accepted, equipment handed over
UNSAFE = 2     # equipment is free, but giving it would risk a deadlock -> refused


def is_safe(patients, avail):
    """The SAFETY algorithm: can every active patient finish in some order?

    Returns (True/False, safe_sequence) where safe_sequence is the list of
    patient indices in the order they could finish.
    """
    work = list(avail)   # equipment we imagine to be free (grows as imaginary patients finish)

    # Only patients that currently hold equipment (.active) matter.
    # 'finished[i]' starts True for patients that hold nothing (nothing to wait for).
    finished = [not p.active for p in patients]
    active = sum(1 for p in patients if p.active)

    seq = []             # the order in which patients finish
    progress = True      # did we manage to finish at least one patient this pass?
    # Keep sweeping through the patients until nobody else can finish.
    while progress and len(seq) < active:
        progress = False
        for i, p in enumerate(patients):
            if finished[i]:
                continue
            # Can this patient get everything it might still need (max - alloc)
            # from the equipment that is free in our imaginary 'work'?
            if all(p.max[r] - p.alloc[r] <= work[r] for r in range(NRES)):
                # Yes: imagine it finishes and hands all its equipment back.
                for r in range(NRES):
                    work[r] += p.alloc[r]
                finished[i] = True
                seq.append(i)
                progress = True

    # Safe only if EVERY active patient could be finished.
    return len(seq) == active, seq


def request(patients, p, req, avail):
    """The RESOURCE-REQUEST algorithm: patient p asks for 'req' (a list of 3 numbers).

    If granted, p.alloc and avail are updated IN PLACE.  If not, nothing changes.
    Returns one of EXCEEDS / WAIT / GRANTED / UNSAFE.
    """
    # Rule 1: a patient may never ask for more than it declared at the start.
    for r in range(NRES):
        if req[r] > p.max[r] - p.alloc[r]:
            return EXCEEDS
    # Rule 2: the equipment must actually be free right now.
    for r in range(NRES):
        if req[r] > avail[r]:
            return WAIT

    # Rule 3: pretend to grant the request...
    was_active = p.active
    p.active = True
    for r in range(NRES):
        avail[r] -= req[r]
        p.alloc[r] += req[r]
    # ...and keep it only if the resulting state is safe.
    if is_safe(patients, avail)[0]:
        return GRANTED

    # Not safe: undo the pretend-grant exactly.
    for r in range(NRES):
        avail[r] += req[r]
        p.alloc[r] -= req[r]
    p.active = was_active
    return UNSAFE
