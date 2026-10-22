"""
os_demos.py  -  demonstrations of classic Operating-System concepts.
==============================================================================
These are the "OS theory" parts of the project. They are separate from the
scheduler and are meant to be shown/explained in a viva or on a GUI tab.

    banker_demo()             Banker's algorithm on the famous textbook example
    producer_consumer_demo()  one reception thread fills a bounded buffer, doctor threads empty it
    readers_writers_demo()    doctors READ charts while nurses WRITE them - with and without locks
    pipeline_demo(patients)   separate PROCESS --pipe--> thread --buffer--> threads --> table

Every demo RETURNS a dict that includes a 'log' (list of text lines) instead of
printing, so a GUI can show it in a text box. Pass on_event=some_function to also
receive the lines live while the demo runs (called from worker threads!).
delay=1.0 is the original speed, delay=0 runs without pauses.
"""
import multiprocessing
import random
import threading
import time

import banker
from scheduler import Patient, SEVERITY_NAMES


class _Log:
    """A log that several threads can write to at once.
    The lock stops two threads from writing at the same instant and scrambling the order."""
    def __init__(self, on_event=None):
        self.lines, self._lock, self._cb = [], threading.Lock(), on_event

    def __call__(self, line):          # lets us use the object like a function: log("text")
        with self._lock:
            self.lines.append(line)
            if self._cb:
                self._cb(line)          # forward the line to the caller too (live display)


def _sleep(seconds, delay):
    """Sleep 'seconds' scaled by 'delay' (delay=0 means don't sleep at all)."""
    if delay > 0:
        time.sleep(seconds * delay)


# ================================================================ 1. BANKER'S
def banker_demo():
    """Run Banker's algorithm on the textbook example: 5 processes (P0-P4) and
    3 resource types A, B, C with totals 10, 5, 7."""
    # What each process holds now, and the most it may ever need:
    alloc = [(0, 1, 0), (2, 0, 0), (3, 0, 2), (2, 1, 1), (0, 0, 2)]
    maxes = [(7, 5, 3), (3, 2, 2), (9, 0, 2), (2, 2, 2), (4, 3, 3)]
    ps = []
    for i in range(5):
        # We reuse the Patient class just as a container with .max / .alloc / .active.
        p = Patient("P%d" % i, 0, 1, 1, maxes[i], pid=i + 1)
        p.alloc, p.active = list(alloc[i]), True
        ps.append(p)
    avail = [3, 3, 2]          # resources currently free
    log = ["Available: %s" % avail]
    for p in ps:
        log.append("%s  Alloc%s  Max%s  Need%s" % (p.name, tuple(p.alloc), tuple(p.max),
                   tuple(p.max[r] - p.alloc[r] for r in range(3))))
    # Is the starting state safe? If so, in which order can the processes finish?
    safe, seq = banker.is_safe(ps, avail)
    seq_names = ["P%d" % i for i in seq]
    log.append("Initial state is SAFE. Safe sequence: " + " -> ".join(seq_names) if safe
               else "Initial state is UNSAFE")

    texts = {banker.GRANTED: "GRANTED",
             banker.WAIT: "DENIED - resources not available, must wait",
             banker.UNSAFE: "DENIED - would leave the system in an UNSAFE state",
             banker.EXCEEDS: "ERROR - exceeds declared maximum"}
    requests = []
    # Three example requests: (who, how much). Expected: granted / must wait / unsafe.
    for who, req in [(1, (1, 0, 2)), (4, (3, 3, 0)), (0, (0, 2, 0))]:
        rc = banker.request(ps, ps[who], req, avail)
        requests.append({"process": "P%d" % who, "request": req, "code": rc, "outcome": texts[rc]})
        log.append("Request P%d %s: %s" % (who, req, texts[rc]))
    return {"initial_safe": safe, "safe_sequence": seq_names, "requests": requests, "log": log}


