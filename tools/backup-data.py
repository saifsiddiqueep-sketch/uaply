"""Backs up UAply's data folder (accounts, sessions, applications, swipes, feedback, employers, the partner list) into one timestamped
.tar.gz, and puts a backup back. Standard library only; runs on Render's Shell, a Mac, Linux or Windows.

  python tools/backup-data.py                        back up UAPLY_DATA_DIR (on Render /var/data) into <data>/backups/
  python tools/backup-data.py --out DIR --keep 4     somewhere else; keep the newest 4 backups there (default 4; 0 keeps all)
  python tools/backup-data.py --encrypt              also encrypt it (openssl AES-256, passphrase from UAPLY_BACKUP_PASSPHRASE), for off-site copies
  python tools/backup-data.py --upload OWNER/REPO    then upload it as a release asset of a PRIVATE GitHub repository (token from GITHUB_BACKUP_TOKEN)
  python tools/backup-data.py --list FILE            what a backup holds (its manifest), without changing anything
  python tools/backup-data.py --restore FILE --yes   put a backup back into the data folder (a backup of the current state is made first)

What is in a backup: every file in the data folder except the saved job list (jobs-cache.json: it is rebuilt from the boards in a minute),
earlier backups, and SQLite's side files. Each accounts database (uaply.db) is copied through SQLite's own backup, so a sign-up written
at that moment cannot leave a half-copied database. A manifest.json inside lists every file with its size and SHA-256; a restore checks
them all before it touches anything.

Restoring on Render: the server keeps running while you restore, so restart it straight after (Manual Deploy > Restart service, or
Deploy latest commit): it reads the restored files at start. Anything people did between the restore and the restart is lost. Files that
exist now but are not in the backup are left alone. See DEPLOY.md, "Backups".

The backup holds password hashes, email addresses and applications: keep it private. Never put it in a public place, a chat or this
repository (tools/audit-files.py refuses a committed backup)."""
import argparse
import hashlib
import io
import json
import os
import pathlib
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME_RE = re.compile(r"^uaply-backup-\d{8}-\d{6}Z\.tar\.gz(\.enc)?$")
SKIP_FILES = re.compile(r"^(jobs-cache\.json(\.tmp)?|\.write-check-\d+|.*\.db-(wal|shm|journal)|.*\.tmp)$")
SKIP_DIRS = {"backups", ".restore", "__pycache__"}


def data_dir(arg):
    return os.path.abspath(arg or os.environ.get("UAPLY_DATA_DIR") or os.path.join(ROOT, "data"))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def files_to_back_up(data):
    out = []
    for folder, dirs, files in os.walk(data):
        rel_dir = os.path.relpath(folder, data)
        dirs[:] = sorted(d for d in dirs if not (rel_dir == "." and d in SKIP_DIRS) and not d.startswith(".restore"))
        for name in sorted(files):
            if SKIP_FILES.match(name):
                continue
            full = os.path.join(folder, name)
            if os.path.isfile(full) and not os.path.islink(full):
                out.append(os.path.relpath(full, data).replace(os.sep, "/"))
    return out


SQLITE_READONLY_ROLLBACK = 776   # a read-only connection met a hot journal it is not allowed to roll back


def _online_backup(src_uri, dst):
    a = sqlite3.connect(src_uri, uri=True, timeout=30)
    b = sqlite3.connect(dst)
    try:
        a.backup(b)
    finally:
        b.close()
        a.close()


def _file_state(path):
    """Size, mtime and SHA-256 of a file (None when it is gone): shows that nothing wrote it while it was being copied."""
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return None
    return st.st_size, st.st_mtime_ns, sha256(path)


def _needs_rollback(err, src):
    code = getattr(err, "sqlite_errorcode", None)
    return os.path.exists(src + "-journal") and (code == SQLITE_READONLY_ROLLBACK or (code is None and "readonly" in str(err)))


