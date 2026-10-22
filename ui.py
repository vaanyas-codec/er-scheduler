"""Tkinter interface for the ER scheduling simulator."""
import tkinter as tk
from tkinter import messagebox, ttk

import scheduler
import service
from scenarios import SCENARIOS


class ERSchedulerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ER Scheduler")
        self.root.geometry("1120x760")
        self.root.minsize(900, 620)
        service.init()

        self._configure_style()
        self.tabs = ttk.Notebook(root, padding=10)
        self.tabs.pack(fill="both", expand=True)

        self.patient_tab = ttk.Frame(self.tabs, padding=12)
        self.schedule_tab = ttk.Frame(self.tabs, padding=12)
        self.history_tab = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(self.patient_tab, text="Patients")
        self.tabs.add(self.schedule_tab, text="Scheduling")
        self.tabs.add(self.history_tab, text="Run history")

        self._build_patients_tab()
        self._build_schedule_tab()
        self._build_history_tab()
        self.refresh_patients()
        self.refresh_config()
        self.refresh_history()

    def _configure_style(self):
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Title.TLabel", font=("Segoe UI", 19, "bold"))
        style.configure("Subtitle.TLabel", foreground="#536174")
        style.configure("Treeview", rowheight=27)
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
        style.configure("Accent.TButton", font=("Segoe UI", 9, "bold"))

    def _heading(self, parent, title, subtitle):
        ttk.Label(parent, text=title, style="Title.TLabel").pack(anchor="w")
        ttk.Label(parent, text=subtitle, style="Subtitle.TLabel").pack(anchor="w", pady=(2, 12))

    def _build_patients_tab(self):
        self._heading(self.patient_tab, "Patient intake", "Register patients and review the current queue.")
        body = ttk.Frame(self.patient_tab)
        body.pack(fill="both", expand=True)
        form = ttk.LabelFrame(body, text="Add patient", padding=12)
        form.pack(side="left", fill="y", padx=(0, 12))
        table_frame = ttk.Frame(body)
        table_frame.pack(side="left", fill="both", expand=True)

        self.patient_fields = {}
        fields = [
            ("Name", "name", ""),
            ("Severity (1 critical - 4 minor)", "severity", "2"),
            ("Arrival time", "arrival", "0"),
            ("Treatment time", "burst", "5"),
            ("Ventilators", "vent", "0"),
            ("ECG machines", "ecg", "0"),
            ("X-ray units", "xray", "0"),
        ]
        for row, (label, key, default) in enumerate(fields):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=5)
            value = tk.StringVar(value=default)
            self.patient_fields[key] = value
            ttk.Entry(form, textvariable=value, width=24).grid(row=row, column=1, sticky="ew", padx=(10, 0), pady=5)

        ttk.Button(form, text="Add patient", style="Accent.TButton",
                   command=self.add_patient).grid(row=len(fields), column=0, columnspan=2, sticky="ew", pady=(14, 5))
        ttk.Button(form, text="Load selected sample scenario",
                   command=self.load_scenario).grid(row=len(fields) + 1, column=0, columnspan=2, sticky="ew", pady=5)
        ttk.Label(form, text="Loading a scenario replaces the current patient list.",
                  wraplength=220, style="Subtitle.TLabel").grid(row=len(fields) + 2, column=0, columnspan=2, sticky="w", pady=(7, 0))
        form.columnconfigure(1, weight=1)

        columns = ("id", "name", "severity", "arrival", "burst", "vent", "ecg", "xray")
        self.patient_table = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        labels = ("ID", "Name", "Severity", "Arrival", "Treatment", "Vent", "ECG", "X-ray")
        widths = (48, 130, 105, 70, 85, 55, 55, 55)
        for column, label, width in zip(columns, labels, widths):
            self.patient_table.heading(column, text=label)
            self.patient_table.column(column, width=width, anchor="center")
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.patient_table.yview)
        self.patient_table.configure(yscrollcommand=scrollbar.set)
        self.patient_table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        ttk.Button(self.patient_tab, text="Remove selected patient",
                   command=self.delete_patient).pack(anchor="e", pady=(10, 0))

    def _build_schedule_tab(self):
        self._heading(self.schedule_tab, "Scheduling control", "Choose available staff and equipment, then run or compare policies.")
        setup = ttk.LabelFrame(self.schedule_tab, text="Hospital resources", padding=12)
        setup.pack(fill="x")

        self.doctor_vars = {}
        self.doctor_frame = ttk.Frame(setup)
        self.doctor_frame.grid(row=0, column=0, sticky="nw", padx=(0, 32))
        ttk.Label(self.doctor_frame, text="Doctors on duty", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 6))

        self.equipment_vars = {}
        self.equipment_frame = ttk.Frame(setup)
        self.equipment_frame.grid(row=0, column=1, sticky="nw")
        ttk.Label(self.equipment_frame, text="Equipment totals", font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        self.policy_var = tk.StringVar(value="priority")
        self.policy_choices = {
            "fcfs": "FCFS",
            "sjf": "SJF (non-preemptive)",
            "priority": "Priority (preemptive + aging)",
            "rr": "Round Robin",
        }
        self.policy_var.set(self.policy_choices["priority"])
        controls = ttk.Frame(self.schedule_tab)
        controls.pack(fill="x", pady=12)
        ttk.Label(controls, text="Policy").pack(side="left")
        self.policy_box = ttk.Combobox(controls, state="readonly", width=32, textvariable=self.policy_var,
                                       values=list(self.policy_choices.values()))
        self.policy_box.pack(side="left", padx=8)
        self.policy_box.bind("<<ComboboxSelected>>", self._show_policy)
        ttk.Button(controls, text="Run selected policy", style="Accent.TButton",
                   command=self.run_selected).pack(side="left", padx=(4, 8))
        ttk.Button(controls, text="Compare all policies", command=self.compare_policies).pack(side="left")
        self.policy_hint = ttk.Label(self.schedule_tab, style="Subtitle.TLabel")
        self.policy_hint.pack(anchor="w", pady=(0, 8))

        self.results = ttk.Treeview(self.schedule_tab, show="tree headings", height=9)
        self.results["columns"] = ("wait", "tat", "response", "critical", "util", "switches", "denials")
        self.results.heading("#0", text="Policy / patient")
        self.results.column("#0", width=210)
        for key, label, width in (
                ("wait", "Avg wait", 80), ("tat", "Avg turnaround", 105), ("response", "Avg response", 100),
                ("critical", "Critical wait", 95), ("util", "Utilisation %", 95),
                ("switches", "Switches", 75), ("denials", "Equipment denials", 115)):
            self.results.heading(key, text=label)
            self.results.column(key, width=width, anchor="center")
        self.results.pack(fill="both", expand=True)

        self.detail = tk.Text(self.schedule_tab, height=8, wrap="none", state="disabled",
                              font=("Consolas", 9), background="#f7f9fc")
        self.detail.pack(fill="x", pady=(10, 0))
        self._show_policy()

    def _build_history_tab(self):
        self._heading(self.history_tab, "Saved runs", "Select a saved schedule to view its summary and patient outcomes.")
        self.history_table = ttk.Treeview(self.history_tab, columns=("id", "created", "policy", "doctors"),
                                          show="headings", selectmode="browse")
        for key, title, width in (("id", "Run", 70), ("created", "Created", 190),
                                  ("policy", "Policy", 220), ("doctors", "Doctors", 90)):
            self.history_table.heading(key, text=title)
            self.history_table.column(key, width=width, anchor="center")
        self.history_table.pack(fill="both", expand=True)
        self.history_table.bind("<<TreeviewSelect>>", self.show_history_detail)
        self.history_detail = tk.Text(self.history_tab, height=12, wrap="word", state="disabled",
                                      font=("Consolas", 9), background="#f7f9fc")
        self.history_detail.pack(fill="x", pady=(12, 0))
        ttk.Button(self.history_tab, text="Refresh history", command=self.refresh_history).pack(anchor="e", pady=(8, 0))
        self.history_runs = {}

    def _show_policy(self, _event=None):
        descriptions = {
            "fcfs": "First Come First Served",
            "sjf": "Shortest Job First (non-preemptive)",
            "priority": "Priority is preemptive, with aging and escalation to prevent starvation.",
            "rr": "Round Robin gives each patient a time slice.",
        }
        policy = next((key for key, label in self.policy_choices.items() if label == self.policy_var.get()), "")
        self.policy_hint.configure(text=descriptions.get(policy, ""))

    def refresh_patients(self):
        self.patient_table.delete(*self.patient_table.get_children())
        severity_names = scheduler.SEVERITY_NAMES
        for patient in service.list_patients():
            values = (
                patient["id"], patient["name"],
                "%d - %s" % (patient["severity"], severity_names[patient["severity"]]),
                patient["arrival"], patient["burst"], patient["vent"], patient["ecg"], patient["xray"])
            self.patient_table.insert("", "end", iid=str(patient["id"]), values=values)

    def refresh_config(self):
        config = service.get_config()
        for widget in self.doctor_frame.winfo_children()[1:]:
            widget.destroy()
        self.doctor_vars.clear()
        for doctor in config["doctors"]:
            variable = tk.BooleanVar(value=bool(doctor["on_duty"]))
            self.doctor_vars[doctor["id"]] = variable
            ttk.Checkbutton(self.doctor_frame, text=doctor["name"], variable=variable).pack(anchor="w")

        for widget in self.equipment_frame.winfo_children()[1:]:
            widget.destroy()
        for row, item in enumerate(config["equipment"], start=1):
            ttk.Label(self.equipment_frame, text=item["name"]).grid(row=row, column=0, sticky="w", pady=3)
            variable = tk.StringVar(value=str(item["total"]))
            self.equipment_vars[item["code"]] = variable
            ttk.Spinbox(self.equipment_frame, from_=0, to=20, width=6, textvariable=variable).grid(
                row=row, column=1, padx=(12, 0), pady=3)

    def _selected_doctors(self):
        return [doctor_id for doctor_id, variable in self.doctor_vars.items() if variable.get()]

    def _equipment(self):
        return {code: variable.get() for code, variable in self.equipment_vars.items()}

    def save_config(self):
        service.set_config(self._selected_doctors(), self._equipment())

    def add_patient(self):
        try:
            fields = self.patient_fields
            service.add_patient(fields["name"].get(), fields["severity"].get(),
                                fields["arrival"].get(), fields["burst"].get(),
                                fields["vent"].get(), fields["ecg"].get(), fields["xray"].get())
        except ValueError as error:
            messagebox.showerror("Invalid patient", str(error), parent=self.root)
            return
        fields["name"].set("")
        self.refresh_patients()

    def delete_patient(self):
        selection = self.patient_table.selection()
        if not selection:
            messagebox.showinfo("Select a patient", "Choose a patient to remove.", parent=self.root)
            return
        service.delete_patient(int(selection[0]))
        self.refresh_patients()

    def load_scenario(self):
        choices = ["%d. %s" % (index + 1, scenario["title"])
                   for index, scenario in enumerate(SCENARIOS)]
        selected = self._choose_scenario(choices)
        if selected is None:
            return
        if not messagebox.askyesno("Replace patient list",
                                   "Load this scenario and replace the current patients and resource settings?",
                                   parent=self.root):
            return
        try:
            service.load_scenario(selected)
        except ValueError as error:
            messagebox.showerror("Unable to load scenario", str(error), parent=self.root)
            return
        self.refresh_patients()
        self.refresh_config()

    def _choose_scenario(self, choices):
        dialog = tk.Toplevel(self.root)
        dialog.title("Load scenario")
        dialog.transient(self.root)
        dialog.grab_set()
        ttk.Label(dialog, text="Choose a built-in scenario:").pack(padx=16, pady=(16, 5), anchor="w")
        selected = tk.StringVar(value=choices[0])
        combo = ttk.Combobox(dialog, textvariable=selected, values=choices, state="readonly", width=75)
        combo.pack(padx=16, pady=5)
        result = {"index": None}

        def accept():
            result["index"] = choices.index(selected.get())
            dialog.destroy()

        buttons = ttk.Frame(dialog)
        buttons.pack(fill="x", padx=16, pady=12)
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text="Load", command=accept).pack(side="right", padx=(0, 8))
        self.root.wait_window(dialog)
        return result["index"]

    def _clear_results(self):
        self.results.delete(*self.results.get_children())
        self._set_text(self.detail, "")

    def _run_parameters(self):
        self.save_config()
        return {"on_duty_ids": self._selected_doctors(), "equipment": self._equipment()}

    def run_selected(self):
        try:
            params = self._run_parameters()
            policy = next(key for key, label in self.policy_choices.items() if label == self.policy_var.get())
            result = service.run_schedule(policy, **params, verbose=True)
        except ValueError as error:
            messagebox.showerror("Unable to run schedule", str(error), parent=self.root)
            return
        self._clear_results()
        self._add_result(result["policy"], result["metrics"])
        self._show_schedule_detail(result)
        self.refresh_history()

    def compare_policies(self):
        try:
            results = service.compare_policies(**self._run_parameters())
        except ValueError as error:
            messagebox.showerror("Unable to compare policies", str(error), parent=self.root)
            return
        self._clear_results()
        for result in results.values():
            self._add_result(result["policy"], result["metrics"])
        self._set_text(self.detail, "Comparison runs are not saved. Run a single policy to save it in history.")

    def _add_result(self, label, metrics):
        values = (
            "%.2f" % metrics["avg_wait"], "%.2f" % metrics["avg_tat"],
            "%.2f" % metrics["avg_resp"], "%.2f" % metrics["avg_wait_critical"],
            "%.1f" % metrics["utilisation"], metrics["switches"], metrics["denials"])
        self.results.insert("", "end", text=label, values=values)

    def _show_schedule_detail(self, result):
        metrics = result["metrics"]
        lines = [
            "Run #%s | %s | Makespan: %s | Invariants: %s" %
            (result["run_id"], result["policy"], metrics["makespan"],
             "PASS" if metrics["invariants_ok"] else "FAIL"),
            "",
            "Doctor timeline:",
        ]
        for doctor in sorted({item["doctor"] for item in result["gantt"]}):
            segments = ["[%s-%s %s]" % (item["start"], item["end"], item["patient"])
                        for item in result["gantt"] if item["doctor"] == doctor]
            lines.append("  Doctor %d: %s" % (doctor, "  ".join(segments) or "Idle"))
        lines.extend(("", "Patient outcomes:"))
        lines.extend("  %-16s start=%-4s finish=%-4s wait=%-4s turnaround=%-4s denied=%s" %
                     (patient["name"], patient["start"], patient["finish"], patient["wait"],
                      patient["tat"], patient["denied"]) for patient in result["patients"])
        if result.get("log"):
            lines.extend(("", "Simulation trace:"))
            lines.extend(result["log"])
        self._set_text(self.detail, "\n".join(lines))

    def refresh_history(self):
        self.history_table.delete(*self.history_table.get_children())
        self.history_runs = {}
        for run in service.list_runs(100):
            run_id = run["id"]
            self.history_runs[str(run_id)] = run
            self.history_table.insert("", "end", iid=str(run_id),
                                      values=(run_id, run["created"], run["policy"], run["doctors"]))
        self._set_text(self.history_detail, "")

    def show_history_detail(self, _event=None):
        selection = self.history_table.selection()
        if not selection:
            return
        run = self.history_runs[selection[0]]
        result = run["result"]
        metrics = result["metrics"]
        lines = [
            "Run #%s | %s | Created: %s" % (run["id"], result["policy"], run["created"]),
            "Avg wait: %.2f | Avg turnaround: %.2f | Avg response: %.2f | Utilisation: %.1f%%" %
            (metrics["avg_wait"], metrics["avg_tat"], metrics["avg_resp"], metrics["utilisation"]),
            "Makespan: %s | Context switches: %s | Equipment denials: %s | Invariants: %s" %
            (metrics["makespan"], metrics["switches"], metrics["denials"],
             "PASS" if metrics["invariants_ok"] else "FAIL"),
            "",
            "Patient outcomes:",
        ]
        lines.extend("  %-16s start=%-4s finish=%-4s wait=%-4s turnaround=%-4s denied=%s" %
                     (patient["name"], patient["start"], patient["finish"], patient["wait"],
                      patient["tat"], patient["denied"]) for patient in result["patients"])
        self._set_text(self.history_detail, "\n".join(lines))

    @staticmethod
    def _set_text(widget, value):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")


def run():
    root = tk.Tk()
    ERSchedulerApp(root)
    root.mainloop()


if __name__ == "__main__":
    run()
