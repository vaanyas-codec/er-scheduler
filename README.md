# ER Scheduler - pure Python backend

Python rewrite of the C engine + web server, with no GUI code and no outside packages
(standard library only). Write your GUI (Tkinter, PyQt, ...) on top of `service.py`.

## Files
| File | What it does |
|---|---|
| `banker.py` | Banker's algorithm (`is_safe`, `request`) |
| `scheduler.py` | The simulator: FCFS, SJF, Priority (preemptive + aging + escalation), Round Robin |
| `scenarios.py` | The 4 built-in test cases |
| `database.py` | SQLite storage (same schema as the old `er.db`, so an old file still works) |
| `service.py` | **The API your GUI should call** |
| `os_demos.py` | Banker demo, producer-consumer, readers-writers, process+pipe pipeline |
| `ui.py` | Tkinter interface for patient intake, scheduling, comparisons, and history |
| `main.py` | Launches the UI by default; also supports command-line demos |
| `test_backend.py` | Self-check (`python test_backend.py`) |

## How to run (VS Code or any terminal)
1. Open the `er_scheduler` folder in VS Code (File > Open Folder).
2. Open a terminal: menu Terminal > New Terminal (shortcut Ctrl+`). It opens inside the folder.
3. Run one of these (use `python` instead of `python3` on Windows):

        python3 test_backend.py       # self-check, should end with "All checks passed."
        python main.py                # launch the full project UI
        python ui.py                  # launch the UI directly
        python main.py sim 1          # one built-in test case (1-4)
        python main.py all            # everything (takes a few seconds)
        python3 main.py banker        # also: intake | rw | pipeline

Nothing needs installing beyond Python with Tkinter enabled. `er.db` is created automatically on first use.
The play button in VS Code also works: it runs the file that is open.

`er.db` is created next to the code on first run (or set the `ER_DB` environment variable).

## Using it from a GUI
    import service
    service.init()                                   # once at start-up

    service.add_patient("Asha", severity=2, arrival=0, burst=5, vent=1)   # severity 1=critical .. 4=minor
    service.list_patients()          # -> list of dicts
    service.delete_patient(3);  service.clear_patients()

    service.get_config()             # doctors (id, name, on_duty) + equipment totals
    service.set_config([1, 2], {"vent": 2, "ecg": 2, "xray": 1})

    res = service.run_schedule("priority", on_duty_ids=[1, 2])   # "fcfs" | "sjf" | "priority" | "rr"
    res["metrics"]     # avg_wait, avg_tat, avg_resp, avg_wait_critical, utilisation, makespan, switches, denials, invariants_ok
    res["patients"]    # per patient: name, start, finish, wait, tat, resp, denied, ...
    res["gantt"]       # [{"doctor":1,"patient":"Asha","patient_id":1,"start":0,"end":5}, ...] -> draw as bars
    service.compare_policies(on_duty_ids=[1, 2])   # all 4 policies, not saved
    service.list_runs()                            # history
    service.load_scenario(0)                       # fill the DB with built-in test case 1-4 (index 0-3)

Bad input raises `ValueError` with a readable message, so in the GUI:
`try: ... except ValueError as e: show_error(str(e))`.

### GUI tips
* Run slow work (the threaded demos) in a background thread; `os_demos` functions accept
  `on_event=callback` for live log lines, but those arrive from worker threads - pass them to the
  GUI thread through a `queue.Queue` (Tkinter: poll it with `after()`).
* `pipeline_demo` starts a child process, so your program's entry point must be inside
  `if __name__ == "__main__":`.
* `delay=0` makes the demos run instantly; `delay=1.0` is the original pace.

## Differences from the C/web version
* `gantt` entries are dicts (the old JSON used lists); `patients` has a few extra fields.
* `run_schedule` takes equipment totals from the database unless you pass them (the old server
  silently defaulted to 2/2/1).
* The demos return data (with a `log` list) instead of printing.
* The HTTP server, the C binary and the `static/` page are gone; nothing needs compiling.