# ============================================ bounded buffer (used by 2 and 4)
class BoundedBuffer:
    """A fixed-size queue shared by producer and consumer threads.

    Two SEMAPHORES (counters that make threads wait) + one LOCK keep it correct:
        empty = number of free slots   -> a producer waits when it hits 0 (buffer full)
        full  = number of used slots   -> a consumer waits when it hits 0 (buffer empty)
        lock  = only one thread may change the buffer's internals at a time
    Putting None in the buffer is a 'poison pill': it tells a consumer "no more work, stop".
    """
    def __init__(self, size):
        self.size = size
        self.items = [None] * size           # the circular array
        self.head = self.tail = self.count = 0   # head = next to read, tail = next to write
        self.produced = self.consumed = 0
        self.empty = threading.Semaphore(size)   # starts with 'size' free slots
        self.full = threading.Semaphore(0)       # starts with 0 filled slots
        self.lock = threading.Lock()

    def put(self, item, on_put=None):
        self.empty.acquire()                 # wait for a free slot (blocks if full)
        with self.lock:                      # critical section
            self.items[self.tail] = item
            self.tail = (self.tail + 1) % self.size    # wrap around the end of the array
            self.count += 1
            if item is not None:             # poison pills are not counted
                self.produced += 1
                if on_put:
                    on_put(item, self.count)
        self.full.release()                  # tell consumers there is one more item

    def get(self):
        self.full.acquire()                  # wait for an item (blocks if empty)
        with self.lock:
            item = self.items[self.head]
            self.head = (self.head + 1) % self.size
            self.count -= 1
            if item is not None:
                self.consumed += 1
        self.empty.release()                 # tell producers there is one more free slot
        return item


# ====================================================== 2. PRODUCER-CONSUMER
def producer_consumer_demo(n_patients=12, buffer_size=5, n_doctors=2, delay=1.0, on_event=None):
    """Reception (producer) registers patients into a small buffer; doctor threads (consumers)
    take them out. Checks that no patient is lost or treated twice."""
    log = _Log(on_event)
    buf = BoundedBuffer(buffer_size)

    def reception():                          # the PRODUCER thread
        for i in range(1, n_patients + 1):
            rec = {"seq": i - 1, "name": "Pt%d" % i, "sev": (i * 7) % 4 + 1}   # made-up severity pattern
            _sleep(0.04, delay)               # patients walk in every so often
            buf.put(rec, lambda r, cnt: log("Reception : queued patient %2d %-7s (%-11s) | buffer %d/%d"
                                            % (r["seq"] + 1, r["name"], SEVERITY_NAMES[r["sev"]], cnt, buffer_size)))
        for _ in range(n_doctors):
            buf.put(None)                     # one poison pill per doctor: "go home"

    def doctor(did):                          # a CONSUMER thread
        while True:
            rec = buf.get()
            if rec is None:                   # poison pill -> stop
                break
            log("Doctor %d  : treating patient %2d %-7s (%s)" % (did, rec["seq"] + 1, rec["name"], SEVERITY_NAMES[rec["sev"]]))
            _sleep(0.12, delay)               # treatment takes longer than registration, so the buffer fills

    threads = [threading.Thread(target=reception)] + \
              [threading.Thread(target=doctor, args=(i + 1,)) for i in range(n_doctors)]
    for t in threads: t.start()
    for t in threads: t.join()                # wait for everyone to finish
    # Correct if everything registered was treated exactly once and nothing is left over.
    ok = buf.produced == buf.consumed and buf.count == 0
    log("Summary: registered=%d treated=%d buffer left=%d -> %s"
        % (buf.produced, buf.consumed, buf.count, "CONSISTENT (no loss, no duplication)" if ok else "MISMATCH"))
    return {"registered": buf.produced, "treated": buf.consumed, "buffer_left": buf.count,
            "consistent": ok, "log": log.lines}


