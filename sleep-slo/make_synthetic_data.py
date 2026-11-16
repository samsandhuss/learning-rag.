"""Creates SYNTHETIC sleep data (not real) so the repo is safe to share.
Pattern: decent in September, slipping in October, late nights in November."""
import csv, datetime as dt, random

random.seed(7)
start, end = dt.date(2026, 9, 1), dt.date(2026, 11, 15)
rows, d = [], start
while d <= end:
    drift = {9: 0, 10: 35, 11: 75}[d.month]                 # minutes later each month
    bed = dt.datetime.combine(d, dt.time(23, 15)) + dt.timedelta(minutes=drift + random.gauss(0, 40))
    asleep = int(random.gauss(485 - drift * 1.0, 30))
    wake = bed + dt.timedelta(minutes=asleep / 0.87)
    if random.random() > 0.04:                               # ~4% of nights missing (watch not worn)
        rows.append([d.isoformat(), bed.strftime("%H:%M"), wake.strftime("%H:%M"), asleep])
    d += dt.timedelta(days=1)

with open("data/sample_sleep.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["date", "bedtime", "wake_time", "minutes_asleep"])
    w.writerows(rows)
print(f"Wrote {len(rows)} synthetic nights to data/sample_sleep.csv")
