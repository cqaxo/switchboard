"""Run the observability checks and print a human-readable summary.

Run from the repo root:
    python run_monitor.py
"""

from switchboard.monitor import run_monitor


def main():
    r = run_monitor()
    f, v = r["freshness"], r["volume"]
    print(f"Freshness: newest record {f['newest_record']} "
          f"({f['age_days']} days old)")
    print(f"Volume: {v['recent_daily_rate']}/day recent vs "
          f"{v['baseline_daily_rate']}/day baseline "
          f"({v['change_fraction']:+.1%})"
          + ("  ALERT" if v["alert"] else ""))
    print("\nQuality flag rates (recent vs baseline):")
    for col, q in r["quality"].items():
        print(f"  {col}: {q['recent_pct']}% vs {q['baseline_pct']}%")
    print(f"\nDrifting complaint types ({len(r['drift'])} flagged):")
    for d in r["drift"]:
        print(f"  {d['complaint_type']}: {d['baseline_share_pct']}% -> "
              f"{d['recent_share_pct']}% ({d['change_points']:+.2f} pts)")
    print(f"\nReport written to {r['report_path']}")


if __name__ == "__main__":
    main()