"""
Sleep as a service: Service Level Indicators, a Service Level Objective,
an error budget, and a plain-English morning note.

    python sleep_slo.py                              # synthetic sample data
    python sleep_slo.py --data data/real/my_sleep.csv   # your own export (never committed)

Writes out/note.md (the morning note) and out/evidence.json (the audit record:
which data, which config and which code version produced the note).
Not medical advice: it only compares your sleep against targets you set.
"""
import argparse, calendar, csv, datetime as dt, hashlib, json, math, os, pathlib, statistics

HERE = pathlib.Path(__file__).parent
DISCLAIMER = "This note compares your sleep with targets you set. It is not medical advice."


# ---------- Load ----------
def load_nights(path):
    nights = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            nights.append({"date": dt.date.fromisoformat(r["date"]),
                           "bedtime": r["bedtime"],
                           "minutes_asleep": int(r["minutes_asleep"])})
    return sorted(nights, key=lambda n: n["date"])


def evening_minutes(hhmm):
    """Minutes since 18:00, so 23:30 -> 330 and 00:30 -> 390. Handles nights that cross midnight."""
    h, m = map(int, hhmm.split(":"))
    return (h * 60 + m - 18 * 60) % 1440


def clock(evening_mins):
    t = (int(round(evening_mins)) + 18 * 60) % 1440
    return f"{t // 60:02d}:{t % 60:02d}"


# ---------- Service Level Indicators (one verdict per night) ----------
def grade_night(n, cfg):
    on_time = evening_minutes(n["bedtime"]) <= evening_minutes(cfg["bedtime_cutoff"])
    long_enough = n["minutes_asleep"] >= cfg["target_sleep_minutes"]
    return {**n, "on_time": on_time, "long_enough": long_enough, "good": on_time and long_enough}


# ---------- Service Level Objective + error budget ----------
def assess(nights, cfg, today=None):
    if not nights:
        return {"status": "no_data", "recorded": 0, "window_days": cfg["window_days"]}
    today = today or nights[-1]["date"]
    start = today - dt.timedelta(days=cfg["window_days"] - 1)
    window = [grade_night(n, cfg) for n in nights if start <= n["date"] <= today]

    recorded, expected = len(window), cfg["window_days"]
    completeness = recorded / expected
    good = sum(n["good"] for n in window)
    bad = recorded - good
    allowed_bad = math.floor(round((1 - cfg["slo_target"]) * recorded, 6))  # round first: 0.2*30 is 5.999.. in floating point
    remaining = allowed_bad - bad

    if completeness < 0.6:
        status = "insufficient_data"
    elif remaining < 0:
        status = "breached"
    elif remaining <= allowed_bad * 0.5:
        status = "at_risk"
    else:
        status = "healthy"

    late = sum(not n["on_time"] for n in window)
    short = sum(not n["long_enough"] for n in window)
    cause = None if bad == 0 else ("bedtime" if late >= short else "duration")

    return {
        "status": status, "window_start": start.isoformat(), "window_end": today.isoformat(),
        "window_days": expected, "recorded": recorded, "completeness": round(completeness, 2),
        "good_nights": good, "bad_nights": bad,
        "sli_good_night_rate": round(good / recorded, 3) if recorded else 0,
        "slo_target": cfg["slo_target"],
        "error_budget_nights": allowed_bad, "error_budget_remaining": remaining,
        "burn_rate": round(bad / allowed_bad, 2) if allowed_bad else (0.0 if bad == 0 else None),
        "late_nights": late, "short_nights": short, "main_cause": cause,
        "avg_minutes_asleep": round(statistics.mean(n["minutes_asleep"] for n in window)),
        "avg_bedtime": clock(statistics.mean(evening_minutes(n["bedtime"]) for n in window)),
        "months": month_summary(nights, cfg, today),
    }


