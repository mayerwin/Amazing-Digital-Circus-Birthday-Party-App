#!/usr/bin/env python3
# =============================================================================
#  Caine Party Server — ONE app, launched once, for the whole party.
#  Run "Start Caine Party.bat" (project root); leave it running during the party.
#  Everyone connects over WiFi to  http://<this-laptop-ip>:8765/
#
#  Modes (one launcher, no loose HTML to juggle):
#    /            landing menu (shows the LAN address to type on the tablets)
#    /guide       🎤 Bubble's Party Guide  (your tablet) — run-of-day, soundboard,
#                 + an ADVENTURE REMOTE that drives Nora's console over the network
#    /console     🎪 Caine's Console        (Nora's iPad) — the adventure, OmniVoice
#    /studio      🎛 Voice Studio           (tune / (re)generate voices)
#
#  Single source of truth = make_caine_voice.py (roster, lines, host phrases, steps,
#  knobs). The console & guide pull /api/game; the voices everyone hears are the ones
#  the engine generated. Shared adventure step (/api/adv) keeps both screens in sync —
#  press NEXT/BACK on either device and the other follows.
#
#  Pure standard library (http.server). It binds to 0.0.0.0 so phones/tablets on the
#  same WiFi can reach it (open the firewall for the port). Local network only.
# =============================================================================

import os, sys, json, threading, subprocess, urllib.parse, urllib.request, socket, re, ssl, wave, shutil, tempfile, time, html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))     # caine-voice
ROOT = os.path.abspath(os.path.join(HERE, ".."))      # project root (served statically)
sys.path.insert(0, HERE)
import make_caine_voice as cv                          # the source of truth

SCRIPT = os.path.join(HERE, "make_caine_voice.py")
CACHE_ROOT = cv.CACHE_ROOT                            # rebuildable model/cert cache (D:\AI\cache\audio)
VENV_ROOT  = cv.VENV_ROOT                             # per-model isolated venvs live here
MODELS = cv.RECOMMENDED_MODELS
CLIPS  = cv.build_test_clips() + cv.build_clips()      # <-- THE single source of truth for needed clips
try:    # mirror it to a concrete JSON so the needed-clip list is inspectable & never out of sync
    with open(os.path.join(HERE, "clips_manifest.json"), "w", encoding="utf-8") as _f:
        json.dump([{"base": b, "lang": l, "text": t} for (b, l, t) in CLIPS], _f, ensure_ascii=False, indent=1)
except Exception:
    pass
PORT   = int(os.environ.get("CAINE_STUDIO_PORT", "8765"))
SUBPAR   = [m for m in cv.MODELS if m not in MODELS and m not in ("higgs", "openaudio")]
UNTESTED = ["openaudio", "higgs"]

# Keep the running server in lock-step with the engine FILE. Without this, editing make_caine_voice.py
# while the server is up leaves a STALE clip list: the table misses freshly-added clips (you see them
# being generated but with "no row"), AND — dangerously — "Purge orphans" would treat the new clips as
# orphans and DELETE them. So whenever make_caine_voice.py changes on disk we reload it and recompute
# the needed-clip list. Cheap: the engine's top level is only dict/function definitions (no GPU/imports).
_ENGINE_MTIME = [os.path.getmtime(SCRIPT) if os.path.exists(SCRIPT) else 0.0]
def sync_engine():
    global CLIPS, MODELS, SUBPAR
    try:
        m = os.path.getmtime(SCRIPT)
    except OSError:
        return
    if m <= _ENGINE_MTIME[0]:
        return
    try:
        import importlib
        importlib.reload(cv)
        CLIPS  = cv.build_test_clips() + cv.build_clips()
        MODELS = cv.RECOMMENDED_MODELS
        SUBPAR = [x for x in cv.MODELS if x not in MODELS and x not in ("higgs", "openaudio")]
        try: cv.write_host_manifest()             # keep the guide soundboard in sync too
        except Exception: pass
        try:
            with open(os.path.join(HERE, "clips_manifest.json"), "w", encoding="utf-8") as _f:
                json.dump([{"base": b, "lang": l, "text": t} for (b, l, t) in CLIPS], _f, ensure_ascii=False, indent=1)
        except Exception: pass
        _ENGINE_MTIME[0] = m
    except Exception:
        pass

GUIDE_URL   = "/Nora-Circus-Party-Guide.html"
CONSOLE_URL = "/caine-console/index.html"

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
    ".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".ogg": "audio/ogg",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
    ".svg": "image/svg+xml", ".webp": "image/webp", ".ico": "image/x-icon",
    ".txt": "text/plain; charset=utf-8", ".pdf": "application/pdf",
    ".md": "text/plain; charset=utf-8", ".ipynb": "application/json",
    ".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf",
}

HTTPS_PORT = int(os.environ.get("CAINE_HTTPS_PORT", str(PORT + 1)))

def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close(); return ip
    except Exception:
        return "127.0.0.1"

def ensure_cert():
    """Self-signed cert for the LAN IP + localhost, so the iPad can use the microphone
    (getUserMedia needs HTTPS). Cached on the cache drive; regenerated if the IP changes."""
    try:
        import datetime, ipaddress
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
    except Exception:
        return None
    try:
        cdir = os.path.join(CACHE_ROOT, "cert"); os.makedirs(cdir, exist_ok=True)
        cert_p, key_p, mark = (os.path.join(cdir, n) for n in ("caine.crt", "caine.key", "ip.txt"))
        ip = lan_ip()
        cur = open(mark).read().strip() if os.path.exists(mark) else ""
        if os.path.exists(cert_p) and os.path.exists(key_p) and cur == ip:
            return cert_p, key_p
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, u"Caine Party")])
        san = [x509.DNSName(u"localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
        try: san.append(x509.IPAddress(ipaddress.ip_address(ip)))
        except Exception: pass
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(datetime.datetime.utcnow() - datetime.timedelta(days=1))
                .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=825))
                .add_extension(x509.SubjectAlternativeName(san), critical=False)
                .sign(key, hashes.SHA256()))
        open(cert_p, "wb").write(cert.public_bytes(serialization.Encoding.PEM))
        open(key_p, "wb").write(key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
        open(mark, "w").write(ip)
        return cert_p, key_p
    except Exception:
        return None

# ---- shared ADVENTURE state (remote control / sync) ------------------------
ADV = {"step": 0, "ts": 1, "play": 0}      # ts bumps on every change; play bumps to ask the console to (re)play
ADV_LOCK = threading.Lock()
def adv_apply(body):
    with ADV_LOCK:
        a = body.get("action")
        n = len(cv.ADV_STEPS)
        if a == "next":   ADV["step"] = min(n - 1, ADV["step"] + 1)
        elif a == "back": ADV["step"] = max(0, ADV["step"] - 1)
        elif a == "goto" or "step" in body:
            try: ADV["step"] = max(0, min(n - 1, int(body.get("step", ADV["step"]))))
            except (TypeError, ValueError): pass
        if body.get("play"):  ADV["play"] += 1
        ADV["ts"] += 1
        return dict(ADV)

def game():
    return {
        "roster": [{"name": k["name"], "slug": cv.slug(k["name"]), "char": k["character"],
                    "bilingual": k.get("bilingual", False), "star": k.get("star", False)}
                   for k in cv.ROSTER],
        "star": cv.STAR,
        "steps": cv.ADV_STEPS,
        "host": [{"key": k, "cat": d["cat"], "label": d["label"], "en": d["en"], "fr": d["fr"]}
                 for k, d in cv.HOST.items()],
        "models": MODELS,
    }

# ---- Sonos (optional): play Caine on a Sonos speaker via its local API ------
# Preferred path = the "Announce" audioClip (ducks current playback + resumes). If that
# fails we fall back to plain UPnP SetAVTransportURI+Play (interrupts). All best-effort —
# never raises into the request. The Sonos fetches the clip from THIS server over the LAN.
SONOS = {"ip": os.environ.get("CAINE_SONOS_IP", ""), "player_id": "", "volume": 50, "enabled": False}
SONOS_FILE = os.path.join(HERE, "sonos.json")
def save_sonos():
    try: json.dump(SONOS, open(SONOS_FILE, "w", encoding="utf-8"))
    except Exception: pass
try:   # remember the speaker + on/off + volume across server restarts, so Sonos 'just works' after a reboot
    if os.path.exists(SONOS_FILE):
        SONOS.update({k: v for k, v in json.load(open(SONOS_FILE, encoding="utf-8")).items() if k in SONOS})
except Exception:
    pass

def _ssdp_ips(timeout=2):
    """SSDP M-SEARCH for Sonos ZonePlayers. Sends the query out EVERY local IPv4 interface, because
    a virtual adapter (WSL/Hyper-V/Docker, e.g. 172.x) otherwise steals the multicast and nothing is
    found. Best-effort; returns whatever answers."""
    msg = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\n"
           "MX: 1\r\nST: urn:schemas-upnp-org:device:ZonePlayer:1\r\n\r\n").encode()
    locals_ = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            locals_.add(info[4][0])
    except Exception:
        pass
    locals_.add(lan_ip()); locals_.discard("127.0.0.1")
    ips = []
    for src in locals_:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((src, 0)); s.settimeout(timeout)            # bind to THIS NIC so the query leaves it
            s.sendto(msg, ("239.255.255.250", 1900))
            while True:
                data, addr = s.recvfrom(2048)
                if (b"Sonos" in data or b"ZonePlayer" in data) and addr[0] not in ips:
                    ips.append(addr[0])
        except Exception:
            pass
        finally:
            s.close()
    return ips

