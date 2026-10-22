"""
database.py  -  SQLite storage.
==============================================================================
SQLite is a database stored in ONE file (er.db) and built into Python, so there
is nothing to install.  This file only creates the tables and gives you a safe
way to open the database; the real queries live in service.py.

Tables
    patients   the people waiting to be treated (what you type into the GUI)
    doctors    the 4 doctors and whether each is on duty
    equipment  how many ventilators / ECG machines / X-ray units exist
    runs       history: every schedule you ran, with its full result as JSON text
    outcomes   one row per patient per run (start, finish, waiting time ...)
"""
import os, sqlite3
from contextlib import contextmanager

HERE = os.path.dirname(os.path.abspath(__file__))   # folder this file lives in
# The database file goes next to the code, unless the ER_DB environment variable
# says otherwise (test_backend.py uses that to avoid touching your real data).
DB_PATH = os.environ.get("ER_DB", os.path.join(HERE, "er.db"))

# 'IF NOT EXISTS' makes this safe to run every time the program starts.
# CHECK(...) lets the database itself refuse nonsense (e.g. severity 9).
SCHEMA = """
CREATE TABLE IF NOT EXISTS patients(
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
    severity INTEGER NOT NULL CHECK(severity BETWEEN 1 AND 4),
    arrival INTEGER NOT NULL CHECK(arrival>=0), burst INTEGER NOT NULL CHECK(burst>=1),
    vent INTEGER NOT NULL DEFAULT 0, ecg INTEGER NOT NULL DEFAULT 0, xray INTEGER NOT NULL DEFAULT 0,
    created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS runs(
    id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT DEFAULT CURRENT_TIMESTAMP,
    policy TEXT, doctors INTEGER, vent INTEGER, ecg INTEGER, xray INTEGER, result TEXT);
CREATE TABLE IF NOT EXISTS doctors(
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, on_duty INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS equipment(
    code TEXT PRIMARY KEY, name TEXT NOT NULL, total INTEGER NOT NULL CHECK(total>=0));
CREATE TABLE IF NOT EXISTS outcomes(
    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    patient_id INTEGER, patient_name TEXT NOT NULL, started INTEGER, finished INTEGER,
    waited INTEGER, equipment_holds INTEGER);
"""


@contextmanager
def connect():
    """Open the database for a 'with' block:

        with connect() as c:
            c.execute("SELECT ...")

    On success the changes are saved (commit); on an error they are undone
    (rollback); either way the connection is closed afterwards.
    """
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row            # rows behave like dicts: row["name"]
    c.execute("PRAGMA foreign_keys=ON")    # make SQLite enforce REFERENCES / ON DELETE CASCADE
    try:
        yield c                            # <- your 'with' block runs here
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def init_db():
    """Create the tables and, the very first time, add 4 doctors and 3 equipment types."""
    with connect() as c:
        c.executescript(SCHEMA)
        if not c.execute("SELECT 1 FROM doctors").fetchone():       # table empty -> seed it
            c.executemany("INSERT INTO doctors(name,on_duty) VALUES(?,?)",
                          [("Dr. Rao", 1), ("Dr. Iyer", 1), ("Dr. Khan", 0), ("Dr. Mehta", 0)])
        if not c.execute("SELECT 1 FROM equipment").fetchone():
            c.executemany("INSERT INTO equipment VALUES(?,?,?)",
                          [("vent", "Ventilator", 2), ("ecg", "ECG machine", 2), ("xray", "X-ray unit", 1)])