def month_summary(nights, cfg, today):
    """This calendar month vs last, and what next month needs."""
    def stats(y, m):
        ns = [grade_night(n, cfg) for n in nights if (n["date"].year, n["date"].month) == (y, m)]
        if not ns:
            return None
        return {"month": f"{y}-{m:02d}", "nights": len(ns), "good": sum(n["good"] for n in ns),
                "good_rate": round(sum(n["good"] for n in ns) / len(ns), 2),
                "avg_minutes_asleep": round(statistics.mean(n["minutes_asleep"] for n in ns)),
                "avg_bedtime": clock(statistics.mean(evening_minutes(n["bedtime"]) for n in ns))}
    y, m = today.year, today.month
    py, pm = (y, m - 1) if m > 1 else (y - 1, 12)
    ny, nm = (y, m + 1) if m < 12 else (y + 1, 1)
    days_next = calendar.monthrange(ny, nm)[1]
    return {"this": stats(y, m), "last": stats(py, pm),
            "next_month": f"{calendar.month_name[nm]} {ny}",
            "good_nights_needed_next_month": math.ceil(cfg["slo_target"] * days_next),
            "days_next_month": days_next}


# ---------- Vector search: pick the most relevant tip from the knowledge base ----------
CAUSE_QUERIES = {
    "bedtime": "going to bed later than planned, staying up late, missing the bedtime cut-off",
    "duration": "short nights, how to fix not sleeping long enough, keeping the same wake-up time and moving bedtime earlier",
}


def retrieve_tip(cause, kb_dir=HERE / "knowledge"):
    """Loads the tips into an in-memory ChromaDB collection and returns the closest one to the problem."""
    if cause not in CAUSE_QUERIES:
        return None
    import chromadb
    from sklearn.feature_extraction.text import TfidfVectorizer

    docs = {p.stem: p.read_text() for p in sorted(pathlib.Path(kb_dir).glob("*.md"))}
    if not docs:
        return None
    vec = TfidfVectorizer(stop_words="english").fit(list(docs.values()))
    embed = lambda texts: vec.transform(texts).toarray().tolist()
    col = chromadb.EphemeralClient().get_or_create_collection("sleep_tips", metadata={"hnsw:space": "cosine"})
    col.upsert(ids=list(docs), documents=list(docs.values()), embeddings=embed(list(docs.values())))
    r = col.query(query_embeddings=embed([CAUSE_QUERIES[cause]]), n_results=1)
    text = r["documents"][0][0]
    title = text.splitlines()[0].lstrip("# ").strip()
    body = " ".join(text.splitlines()[1:]).strip()
    return {"id": r["ids"][0][0], "title": title, "text": body, "similarity": round(1 - r["distances"][0][0], 2)}


# ---------- The morning note ----------
def hm(mins):
    return f"{mins // 60}h {mins % 60:02d}m"