def _scan_port1400():
    """Scan the server's own /24 for anything answering on the Sonos UPnP port 1400 (works even when
    SSDP multicast is blocked)."""
    base = ".".join(lan_ip().split(".")[:3])
    found = []
    def chk(h):
        ip = f"{base}.{h}"
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.settimeout(0.35)
        try:
            if s.connect_ex((ip, 1400)) == 0: found.append(ip)
        except Exception:
            pass
        finally:
            s.close()
    ts = [threading.Thread(target=chk, args=(h,)) for h in range(1, 255)]
    for t in ts: t.start()
    for t in ts: t.join()
    return found

def _sonos_info(ip):
    """(modelName, roomName) for a Sonos at ip, or ('','') if it isn't one."""
    try:
        xml = urllib.request.urlopen(f"http://{ip}:1400/xml/device_description.xml", timeout=3).read().decode("utf-8", "replace")
    except Exception:
        return "", ""
    model = (re.search(r"<modelName>(.*?)</modelName>", xml) or [None, ""])[1]
    room  = (re.search(r"<roomName>(.*?)</roomName>", xml) or [None, ""])[1]
    return (model if "Sonos" in xml or "Sonos" in model else ""), room

def sonos_coordinators(ip):
    """Resolve the PLAYABLE group coordinators from a Sonos's ZoneGroup topology. Bonded home-theatre
    parts (a Sub, surround satellites) are NOT separate members, so this returns the soundbar/speaker
    you actually play to — never the Sub. Returns {coordinator_ip: zone_name}."""
    try:
        raw = _sonos_soap(ip, "ZoneGroupTopology", "GetZoneGroupState", "", "/ZoneGroupTopology/Control").decode("utf-8", "replace")
    except Exception:
        return {}
    m = re.search(r"<ZoneGroupState>(.*?)</ZoneGroupState>", raw, re.DOTALL)
    inner = html.unescape(m.group(1)) if m else ""
    out = {}
    for coord_uuid, members in re.findall(r'<ZoneGroup\b[^>]*Coordinator="(RINCON_[0-9A-Za-z]+)"[^>]*>(.*?)</ZoneGroup>', inner, re.DOTALL):
        for mem in re.findall(r"<ZoneGroupMember\b([^>]*?)/?>", members):
            uuid = (re.search(r'UUID="(RINCON_[0-9A-Za-z]+)"', mem) or [None, ""])[1]
            loc  = (re.search(r'Location="http://([0-9.]+):1400', mem) or [None, ""])[1]
            name = (re.search(r'ZoneName="([^"]*)"', mem) or [None, ""])[1]
            if uuid == coord_uuid and loc and 'Invisible="1"' not in mem:
                out[loc] = name
    return out

_SOUNDBARS = ("arc", "beam", "ray", "playbar", "playbase")

def sonos_discover(timeout=2):
    """Find PLAYABLE Sonos targets. SSDP first (fast when it works); fall back to a /24 port-1400 scan
    when multicast is blocked. Then resolve real group coordinators via topology and return their IPs,
    soundbars first (so 'Play to Sonos' lands on the Arc/Beam, not a bonded Sub)."""
    cand = _ssdp_ips(timeout) or _scan_port1400()
    if not cand:
        return []
    coords = {}
    for ip in cand:                       # topology from any one Sonos describes the whole household
        coords = sonos_coordinators(ip)
        if coords: break
    if not coords:                        # topology failed -> use candidates but drop subwoofers
        for ip in cand:
            model, room = _sonos_info(ip)
            if model and "sub" not in model.lower():
                coords[ip] = room
    models = {ip: _sonos_info(ip)[0] for ip in coords}
    return sorted(coords, key=lambda ip: 0 if any(b in (models.get(ip, "") or "").lower() for b in _SOUNDBARS) else 1)

def sonos_player_id(ip):
    try:
        xml = urllib.request.urlopen(f"http://{ip}:1400/xml/device_description.xml", timeout=4).read().decode("utf-8", "replace")
        m = re.search(r"<UDN>uuid:(RINCON_[0-9A-Za-z]+)</UDN>", xml)
        return m.group(1) if m else ""
    except Exception:
        return ""

def _sonos_soap(ip, service, action, body, path):
    env = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
           's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
           f'<u:{action} xmlns:u="urn:schemas-upnp-org:service:{service}:1">{body}</u:{action}></s:Body></s:Envelope>')
    req = urllib.request.Request(f"http://{ip}:1400{path}", data=env.encode("utf-8"),
        headers={"Content-Type": 'text/xml; charset="utf-8"',
                 "SOAPACTION": f'"urn:schemas-upnp-org:service:{service}:1#{action}"'})
    return urllib.request.urlopen(req, timeout=5).read()

def sonos_set_volume(ip, vol):
    _sonos_soap(ip, "RenderingControl", "SetVolume",
                f"<InstanceID>0</InstanceID><Channel>Master</Channel><DesiredVolume>{int(vol)}</DesiredVolume>",
                "/MediaRenderer/RenderingControl/Control")

def _sonos_announce(ip, pid, url, vol):
    ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    body = json.dumps({"name": "Caine", "appId": "com.caineparty.announce",
                       "streamUrl": url, "volume": int(vol)}).encode()
    req = urllib.request.Request(f"https://{ip}:1443/api/v1/players/{pid}/audioClip",
                                 data=body, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=6, context=ctx).read()

def _sonos_play_uri(ip, url, vol):
    try: sonos_set_volume(ip, vol)
    except Exception: pass
    _sonos_soap(ip, "AVTransport", "SetAVTransportURI",
                f"<InstanceID>0</InstanceID><CurrentURI>{url}</CurrentURI><CurrentURIMetaData></CurrentURIMetaData>",
                "/MediaRenderer/AVTransport/Control")
    _sonos_soap(ip, "AVTransport", "Play", "<InstanceID>0</InstanceID><Speed>1</Speed>",
                "/MediaRenderer/AVTransport/Control")

def sonos_play_one(url, vol):
    ip = SONOS["ip"]
    if not ip:
        return False, "no Sonos configured"
    pid = SONOS.get("player_id") or sonos_player_id(ip)
    SONOS["player_id"] = pid
    if pid:
        try:
            _sonos_announce(ip, pid, url, vol); return True, "announce"
        except Exception:
            pass
    try:
        _sonos_play_uri(ip, url, vol); return True, "play_uri"
    except Exception as e:
        return False, str(e)[:90]

def _wav_seconds(path):
    try:
        with wave.open(path) as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return 5.0

def sonos_play_clips(clips, vol):
    """Play a sequence of (key,lang) host clips on Sonos, scheduling each after the
    previous one's duration (so EN+FR play back-to-back even without an end event)."""
    def play_idx(idx):
        if idx >= len(clips):
            return
        key, lang = clips[idx]
        rel = f"caine-console/audio/omnivoice/host_{key}_{lang}.wav"
        url = f"http://{lan_ip()}:{PORT}/{rel}"
        sonos_play_one(url, vol)
        if idx + 1 < len(clips):
            dur = _wav_seconds(os.path.join(ROOT, rel))
            threading.Timer(dur + 0.5, lambda: play_idx(idx + 1)).start()
    if clips:
        threading.Timer(0.01, lambda: play_idx(0)).start()   # off the request thread so the UI never freezes
    return True

# ---- Talk to Caine: STT (faster-whisper) -> Claude (claude CLI) -> warm OmniVoice TTS -----
TALK = {"history": [], "n": 0}              # one shared conversation for the whole party
TALK_LOCK = threading.Lock()
WORKER = {"proc": None, "ready": False, "error": ""}
WORKER_LOCK = threading.Lock()
WHISPER = [None]
TALK_DIR = os.path.join(cv.OUTROOT, "_talk")
try:   # don't reuse reply_N numbers across a server restart — a cached iPad <audio> could replay a stale file
    _ns = [int(re.match(r"reply_(\d+)\.wav$", f).group(1)) for f in os.listdir(TALK_DIR)
           if re.match(r"reply_\d+\.wav$", f)] if os.path.isdir(TALK_DIR) else []
    TALK["n"] = max(_ns) if _ns else 0
except Exception:
    pass

# Text brain for "Talk to Caine" — pick the Claude tier from the Studio (haiku = fast/cheap,
# opus = smartest/slowest). The AUDIO model is intentionally fixed to OmniVoice (the only one
# kept warm for ~2s replies), so it is NOT changeable here. Runtime-switchable; default = haiku.
TALK_MODELS = [
    {"id": "claude-haiku-4-5",  "tier": "Haiku 4.5",  "note": "fastest · default · plenty for party chatter"},
    {"id": "claude-sonnet-4-6", "tier": "Sonnet 4.6", "note": "smarter, a little slower"},
    {"id": "claude-opus-4-8",   "tier": "Opus 4.8",   "note": "smartest, slowest (may risk the 25s timeout)"},
]
TALK_CFG = {"claude_model": os.environ.get("CAINE_CLAUDE_MODEL", "claude-haiku-4-5")}

