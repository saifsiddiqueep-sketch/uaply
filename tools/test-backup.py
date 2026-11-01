"""Tests tools/backup-data.py on a throwaway data folder shaped like Render's /var/data. No network: the GitHub upload goes to a stand-in.
  python tools/test-backup.py [port]        (default 20524, for the stand-in GitHub)"""
import http.server
import importlib.util
import io
import json
import os
import pathlib
import shutil
import sqlite3
import sys
import tarfile
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 20524
TMP = tempfile.mkdtemp(prefix="uaply-backup-test-")
DATA = os.path.join(TMP, "var-data")
R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


spec = importlib.util.spec_from_file_location("backup_data", os.path.join(HERE, "backup-data.py"))
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)


def refused(fn, *a, **k):
    """The message a refusal exits with ('' when it went ahead)."""
    try:
        fn(*a, **k)
        return ""
    except SystemExit as e:
        return str(e.code)


def users(db):
    c = sqlite3.connect(db)
    try:
        return [r[0] for r in c.execute("SELECT email FROM users ORDER BY id")]
    finally:
        c.close()


try:
    # ---------- a data folder as the server leaves it ----------
    os.makedirs(os.path.join(DATA, "dev"))
    db = os.path.join(DATA, "dev", "uaply.db")
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE users(id INTEGER PRIMARY KEY, email TEXT)")
    c.executemany("INSERT INTO users(email) VALUES (?)", [("a%d@example.com" % i,) for i in range(200)])
    c.commit()
    c.close()
    files = {"dev/applications.jsonl": '{"id": "app1"}\n', "dev/decisions.jsonl": '{"dir": "pass"}\n', "dev/feedback.jsonl": '{"rating": 5}\n',
             "dev/employers.json": '{"companies": []}', "uaply-partners.json": '{"employers": []}',
             "jobs-cache.json": '{"_version": 8}', "jobs-cache.json.tmp": "{", ".write-check-123": "ok"}
    for rel, body in files.items():
        with open(os.path.join(DATA, *rel.split("/")), "w", encoding="utf-8") as f:
            f.write(body)

    # ---------- a backup, while the server keeps writing accounts ----------
    stop = threading.Event()

    def writer():
        w = sqlite3.connect(db, timeout=30)
        n = 0
        while not stop.is_set():
            w.execute("INSERT INTO users(email) VALUES (?)", ("live%d@example.com" % n,))
            w.commit()
            n += 1
        w.close()
    th = threading.Thread(target=writer)
    th.start()
    try:
        path, man = B.make_backup(DATA, os.path.join(DATA, "backups"))
    finally:
        stop.set()
        th.join()
    names = sorted(man["files"])
    t("the backup is a timestamped .tar.gz in <data>/backups", (os.path.dirname(path), bool(B.NAME_RE.match(os.path.basename(path)))),
      (os.path.join(DATA, "backups"), True))
    t("it holds the accounts database, applications, swipes, feedback, employers and the partner list", names,
      ["dev/applications.jsonl", "dev/decisions.jsonl", "dev/employers.json", "dev/feedback.jsonl", "dev/uaply.db", "uaply-partners.json"])
    t("...and not the saved job list, SQLite's side files, write checks or earlier backups",
      any(n.startswith(("jobs-cache", "backups")) or n.endswith("-journal") or ".write-check" in n for n in names), False)
    with tarfile.open(path, "r:gz") as tar:
        snap = os.path.join(TMP, "snap.db")
        with tar.extractfile("data/dev/uaply.db") as src, open(snap, "wb") as f:
            shutil.copyfileobj(src, f)
    c = sqlite3.connect(snap)
    t("the database copied while it was being written is whole (integrity_check ok, the first 200 accounts there)",
      (c.execute("PRAGMA integrity_check").fetchone()[0], c.execute("SELECT count(*) FROM users WHERE email LIKE 'a%'").fetchone()[0]), ("ok", 200))
    c.close()
    t("--list shows the manifest without changing anything", sorted(B.list_backup(path)["files"]), names)
    if os.name != "nt":
        t("the backup file can be read by its owner only", oct(os.stat(path).st_mode & 0o777), "0o600")

    # keeping the newest N
    for _ in range(3):
        B.make_backup(DATA, os.path.join(TMP, "keep"), keep=2, quiet=True)
        time.sleep(1.1)
    t("--keep 2 leaves the two newest backups", len(os.listdir(os.path.join(TMP, "keep"))), 2)

    # ---------- a restore ----------
    os.remove(os.path.join(DATA, "dev", "applications.jsonl"))
    c = sqlite3.connect(db)
    c.execute("DELETE FROM users")
    c.commit()
    c.close()
    with open(os.path.join(DATA, "dev", "new-since.txt"), "w") as f:
        f.write("made after the backup")
    t("a restore without --yes changes nothing", (bool(refused(B.restore, path, DATA)), users(db)), (True, []))
    with open(db + "-journal", "w") as f:           # a side file left by a crash: the backup made before the restore must still work
        f.write("x")
    B.restore(path, DATA, yes=True)
    t("after a restore the accounts are back", users(db)[:3], ["a0@example.com", "a1@example.com", "a2@example.com"])
    t("...and the applications file", open(os.path.join(DATA, "dev", "applications.jsonl"), encoding="utf-8").read(), '{"id": "app1"}\n')
    t("...a file made since is left alone", os.path.exists(os.path.join(DATA, "dev", "new-since.txt")), True)
    t("...the old database's side file is gone (it would be applied to the restored one)", os.path.exists(db + "-journal"), False)
    before = [f for f in os.listdir(os.path.join(DATA, "backups")) if B.NAME_RE.match(f)]
    t("...and the state before the restore was backed up first", len(before), 2)
    t("...no staging folder is left on the disk", [d for d in os.listdir(DATA) if d.startswith(".restore")], [])

    # ---------- a journal left by a crash (a hot journal) ----------
    def crashed(folder):
        """A data folder whose accounts database was cut off in the middle of a write: the database already holds part of the change,
        its journal holds the pages as they were. Opening it for writing would roll the change back; a read-only connection may not."""
        live = os.path.join(TMP, "crash-live.db")
        for f in (live, live + "-journal"):
            if os.path.exists(f):
                os.remove(f)
        w = sqlite3.connect(live, isolation_level=None)
        w.execute("CREATE TABLE users(id INTEGER PRIMARY KEY, email TEXT, pad TEXT)")
        w.execute("BEGIN")
        w.executemany("INSERT INTO users(email, pad) VALUES (?, ?)", [("a%d@example.com" % i, "p" * 400) for i in range(300)])
        w.execute("COMMIT")
        w.execute("PRAGMA cache_size=2")                # a small cache makes SQLite write changed pages before the commit
        w.execute("BEGIN")
        w.execute("UPDATE users SET email = 'changed' || id, pad = 'q' || pad")
        os.makedirs(os.path.join(folder, "dev"), exist_ok=True)
        out = os.path.join(folder, "dev", "uaply.db")
        shutil.copyfile(live, out)                      # the files as a crash at this moment leaves them
        shutil.copyfile(live + "-journal", out + "-journal")
        w.execute("ROLLBACK")
        w.close()
        return out
    states = lambda f: (B.sha256(f), B.sha256(f + "-journal"))

    hot = crashed(os.path.join(TMP, "probe"))
    msg = ""
    try:
        B._online_backup(pathlib.Path(hot).as_uri() + "?mode=ro", os.path.join(TMP, "probe.db"))
    except sqlite3.DatabaseError as e:
        msg = "%s %s" % (getattr(e, "sqlite_errorcode", None), e)
    t("(the test's crashed database really has a hot journal: a plain read-only backup of it fails as the one in card 053 did)",
      ("readonly" in msg, os.path.getsize(hot + "-journal") > 0), (True, True))

    CRASH = os.path.join(TMP, "crash-data")
    hot = crashed(CRASH)
    was = states(hot)
    cpath, cman = B.make_backup(CRASH, os.path.join(TMP, "crash-out"), quiet=True)
    with tarfile.open(cpath, "r:gz") as tar:
        snap = os.path.join(TMP, "crash-snap.db")
        with tar.extractfile("data/dev/uaply.db") as src, open(snap, "wb") as f:
            shutil.copyfileobj(src, f)
    c = sqlite3.connect(snap)
    t("a database with a hot journal is backed up as it was before the cut-off write (integrity ok, 300 accounts, none half-changed)",
      (c.execute("PRAGMA integrity_check").fetchone()[0], c.execute("SELECT count(*) FROM users WHERE email LIKE 'a%'").fetchone()[0],
       c.execute("SELECT count(*) FROM users WHERE email LIKE 'changed%'").fetchone()[0]), ("ok", 300, 0))
    c.close()
    t("...the live database and its journal are left exactly as they were (nothing opened them for writing)", states(hot), was)
    t("...the manifest says the journal was rolled back in a private copy, and the journal is not in the backup",
      ("private copy" in cman.get("notes", {}).get("dev/uaply.db", ""), sorted(cman["files"])), (True, ["dev/uaply.db"]))
    t("...and no private copy is left in the temp folder", [d for d in os.listdir(tempfile.gettempdir()) if d.startswith("uaply-recover-")], [])

    B.restore(path, CRASH, yes=True)
    t("a restore into a folder whose database has a hot journal works (the card 053 failure), and the old journal is gone",
      (users(hot)[:2], os.path.exists(hot + "-journal")), (["a0@example.com", "a1@example.com"], False))
    first = sorted(f for f in os.listdir(os.path.join(CRASH, "backups")) if B.NAME_RE.match(f))
    t("...the copy saved before it holds the crashed database as it was before the cut-off write",
      "private copy" in B.list_backup(os.path.join(CRASH, "backups", first[0])).get("notes", {}).get("dev/uaply.db", ""), True)

    hot = crashed(os.path.join(TMP, "busy"))
    was = states(hot)
    real, tick = B._file_state, iter(range(1000000))
    B._file_state = lambda f: next(tick)            # the files change between every look, as if a writer kept working
    try:
        msg = refused(B.copy_sqlite, hot, os.path.join(TMP, "busy.db"))
    finally:
        B._file_state = real
    t("a hot journal that keeps changing while it is copied is refused after 3 tries, and the live files are untouched",
      ("kept changing" in msg, states(hot)), (True, was))

    # ---------- damaged and hostile backups ----------
    def tamper(name, member_name, data, keep_manifest=True):
        out = os.path.join(TMP, name)
        with tarfile.open(path, "r:gz") as src, tarfile.open(out, "w:gz") as dst:
            for m in src.getmembers():
                if m.name == "manifest.json" and not keep_manifest:
                    continue
                if m.name == member_name:
                    continue
                dst.addfile(m, src.extractfile(m))
            if data is not None:
                info = tarfile.TarInfo(member_name)
                info.size = len(data)
                dst.addfile(info, io.BytesIO(data))
        return out
    snapshot = users(db)
    msg = refused(B.restore, tamper("damaged.tar.gz", "data/dev/applications.jsonl", b'{"id": "changed"}\n'), DATA, yes=True)
    t("a backup whose file does not match its manifest is refused and nothing changes", ("does not match" in msg, users(db)), (True, snapshot))
    msg = refused(B.restore, tamper("escape.tar.gz", "data/../../escape.txt", b"x"), DATA, yes=True)
    t("an entry that points outside the data folder is refused", ("outside" in msg, os.path.exists(os.path.join(TMP, "escape.txt"))), (True, False))
    msg = refused(B.restore, tamper("short.tar.gz", "data/dev/feedback.jsonl", None), DATA, yes=True)
    t("a backup missing a file its manifest lists is refused", "lacks files" in msg, True)
    msg = refused(B.restore, tamper("nomanifest.tar.gz", "x", None, keep_manifest=False), DATA, yes=True)
    t("a file that is not a UAply backup is refused", "not a UAply backup" in msg, True)

    # ---------- encryption (openssl) ----------
    if shutil.which("openssl"):
        os.environ["UAPLY_BACKUP_PASSPHRASE"] = "correct horse battery staple"
        enc, _ = B.make_backup(DATA, os.path.join(TMP, "enc"), encrypt=True, quiet=True)
        raw = open(enc, "rb").read(16)
        t("--encrypt leaves only the encrypted file (.tar.gz.enc, openssl's Salted__ header)", (enc.endswith(".enc"), raw[:8], len(os.listdir(os.path.join(TMP, "enc")))),
          (True, b"Salted__", 1))
        t("an encrypted backup lists with the passphrase", sorted(B.list_backup(enc)["files"]), sorted(names + ["dev/new-since.txt"]))
        os.environ["UAPLY_BACKUP_PASSPHRASE"] = "the wrong passphrase!"
        t("...and is refused with a wrong one", bool(refused(B.list_backup, enc)), True)
        os.environ["UAPLY_BACKUP_PASSPHRASE"] = "short"
        t("a passphrase under 12 characters is refused", "12 characters" in refused(B.make_backup, DATA, os.path.join(TMP, "enc2"), encrypt=True, quiet=True), True)
        os.environ.pop("UAPLY_BACKUP_PASSPHRASE", None)
    else:
        print("SKIP encryption (no openssl command here)")

    # ---------- the off-site copy: a private GitHub repository's releases (a stand-in GitHub) ----------
    seen = []

    class GH(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            seen.append(("GET", self.path, self.headers.get("Authorization")))
            self._json(200, {"private": "/public" not in self.path})

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n)
            seen.append(("POST", self.path, len(body)))
            if self.path.endswith("/releases"):
                return self._json(201, {"id": 77, "tag": json.loads(body)["tag_name"]})
            self._json(201, {"size": n})
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), GH)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    gh = "http://127.0.0.1:%d" % PORT
    os.environ.pop("GITHUB_BACKUP_TOKEN", None)
    t("an upload without GITHUB_BACKUP_TOKEN is refused before anything is sent", ("GITHUB_BACKUP_TOKEN" in refused(B.upload_github, path, "me/backups", gh, gh), seen), (True, []))
    os.environ["GITHUB_BACKUP_TOKEN"] = "github_pat_" + "x" * 40                       # made up
    t("an upload to a public repository is refused", "not a private repository" in refused(B.upload_github, path, "me/public", gh, gh), True)
    seen.clear()
    tag = B.upload_github(path, "me/backups", gh, gh)
    t("an upload creates a release named after the backup and sends the whole file as its asset",
      (tag.startswith("backup-"), [s[0] for s in seen], seen[-1][2] == os.path.getsize(path), "/releases/77/assets?name=uaply-backup-" in seen[-1][1]),
      (True, ["GET", "POST", "POST"], True, True))
    t("...with the token only in the Authorization header", seen[0][2], "Bearer " + os.environ["GITHUB_BACKUP_TOKEN"])
    os.environ.pop("GITHUB_BACKUP_TOKEN", None)
    srv.shutdown()
    srv.server_close()
except Exception as e:
    import traceback
    traceback.print_exc()
    t("the checks ran to the end", "%s: %s" % (type(e).__name__, e), "no error")
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
