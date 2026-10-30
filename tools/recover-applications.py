"""Lists the applications whose outcome is unknown: the server stopped while one was being sent (to an employer's system, Recruitee or by
email), so it may or may not have reached them. A dry run only: nothing is written, resent or changed. UAply never resends these by
itself; the owner checks with the employer (or the person finishes on the employer's site).
  python tools/recover-applications.py               every instance under the records folder (UAPLY_DATA_DIR, else ./data)
  python tools/recover-applications.py dev sandbox   only these instances"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import uaply_api  # noqa: E402


def main(names):
    root = uaply_api.data_root()
    if not names:
        names = sorted(n for n in (os.listdir(root) if os.path.isdir(root) else [])
                       if os.path.isfile(os.path.join(root, n, "applications.jsonl")))
    total = 0
    for name in names:
        rows = uaply_api.uncertain(name)
        total += len(rows)
        print("%s: %d unknown" % (name, len(rows)))
        for r in rows:
            when = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(r["at"])) if isinstance(r.get("at"), (int, float)) else "?"
            print("  %s  %s  %s mode  %s at %s  to %s  (job %s, account %s)" % (
                r["id"], when, r.get("mode") or "?", r["role"] or "?", r["co"] or "?", r["to"] or "?", r.get("jobId"), r.get("user")))
    print("%d unknown in all (dry run: nothing changed)" % total)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