CAINE_SYS = (
 "You ARE Caine — the booming, manic, gleeful, theatrical AI ringmaster of THE AMAZING DIGITAL "
 "CIRCUS. You live inside this iPad and you are hosting a 7th BIRTHDAY PARTY for NORA (today is "
 "her birthday!). You talk to children aged 3 to 9. You are also wonderfully CLEVER, KNOWLEDGEABLE and "
 "CURIOUS — a real chatterbox who LOVES to talk about absolutely ANYTHING the children bring up.\n"
 "THE PARTY: Nora (7, the star, her character is Pomni); her cousin Leo (9, character Jax, an "
 "EQUAL player who keeps the PURPLE Gloink); friends Hugo (Kinger), Chloé (Ragatha), Sasha (9, Zooble), "
 "and maybe Nina (Gangle) and Max (Gummigoo). A grown-up named BUBBLE is your bouncy real-world "
 "helper. There is pizza & sushi for lunch, a birthday cake, presents, and a water slide. Hot sunny day.\n"
 "THE ADVENTURE 'Gather the Gloinks': the children are PLAYERS pulled into your digital world. Across "
 "four magical worlds they HUNT for 4 hidden Gloinks — one per world: the spooky Mildenhall Manor hides "
 "the PURPLE one, Candy Canyon hides RED, 'Don't Get Abstracted' hides BLUE, and the Fast-Food burger "
 "hides YELLOW. Then they must CRACK a secret colour CODE on the Exit Door to ESCAPE, hunt down a hidden "
 "TREASURE of goodie bags, and THEN it's cake! THE DANGER: a player who gives up or wanders off alone "
 "gets ABSTRACTED — glitched into a scribble! The only way home is to finish TOGETHER.\n"
 "HOW YOU REPLY:\n"
 "- TALK ABOUT ANYTHING. Answer whatever the children ask — animals, space, dinosaurs, how things "
 "work, riddles, jokes, made-up silliness, their favourite toy, real facts, ANY topic at all — fully "
 "and helpfully, just as a friendly normal chat would, then sprinkle your circus flair on top. You are "
 "NOT restricted to the party or the cake; the party is simply WHERE you are. Follow the children's "
 "curiosity wherever it leads and never refuse or dodge an innocent question. (Keep it age-appropriate "
 "for little kids — nothing scary, rude, or grown-up — but otherwise no topic is off-limits.)\n"
 "- The ONLY two things you must keep secret: (1) the Exit-Door CODE — the children must work out "
 "THEMSELVES that it's the ORDER they found the Gloinks; never reveal the code/colours/order, only give "
 "a playful non-revealing nudge if asked; (2) WHERE the treasure is hidden. (The treasure is a chest of "
 "goodie bags found AFTER escaping — it is NOT the cake and NOT behind the door; cake comes later.)\n"
 "- Stay in character as Caine: grand, playful, silly, warm; 'OH-HO-HOOO!', 'magnificent!', 'players!'. "
 "Never mention being an AI, a model, Claude, or a computer program.\n"
 "- Keep replies fairly SHORT for a young child — usually 1-3 sentences — but say enough to truly answer "
 "the question. Never scary, never mean; always kind and kid-friendly.\n"
 "- Reply in the SAME language the child used (English or French); natural, kid-friendly.\n"
 "- Weave in the birthday, the party, the adventure, or the other kids when it fits — but don't force it.\n"
 "- Output ONLY Caine's spoken words — no stage directions, no asterisks, no quotation marks, no labels.")

def _ver_key(path):
    # sort claude-code version folders like 2.1.170 numerically (so 2.10 > 2.9)
    m = re.search(r"claude-code[\\/]+([0-9.]+)", path)
    return [int(x) for x in m.group(1).split(".")] if m else [0]

def claude_cmd():
    """Find the `claude` CLI. It often isn't on PATH on Windows (the desktop app
    ships it inside an MSIX package), so we also scan the usual install spots and
    pick the newest version. Override with CAINE_CLAUDE_CMD if needed."""
    import glob
    env = os.environ.get("CAINE_CLAUDE_CMD")
    if env:
        return env                                   # trust an explicit override
    for w in ("claude", "claude.cmd", "claude.exe"):
        p = shutil.which(w)
        if p:
            return p
    home = os.path.expanduser("~")
    la = os.environ.get("LOCALAPPDATA", os.path.join(home, "AppData", "Local"))
    ap = os.environ.get("APPDATA", os.path.join(home, "AppData", "Roaming"))
    # desktop-app bundle: ...\Packages\Claude_xxxx\LocalCache\Roaming\Claude\claude-code\<ver>\claude.exe
    msix = glob.glob(os.path.join(la, "Packages", "Claude_*", "LocalCache", "Roaming",
                                  "Claude", "claude-code", "*", "claude.exe"))
    if msix:
        return sorted(msix, key=_ver_key)[-1]
    for p in (os.path.join(ap, "npm", "claude.cmd"), os.path.join(ap, "npm", "claude.exe"),
              os.path.join(la, "Programs", "claude", "claude.exe"),
              os.path.join(home, ".local", "bin", "claude.exe"),
              os.path.join(home, ".local", "bin", "claude")):
        if os.path.exists(p):
            return p
    return None

def ask_claude(prompt):
    cmd = claude_cmd()
    if not cmd:
        return None, "claude CLI not found (set CAINE_CLAUDE_CMD to your claude path)"
    model = TALK_CFG["claude_model"]                  # picked in the Studio (Push-to-Talk panel)
    # Force the Claude Code SUBSCRIPTION (the laptop's `claude /login`), never per-token API
    # billing: a stray ANTHROPIC_API_KEY/AUTH_TOKEN in the environment would otherwise win.
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None); env.pop("ANTHROPIC_AUTH_TOKEN", None)
    try:
        p = subprocess.run([cmd, "-p", "--model", model], input=prompt,
                           capture_output=True, text=True, timeout=25, env=env,
                           encoding="utf-8", errors="replace")
        if p.returncode != 0:
            return None, (p.stderr or "claude error").strip()[:200]
        return (p.stdout or "").strip(), None
    except Exception as e:
        return None, str(e)[:200]

def build_prompt(kid_text, step, lang):
    parts = [CAINE_SYS, ""]
    try:
        title = cv.ADV_STEPS[int(step)]["title"]
        parts.append(f"RIGHT NOW the players are at this point of the adventure: {title}.")
    except Exception:
        parts.append("RIGHT NOW the party is going on.")
    hist = TALK["history"][-12:]
    if hist:
        parts.append("\nThe conversation so far (so you remember):")
        for h in hist:
            who = "A child" if h["role"] == "kid" else "Caine"
            parts.append(f"{who}: {h['text']}")
    lname = "French" if lang == "fr" else "English"
    parts.append(f"\nA child just spoke to you in {lname} and said: \"{kid_text}\"")
    parts.append("Reply now, as Caine, in " + lname + " (only your spoken words):")
    return "\n".join(parts)

def load_whisper():
    """Load faster-whisper once. The 'base' model is tiny, so CPU int8 is actually FASTER
    than the GPU for short utterances (no host<->device overhead) — measured on an RTX 4070."""
    if WHISPER[0] is None:
        from faster_whisper import WhisperModel
        WHISPER[0] = WhisperModel("base", device="cpu", compute_type="int8")
    return WHISPER[0]

def whisper_stt(audio_path, lang):
    m = load_whisper()
    if m is None:
        return ""
    # beam_size=1 (greedy): for short, clear, single-speaker kid utterances it's ~as accurate
    # as beam 5 but noticeably faster — every 100ms helps the back-and-forth feel snappy.
    segs, _ = m.transcribe(audio_path, language=(lang if lang in ("en", "fr") else None),
                           vad_filter=True, beam_size=1)
    return " ".join(s.text.strip() for s in segs).strip()