def copy_sqlite(src, dst, tries=3):
    """A consistent copy of a database another process may be writing to (SQLite's online backup). Returns a note when a journal
    left by a crash had to be rolled back, else None.

    A crash in the middle of a write leaves a hot <db>-journal, and the read-only connection used here may not roll it back. The live
    database is never opened for writing to fix that (rolling back a journal that belongs to another copy of the file would damage it):
    the database and its journal are copied into a private folder, the copy is recovered and checked there, and the copy is backed up.
    The live files stay exactly as they were; the server rolls the journal back itself the next time it opens the database."""
    src = os.path.abspath(src)
    uri = pathlib.Path(src).as_uri() + "?mode=ro"
    for _ in range(tries):
        if os.path.exists(dst):
            os.remove(dst)
        try:
            _online_backup(uri, dst)
            return None
        except sqlite3.DatabaseError as e:
            if not _needs_rollback(e, src):
                raise
        work = tempfile.mkdtemp(prefix="uaply-recover-")
        try:
            copy = os.path.join(work, "recover.db")
            before = (_file_state(src), _file_state(src + "-journal"))
            if before[1] is None:                       # a writer rolled the journal back meanwhile: the plain way works again
                continue
            shutil.copyfile(src, copy)
            shutil.copyfile(src + "-journal", copy + "-journal")
            if (_file_state(src), _file_state(src + "-journal")) != before:
                time.sleep(0.2)                         # something wrote the files while they were copied: start again
                continue
            c = sqlite3.connect(copy)                   # the first read of the private copy rolls its journal back
            try:
                ok = c.execute("PRAGMA integrity_check").fetchone()[0]
            finally:
                c.close()
            if ok != "ok" or os.path.exists(copy + "-journal"):
                sys.exit("[backup] refused: %s has a journal left by a crash, and rolling it back (in a private copy) gives a damaged "
                         "database (%s). The live files were not changed. Ask Saif before anything opens it for writing." % (src, ok[:200]))
            if os.path.exists(dst):
                os.remove(dst)
            _online_backup(pathlib.Path(copy).as_uri() + "?mode=ro", dst)
            return "rolled back a journal left by a crash, in a private copy; the live database was not changed"
        finally:
            shutil.rmtree(work, ignore_errors=True)
    sys.exit("[backup] refused: %s has a journal left by a crash, and it kept changing while it was copied (%d tries). "
             "The live files were not changed; run the backup again in a minute." % (src, tries))


