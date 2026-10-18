"""Read-only check that every email address is one account, for a data folder on this computer or on the live disk (Render, Shell):
  python tools/audit-accounts.py [data_folder] [--full]
The folder defaults to UAPLY_DATA_DIR, else ./data. It opens every <instance>/uaply.db under it READ-ONLY (it never writes, locks for
writing or creates anything) and reports, per instance:
  * DUPLICATE  two or more accounts whose addresses have the same canonical key (auth_api.canonical_email: NFKC, trimmed, lower case)
  * NOT CANONICAL  a stored address that is not already in its canonical form (or that would be refused today)
  * GOOGLE LINK  one Google account linked to more than one UAply account (the database should make this impossible)
  * ORPHAN  sessions, Google links, reset links or codes that point at an account that no longer exists
  * note: one inbox, several accounts  addresses that differ only by a +tag or Gmail dots. Allowed on purpose (docs/ACCOUNTS.md); listed
    so the owner can see them, never counted as a problem
Addresses are masked (a***@gmail.com) unless --full is given; the account numbers are always shown, so a problem can be found either way.
Exit code: 0 when nothing is wrong, 1 when a DUPLICATE, NOT CANONICAL, GOOGLE LINK or ORPHAN was found, 2 when the folder has no databases."""
import os
import sqlite3
import sys
import urllib.parse
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import auth_api  # noqa: E402  (only its canonical_email; nothing is started)


def mask(email, full):
    if full:
        return email
    local, _, dom = email.rpartition("@")
    return (local[:1] + "***@" + dom) if local else "***"


def inbox_key(email):
    """The inbox an address reaches: +tag dropped everywhere, dots dropped for Gmail (googlemail.com is the same as gmail.com)."""
    local, _, dom = email.rpartition("@")
    local = local.split("+", 1)[0]
    if dom in ("gmail.com", "googlemail.com"):
        return local.replace(".", "") + "@gmail.com"
    return local + "@" + dom


def open_ro(path):
    uri = "file:" + urllib.parse.quote(os.path.abspath(path).replace("\\", "/")) + "?mode=ro"
    c = sqlite3.connect(uri, uri=True, timeout=5)
    c.row_factory = sqlite3.Row
    return c


def audit_db(path, full):
    """Returns (problems, notes, users) for one uaply.db."""
    problems, notes = [], []
    c = open_ro(path)
    try:
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        users = [dict(r) for r in c.execute("SELECT id, email FROM users ORDER BY id")] if "users" in tables else []
        ids = {u["id"] for u in users}
        by_key = defaultdict(list)
        for u in users:
            key = auth_api.canonical_email(u["email"])
            if key != u["email"]:
                problems.append("NOT CANONICAL  account %d is stored as %s%s" % (
                    u["id"], mask(str(u["email"]), full), "" if key else " (not an address UAply accepts today)"))
            by_key[key or str(u["email"]).strip().lower()].append(u["id"])
        for key, owners in sorted(by_key.items()):
            if len(owners) > 1:
                problems.append("DUPLICATE  %s is %d accounts: %s" % (mask(key, full), len(owners), ", ".join(map(str, owners))))
        by_inbox = defaultdict(list)
        for key, owners in by_key.items():
            by_inbox[inbox_key(key)].extend((key, o) for o in owners)
        for inbox, members in sorted(by_inbox.items()):
            if len({k for k, _ in members}) > 1:
                notes.append("note: one inbox, several accounts  %s: %s" % (
                    mask(inbox, full), ", ".join("%d (%s)" % (o, mask(k, full)) for k, o in sorted(members, key=lambda m: m[1]))))
        if "identities" in tables:
            for r in c.execute("SELECT provider, subject, COUNT(DISTINCT user_id) n FROM identities GROUP BY provider, subject HAVING n > 1"):
                problems.append("GOOGLE LINK  %s account %s is linked to %d UAply accounts" % (r["provider"], r["subject"][:12] + "...", r["n"]))
        for table in ("sessions", "identities", "password_resets", "email_codes"):
            if table in tables:
                gone = sorted({r[0] for r in c.execute("SELECT user_id FROM %s" % table)} - ids)
                if gone:
                    problems.append("ORPHAN  %s points at %d account(s) that no longer exist: %s" % (table, len(gone), ", ".join(map(str, gone[:20]))))
    finally:
        c.close()
    return problems, notes, users


def main(argv):
    full = "--full" in argv
    args = [a for a in argv if not a.startswith("--")]
    folder = args[0] if args else (os.environ.get("UAPLY_DATA_DIR") or os.path.join(ROOT, "data"))
    dbs = []
    if os.path.isfile(folder):
        dbs = [folder]
    elif os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            p = os.path.join(folder, name, "uaply.db")
            if os.path.isfile(p):
                dbs.append(p)
    if not dbs:
        print("No accounts database (<instance>/uaply.db) under %s" % folder)
        return 2
    bad = 0
    for p in dbs:
        problems, notes, users = audit_db(p, full)
        print("%s: %d account(s), %d problem(s)" % (p, len(users), len(problems)))
        for line in problems + notes:
            print("  " + line)
        bad += len(problems)
    print("OK: every address is one account" if not bad else "FOUND %d problem(s); nothing was changed" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