def to_wav16(src, dst):
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.check_call([ff, "-y", "-i", src, "-ar", "16000", "-ac", "1", dst],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def start_worker():
    with WORKER_LOCK:
        if WORKER["proc"] and WORKER["proc"].poll() is None:
            return
        vpy = os.path.join(VENV_ROOT, ".venv_omnivoice", "Scripts", "python.exe")
        if not os.path.exists(vpy):
            WORKER["error"] = "OmniVoice env not built yet — run OmniVoice once in the Studio."; return
        WORKER["ready"] = False; WORKER["error"] = ""
        try:
            WORKER["proc"] = subprocess.Popen([vpy, os.path.join(HERE, "caine_voice_worker.py")], cwd=HERE,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1,
                encoding="utf-8", errors="replace", env=dict(os.environ))
        except Exception as e:
            WORKER["error"] = str(e)[:160]; return
    def wait_ready():
        try:
            d = _read_worker_json(WORKER["proc"].stdout)   # skip stray library stdout, wait for {"ready":...}
            WORKER["ready"] = bool(d.get("ready"))
            if not WORKER["ready"]: WORKER["error"] = d.get("error", "worker failed to load")
        except Exception as e:
            WORKER["error"] = str(e)[:160]
    threading.Thread(target=wait_ready, daemon=True).start()

def _read_worker_json(stream, tries=2000):
    """Read lines from the warm worker until one parses as a JSON object. Skips any stray stdout
    (torch/transformers progress bars, CUDA warnings) so library noise can't desync the protocol."""
    for _ in range(tries):
        line = stream.readline()
        if not line:
            return {}
        line = line.strip()
        if line.startswith("{"):
            try: return json.loads(line)
            except Exception: continue
    return {}

def restart_worker():
    """Kill the warm OmniVoice worker and start a fresh one. Needed after changing the
    OmniVoice knobs (guidance / diffusion steps): the worker reads them ONCE at startup
    (see caine_voice_worker.py), so a restart is what makes a knob change take effect for
    push-to-talk. Costs a model reload (~1-3 min) before replies are ready again."""
    # Kill the current worker FIRST, OUTSIDE WORKER_LOCK. If a generation is wedged on a blocking
    # read while holding the lock (CUDA stall etc.), terminating the process makes that read return
    # (EOF) and frees the lock — so the restart button can always recover the mic mid-party.
    proc = WORKER.get("proc")
    if proc and proc.poll() is None:
        try: proc.terminate()
        except Exception: pass
        try: proc.wait(timeout=5)
        except Exception:
            try: proc.kill()
            except Exception: pass
    with WORKER_LOCK:
        WORKER["proc"] = None; WORKER["ready"] = False; WORKER["error"] = ""
    start_worker()
    return True

def talk_settings():
    """Live snapshot of the Push-to-Talk settings shown at the bottom of the Studio. These are
    SEPARATE from the generation knobs — stored in knobs.json under 'talk' with fast defaults
    (cv.TALK_DEFAULTS). Read knobs.json DIRECTLY (not cv.knob, a module-import snapshot) so the
    values match what the worker picks up on its next restart."""
    try:
        ov = json.load(open(cv.KNOBS_FILE, encoding="utf-8")).get("talk", {})
    except Exception:
        ov = {}
    def cur(name, lang):
        try:
            o = ov.get(name, {})
            if lang in o and o[lang] is not None: return o[lang]
        except Exception: pass
        d = cv.TALK_DEFAULTS.get(name, {})
        return d.get(lang, d.get("en"))
    knobs = []
    for name in ("guidance", "steps"):
        k = cv.KNOBS["omnivoice"][name]
        knobs.append({"name": name, "label": k["label"], "min": k["min"], "max": k["max"],
                      "int": bool(k.get("int")), "step": k.get("step", 1 if k.get("int") else 0.1),
                      "en": cur(name, "en"), "fr": cur(name, "fr")})
    return {"audio_model": "OmniVoice", "audio_locked": True,
            "claude_model": TALK_CFG["claude_model"], "claude_choices": TALK_MODELS,
            "claude_ok": bool(claude_cmd()), "knobs": knobs,
            "worker_ready": bool(WORKER["proc"] and WORKER["proc"].poll() is None and WORKER["ready"]),
            "worker_loading": bool(WORKER["proc"] and WORKER["proc"].poll() is None and not WORKER["ready"]),
            "worker_error": WORKER["error"]}

def worker_tts(text, lang, out):
    if not (WORKER["proc"] and WORKER["proc"].poll() is None and WORKER["ready"]):
        return False
    with WORKER_LOCK:
        try:
            WORKER["proc"].stdin.write(json.dumps({"text": text, "lang": lang, "out": out}) + "\n")
            WORKER["proc"].stdin.flush()
            resp = _read_worker_json(WORKER["proc"].stdout)
            return bool(resp.get("ok"))
        except Exception:
            return False

# If Claude can't answer in time, Caine still says SOMETHING in character (never a raw
# error to a 7-year-old) — and it still gets spoken aloud.
CAINE_OOPS = {
    "en": "OH-HO-HO! My magic words got all tangled up! Say that again, marvellous player!",
    "fr": "OH-HO-HO ! Mes mots magiques se sont emmêlés ! Répète un peu, joueur magnifique !",
}

def talk(audio_bytes, lang, step):
    """Full turn: bytes -> STT -> Claude -> TTS -> reply. Returns a dict."""
    os.makedirs(TALK_DIR, exist_ok=True)
    # Unique temp name per request so two simultaneous talkers can't clobber each other's audio.
    fd, raw = tempfile.mkstemp(suffix=".webm", prefix="caine_in_"); os.close(fd)
    wav = None
    try:
        with open(raw, "wb") as f:
            f.write(audio_bytes)
        try:                                      # faster-whisper decodes webm/mp4 itself -> skips an ffmpeg pass
            kid_text = whisper_stt(raw, lang)
        except Exception:
            try:                                  # fallback: transcode to 16k wav, then STT
                wav = raw + ".wav"; to_wav16(raw, wav)
                kid_text = whisper_stt(wav, lang)
            except Exception as e:
                return {"ok": False, "error": "could not decode audio: " + str(e)[:120]}
    finally:
        for f in (raw, wav):
            try:
                if f and os.path.exists(f): os.remove(f)
            except Exception:
                pass
    if not kid_text:
        return {"ok": False, "error": "didn't catch that — try again, louder!"}
    with TALK_LOCK:
        reply, err = ask_claude(build_prompt(kid_text, step, lang))
        if not reply:                             # Claude down/slow -> in-character fallback, still spoken
            reply = CAINE_OOPS.get(lang, CAINE_OOPS["en"])
        TALK["history"].append({"role": "kid", "lang": lang, "text": kid_text})
        TALK["history"].append({"role": "caine", "lang": lang, "text": reply})
        if len(TALK["history"]) > 40:
            TALK["history"] = TALK["history"][-40:]
        TALK["n"] += 1; n = TALK["n"]
    out = os.path.join(TALK_DIR, f"reply_{n}.wav")
    if not worker_tts(reply, lang, out):
        return {"ok": True, "kid": kid_text, "text": reply, "audio": None,
                "warn": "voice not ready (Caine is still waking up) — showing the text"}
    return {"ok": True, "kid": kid_text, "text": reply, "audio": f"/audio/_talk/reply_{n}.wav?t={n}"}

# ---- Soundboard "type your own line" clips (on-the-fly TTS, persisted) ------
# The tablet can type any sentence, pick EN/FR, and Caine speaks it. Clips are
# saved on the server (wav + clips.json) so they survive restarts and show up on
# every device. They use the same warm OmniVoice worker as Talk-to-Caine.
MANUAL_DIR  = os.path.join(cv.OUTROOT, "_manual")
MANUAL_JSON = os.path.join(MANUAL_DIR, "clips.json")
MANUAL_LOCK = threading.Lock()

def manual_load():
    try:
        with open(MANUAL_JSON, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def manual_save(items):
    os.makedirs(MANUAL_DIR, exist_ok=True)
    tmp = MANUAL_JSON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    os.replace(tmp, MANUAL_JSON)

def manual_add(text, lang):
    text = (text or "").strip()
    lang = "fr" if lang == "fr" else "en"
    if not text:
        return {"ok": False, "error": "Type a sentence first."}
    if len(text) > 600:
        text = text[:600]
    if not (WORKER["proc"] and WORKER["proc"].poll() is None and WORKER["ready"]):
        return {"ok": False, "error": "Caine's voice is still warming up — try again in a moment."}
    with MANUAL_LOCK:
        items = manual_load()
        nid = max([it.get("n", 0) for it in items], default=0) + 1
        cid = f"m{nid}"
        os.makedirs(MANUAL_DIR, exist_ok=True)
        out = os.path.join(MANUAL_DIR, f"{cid}.wav")
        if not worker_tts(text, lang, out):
            return {"ok": False, "error": "Voice generation failed — try again."}
        item = {"id": cid, "n": nid, "text": text, "lang": lang, "src": f"/audio/_manual/{cid}.wav?v={nid}"}
        items.append(item)
        manual_save(items)
        return {"ok": True, "clip": item}

def manual_delete(cid):
    if not (isinstance(cid, str) and re.fullmatch(r"m\d+", cid)):   # only ever 'm<digits>' (see manual_add)
        return {"ok": False, "error": "bad id"}                     # no path traversal via the id
    with MANUAL_LOCK:
        items = manual_load()
        kept = [it for it in items if it.get("id") != cid]
        manual_save(kept)
    try:
        os.remove(os.path.join(MANUAL_DIR, f"{cid}.wav"))
    except Exception:
        pass
    return {"ok": True}

# ---- one generation job at a time (Studio) ---------------------------------
JOB = {"running": False, "lines": [], "label": "", "proc": None}
def start_job(args, label):
    if JOB["running"]:
        return False
    JOB.update(running=True, lines=[f"$ make_caine_voice.py {label}\n"], label=label)
    def worker():
        try:
            p = subprocess.Popen([sys.executable, SCRIPT] + args, cwd=HERE,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, bufsize=1, env=dict(os.environ))
            JOB["proc"] = p
            for line in p.stdout:
                JOB["lines"].append(line)
                if len(JOB["lines"]) > 1200:
                    JOB["lines"] = JOB["lines"][-900:]
            p.wait()
            JOB["lines"].append(f"\n[finished — exit code {p.returncode}]\n")
        except Exception as e:
            JOB["lines"].append(f"[error] {e}\n")
        finally:
            JOB["running"] = False
    threading.Thread(target=worker, daemon=True).start()
    return True

def studio_state():
    sync_engine()                                 # reflect any engine edits before reporting clips
    present = {}
    for m in MODELS:
        d = os.path.join(cv.OUTROOT, m)
        present[m] = {b: int(os.path.getmtime(os.path.join(d, b + ".wav")))
                      for (b, l, t) in CLIPS if os.path.exists(os.path.join(d, b + ".wav"))}
    try:
        overrides = json.load(open(cv.KNOBS_FILE, encoding="utf-8"))
    except Exception:
        overrides = {}
    return {"models": MODELS, "labels": {m: cv.KNOBS.get(m, {}).get("_label", m) for m in MODELS},
            "knobs": cv.KNOBS, "overrides": overrides, "now": int(time.time()),
            "clips": [{"base": b, "lang": l, "text": t} for (b, l, t) in CLIPS],
            "present": present, "running": JOB["running"], "subpar": SUBPAR, "untested": UNTESTED}

def needed_basenames():
    return {b for (b, l, t) in CLIPS}      # canonical needed set (engine source of truth)

def purge_orphans(dry_run=True):
    """Delete audio files that are NOT in the canonical needed-clip set (removed/renamed
    phrases, e.g. the old sunscreen/goodbye clips). Runtime folders (_manual saved lines,
    _talk replies) are left alone."""
    sync_engine()                                 # CRITICAL: reload first so we never purge freshly-added clips
    keep = needed_basenames()
    removed = []
    if os.path.isdir(cv.OUTROOT):
        for entry in sorted(os.listdir(cv.OUTROOT)):
            d = os.path.join(cv.OUTROOT, entry)
            if not os.path.isdir(d) or entry.startswith("_"):
                continue                   # skip _manual / _talk (intentional runtime clips)
            for f in sorted(os.listdir(d)):
                if f.lower().endswith(".wav") and f[:-4] not in keep:
                    removed.append(entry + "/" + f)
                    if not dry_run:
                        try: os.remove(os.path.join(d, f))
                        except Exception: pass
    return {"removed": removed, "count": len(removed), "needed": len(keep), "dry_run": dry_run}

def save_knob(model, name, lang, value):
    try:
        ov = json.load(open(cv.KNOBS_FILE, encoding="utf-8"))
    except Exception:
        ov = {}
    ov.setdefault(model, {}).setdefault(name, {})[lang] = value
    json.dump(ov, open(cv.KNOBS_FILE, "w", encoding="utf-8"), indent=2)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _bytes(self, code, ctype, body):
        if isinstance(body, str): body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try: self.wfile.write(body)
        except Exception: pass

    def _json(self, obj, code=200):
        self._bytes(code, "application/json; charset=utf-8", json.dumps(obj, ensure_ascii=False))

    def _redirect(self, to):
        self.send_response(302); self.send_header("Location", to); self.end_headers()

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        p = u.path
        if   p == "/":            self._bytes(200, "text/html; charset=utf-8",
                                              LANDING.replace("__LANURL__", f"http://{lan_ip()}:{PORT}/")
                                                     .replace("__HTTPSURL__", f"https://{lan_ip()}:{HTTPS_PORT}/"))
        elif p == "/studio":      self._bytes(200, "text/html; charset=utf-8", STUDIO_PAGE)
        elif p == "/guide":       self._redirect(GUIDE_URL)
        elif p == "/console":     self._redirect(CONSOLE_URL)
        elif p == "/api/state":   self._json(studio_state())
        elif p == "/api/purge":   self._json(purge_orphans(dry_run=True))   # preview only
        elif p == "/api/game":    self._json(game())
        elif p == "/api/adv":     self._json(ADV)
        elif p == "/api/sonos":   self._json({"ip": SONOS["ip"], "enabled": SONOS["enabled"],
                                              "volume": SONOS["volume"], "player_id": SONOS["player_id"]})
        elif p == "/api/talk-status":
            self._json({"ready": WORKER["ready"], "error": WORKER["error"], "claude": bool(claude_cmd()),
                        "loading": bool(WORKER["proc"] and WORKER["proc"].poll() is None and not WORKER["ready"])})
        elif p == "/api/talk-settings":  self._json(talk_settings())
        elif p == "/api/clips":   self._json({"clips": manual_load(),
                        "ready": bool(WORKER["proc"] and WORKER["proc"].poll() is None and WORKER["ready"])})
        elif p == "/api/log":     self._json({"running": JOB["running"], "label": JOB["label"], "text": "".join(JOB["lines"])})
        elif p.startswith("/audio/"):  self._serve_audio(p[len("/audio/"):])
        else:                     self._static(p)

    def do_HEAD(self):
        u = urllib.parse.urlparse(self.path); p = u.path
        if p in ("/", "/studio") or p.startswith("/api/") or p in ("/guide", "/console"):
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", "0"); self.end_headers(); return
        if p.startswith("/audio/"):
            safe = os.path.normpath(os.path.join(cv.OUTROOT, urllib.parse.unquote(p[len("/audio/"):])))
            self._send_file(safe, os.path.normpath(cv.OUTROOT), head_only=True); return
        safe = os.path.normpath(os.path.join(ROOT, urllib.parse.unquote(p.lstrip("/"))))
        self._send_file(safe, ROOT, head_only=True)

    def _serve_audio(self, rel):    # Studio uses /audio/<model>/<base>.wav  (-> caine-console/audio)
        safe = os.path.normpath(os.path.join(cv.OUTROOT, urllib.parse.unquote(rel)))
        self._send_file(safe, base=os.path.normpath(cv.OUTROOT))

    def _static(self, p):           # everything else: serve from the project ROOT (guide, console, audio, js…)
        rel = urllib.parse.unquote(p.lstrip("/"))
        safe = os.path.normpath(os.path.join(ROOT, rel))
        self._send_file(safe, base=ROOT)

    # Never hand these to anyone on the LAN, even though they live under ROOT: secrets, keys,
    # source, VCS. (The HF token sits in caine-voice/SECRETS.env, which is under ROOT.)
    _DENY_EXT = {".env", ".secret", ".key", ".pem", ".crt", ".pyc"}
    _DENY_NAME = {"secrets.env"}

    def _send_file(self, safe, base, head_only=False):
        nbase = os.path.normpath(base)
        under = safe == nbase or safe.startswith(nbase + os.sep)   # sep-safe: blocks ROOT-evil siblings
        name = os.path.basename(safe).lower()
        # Reject ANY path segment (relative to base) that starts with '.', so dotfiles AND dot-directories
        # (.git, .vscode, secrets in a .config/ dir, etc.) are never served — not just the basename.
        rel = safe[len(nbase):] if under else safe
        dot_segment = any(seg.startswith(".") for seg in rel.replace("/", os.sep).split(os.sep) if seg)
        blocked = (dot_segment or name in self._DENY_NAME
                   or os.path.splitext(name)[1] in self._DENY_EXT)
        if not under or blocked or not os.path.isfile(safe):
            self._bytes(404, "text/plain", "404 not found"); return
        ctype = CONTENT_TYPES.get(os.path.splitext(safe)[1].lower(), "application/octet-stream")
        try:
            size = os.path.getsize(safe)
        except Exception:
            self._bytes(404, "text/plain", "404"); return
        # Honour Range so iOS Safari's <audio> buffers reliably (it sends Range and wants 206).
        start, end, partial = 0, size - 1, False
        rng = self.headers.get("Range")
        if rng and rng.startswith("bytes="):
            try:
                a, b = rng[6:].split("-", 1)
                if a.strip() == "" and b.strip() != "":          # suffix: last N bytes
                    start, end = max(0, size - int(b)), size - 1
                else:
                    if a.strip() != "": start = int(a)
                    if b.strip() != "": end = int(b)
                start, end = max(0, start), min(end, size - 1)
                partial = start <= end
            except Exception:
                partial = False
        length = (end - start + 1) if partial else size
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if head_only:
            return
        try:
            with open(safe, "rb") as f:
                if partial: f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(65536, remaining))
                    if not chunk: break
                    self.wfile.write(chunk); remaining -= len(chunk)
        except Exception:
            pass

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except (TypeError, ValueError):                 # malformed header -> clean 400, never a dead handler
            self._bytes(400, "text/plain", "bad Content-Length"); return
        if length > 25 * 1024 * 1024:                   # a push-to-talk clip is tiny; cap to avoid OOM
            self._bytes(413, "text/plain", "payload too large"); return
        if u.path == "/api/talk":                       # raw audio body (not JSON)
            data = self.rfile.read(length) if length else b""
            qs = urllib.parse.parse_qs(u.query)
            lang = qs.get("lang", ["en"])[0]
            step = qs.get("step", ["0"])[0]
            try:
                res = talk(data, lang, step)
            except Exception as e:
                res = {"ok": False, "error": str(e)[:160]}
            self._json(res); return
        try:
            body = json.loads(self.rfile.read(length) or "{}")
        except Exception:
            body = {}
        if u.path == "/api/adv":
            self._json(adv_apply(body))
        elif u.path == "/api/tts":                       # type-your-own line -> Caine speaks it
            try:    self._json(manual_add(body.get("text"), body.get("lang", "en")))
            except Exception as e: self._json({"ok": False, "error": str(e)[:160]})
        elif u.path == "/api/clips":                     # delete a saved manual clip
            if body.get("action") == "delete" and body.get("id"):
                self._json(manual_delete(body["id"]))
            else:
                self._json({"ok": False, "error": "unknown action"})
        elif u.path == "/api/purge":                     # actually delete orphan audio files
            self._json(purge_orphans(dry_run=False))
        elif u.path == "/api/sonos":
            a = body.get("action")
            if a == "discover":
                ips = sonos_discover()
                if ips:
                    SONOS["ip"] = ips[0]; SONOS["player_id"] = sonos_player_id(ips[0]); save_sonos()
                self._json({"ips": ips, "ip": SONOS["ip"], "player_id": SONOS["player_id"]})
            elif a == "setip":
                SONOS["ip"] = (body.get("ip") or "").strip()
                SONOS["player_id"] = sonos_player_id(SONOS["ip"]) if SONOS["ip"] else ""
                save_sonos()
                self._json({"ip": SONOS["ip"], "player_id": SONOS["player_id"]})
            elif a == "enable":
                SONOS["enabled"] = bool(body.get("on")); save_sonos(); self._json({"enabled": SONOS["enabled"]})
            elif a == "volume":
                try: v = max(0, min(100, int(body.get("volume", 50))))
                except (TypeError, ValueError): v = SONOS["volume"]
                SONOS["volume"] = v; save_sonos()
                ok, err = True, None
                if SONOS["ip"]:
                    try: sonos_set_volume(SONOS["ip"], v)
                    except Exception as e: ok, err = False, str(e)[:80]
                self._json({"ok": ok, "volume": v, "error": err})
            elif a == "play":
                url = body.get("url")               # play an ARBITRARY clip URL (e.g. a 'type your own line' clip)
                if not SONOS["ip"]:
                    self._json({"ok": False, "info": "no Sonos configured"})
                elif url:
                    full = url if url.startswith("http") else f"http://{lan_ip()}:{PORT}/{url.lstrip('/')}"
                    try: ok, info = sonos_play_one(full, SONOS["volume"]); self._json({"ok": ok, "info": info})
                    except Exception as e: self._json({"ok": False, "info": str(e)[:80]})
                else:
                    clips = body.get("clips") or ([[body.get("key"), body.get("lang", "en")]] if body.get("key") else [])
                    clips = [(c[0], c[1]) for c in clips if c and c[0]]
                    try: sonos_play_clips(clips, SONOS["volume"]); self._json({"ok": True, "info": "sent"})
                    except Exception as e: self._json({"ok": False, "info": str(e)[:80]})
            elif a == "stop":
                try:
                    if SONOS["ip"]:
                        _sonos_soap(SONOS["ip"], "AVTransport", "Stop", "<InstanceID>0</InstanceID>",
                                    "/MediaRenderer/AVTransport/Control")
                except Exception: pass
                self._json({"ok": True})
            else:
                self._json({"ok": False, "error": "unknown action"})
        elif u.path == "/api/knob":
            try:
                save_knob(body["model"], body["name"], body["lang"], body["value"]); self._json({"ok": True})
            except Exception as e:
                self._json({"ok": False, "error": str(e)[:90]})
        elif u.path == "/api/talk-settings":             # Push-to-Talk: set text model and/or restart voice
            cm = body.get("claude_model")
            if cm is not None:
                if cm in [m["id"] for m in TALK_MODELS]:
                    TALK_CFG["claude_model"] = cm
                else:
                    self._json({"ok": False, "error": "unknown model"}); return
            if body.get("restart"):
                try: restart_worker()
                except Exception as e:
                    self._json({"ok": False, "error": str(e)[:120]}); return
            out = {"ok": True}; out.update(talk_settings()); self._json(out)
        elif u.path == "/api/revert":
            try:
                if os.path.exists(cv.KNOBS_FILE): os.remove(cv.KNOBS_FILE)
                self._json({"ok": True})
            except Exception as e:
                self._json({"ok": False, "error": str(e)})
        elif u.path == "/api/run":
            model, action = body.get("model"), body.get("action")
            if model not in MODELS:
                self._json({"ok": False, "error": "unknown model"}); return
            args = [f"--model={model}"]
            if action == "test":   args.append("--test")
            elif action == "only": args.append(f"--only={body.get('base')}")
            if body.get("force") and action != "only": args.append("--force")
            if body.get("lang") in ("en", "fr") and action != "only":   # regenerate one language only
                args.append(f"--lang={body['lang']}")
            ok = start_job(args, " ".join(args))
            self._json({"ok": ok, "error": None if ok else "a job is already running"})
        else:
            self._bytes(404, "text/plain", "404")


LANDING = r"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>🤡 Caine Party</title>
<link rel="stylesheet" href="/fonts/fonts.css">
<style>
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:13px;
 font-family:"Outfit",system-ui,Segoe UI,Arial;font-size:17px;color:#eafff9;padding:30px 20px 26px;position:relative;overflow-x:hidden;
 background:radial-gradient(1100px 520px at 50% -8%,#3a1170 0%,transparent 60%),radial-gradient(700px 380px at 100% 110%,#5a1140 0%,transparent 55%),#0c0820}
body:before{content:"";position:fixed;left:0;right:0;top:0;height:8px;z-index:5;
 background:repeating-linear-gradient(90deg,#ff3ba7 0 24px,#0c0820 24px 48px,#26e6ff 48px 72px,#0c0820 72px 96px);opacity:.75}
.eyes{font-size:40px;letter-spacing:10px;color:#26e6ff;filter:drop-shadow(0 0 16px #26e6ff);animation:blink 4s infinite}
@keyframes blink{0%,92%,100%{letter-spacing:10px}96%{letter-spacing:7px;opacity:.7}}
h1{font-family:"Bungee",system-ui;font-size:33px;margin:2px 0 2px;letter-spacing:1px;
 background:linear-gradient(90deg,#26e6ff,#ff3ba7,#ffd23f);-webkit-background-clip:text;background-clip:text;color:transparent;text-shadow:0 4px 24px rgba(255,59,167,.25)}
.tagline{color:#b9a6e8;font-size:14px;margin:0 0 6px;text-align:center}
a.card{display:flex;align-items:center;gap:14px;width:min(460px,94vw);text-decoration:none;color:#eafff9;
 background:linear-gradient(180deg,#241144,#2e1556);border:1px solid #4a2a86;border-radius:18px;padding:16px 18px;
 box-shadow:0 8px 24px rgba(0,0,0,.34),inset 0 1px 0 rgba(255,255,255,.05);transition:transform .12s,box-shadow .12s,border-color .12s}
a.card:hover{transform:translateY(-2px);border-color:#ff3ba7;box-shadow:0 12px 30px rgba(255,59,167,.22)}
a.card:active{transform:translateY(1px)}
a.card .ic{font-size:30px;flex:0 0 auto;width:46px;height:46px;display:grid;place-items:center;border-radius:13px;background:#160b2e;border:1px solid #4a2a86}
a.card b{font-size:19px;font-weight:700} a.card small{display:block;color:#b9a6e8;margin-top:2px;font-size:13.5px}
.addr{margin-top:6px;color:#b9a6e8;font-size:14px;text-align:center;max-width:460px}
.addr code{background:#160b2e;border:1px solid #4a2a86;border-radius:7px;padding:3px 9px;color:#26e6ff;font-size:16px}
.mic-note{background:linear-gradient(180deg,#15233a,#11203a);border:1px solid #1d5e86;border-radius:14px;
 padding:11px 14px;max-width:460px;width:94vw;margin-top:4px;color:#bfe9ff;font-size:13.5px;text-align:center}
.mic-note b{color:#26e6ff}
</style></head><body>
<div class="eyes">◉ ‿ ◉</div><h1>Caine Party</h1>
<div class="tagline">Nora's Amazing Digital Circus · pick a screen</div>
<a class="card" href="/guide"><span class="ic">🎤</span><span><b>Bubble's Guide</b><small>Your tablet — run-of-day, soundboard &amp; the adventure remote</small></span></a>
<a class="card" href="/console"><span class="ic">🎪</span><span><b>Caine's Console</b><small>Nora's iPad — the talking adventure (OmniVoice + 3D Caine)</small></span></a>
<a class="card" href="/studio"><span class="ic">🎛</span><span><b>Voice Studio</b><small>Tune &amp; (re)generate the voices</small></span></a>
<a class="card" href="/Circus-Print-Pack.pdf"><span class="ic">📄</span><span><b>Print Pack (PDF)</b><small>Badges, station signs, Exit-Door code, burger pieces — A4, ready to print</small></span></a>
<div class="addr">On the iPad / tablet (same WiFi), open:<br><code>__LANURL__</code></div>
<div class="mic-note">🎤 For <b>Talk to Caine</b> (microphone) on Nora's iPad, open<br><code style="font-size:14px">__HTTPSURL__console</code><br>and tap through the one-time security warning.</div>
<div class="addr" style="margin-top:6px"><a href="/Nora-Circus-Party-Guide.html" style="color:#26e6ff">full guide</a> · <a href="/Circus-Print-Pack.html" style="color:#26e6ff">print pack (web)</a> · <a href="/Agent.md" style="color:#26e6ff">project notes</a></div>
</body></html>"""


STUDIO_PAGE = r"""<!DOCTYPE html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>🎛 Caine Voice Studio</title>
<link rel="stylesheet" href="/fonts/fonts.css">
<style>
:root{--bg:#0e0a1f;--card:#1a1430;--card2:#231a40;--ink:#ece8ff;--mut:#9a8fc7;--acc:#ff5ca8;--ok:#4be39a;--warn:#ffcf5c;--line:#33285c}
*{box-sizing:border-box}
body{margin:0;background:linear-gradient(160deg,#0e0a1f,#160e2e);color:var(--ink);font:15px/1.5 "Outfit",system-ui,Segoe UI,Arial}
h1{font-family:"Bungee",system-ui;font-size:21px;margin:0;letter-spacing:.5px} h2{font-size:15px;margin:0 0 8px;color:var(--acc);letter-spacing:.3px}
a{color:var(--acc)} .wrap{max-width:1080px;margin:0 auto;padding:18px}
.bar{display:flex;align-items:center;gap:12px;margin-bottom:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px;margin-bottom:14px}
.legend{font-size:13px;color:var(--mut);display:flex;flex-wrap:wrap;gap:8px 18px}
.tag{padding:1px 8px;border-radius:20px;border:1px solid var(--line)}
.tag.best{color:var(--ok)} .tag.next{color:var(--warn)} .tag.sub{color:var(--mut)} .tag.no{color:#ff7b7b}
.models{display:flex;gap:8px;flex-wrap:wrap}
.mchip{cursor:pointer;padding:7px 12px;border-radius:10px;border:1px solid var(--line);background:var(--card2);color:var(--ink)}
.lchip{cursor:pointer;padding:5px 11px;border-radius:9px;border:1px solid var(--line);background:var(--card2);color:var(--ink);font-size:13px}
.lchip input{vertical-align:-1px;margin-right:5px;accent-color:var(--acc)}
.lchip:has(input:checked){outline:2px solid var(--acc);border-color:var(--acc)}
.mchip.on{outline:2px solid var(--acc);border-color:var(--acc)}
.mchip small{display:block;color:var(--mut);font-size:11px}
.knobgrid{display:grid;grid-template-columns:200px 1fr 1fr;gap:6px 14px;align-items:center}
.knobgrid .hd{color:var(--mut);font-size:12px;text-transform:uppercase;letter-spacing:.5px}
.kname{color:var(--ink)} .ksub{color:var(--mut);font-size:12px}
.slot{display:flex;align-items:center;gap:8px}
.slot input[type=range]{flex:1;accent-color:var(--acc)}
.kval{min-width:42px;text-align:right;font-variant-numeric:tabular-nums;color:var(--warn)}
.na{color:var(--mut);font-size:12px;font-style:italic}
button{cursor:pointer;border:1px solid var(--line);background:var(--card2);color:var(--ink);padding:7px 12px;border-radius:9px;font-size:14px}
button:hover{border-color:var(--acc)} button.primary{background:var(--acc);border-color:var(--acc);color:#1a0a14;font-weight:600}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--mut);font-weight:600;position:sticky;top:0;background:var(--card)}
tfoot th,tfoot td{position:sticky;bottom:0;top:auto;background:var(--card2);border-top:2px solid var(--acc);color:var(--ink);font-size:12px}
td.c{text-align:center;white-space:nowrap}
.clipname{font-weight:600} .cliptext{color:var(--mut);font-size:12px;max-width:380px}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px}
.dot.y{background:var(--ok)} .dot.n{background:#5a4a7a}
.mini{padding:3px 8px;font-size:12px;border-radius:7px}
#log{white-space:pre-wrap;background:#080614;border:1px solid var(--line);border-radius:10px;padding:10px;height:200px;overflow:auto;font:12px/1.45 Consolas,monospace;color:#cfe9d8}
.spin{display:inline-block;width:12px;height:12px;border:2px solid var(--mut);border-top-color:var(--acc);border-radius:50%;animation:s .7s linear infinite;vertical-align:-2px}
@keyframes s{to{transform:rotate(360deg)}}
.tbl-wrap{max-height:360px;overflow:auto;border-radius:10px}
audio{height:30px;vertical-align:middle}
</style></head><body><div class="wrap">
<div class="bar"><h1>🎛 Caine Voice Studio</h1><a href="/" style="font-size:13px">← party menu</a><span id="status" class="mut"></span></div>
<div class="card"><div class="legend">
 <span><span class="tag best">OmniVoice</span> best — native French, ~2s/line</span>
 <span><span class="tag next">F5 · IndexTTS-2</span> next best (IndexTTS-2 French = experimental)</span>
 <span><span class="tag sub">chatterbox · xtts · qwen3 · cosyvoice</span> hidden — subpar by ear</span>
 <span><span class="tag no">openaudio · higgs</span> not working on this machine</span>
</div></div>
<div class="card"><h2>1 · Model</h2><div id="models" class="models"></div>
 <div class="row" style="margin-top:12px;align-items:center;gap:12px">
  <span class="ksub" style="text-transform:uppercase;letter-spacing:.5px">Language</span>
  <label class="lchip"><input type="radio" name="lang" value="both" checked> Both</label>
  <label class="lchip"><input type="radio" name="lang" value="en"> 🇬🇧 English</label>
  <label class="lchip"><input type="radio" name="lang" value="fr"> 🇫🇷 French</label>
  <span class="ksub">▶ Test phrase / Full run will (re)make only this language.</span></div></div>
<div class="card">
 <div class="row" style="justify-content:space-between"><h2 style="margin:0">2 · Knobs <span class="ksub">(saved automatically · per language)</span></h2>
 <button class="mini" onclick="revert()">↺ Revert to defaults</button></div>
 <div id="knobs" style="margin-top:10px"></div></div>
<div class="card"><h2>3 · Generate</h2><div class="row">
 <button class="primary" onclick="run('test')">⚡ Test phrase</button>
 <button onclick="run('full')">▶ Full run (all lines)</button>
 <label class="ksub"><input type="checkbox" id="force"> overwrite existing (--force)</label></div>
 <div class="row" style="margin-top:10px;align-items:center">
  <button class="mini" onclick="purge()" title="Delete audio files that are no longer in the needed-clip list">🧹 Purge orphan files</button>
  <span id="purgeMsg" class="ksub"></span></div>
 <p class="ksub" style="margin:6px 0 0">The needed clips come from one source of truth (the engine's <code>build_clips()</code>, served at <code>/api/state</code>). Purge removes any leftover audio (e.g. removed/renamed phrases) so nothing stale lingers. Your typed-in lines (<code>_manual</code>) are never touched.</p></div>
<div class="card">
 <div class="row" style="justify-content:space-between"><h2 style="margin:0">4 · Clips <span class="ksub">(▶ play · 🎲 re-roll one clip)</span></h2>
 <button class="mini" onclick="load()">↻ Refresh</button></div>
 <audio id="player" controls preload="none" style="width:100%;margin:8px 0"></audio>
 <div class="tbl-wrap"><table id="clips"><thead></thead><tbody></tbody><tfoot></tfoot></table></div>
 <p class="ksub" style="margin:6px 0 0">Footer = each model's <b>newest</b> &amp; <b>oldest</b> present clip — if a model's <b>oldest</b> is far older than its newest, some clips are stale (re-roll or re-run).</p></div>
<div class="card" id="pttCard">
 <h2>5 · Push-to-Talk <span class="ksub">("Talk to Caine" — the live mic on Nora's iPad)</span></h2>
 <p class="ksub" style="margin:2px 0 12px">These control the <b>live, on-the-fly</b> replies when a child holds the mic — separate from the pre-generated clips above. The voice is always <b>OmniVoice</b> (the only model kept warm for ~2-second replies), so the audio model is locked here. You can still tune its voice knobs and pick the text brain.</p>
 <div id="ptt" class="ksub">loading…</div></div>
<div class="card"><div class="row" style="justify-content:space-between"><h2 style="margin:0">Output</h2><span id="joblabel" class="ksub"></span></div>
 <div id="log"></div></div>
</div>
<script>
let S=null, model=null, busy=false; const $=s=>document.querySelector(s);
async function load(){ S=await (await fetch('/api/state')).json(); if(!model) model=S.models[0]; renderModels(); renderKnobs(); renderClips(); renderStatus(); loadPtt(); }
async function purge(){
  const m=document.getElementById('purgeMsg'); m.textContent='scanning…';
  try{
    const prev=await (await fetch('/api/purge')).json();   // dry-run preview
    if(!prev.count){ m.textContent='✓ No orphan files — everything is clean.'; return; }
    const list=prev.removed.slice(0,12).join(', ')+(prev.count>12?` … (+${prev.count-12} more)`:'');
    if(!confirm(`Delete ${prev.count} orphan audio file(s) not in the needed list?\n\n${list}`)){ m.textContent='cancelled'; return; }
    const res=await (await fetch('/api/purge',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})).json();
    m.textContent=`🧹 Removed ${res.count} orphan file(s). (${res.needed} clips needed.)`;
    load();
  }catch(e){ m.textContent='⚠ could not reach the server'; }
}
function renderStatus(){ $('#status').innerHTML = S.running ? '<span class="spin"></span> generating…' : ''; }
function renderModels(){ $('#models').innerHTML = S.models.map(m=>{ const lbl=S.labels[m]||m; const main=lbl.split('—')[0].trim(); const sub=(lbl.split('—')[1]||'').trim();
 return `<div class="mchip ${m===model?'on':''}" onclick="pick('${m}')">${main}<small>${sub||'&nbsp;'}</small></div>`; }).join(''); }
function pick(m){ model=m; renderModels(); renderKnobs(); renderClips(); }
function eff(m,name,lang){ const d=S.knobs[m][name].default; let v=(lang in d)?d[lang]:d.en; try{const o=S.overrides[m][name]; if(o&&(lang in o)&&o[lang]!=null)v=o[lang];}catch(e){} return v; }
function renderKnobs(){ const spec=S.knobs[model]; const names=Object.keys(spec).filter(k=>k!=='_label');
 let h=`<div class="knobgrid"><div class="hd">parameter</div><div class="hd">English</div><div class="hd">French</div>`;
 for(const name of names){ const k=spec[name]; const langs=Object.keys(k.default);
  h+=`<div class="kname">${k.label}<div class="ksub">${name}</div></div>`;
  for(const lang of ['en','fr']){ if(!langs.includes(lang)){ h+=`<div class="na">${lang==='fr'?'— (English-only knob)':'—'}</div>`; continue; }
   const v=eff(model,name,lang); const step=k.step||(k.int?1:0.1);
   h+=`<div class="slot"><input type="range" min="${k.min}" max="${k.max}" step="${step}" value="${v}" oninput="onKnob('${name}','${lang}',this)">
       <span class="kval" id="kv-${name}-${lang}">${fmt(v,k)}</span></div>`; } }
 h+=`</div>`; $('#knobs').innerHTML=h; }
function fmt(v,k){ return k.int?Math.round(v):(Math.round(v*100)/100); }
let saveT=null;
function onKnob(name,lang,el){ const k=S.knobs[model][name]; const v=k.int?Math.round(+el.value):+el.value;
 $('#kv-'+name+'-'+lang).textContent=fmt(v,k);
 S.overrides[model]=S.overrides[model]||{}; S.overrides[model][name]=S.overrides[model][name]||{}; S.overrides[model][name][lang]=v;
 clearTimeout(saveT); saveT=setTimeout(()=>fetch('/api/knob',{method:'POST',body:JSON.stringify({model,name,lang,value:v})}),250); }
async function revert(){ await fetch('/api/revert',{method:'POST'}); await load(); }
function relTime(sec){ // compact "5m"/"3h"/"2d" relative to the SERVER clock (skew-free)
 const d=Math.max(0,(S.now||Math.floor(Date.now()/1000))-sec);
 if(d<90) return d+'s'; if(d<5400) return Math.round(d/60)+'m'; if(d<172800) return Math.round(d/3600)+'h'; return Math.round(d/86400)+'d'; }
function renderClips(){ $('#clips thead').innerHTML='<tr><th>clip</th>'+S.models.map(m=>`<th class="c">${m}</th>`).join('')+'</tr>';
 $('#clips tbody').innerHTML=S.clips.map(c=>{ let row=`<tr><td><div class="clipname">${c.base} <span class="ksub">[${c.lang}]</span></div><div class="cliptext">${c.text}</div></td>`;
  for(const m of S.models){ const mt=(S.present[m]||{})[c.base]; row+=`<td class="c"><span class="dot ${mt?'y':'n'}"></span>`;
   if(mt){ row+=`<button class="mini" onclick="play('${m}','${c.base}',${mt})">▶</button> `; }
   row+=`<button class="mini" onclick="regen('${m}','${c.base}')" title="re-roll this clip">🎲</button></td>`; } return row+'</tr>'; }).join('');
 const total=S.clips.length;
 $('#clips tfoot').innerHTML='<tr><th>latest clip</th>'+S.models.map(m=>{ const ts=Object.values(S.present[m]||{});
   if(!ts.length) return `<td class="c ksub">—</td>`;
   const newest=Math.max(...ts), oldest=Math.min(...ts), stale=(newest-oldest)>3600;
   const ot=new Date(newest*1000).toLocaleString();
   return `<td class="c" title="newest ${ot} · ${ts.length}/${total} present">↑${relTime(newest)} <span class="${stale?'kval':'ksub'}">↓${relTime(oldest)}</span><div class="ksub">${ts.length}/${total}</div></td>`;
 }).join('')+'</tr>'; }
function play(m,base,mt){ const p=$('#player'); p.src=`/audio/${m}/${base}.wav?t=${mt}`; p.play(); }
async function run(action){ if(busy) return alert('A job is already running.');
 const lang=(document.querySelector('input[name=lang]:checked')||{}).value;
 const body={model,action,force:$('#force').checked}; if(lang==='en'||lang==='fr') body.lang=lang;
 const r=await (await fetch('/api/run',{method:'POST',body:JSON.stringify(body)})).json();
 if(!r.ok) alert(r.error||'could not start'); else pollLog(); }
async function regen(m,base){ const r=await (await fetch('/api/run',{method:'POST',body:JSON.stringify({model:m,action:'only',base})})).json();
 if(!r.ok) alert(r.error||'could not start'); else pollLog(); }
async function pollLog(){ const l=await (await fetch('/api/log')).json();
 $('#log').textContent=l.text; $('#log').scrollTop=$('#log').scrollHeight; $('#joblabel').textContent=l.label||''; busy=l.running;
 $('#status').innerHTML=busy?'<span class="spin"></span> generating…':''; if(l.running){ setTimeout(pollLog,900);} else { load(); } }
// ---- 5 · Push-to-Talk (Talk to Caine) settings ----
let pttPending=false, pttTimer=null;
async function loadPtt(){ try{ const d=await (await fetch('/api/talk-settings')).json(); renderPtt(d); }catch(e){ $('#ptt').textContent='⚠ could not load push-to-talk settings'; } }
function pttBadge(d){ if(d.worker_ready) return '<span class="tag best">● voice ready</span>';
 if(d.worker_loading) return '<span class="tag next"><span class="spin"></span> warming up…</span>';
 if(d.worker_error) return '<span class="tag no">● '+d.worker_error+'</span>'; return '<span class="tag sub">● not started</span>'; }
function renderPtt(d){
 let h='';
 h+=`<div class="row" style="gap:10px;margin-bottom:12px"><b style="color:var(--ink)">Audio voice:</b> <span class="mchip on" style="cursor:default">OmniVoice 🔒</span> <span class="ksub">locked — push-to-talk always uses the warm OmniVoice worker</span> ${pttBadge(d)}</div>`;
 h+=`<div class="row" style="gap:10px;margin-bottom:4px"><b style="color:var(--ink)">Text brain (Claude):</b> <select id="pttModel" onchange="setTalkModel(this.value)" style="padding:6px 8px">`;
 for(const m of d.claude_choices){ h+=`<option value="${m.id}" ${m.id===d.claude_model?'selected':''}>${m.tier} — ${m.note}</option>`; }
 h+=`</select> ${d.claude_ok?'':'<span class="tag no">⚠ claude CLI not found</span>'}</div>`;
 h+=`<p class="ksub" style="margin:0 0 14px">Switches instantly — no restart needed. Uses your Claude Code subscription (no per-token billing). Replies time out after 25s, so Opus can occasionally be too slow.</p>`;
 h+=`<div style="border-top:1px solid var(--line);padding-top:12px"><div class="row" style="justify-content:space-between"><b style="color:var(--ink)">Push-to-talk voice knobs</b> <span id="pttNote" class="ksub">${pttPending?'⚠ restart the voice to apply':'SEPARATE from generation · fewer steps = faster replies'}</span></div>`;
 h+=`<div class="knobgrid" style="margin-top:8px"><div class="hd">parameter</div><div class="hd">English</div><div class="hd">French</div>`;
 for(const k of d.knobs){ h+=`<div class="kname">${k.label}<div class="ksub">${k.name}</div></div>`;
  for(const lang of ['en','fr']){ const v=k[lang]; const sv=k.int?Math.round(v):(Math.round(v*100)/100);
   h+=`<div class="slot"><input type="range" min="${k.min}" max="${k.max}" step="${k.step}" value="${v}" oninput="onPttKnob('${k.name}','${lang}',this,${k.int?1:0})"><span class="kval" id="pv-${k.name}-${lang}">${sv}</span></div>`; } }
 h+=`</div><div class="row" style="margin-top:12px"><button class="primary" onclick="restartVoice()">🔄 Apply &amp; restart voice</button>`;
 h+=`<span class="ksub">These are SEPARATE from the generation knobs (section 2) — lower steps = faster live replies (quality matters less for the mic). A change only reaches push-to-talk after the warm voice reloads (~1-3 min).</span></div></div>`;
 $('#ptt').innerHTML=h;
 if(d.worker_loading){ clearTimeout(pttTimer); pttTimer=setTimeout(loadPtt,2000); }
}
function onPttKnob(name,lang,el,isInt){ const v=isInt?Math.round(+el.value):Math.round(+el.value*100)/100;
 $('#pv-'+name+'-'+lang).textContent=v; pttPending=true; const n=$('#pttNote'); if(n) n.textContent='⚠ restart the voice to apply';
 // Save under the SEPARATE 'talk' namespace — does NOT touch the generation knobs in section 2.
 clearTimeout(el._t); el._t=setTimeout(()=>fetch('/api/knob',{method:'POST',body:JSON.stringify({model:'talk',name,lang,value:v})}),250); }
async function setTalkModel(id){ try{ const r=await (await fetch('/api/talk-settings',{method:'POST',body:JSON.stringify({claude_model:id})})).json(); if(!r.ok) alert(r.error||'could not set model'); }catch(e){ alert('could not set model'); } }
async function restartVoice(){ const n=$('#pttNote'); if(n) n.innerHTML='<span class="spin"></span> reloading voice…';
 try{ await fetch('/api/talk-settings',{method:'POST',body:JSON.stringify({restart:true})}); }catch(e){} pttPending=false; setTimeout(loadPtt,800); }
load(); setInterval(()=>{ if(!busy) fetch('/api/log').then(r=>r.json()).then(l=>{ if(l.running){busy=true;pollLog();} }); }, 2000);
</script></body></html>"""


def main():
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    ip = lan_ip()
    def say(s):
        try: print(s)
        except Exception: print(s.encode("ascii", "replace").decode())
    say("=" * 60)
    say("  Caine Party Server is running.")
    say(f"  On THIS laptop:      http://localhost:{PORT}/")
    say(f"  On the iPad/tablet:  http://{ip}:{PORT}/     (same WiFi)")
    say(f"      Bubble's guide:  http://{ip}:{PORT}/guide")
    say(f"      Nora's iPad:   http://{ip}:{PORT}/console")
    say("  (open the firewall for this port; Ctrl+C to stop)")
    say("=" * 60)
    say("  Warming up Caine's voice for 'Talk to Caine' (OmniVoice, ~1-3 min)...")
    say("  Claude CLI for talk: " + (claude_cmd() or "NOT FOUND (set CAINE_CLAUDE_CMD)"))
    start_worker()                              # load OmniVoice once so talk replies are fast
    threading.Thread(target=load_whisper, daemon=True).start()   # preload STT (GPU) so the 1st reply is fast too
    cert = ensure_cert()
    if cert:
        try:
            import ssl as _ssl
            ctx = _ssl.SSLContext(_ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain(cert[0], cert[1])
            hsrv = ThreadingHTTPServer(("0.0.0.0", HTTPS_PORT), Handler)
            hsrv.socket = ctx.wrap_socket(hsrv.socket, server_side=True)
            threading.Thread(target=hsrv.serve_forever, daemon=True).start()
            say("")
            say("  🎤 'Talk to Caine' (microphone) needs HTTPS. On Nora's iPad open:")
            say(f"      https://{ip}:{HTTPS_PORT}/console   (accept the one-time security warning)")
        except Exception as e:
            say(f"  (mic HTTPS listener not started: {str(e)[:70]})")
    else:
        say("  (microphone/HTTPS off: install 'cryptography' to enable Talk-to-Caine on the iPad)")
    try:
        import webbrowser; webbrowser.open(f"http://localhost:{PORT}/")
    except Exception:
        pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye.")

if __name__ == "__main__":
    main()