# ======================================================== 3. READERS-WRITERS
class _RWLock:
    """Readers-writers lock with WRITER PRIORITY.
    Many readers may read at once, but a writer needs the chart to itself.
    A new reader must wait while any writer is waiting, so writers can't starve."""
    def __init__(self):
        self.cv = threading.Condition()       # a lock that threads can also wait on
        self.readers = self.waiting_writers = self.max_readers = 0
        self.writing = False

    def begin_read(self):
        with self.cv:
            self.cv.wait_for(lambda: not self.writing and self.waiting_writers == 0)
            self.readers += 1
            self.max_readers = max(self.max_readers, self.readers)   # stat: most simultaneous readers

    def end_read(self):
        with self.cv:
            self.readers -= 1
            if self.readers == 0:
                self.cv.notify_all()          # last reader out wakes up waiting writers

    def begin_write(self):
        with self.cv:
            self.waiting_writers += 1         # announce: a writer is waiting (blocks NEW readers)
            self.cv.wait_for(lambda: not self.writing and self.readers == 0)
            self.waiting_writers -= 1
            self.writing = True

    def end_write(self):
        with self.cv:
            self.writing = False
            self.cv.notify_all()


def _rw_run(protect, n_charts, n_readers, n_writers, reads, writes, delay):
    """One experiment. A chart is CONSISTENT only when b == 2*a. A writer changes a, then b,
    so a reader that sneaks in between sees a 'torn' chart (a changed, b not yet).
    protect=False: no locking (the race is visible). protect=True: locking (race is gone)."""
    charts = [{"a": 0, "b": 0, "version": 0} for _ in range(n_charts)]
    rw = _RWLock()
    stat = threading.Lock()   # protects the counters below
    s = {"reads": 0, "writes": 0, "torn": 0, "overlap": 0, "active_r": 0, "active_w": 0}

    def reader(k):            # a doctor reading charts
        rnd = random.Random(100 + k)          # fixed seed -> same random choices every run
        for _ in range(reads):
            ch = charts[rnd.randrange(n_charts)]
            if protect: rw.begin_read()
            with stat:
                if s["active_w"] > 0: s["overlap"] += 1    # a writer is active at the same time = a race
                s["active_r"] += 1
            a = ch["a"]; _sleep(0.0003, 1); b = ch["b"]    # read a, pause, read b (a writer may slip in)
            with stat:
                s["active_r"] -= 1; s["reads"] += 1
                if b != 2 * a: s["torn"] += 1              # inconsistent chart seen
            if protect: rw.end_read()
            _sleep((500 + rnd.randrange(1000)) / 1e6, delay)

    def writer(k):            # a nurse updating charts
        rnd = random.Random(900 + k)
        for j in range(writes):
            ch, v = charts[rnd.randrange(n_charts)], (k + 1) * 1000 + j + 1
            if protect: rw.begin_write()
            with stat:
                if s["active_r"] > 0 or s["active_w"] > 0: s["overlap"] += 1
                s["active_w"] += 1
            ch["a"] = v; _sleep(0.0003, 1); ch["b"] = 2 * v; ch["version"] += 1   # two-step update
            with stat:
                s["active_w"] -= 1; s["writes"] += 1
            if protect: rw.end_write()
            _sleep((1500 + rnd.randrange(1500)) / 1e6, delay)

    ts = [threading.Thread(target=writer, args=(i,)) for i in range(n_writers)] + \
         [threading.Thread(target=reader, args=(i,)) for i in range(n_readers)]
    for t in ts: t.start()
    for t in ts: t.join()
    return {"synchronized": protect, "reads": s["reads"], "writes": s["writes"], "torn_reads": s["torn"],
            "overlaps": s["overlap"], "max_concurrent_readers": rw.max_readers if protect else None}


def readers_writers_demo(n_charts=4, n_readers=4, n_writers=2, reads=25, writes=12, delay=1.0):
    """Run the experiment twice: WITHOUT locks (should show a race) and WITH locks (must be clean)."""
    n_charts = max(1, min(n_charts, 32))
    unsafe = _rw_run(False, n_charts, n_readers, n_writers, reads, writes, delay)
    safe = _rw_run(True, n_charts, n_readers, n_writers, reads, writes, delay)
    log = []
    for r in (unsafe, safe):
        line = "%-30s: reads=%d writes=%d | torn reads=%d | reader/writer overlaps=%d" % (
            "WITH synchronization" if r["synchronized"] else "WITHOUT (intentionally unsafe)",
            r["reads"], r["writes"], r["torn_reads"], r["overlaps"])
        if r["synchronized"]:
            line += " | max concurrent readers=%d" % r["max_concurrent_readers"]
        log.append(line)
    log.append("The unsafe run shows the race (overlaps are the reliable evidence; torn reads depend on timing).")
    log.append("The synchronized run must show 0 torn reads and 0 overlaps.")
    return {"unsafe": unsafe, "safe": safe, "synchronized_ok": safe["torn_reads"] == 0 and safe["overlaps"] == 0,
            "log": log}