def generate_note(a, cfg, tip=None):
    if a["status"] == "no_data":
        return f"# Morning sleep note\n\nNo sleep data found yet, so there is nothing to assess.\n\n_{DISCLAIMER}_\n"
    lines = ["# Morning sleep note", ""]
    if a["status"] == "insufficient_data":
        lines += [f"Not enough data to judge: only {a['recorded']} of the last {a['window_days']} nights were recorded "
                  f"({a['completeness']:.0%}). Wear the tracker more nights and check again.", "", f"_{DISCLAIMER}_"]
        return "\n".join(lines) + "\n"

    headline = {"healthy": "On track.", "at_risk": "At risk: the error budget is nearly spent.",
                "breached": "Service Level Objective breached: the error budget is spent."}[a["status"]]
    lines += [f"**{headline}**", "",
              f"- Good nights: **{a['good_nights']} of {a['recorded']}** ({a['sli_good_night_rate']:.0%}) "
              f"against a target of {a['slo_target']:.0%}",
              f"- Error budget: {a['error_budget_nights']} bad nights allowed, {a['bad_nights']} used "
              f"({'over by ' + str(-a['error_budget_remaining']) if a['error_budget_remaining'] < 0 else str(a['error_budget_remaining']) + ' left'})",
              f"- Average sleep: {hm(a['avg_minutes_asleep'])} (target {hm(cfg['target_sleep_minutes'])}), "
              f"average bedtime {a['avg_bedtime']} (cut-off {cfg['bedtime_cutoff']})", ""]

    mo = a["months"]
    if mo["this"] and mo["last"]:
        t, l = mo["this"], mo["last"]
        direction = "better" if t["good_rate"] > l["good_rate"] else "worse" if t["good_rate"] < l["good_rate"] else "the same"
        lines += [f"**This month vs last:** {t['good_rate']:.0%} good nights vs {l['good_rate']:.0%} ({direction}). "
                  f"Bedtime {t['avg_bedtime']} vs {l['avg_bedtime']}.", ""]

    lines.append("**To beat it next month:**")
    if a["main_cause"] == "bedtime":
        lines.append(f"- Bedtime is the main cause ({a['late_nights']} late nights). "
                     f"Be in bed by {cfg['bedtime_cutoff']} on {mo['good_nights_needed_next_month']} of "
                     f"{mo['days_next_month']} nights in {mo['next_month']}.")
        lines.append("- Start winding down 45 minutes before the cut-off.")
    elif a["main_cause"] == "duration":
        gap = max(cfg["target_sleep_minutes"] - a["avg_minutes_asleep"], 0)
        lines.append(f"- Length is the main cause ({a['short_nights']} short nights), about {gap} minutes short on average. "
                     f"Protect a full {hm(cfg['target_sleep_minutes'])} on {mo['good_nights_needed_next_month']} nights in {mo['next_month']}.")
        lines.append("- Keep the wake-up time fixed and move bedtime earlier.")
    else:
        lines.append("- Keep doing what you are doing.")
    if a["status"] == "breached":
        lines.append("- Budget spent, so rest comes first: no late-night work until you are back within target.")
    if tip:
        lines += ["", f"**Tip from your knowledge base:** {tip['title']} (vector search match {tip['similarity']:.2f})",
                  f"> {tip['text']}"]
    lines += ["", f"_{DISCLAIMER}_"]
    return "\n".join(lines) + "\n"


# ---------- Evidence (audit record) ----------
def sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.environ.get("SLEEP_DATA", str(HERE / "data/sample_sleep.csv")))
    ap.add_argument("--config", default=os.environ.get("SLEEP_CONFIG", str(HERE / "config.json")))
    ap.add_argument("--out", default=os.environ.get("SLEEP_OUT", str(HERE / "out")))
    ap.add_argument("--bedtime-cutoff", default=os.environ.get("BEDTIME_CUTOFF") or None, help="override, e.g. 00:00")
    ap.add_argument("--target-hours", type=float, default=float(os.environ["TARGET_HOURS"]) if os.environ.get("TARGET_HOURS") else None)
    ap.add_argument("--slo-target", type=float, default=float(os.environ["SLO_TARGET"]) if os.environ.get("SLO_TARGET") else None)
    a = ap.parse_args()

    cfg = json.loads(pathlib.Path(a.config).read_text())
    if a.bedtime_cutoff:
        cfg["bedtime_cutoff"] = a.bedtime_cutoff
    if a.target_hours:
        cfg["target_sleep_minutes"] = int(round(a.target_hours * 60))
    if a.slo_target:
        cfg["slo_target"] = a.slo_target
    result = assess(load_nights(a.data), cfg)
    tip = retrieve_tip(result.get("main_cause"))
    note = generate_note(result, cfg, tip)

    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "note.md").write_text(note)
    evidence = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "code_version": os.environ.get("GIT_SHA", "local"),
        "data_file": pathlib.Path(a.data).name, "data_sha256": sha256(a.data),
        "config_sha256": sha256(a.config), "config_used": cfg, "result": result,
        "retrieved_tip": tip,
    }
    (out / "evidence.json").write_text(json.dumps(evidence, indent=2))
    print(note)
    print(f"Evidence written to {out / 'evidence.json'}")


if __name__ == "__main__":
    main()