def make_backup(data, out_dir, keep=4, encrypt=False, quiet=False, label=""):
    if not os.path.isdir(data):
        sys.exit("[backup] no data folder at %s (set UAPLY_DATA_DIR or pass --data)" % data)
    os.makedirs(out_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%SZ", time.gmtime())
    final = os.path.join(out_dir, "uaply-backup-%s.tar.gz" % stamp)
    work = tempfile.mkdtemp(prefix="uaply-backup-")
    try:
        manifest = {"made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "from": data, "label": label,
                    "commit": (os.environ.get("RENDER_GIT_COMMIT") or "")[:7] or None, "files": {}}
        tmp_tar = final + ".part"
        with tarfile.open(tmp_tar, "w:gz", compresslevel=6) as tar:
            for rel in files_to_back_up(data):
                src = os.path.join(data, rel)
                if rel.endswith(".db"):
                    snap = os.path.join(work, "db-%d" % len(manifest["files"]))
                    note = copy_sqlite(src, snap)
                    src = snap
                    if note:
                        manifest.setdefault("notes", {})[rel] = note
                        if not quiet:
                            print("[backup] %s: %s" % (rel, note))
                manifest["files"][rel] = {"bytes": os.path.getsize(src), "sha256": sha256(src)}
                tar.add(src, arcname="data/" + rel, recursive=False)
            blob = json.dumps(manifest, indent=1, sort_keys=True).encode("utf-8")
            info = tarfile.TarInfo("manifest.json")
            info.size, info.mtime, info.mode = len(blob), int(time.time()), 0o600
            tar.addfile(info, io.BytesIO(blob))
        os.replace(tmp_tar, final)
        try:
            os.chmod(final, 0o600)
        except OSError:
            pass
        if encrypt:
            final = encrypt_file(final)
        if keep:
            old = sorted(f for f in os.listdir(out_dir) if NAME_RE.match(f))
            for f in old[:-keep]:
                os.remove(os.path.join(out_dir, f))
        if not quiet:
            total = sum(v["bytes"] for v in manifest["files"].values())
            print("[backup] %s: %d files, %.1f MB of data, %.1f MB packed" % (final, len(manifest["files"]), total / 1e6, os.path.getsize(final) / 1e6))
        return final, manifest
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _openssl(args, passphrase):
    exe = shutil.which("openssl")
    if not exe:
        sys.exit("[backup] --encrypt needs the openssl command (it is on Render's Linux and on Macs); none found here")
    env = dict(os.environ, UAPLY_BACKUP_PASSPHRASE=passphrase)
    r = subprocess.run([exe, "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-pass", "env:UAPLY_BACKUP_PASSPHRASE"] + args,
                       env=env, capture_output=True, text=True)
    if r.returncode:
        sys.exit("[backup] openssl failed: %s" % (r.stderr.strip()[:300] or r.returncode))


def _passphrase():
    p = os.environ.get("UAPLY_BACKUP_PASSPHRASE") or ""
    if len(p) < 12:
        sys.exit("[backup] set UAPLY_BACKUP_PASSPHRASE (12 characters or more) in this shell first; it is never saved anywhere. "
                 "Write it down somewhere safe: without it the backup cannot be opened.")
    return p


def encrypt_file(path):
    out = path + ".enc"
    _openssl(["-salt", "-in", path, "-out", out], _passphrase())
    os.remove(path)
    return out


def decrypt_to(path, out):
    _openssl(["-d", "-in", path, "-out", out], _passphrase())


def open_backup(path, work):
    """The .tar.gz of a backup (decrypted into work/ when it is a .enc), and its manifest."""
    if path.endswith(".enc"):
        plain = os.path.join(work, "backup.tar.gz")
        decrypt_to(path, plain)
        path = plain
    tar = tarfile.open(path, "r:gz")
    try:
        manifest = json.load(tar.extractfile("manifest.json"))
    except (KeyError, ValueError) as e:
        tar.close()
        sys.exit("[backup] %s is not a UAply backup (no readable manifest.json: %s)" % (path, e))
    return tar, manifest


def safe_member(m):
    name = m.name
    return (m.isfile() and name.startswith("data/") and ".." not in name.split("/") and not name.startswith("/") and ":" not in name
            and "\\" not in name)


def restore(path, data, yes=False):
    if not yes:
        sys.exit("[backup] a restore replaces the files in %s with the backup's. Run again with --yes to go ahead." % data)
    work = tempfile.mkdtemp(prefix="uaply-restore-")
    try:
        tar, manifest = open_backup(path, work)
        with tar:
            members = [m for m in tar.getmembers() if m.name != "manifest.json"]
            bad = [m.name for m in members if not safe_member(m)]
            if bad:
                sys.exit("[backup] refused: the backup has entries outside its data folder: %s" % bad[:5])
            stage = os.path.join(data, ".restore-%d" % os.getpid())   # on the same disk, so each file is moved into place in one step
            os.makedirs(stage, exist_ok=True)
            try:
                for m in members:
                    rel = m.name[len("data/"):]
                    dst = os.path.join(stage, *rel.split("/"))
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    with tar.extractfile(m) as src, open(dst, "wb") as f:
                        shutil.copyfileobj(src, f)
                    want = manifest["files"].get(rel)
                    if not want or want["sha256"] != sha256(dst):
                        sys.exit("[backup] refused: %s does not match the manifest (the backup is damaged); nothing was changed" % rel)
                missing = sorted(set(manifest["files"]) - {m.name[len("data/"):] for m in members})
                if missing:
                    sys.exit("[backup] refused: the backup lacks files its manifest lists: %s; nothing was changed" % missing[:5])
                before, _ = make_backup(data, os.path.join(data, "backups"), keep=0, quiet=True, label="before restore of " + os.path.basename(path))
                print("[backup] the current data was saved first: %s" % before)
                for rel in sorted(manifest["files"]):
                    dst = os.path.join(data, *rel.split("/"))
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    for side in ("-wal", "-shm", "-journal"):            # an old database's side files must not be applied to the restored one
                        if rel.endswith(".db") and os.path.exists(dst + side):
                            os.remove(dst + side)
                    os.replace(os.path.join(stage, *rel.split("/")), dst)
            finally:
                shutil.rmtree(stage, ignore_errors=True)
        print("[backup] restored %d files from %s (made %s). Restart the server now so it reads them (on Render: Manual Deploy > Restart service)."
              % (len(manifest["files"]), os.path.basename(path), manifest.get("made")))
    finally:
        shutil.rmtree(work, ignore_errors=True)


def list_backup(path):
    work = tempfile.mkdtemp(prefix="uaply-list-")
    try:
        tar, manifest = open_backup(path, work)
        tar.close()
        print("backup made %s from %s%s" % (manifest.get("made"), manifest.get("from"), (" (commit %s)" % manifest["commit"]) if manifest.get("commit") else ""))
        for rel, v in sorted(manifest["files"].items()):
            print("  %10d  %s" % (v["bytes"], rel))
        return manifest
    finally:
        shutil.rmtree(work, ignore_errors=True)


def upload_github(path, repo, api="https://api.github.com", uploads="https://uploads.github.com"):
    """Upload the backup as an asset of a new release in a PRIVATE GitHub repository (free, off Render). The token is a fine-grained one the
    owner created for that one repository with Contents: read and write, typed into this shell as GITHUB_BACKUP_TOKEN; never saved."""
    token = os.environ.get("GITHUB_BACKUP_TOKEN") or ""
    if not re.fullmatch(r"[A-Za-z0-9_]{20,255}", token):
        sys.exit("[backup] set GITHUB_BACKUP_TOKEN in this shell first (a fine-grained token for %s only, Contents: read and write)" % repo)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        sys.exit("[backup] --upload takes OWNER/REPO, e.g. saifsiddiqueep-sketch/uaply-backups")
    h = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "uaply-backup"}

    def call(method, url, body=None, ctype="application/json"):
        data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
        rq = urllib.request.Request(url, data=data, method=method, headers=dict(h, **({"Content-Type": ctype} if data is not None else {})))
        try:
            with urllib.request.urlopen(rq, timeout=300) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            sys.exit("[backup] GitHub said %d to %s %s: %s" % (e.code, method, url.split("?")[0], e.read()[:300].decode("utf-8", "replace")))

    meta = call("GET", "%s/repos/%s" % (api, repo))
    if meta.get("private") is not True:
        sys.exit("[backup] refused: %s is not a private repository. Backups hold password hashes and email addresses." % repo)
    name = os.path.basename(path)
    tag = "backup-" + re.sub(r"^uaply-backup-|\.tar\.gz(\.enc)?$", "", name)
    rel = call("POST", "%s/repos/%s/releases" % (api, repo), {"tag_name": tag, "name": tag, "body": "UAply data backup %s" % name, "draft": False, "prerelease": True})
    with open(path, "rb") as f:
        blob = f.read()
    asset = call("POST", "%s/repos/%s/releases/%s/assets?name=%s" % (uploads, repo, rel["id"], urllib.parse.quote(name)), blob, "application/octet-stream")
    if asset.get("size") != len(blob):
        sys.exit("[backup] the upload did not finish (GitHub has %s bytes of %d)" % (asset.get("size"), len(blob)))
    print("[backup] uploaded to %s, release %s (%d bytes)" % (repo, tag, len(blob)))
    return tag


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", help="the data folder (default UAPLY_DATA_DIR, else ./data)")
    ap.add_argument("--out", help="where backups go (default <data>/backups)")
    ap.add_argument("--keep", type=int, default=4, help="how many backups to keep in --out (default 4; 0 keeps all)")
    ap.add_argument("--encrypt", action="store_true", help="encrypt with openssl, passphrase from UAPLY_BACKUP_PASSPHRASE")
    ap.add_argument("--upload", metavar="OWNER/REPO", help="upload to a private GitHub repository's releases (token from GITHUB_BACKUP_TOKEN)")
    ap.add_argument("--list", metavar="FILE", help="show what a backup holds")
    ap.add_argument("--restore", metavar="FILE", help="put a backup back into the data folder")
    ap.add_argument("--yes", action="store_true", help="confirm a restore")
    a = ap.parse_args(argv)
    data = data_dir(a.data)
    if a.list:
        return list_backup(a.list)
    if a.restore:
        return restore(a.restore, data, a.yes)
    path, _ = make_backup(data, os.path.abspath(a.out) if a.out else os.path.join(data, "backups"), a.keep, a.encrypt)
    if a.upload:
        if not path.endswith(".enc"):
            print("[backup] note: uploading without --encrypt; the repository must stay private")
        upload_github(path, a.upload)
    return path


if __name__ == "__main__":
    main()