# ================================================== 4. PIPELINE (process + pipe)
def _reception_process(conn, records):
    """Runs in a SEPARATE PROCESS (its own memory!). It can only talk to the main program
    through the pipe 'conn': it sends every record, then None as an 'end of data' marker."""
    for rec in records:
        conn.send(rec)
    conn.send(None)
    conn.close()


def pipeline_demo(patients, n_triage=2, buffer_size=5, delay=1.0, on_event=None):
    """Move patient data through a whole pipeline:

        reception PROCESS --pipe--> intake THREAD --bounded buffer--> triage THREADS --> patient table

    patients  list of dicts (name, arrival, burst, severity, claim) - e.g. SCENARIOS[0]["patients"]
    Afterwards it checks the table is IDENTICAL to what reception sent. The returned
    result['patients'] can be handed straight to scheduler.simulate().
    Must be called from code that is under  if __name__ == "__main__":
    """
    log = _Log(on_event)
    records = [dict(p, seq=i) for i, p in enumerate(patients)]   # add a sequence number to each record
    # Pipe(duplex=False) = one-way: recv_end can only read, send_end can only write.
    recv_end, send_end = multiprocessing.Pipe(duplex=False)
    child = multiprocessing.Process(target=_reception_process, args=(send_end, records))
    child.start()                         # the reception desk is now running as its own process
    send_end.close()                      # the parent keeps only the reading end

    buf = BoundedBuffer(buffer_size)
    table, table_lock, bad = {}, threading.Lock(), []

    def intake():                         # reads the pipe and puts records into the buffer (producer)
        while True:
            try:
                rec = recv_end.recv()
            except EOFError:              # pipe closed without our end marker = something went wrong
                bad.append(1)
                break
            if rec is None:               # normal end of data
                break
            _sleep(0.02, delay)
            buf.put(rec, lambda r, cnt: log("Pipe-in    : queued patient %2d %-7s | buffer %d/%d"
                                            % (r["seq"] + 1, r["name"], cnt, buffer_size)))
        for _ in range(n_triage):
            buf.put(None)                 # poison pill for each triage thread

    def triage(tid):                      # takes records out of the buffer into the table (consumer)
        while True:
            rec = buf.get()
            if rec is None:
                break
            _sleep(0.03, delay)
            with table_lock:
                table[rec["seq"]] = rec   # slot = sequence number, so thread speed can't change the result
            log("Triage %d   : admitted patient %2d %-7s -> table slot %d" % (tid, rec["seq"] + 1, rec["name"], rec["seq"]))

    threads = [threading.Thread(target=intake)] + [threading.Thread(target=triage, args=(i + 1,)) for i in range(n_triage)]
    for t in threads: t.start()
    for t in threads: t.join()
    recv_end.close()
    child.join()                          # wait for the child process to exit

    # Verify: same count, no pipe error, child exited normally (0), every record identical.
    identical = (len(table) == len(records) and not bad and child.exitcode == 0
                 and all(table.get(i) == r for i, r in enumerate(records)))
    log("Summary: sent=%d via pipe, queued=%d, admitted=%d, child exit=%s -> data %s"
        % (len(records), buf.produced, buf.consumed, child.exitcode,
           "IDENTICAL to what reception sent" if identical else "MISMATCH"))
    ordered = [{k: v for k, v in table[i].items() if k != "seq"} for i in sorted(table)]
    return {"identical": identical, "sent": len(records), "queued": buf.produced,
            "admitted": buf.consumed, "patients": ordered, "log": log.lines}
