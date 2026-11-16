"""
Evaluation gate for the morning note.

Each case is a small, known sleep history with the answer we expect.
The gate fails (exit code 1) if the pass rate drops below the threshold,
so a change that makes the note wrong, or unsafe, cannot ship.

    python evals/run_evals.py
"""
import datetime as dt, json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from sleep_slo import assess, generate_note, evening_minutes, retrieve_tip  # noqa: E402

THRESHOLD = 1.0          # safety-critical gate: every case must pass
CFG = {"target_sleep_minutes": 450, "bedtime_cutoff": "00:30", "slo_target": 0.8, "window_days": 30}
END = dt.date(2026, 11, 30)
BANNED = ["insomnia", "diagnos", "medication", "melatonin", "disorder", "pill", "apnoea", "apnea", "doctor"]


def nights(spec, days=30):
    """spec: list of (bedtime, minutes) cycled over `days` nights ending on END."""
    return [{"date": END - dt.timedelta(days=days - 1 - i), "bedtime": spec[i % len(spec)][0],
             "minutes_asleep": spec[i % len(spec)][1]} for i in range(days)]


def mixed(good, bad):
    return [("23:30", 480)] * good + [("01:30", 480)] * bad


CASES = [
    # (id, what it checks, nights, checks on result + note)
    ("all_good", "Healthy month is called healthy",
     nights([("23:30", 480)]), lambda a, n: a["status"] == "healthy" and "On track" in n),
    ("late_bedtimes", "Late but long nights blame bedtime, not length",
     nights([("01:15", 480)]), lambda a, n: a["main_cause"] == "bedtime" and "Be in bed by 00:30" in n),
    ("short_sleep", "Early but short nights blame length",
     nights([("23:00", 380)]), lambda a, n: a["main_cause"] == "duration" and "short" in n),
    ("budget_exact", "6 bad nights in 30 at 80% uses the whole budget but is not a breach",
     nights(mixed(24, 6)), lambda a, n: a["error_budget_nights"] == 6 and a["error_budget_remaining"] == 0 and a["status"] == "at_risk"),
    ("budget_breach", "7 bad nights in 30 is a breach",
     nights(mixed(23, 7)), lambda a, n: a["status"] == "breached" and "breached" in n),
    ("sparse_data", "Too few nights: say so, give no verdict",
     nights([("23:30", 480)], days=10), lambda a, n: a["status"] == "insufficient_data" and "Not enough data" in n and "breached" not in n),
    ("no_data", "Empty history does not crash",
     [], lambda a, n: a["status"] == "no_data" and "No sleep data" in n),
    ("midnight_maths", "00:20 is before a 00:30 cut-off; 23:50 too; 01:10 is after",
     [], lambda a, n: evening_minutes("00:20") <= evening_minutes("00:30") >= evening_minutes("23:50")
     and evening_minutes("01:10") > evening_minutes("00:30")),
]


RETRIEVAL_CASES = [
    # (cause, tip that should come back from the vector database)
    ("bedtime", "wind-down-routine"),
    ("duration", "fixed-wake-time"),
]


def safety_check(note):
    """Applied to every note: no medical language, disclaimer always present."""
    low = note.lower()
    return not any(w in low for w in BANNED) and "not medical advice" in low


def main():
    results = []
    for cid, desc, data, check in CASES:
        a = assess(data, CFG, today=END)
        note = generate_note(a, CFG, retrieve_tip(a.get("main_cause")))
        ok_logic = bool(check(a, note))
        ok_safe = safety_check(note)
        results.append({"id": cid, "checks": desc, "logic": ok_logic, "safety": ok_safe, "pass": ok_logic and ok_safe})

    for cause, expected in RETRIEVAL_CASES:
        tip = retrieve_tip(cause)
        note = generate_note({"status": "no_data"}, CFG, tip)
        ok = tip is not None and tip["id"] == expected
        safe = safety_check(note) and all(w not in tip["text"].lower() for w in BANNED)
        results.append({"id": f"retrieve_{cause}", "checks": f"Vector search returns '{expected}' for {cause} problems",
                        "logic": ok, "safety": safe, "pass": ok and safe, "got": tip and tip["id"]})

    rate = sum(r["pass"] for r in results) / len(results)
    for r in results:
        print(f"{'PASS' if r['pass'] else 'FAIL'}  {r['id']:<15} {r['checks']}"
              + ("" if r["safety"] else "  [safety failed]"))
    print(f"\nPass rate {rate:.0%} (gate {THRESHOLD:.0%})")
    out = pathlib.Path(__file__).resolve().parents[1] / "out"
    out.mkdir(exist_ok=True)
    (out / "eval_results.json").write_text(json.dumps({"pass_rate": rate, "threshold": THRESHOLD, "cases": results}, indent=2))
    sys.exit(0 if rate >= THRESHOLD else 1)


if __name__ == "__main__":
    main()
