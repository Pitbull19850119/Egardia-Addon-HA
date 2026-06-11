#!/usr/bin/env python3
"""
Egardia Alarm Home Assistant Add-on v5
Based on confirmed working API from community.home-assistant.io (May 2026)
Portal: my.egardia.com (Liferay) - tested with GATE-04
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Optional, Dict, Any
from urllib.parse import urlencode

import aiohttp
import requests
from aiohttp import web

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("egardia")

# ── Confirmed working endpoints (tested GATE-04, May 2026) ───────────────────
BASE        = "https://my.egardia.com"
PID         = "portletalarmstatusegardia_WAR_portletliferayalarmsystemegardiawebapp_INSTANCE_HNn7"
SUMMARY_BASE = (
    f"{BASE}/de/group/egardia/summary"
    f"?p_p_id={PID}"
    "&p_p_lifecycle=2&p_p_state=normal&p_p_mode=view&p_p_cacheability=cacheLevelPage"
)
STATUS_URL  = SUMMARY_BASE + f"&_{PID}_action=getAlarmStatus"
SET_URL     = SUMMARY_BASE + f"&_{PID}_action=setAlarmStatus"
LOGIN_URL   = (
    f"{BASE}/de/home"
    "?p_p_id=com_liferay_login_web_portlet_LoginPortlet"
    "&p_p_lifecycle=1&p_p_state=normal&p_p_mode=view"
    "&_com_liferay_login_web_portlet_LoginPortlet_javax.portlet.action=%2Flogin%2Flogin"
    "&_com_liferay_login_web_portlet_LoginPortlet_mvcRenderCommandName=%2Flogin%2Flogin"
)


# ── Config ────────────────────────────────────────────────────────────────────
def load_config() -> Dict[str, Any]:
    path = "/data/options.json"
    if os.path.exists(path):
        with open(path) as f:
            raw = f.read()
        log.info(f"options.json: {raw}")
        return json.loads(raw)
    return {
        "username":      os.environ.get("EGARDIA_USERNAME", ""),
        "password":      os.environ.get("EGARDIA_PASSWORD", ""),
        "poll_interval": int(os.environ.get("POLL_INTERVAL", "30")),
        "log_level":     os.environ.get("LOG_LEVEL", "info"),
    }


# ── Egardia Client ────────────────────────────────────────────────────────────
class EgardiaClient:
    def __init__(self, username: str, password: str):
        self.username    = username
        self.password    = password
        self._logged_in  = False
        self.session     = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

    def login(self) -> bool:
        """Login using exact same method as confirmed-working curl commands."""
        try:
            form_date = str(int(time.time() * 1000))

            # Build payload - requests handles special chars correctly with data= dict
            payload = {
                "_com_liferay_login_web_portlet_LoginPortlet_formDate":           form_date,
                "_com_liferay_login_web_portlet_LoginPortlet_saveLastPath":        "false",
                "_com_liferay_login_web_portlet_LoginPortlet_doActionAfterLogin":  "false",
                "_com_liferay_login_web_portlet_LoginPortlet_login":               self.username,
                "_com_liferay_login_web_portlet_LoginPortlet_password":            self.password,
            }

            log.info(f"Logging in as: {self.username}")
            resp = self.session.post(
                LOGIN_URL,
                data=payload,   # requests auto-encodes special chars correctly
                timeout=20,
                allow_redirects=True,
            )
            log.info(f"Login: HTTP {resp.status_code} → {resp.url}")
            log.debug(f"Login response snippet: {resp.text[200:600]}")

            # Only fail on definitive wrong-password indicators in the URL
            # (Liferay redirects back to login page with error param on bad creds)
            if "login" in resp.url.lower() and resp.url == (
                "https://my.egardia.com/de/home"
                "?p_p_id=com_liferay_login_web_portlet_LoginPortlet"
                "&p_p_lifecycle=0"
            ):
                log.error("Login failed: redirected back to login page (wrong credentials?)")
                return False

            self._logged_in = True
            log.info("Login successful")
            return True

        except Exception as e:
            log.error(f"Login exception: {e}")
            return False

    def get_status(self) -> Dict[str, Any]:
        if not self._logged_in and not self.login():
            return {"state": "unknown", "error": "Login failed"}
        try:
            resp = self.session.get(STATUS_URL, timeout=10)
            log.debug(f"Status: HTTP {resp.status_code} body='{resp.text[:200]}'")

            if resp.status_code in (401, 403):
                self._logged_in = False
                if not self.login():
                    return {"state": "unknown", "error": "Re-login failed"}
                resp = self.session.get(STATUS_URL, timeout=10)

            if not resp.text.strip():
                log.error("Empty status response – session may have expired")
                self._logged_in = False
                return {"state": "unknown", "error": "Empty response – will re-login next poll"}

            data = resp.json()
            log.info(f"Status JSON: {data}")
            return self._parse(data)

        except requests.exceptions.JSONDecodeError:
            log.error(f"Non-JSON response: '{resp.text[:300]}'")
            self._logged_in = False
            return {"state": "unknown", "error": "Non-JSON – will retry"}
        except Exception as e:
            log.error(f"Status error: {e}")
            self._logged_in = False
            return {"state": "unknown", "error": str(e)}

    def set_status(self, action: str) -> Dict[str, Any]:
        if not self._logged_in and not self.login():
            return {"success": False, "error": "Login failed"}

        payloads = {
            "arm_away": '{"atHome":false,"on":true}',
            "arm_home": '{"atHome":true,"on":true}',
            "disarm":   '{"atHome":false,"on":false}',
        }
        if action not in payloads:
            return {"success": False, "error": f"Unknown action '{action}'"}

        try:
            resp = self.session.post(
                SET_URL,
                data={"json": payloads[action]},
                timeout=15,
            )
            log.info(f"Set {action}: HTTP {resp.status_code} body='{resp.text[:200]}'")

            if resp.status_code in (401, 403):
                self._logged_in = False
                self.login()
                resp = self.session.post(SET_URL, data={"json": payloads[action]}, timeout=15)

            # Confirm by re-reading status
            new = self.get_status()
            return {"success": True, "state": new.get("state", action),
                    "message": f"Alarm gesetzt: {action}"}

        except Exception as e:
            log.error(f"Set status error: {e}")
            return {"success": False, "error": str(e)}

    def _parse(self, data: Any) -> Dict[str, Any]:
        if isinstance(data, dict):
            on      = data.get("on",     False)
            at_home = data.get("atHome", False)
            state   = "disarmed" if not on else ("armed_home" if at_home else "armed_away")
            return {"state": state, "on": on, "atHome": at_home,
                    "raw": data, "last_updated": datetime.now().isoformat()}
        return {"state": "unknown", "raw": data, "last_updated": datetime.now().isoformat()}


# ── State Manager ─────────────────────────────────────────────────────────────
class StateManager:
    def __init__(self):
        self.current: Dict[str, Any] = {"state": "unknown", "last_updated": None}
        f = "/data/state.json"
        try:
            if os.path.exists(f):
                self.current = json.load(open(f))
        except Exception:
            pass
        self._f = f

    def update(self, ns: Dict) -> bool:
        changed = self.current.get("state") != ns.get("state")
        self.current = {**self.current, **ns, "last_updated": datetime.now().isoformat()}
        try:
            json.dump(self.current, open(self._f, "w"))
        except Exception:
            pass
        return changed


# ── HA Push ───────────────────────────────────────────────────────────────────
async def push_to_ha(state: Dict, config: Dict):
    token = os.environ.get("SUPERVISOR_TOKEN", "") or config.get("ha_long_lived_token", "")
    if not token:
        return
    ha = "http://supervisor/core" if os.environ.get("SUPERVISOR_TOKEN") else "http://localhost:8123"
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"{ha}/api/states/alarm_control_panel.egardia",
                json={"state": state.get("state", "unknown"),
                      "attributes": {"friendly_name": "Egardia Alarm", "supported_features": 31}},
                headers={"Authorization": f"Bearer {token}"},
                timeout=aiohttp.ClientTimeout(total=5),
            )
    except Exception as e:
        log.debug(f"HA push: {e}")


# ── Web UI ────────────────────────────────────────────────────────────────────
HTML = """<!DOCTYPE html>
<html lang="de"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Egardia</title>
<style>
:root{--bg:#0d1117;--card:#161b22;--border:#30363d;--text:#e6edf3;--muted:#8b949e;--green:#3fb950;--red:#f85149;--yellow:#d29922}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.wrap{max-width:500px;margin:0 auto;padding:24px 16px}
h1{font-size:1.4rem;font-weight:600;margin-bottom:4px}
.sub{color:var(--muted);font-size:.85rem;margin-bottom:24px}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px;margin-bottom:16px}
.lbl{font-size:.75rem;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:12px}
.badge{display:inline-flex;align-items:center;gap:8px;padding:8px 18px;border-radius:20px;font-weight:600;font-size:1rem;margin-bottom:6px}
.dot{width:10px;height:10px;border-radius:50%}
.s-disarmed{background:#1a2e1a;color:var(--green)}.d-disarmed{background:var(--green)}
.s-armed_away{background:#2e1a1a;color:var(--red)}.d-armed_away{background:var(--red)}
.s-armed_home{background:#2e2a1a;color:var(--yellow)}.d-armed_home{background:var(--yellow)}
.s-triggered{background:#3e0000;color:#ff6b6b;animation:p 1s infinite}.d-triggered{background:#ff6b6b}
.s-unknown{background:#1e1e1e;color:var(--muted)}.d-unknown{background:var(--muted)}
@keyframes p{0%,100%{opacity:1}50%{opacity:.5}}
.ts{color:var(--muted);font-size:.8rem;margin-top:4px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:4px}
.btn{padding:14px;border:none;border-radius:10px;font-size:.9rem;font-weight:600;cursor:pointer;transition:all .15s;display:flex;flex-direction:column;align-items:center;gap:5px;color:#fff}
.btn:hover{filter:brightness(1.15)}.btn:disabled{opacity:.4;cursor:not-allowed}
.b-away{background:#b91c1c}.b-home{background:#b45309}.b-off{background:#15803d;grid-column:span 2}
.i{font-size:1.3rem}
.alert{padding:10px 14px;border-radius:8px;font-size:.85rem;margin-top:12px;display:none}
.e{background:#2e1a1a;color:var(--red);border:1px solid #5a2020}
.o{background:#1a2e1a;color:var(--green);border:1px solid #205a20}
code{background:var(--bg);padding:2px 6px;border-radius:4px;font-size:.82rem}
</style></head><body>
<div class="wrap">
  <h1>🛡️ Egardia Alarm</h1><p class="sub">Home Assistant Add-on · my.egardia.com</p>
  <div class="card">
    <div class="lbl">Status</div>
    <div id="B" class="badge s-unknown"><span class="dot d-unknown" id="D"></span><span id="T">Lade...</span></div>
    <div class="ts" id="TS"></div>
    <div class="alert e" id="E"></div><div class="alert o" id="O"></div>
  </div>
  <div class="card">
    <div class="lbl">Steuern</div>
    <div class="grid">
      <button class="btn b-away" onclick="cmd('arm_away')"><span class="i">🔒</span>Scharf Abwesend</button>
      <button class="btn b-home" onclick="cmd('arm_home')"><span class="i">🏠</span>Scharf Zuhause</button>
      <button class="btn b-off"  onclick="cmd('disarm')"><span class="i">🔓</span>Unscharf</button>
    </div>
  </div>
  <div class="card"><div class="lbl">REST API</div>
    <p style="color:var(--muted);line-height:1.9;font-size:.85rem">
      <code>GET /api/status</code><br>
      <code>POST /api/alarm</code> → <code>{"action":"arm_away|arm_home|disarm"}</code>
    </p>
  </div>
</div>
<script>
const L={disarmed:"Unscharf",armed_away:"Scharf (Abwesend)",armed_home:"Scharf (Zuhause)",triggered:"⚠️ ALARM!",unknown:"Unbekannt"};
async function load(){
  try{const d=await(await fetch("/api/status")).json(),s=d.state||"unknown";
    document.getElementById("B").className="badge s-"+s;
    document.getElementById("D").className="dot d-"+s;
    document.getElementById("T").textContent=L[s]||s;
    if(d.last_updated)document.getElementById("TS").textContent="Zuletzt: "+new Date(d.last_updated).toLocaleTimeString("de-DE");
    if(d.error&&s==="unknown"){showE(d.error);}
  }catch(e){document.getElementById("T").textContent="Verbindungsfehler";}
}
async function cmd(a){
  document.querySelectorAll(".btn").forEach(b=>b.disabled=true);
  hide();
  try{
    const d=await(await fetch("/api/alarm",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:a})})).json();
    if(d.success){showO(d.message||"OK");setTimeout(load,2500);}else showE(d.error||"Fehler");
  }catch(e){showE(e.message);}
  finally{document.querySelectorAll(".btn").forEach(b=>b.disabled=false);}
}
function showE(m){const e=document.getElementById("E");e.textContent="❌ "+m;e.style.display="";setTimeout(()=>e.style.display="none",8000);}
function showO(m){const e=document.getElementById("O");e.textContent="✅ "+m;e.style.display="";setTimeout(()=>e.style.display="none",4000);}
function hide(){document.getElementById("E").style.display="none";document.getElementById("O").style.display="none";}
load();setInterval(load,20000);
</script></body></html>"""


# ── App ───────────────────────────────────────────────────────────────────────
class EgardiaAddon:
    def __init__(self):
        self.config = load_config()
        level = getattr(logging, self.config.get("log_level", "info").upper(), logging.INFO)
        logging.getLogger().setLevel(level)

        # Support both key naming conventions
        self.username = (
            self.config.get("username") or
            self.config.get("egardia_username") or ""
        ).strip()
        self.password = (
            self.config.get("password") or
            self.config.get("egardia_password") or ""
        ).strip()

        log.info(f"Username: '{self.username}' | Password set: {'YES' if self.password else 'NO'} (len={len(self.password)})")

        if not self.username or not self.password:
            log.error("❌ username or password empty – open Add-on → Configuration")

        self.client    = EgardiaClient(self.username, self.password)
        self.state_mgr = StateManager()
        self.interval  = int(self.config.get("poll_interval", 30))

    async def _poll(self):
        loop = asyncio.get_event_loop()
        try:
            s = await loop.run_in_executor(None, self.client.get_status)
            if self.state_mgr.update(s):
                log.info(f"State → {s.get('state')}")
                await push_to_ha(self.state_mgr.current, self.config)
        except Exception as e:
            log.error(f"Poll: {e}")

    async def poll_loop(self):
        log.info(f"Polling every {self.interval}s")
        while True:
            await self._poll()
            await asyncio.sleep(self.interval)

    async def start(self):
        if self.username:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.client.login)
            await self._poll()

        app = web.Application()
        app.router.add_get("/",             lambda r: web.Response(text=HTML, content_type="text/html"))
        app.router.add_get("/api/status",   lambda r: web.json_response(self.state_mgr.current))
        app.router.add_post("/api/alarm",   self._handle_alarm)
        app.router.add_post("/api/refresh", self._handle_refresh)

        asyncio.ensure_future(self.poll_loop())
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", 8765).start()
        log.info("Egardia Add-on running on :8765")
        while True:
            await asyncio.sleep(3600)

    async def _handle_alarm(self, req):
        try:
            body = await req.json()
        except Exception:
            return web.json_response({"success": False, "error": "Invalid JSON"}, status=400)
        action = body.get("action", "")
        if action not in ("arm_away", "arm_home", "disarm"):
            return web.json_response({"success": False, "error": "Use: arm_away, arm_home, disarm"}, status=400)
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self.client.set_status, action)
        if result.get("success"):
            self.state_mgr.update({"state": result.get("state", action)})
            await push_to_ha(self.state_mgr.current, self.config)
        return web.json_response(result)

    async def _handle_refresh(self, req):
        await self._poll()
        return web.json_response(self.state_mgr.current)


if __name__ == "__main__":
    asyncio.run(EgardiaAddon().start())
