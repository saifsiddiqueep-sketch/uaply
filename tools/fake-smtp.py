"""A stand-in mail server for tests: accepts any message over real SMTP and writes it to a file. Nothing leaves this computer.
  python tools/fake-smtp.py [port] [file] [control-file]      (default 2525, ./data/fake-smtp.jsonl, no control file)
Point UAply at it with:  "smtp": {"host": "127.0.0.1", "port": 2525, "starttls": false, "from_addr": "uaply@example.com"}

The optional control file (JSON, read again on every command, so a test can change it while the server runs) makes it answer the way a
real mail service does when it refuses something, for example Brevo with a revoked key or a used-up daily quota:
  {"auth": "535 5.7.8 Authentication failed"}           refuse the login (AUTH PLAIN is offered when a control file is given)
  {"rcpt": {"bad@example.com": "550 5.1.1 no such user", "*": "..."}}   refuse one address, or every address with "*"
  {"data": "421 4.7.0 Daily sending quota exceeded"}    refuse every message after DATA
  {"data_once": ["451 4.3.0 try again"]}                refuse the next message(s) once each, then accept again
  {"drop": true}                                        close the connection right after the greeting"""
import json
import os
import socketserver
import sys
import threading

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 2525
OUT = sys.argv[2] if len(sys.argv) > 2 else "data/fake-smtp.jsonl"
CONTROL = sys.argv[3] if len(sys.argv) > 3 else ""
_lock = threading.Lock()


def control():
    if not CONTROL:
        return {}
    try:
        with open(CONTROL, encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def take_once():
    """The next one-time refusal for DATA, removed from the control file as it is used."""
    with _lock:
        c = control()
        once = c.get("data_once") or []
        if not once:
            return ""
        c["data_once"] = once[1:]
        with open(CONTROL, "w", encoding="utf-8") as f:
            json.dump(c, f)
        return once[0]


class H(socketserver.StreamRequestHandler):
    def reply(self, line):
        self.wfile.write((line + "\r\n").encode())

    def handle(self):
        if control().get("drop"):
            return
        self.reply("220 fake ESMTP ready")
        frm, rcpt = "", []
        while True:
            line = self.rfile.readline()
            if not line:
                return
            cmd = line.decode("utf-8", "replace").strip()
            up = cmd.upper()
            c = control()
            if up.startswith(("EHLO", "HELO")):
                if CONTROL and up.startswith("EHLO"):
                    self.reply("250-fake")
                    self.reply("250 AUTH PLAIN")
                else:
                    self.reply("250 fake")
            elif up.startswith("AUTH"):
                self.reply(c.get("auth") or "235 2.7.0 ok")
            elif up.startswith("MAIL FROM"):
                frm, rcpt = cmd[10:].strip(" <>"), []
                self.reply("250 ok")
            elif up.startswith("RCPT TO"):
                addr = cmd[8:].strip(" <>")
                refuse = (c.get("rcpt") or {}).get(addr.lower()) or (c.get("rcpt") or {}).get("*")
                if refuse:
                    self.reply(refuse)
                else:
                    rcpt.append(addr)
                    self.reply("250 ok")
            elif up == "DATA":
                self.reply("354 end with <CRLF>.<CRLF>")
                body = []
                while True:
                    ln = self.rfile.readline().decode("utf-8", "replace")
                    if ln in (".\r\n", ".\n", ""):
                        break
                    body.append(ln[1:] if ln.startswith("..") else ln)
                refuse = c.get("data") or take_once()
                if refuse:
                    self.reply(refuse)
                    continue
                with _lock, open(OUT, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"from": frm, "to": rcpt, "raw": "".join(body)}) + "\n")
                self.reply("250 queued")
            elif up == "QUIT":
                self.reply("221 bye")
                return
            else:
                self.reply("250 ok")


class S(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
S(("127.0.0.1", PORT), H).serve_forever()
