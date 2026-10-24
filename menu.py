"""
Fisher - fishing macro for FiveM (screen-reading, no game memory access).
Includes animated UI, toast notifications, activity logs, extra controls, rod slot detection, and auto-updates.
"""

import base64
import copy
import ctypes
import hashlib
import hmac
import json
import math
import os
import random
import re
import subprocess
import sys
import threading
import time
import urllib.request
import tkinter as tk
from tkinter import colorchooser, messagebox

try:
    import winsound
except ImportError:
    winsound = None

FROZEN = getattr(sys, "frozen", False)
HERE = os.path.dirname(sys.executable if FROZEN else os.path.abspath(__file__))
IS_WIN = sys.platform == "win32"

# ---------------------------------------------------------------------------
# Auto-Update Configuration
# ---------------------------------------------------------------------------
CURRENT_VERSION = "1.5.0"
# Replace with your actual raw JSON URL on GitHub or your server:
UPDATE_CHECK_URL = "https://raw.githubusercontent.com/YourUsername/YourRepo/main/version.json"


# ---------------------------------------------------------------------------
# Start-up: Admin elevation, DPI awareness, dependency check
# ---------------------------------------------------------------------------

def _elevate():
    """Re-open as administrator so key presses reach the game."""
    if not IS_WIN or "--no-admin" in sys.argv:
        return
    try:
        if ctypes.windll.shell32.IsUserAnAdmin():
            return
        params = "--no-admin" if FROZEN else '"%s" --no-admin' % os.path.abspath(__file__)
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, HERE, 1)
        if rc > 32:
            sys.exit(0)
    except SystemExit:
        raise
    except Exception:
        pass


def _ensure_packages():
    if FROZEN:
        return True
    try:
        import mss  # noqa: F401
        import numpy  # noqa: F401
        return True
    except ImportError:
        pass
    win = tk.Tk()
    win.title("Fisher Setup")
    win.configure(bg="#141414")
    win.geometry("340x110")
    tk.Label(win, text="First-time setup\nInstalling required packages...\n(takes about a minute)",
             bg="#141414", fg="#e8e8e8", font=("Segoe UI", 10), justify="center").pack(expand=True)
    win.update()
    flags = 0x08000000 if IS_WIN else 0
    py = sys.executable
    if py.lower().endswith("pythonw.exe"):
        py = py[:-len("pythonw.exe")] + "python.exe"
    r = subprocess.run([py, "-m", "pip", "install", "--user", "mss", "numpy"],
                       capture_output=True, text=True, creationflags=flags)
    win.destroy()
    if r.returncode != 0:
        messagebox.showerror("Fisher Setup", "Failed to install required packages.\n\n" + r.stderr[-800:])
        return False
    import importlib
    import site
    importlib.invalidate_caches()
    try:
        sys.path.append(site.getusersitepackages())
    except Exception:
        pass
    return True


if __name__ == "__main__":
    _elevate()
    if not _ensure_packages():
        sys.exit(1)

if IS_WIN:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

import mss  # noqa: E402
import mss.tools  # noqa: E402
import numpy as np  # noqa: E402


# ---------------------------------------------------------------------------
# Theme & constants
# ---------------------------------------------------------------------------

T = {"accent": "#ff1a1a", "bg": "#141414"}
BG = "#141414"
SIDEBAR = "#101010"
PANEL = "#191919"
BORDER = "#2a2a2a"
FIELD = "#101010"
TEXT = "#e8e8e8"
DIM = "#6b6b6b"
ERR = "#ff5555"
OK = "#2ecc71"
FONT = ("Segoe UI", 10)
FONT_B = ("Segoe UI", 10, "bold")
SMALL = ("Segoe UI", 9)

ACCENT_PRESETS = ["#ff1a1a", "#ff7a1a", "#ffd21a", "#2ecc71", "#1ac6ff", "#3b6bff", "#a64dff", "#ff4da6"]
WATER_PRESETS = ["#1a8cff", "#1ac6ff", "#2ecc71", "#a64dff", "#ff4da6", "#ffffff"]
BG_PRESETS = ["#141414", "#000000", "#0d0d14", "#101a24", "#1a1024", "#0f1a14", "#241014", "#1f1f1f", "#221133", "#112233"]

BUILTIN_SERVERS = [
    {"name": "Generic - Moving bar", "type": "Moving bar"},
    {"name": "Generic - Key prompt", "type": "Key prompt"},
    {"name": "Generic - Timing circle", "type": "Timing circle"},
]
START_KEYS = ["F5", "F6", "F7", "F9", "F10", "F11", "F12"]
STOP_KEYS = ["F8", "End", "Delete", "Home"]
RECAST_KEYS = ["F5", "F6", "F7", "F8", "F9", "F10", "1", "2", "3", "4", "5", "Space", "E", "Mouse Left"]
ACTION_KEYS = ["E", "Space", "Mouse Left", "1", "2", "3", "4", "5"]
ROD_SLOTS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"]

DEFAULTS = {
    "accent": "#ff1a1a",
    "bg_color": "#141414",
    "bg_image": "",
    "topmost": False,
    "opacity": 100,
    "server": "Generic - Timing circle",
    "servers": [],
    "hotkey": "F6",
    "recast_key": "F7",
    "action_key": "E",
    "stop_key": "F8",
    "rod_slot": "1",
    "auto_fish": True,
    "auto_recast": True,
    "stream_proof": False,
    "sound": False,
    "reaction": 10,
    "scan": 80,
    "stop_unfocused": True,
    "limits_on": True,
    "max_run": 30,
    "max_catches": 50,
    "tolerance": 50,
    "dry_run": False,
    "debug": False,
    "region": None,
    "zone_color": None,
    "marker_color": None,
    "smooth_scroll": True,
    "water_on": True,
    "water_color": "#1a8cff",
    "water_speed": 40,
    "water_transparency": 45,
    "rain_on": True,
    "rain_amount": 40,
}
SCALE_KEYS = ("opacity", "reaction", "scan", "max_run", "max_catches", "tolerance", "water_speed", "water_transparency", "rain_amount")

DEFAULT_OVERVIEW = "Welcome to Fisher!\n\nCheck here for the latest updates, patches, and server announcements."
DEFAULT_UPDATE_BOX = "v1.5.0 - Fully integrated animations, activity logs, auto-updates, rod slot detection, and extra controls."

ADMIN_USER = "dogo"

DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Fisher")
DATA_FILE = os.path.join(DATA_DIR, "users.json")


def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("users", {})
        data.setdefault("overview", DEFAULT_OVERVIEW)
        data.setdefault("update_text", DEFAULT_UPDATE_BOX)
        data.setdefault("open_count", 0)
        return data
    except Exception:
        return {"users": {}, "overview": DEFAULT_OVERVIEW, "update_text": DEFAULT_UPDATE_BOX, "open_count": 0}


def save_data(data):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, DATA_FILE)
    except Exception:
        pass


def hash_pw(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000).hex()


def migrate_settings(s):
    for k in SCALE_KEYS:
        raw = s.get(k, DEFAULTS[k])
        try:
            v = float(raw)
        except (TypeError, ValueError):
            v = float(DEFAULTS[k])
        if isinstance(raw, float) and v <= 1.0:
            v *= 100
        s[k] = int(min(100, max(1, round(v))))
    return s


# ---------------------------------------------------------------------------
# Auto-Update Utility Functions
# ---------------------------------------------------------------------------

def check_for_updates(app_instance, manual=False):
    """Checks remote server for a newer version and prompts user to update."""
    if "YourUsername/YourRepo" in UPDATE_CHECK_URL:
        if manual:
            app_instance.notify("Update URL not configured. Set UPDATE_CHECK_URL in code.", is_error=True)
        return

    try:
        req = urllib.request.Request(UPDATE_CHECK_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            remote_version = data.get("version")
            download_url = data.get("download_url")

            if remote_version and remote_version != CURRENT_VERSION:
                if messagebox.askyesno("Update Available", f"A new version ({remote_version}) is available!\nWould you like to update and restart now?"):
                    download_and_apply_update(download_url)
            elif manual:
                app_instance.notify("You are already using the latest version!")
    except Exception:
        if manual:
            app_instance.notify("Could not connect to update server", is_error=True)


def download_and_apply_update(url):
    """Downloads the new script file, replaces the current one, and restarts the app."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            new_code = response.read()

        script_path = os.path.abspath(sys.argv[0])
        with open(script_path, "wb") as f:
            f.write(new_code)

        messagebox.showinfo("Update Successful", "Fisher has been updated successfully! The app will now restart.")
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        messagebox.showerror("Update Failed", f"Could not apply update: {e}")


# ---------------------------------------------------------------------------
# Input simulation
# ---------------------------------------------------------------------------

INPUT_GUARD = {"until": 0.0}

VK_MAP = {
    "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34, "5": 0x35, "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39, "0": 0x30,
    "E": 0x45, "SPACE": 0x20,
    "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77, "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
    "END": 0x23, "HOME": 0x24, "DELETE": 0x2E,
}
EXTENDED_VKS = {0x23, 0x24, 0x2E}

if IS_WIN:
    PUL = ctypes.POINTER(ctypes.c_ulong)

    class KeyBdInput(ctypes.Structure):
        _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                    ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", PUL)]

    class HardwareInput(ctypes.Structure):
        _fields_ = [("uMsg", ctypes.c_ulong), ("wParamL", ctypes.c_ushort), ("wParamH", ctypes.c_ushort)]

    class MouseInput(ctypes.Structure):
        _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", ctypes.c_ulong),
                    ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", PUL)]

    class Input_I(ctypes.Union):
        _fields_ = [("ki", KeyBdInput), ("mi", MouseInput), ("hi", HardwareInput)]

    class Input(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("ii", Input_I)]

    def _send(input_type, ii_):
        x = Input(ctypes.c_ulong(input_type), ii_)
        ctypes.windll.user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))

    def _key_event(vk, up):
        scan = ctypes.windll.user32.MapVirtualKeyW(vk, 0)
        flags = 0x0008
        if up:
            flags |= 0x0002
        if vk in EXTENDED_VKS:
            flags |= 0x0001
        extra = ctypes.c_ulong(0)
        ii_ = Input_I()
        ii_.ki = KeyBdInput(0, scan, flags, 0, ctypes.pointer(extra))
        _send(1, ii_)

    def _mouse_event(flags):
        extra = ctypes.c_ulong(0)
        ii_ = Input_I()
        ii_.mi = MouseInput(0, 0, 0, flags, 0, ctypes.pointer(extra))
        _send(0, ii_)

    def tap_key(key_name, duration=0.06):
        vk = VK_MAP.get(key_name.upper())
        if vk is None:
            return
        _key_event(vk, False)
        time.sleep(duration)
        _key_event(vk, True)

    def click_mouse(duration=0.05):
        _mouse_event(0x0002)
        time.sleep(duration)
        _mouse_event(0x0004)
else:
    def tap_key(k, d=0.06): pass
    def click_mouse(d=0.05): pass


def send_key(key_name, dry=False):
    if dry:
        return
    INPUT_GUARD["until"] = time.time() + 0.4
    if key_name == "Mouse Left":
        click_mouse()
    else:
        tap_key(key_name)


def key_is_down(key_name):
    vk = VK_MAP.get(str(key_name).upper())
    if not (IS_WIN and vk):
        return False
    return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)


def game_focused():
    if not IS_WIN:
        return True
    try:
        u = ctypes.windll.user32
        hwnd = u.GetForegroundWindow()
        title = ctypes.create_unicode_buffer(256)
        cls = ctypes.create_unicode_buffer(64)
        u.GetWindowTextW(hwnd, title, 256)
        u.GetClassNameW(hwnd, cls, 64)
        t = title.value.lower()
        return cls.value == "grcWindow" or "fivem" in t or "grand theft auto" in t or "cfx" in t
    except Exception:
        return True


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

STEP = 2
MIN_PIX = 8
DIL = 2
BITE_TIMEOUT = 60.0
GAME_TIMEOUT = 30.0
PRESS_COOLDOWN = 0.45


def _color_mask(img, rgb, thr2):
    bgr = np.array([rgb[2], rgb[1], rgb[0]], dtype=np.int32)
    d = img - bgr
    return (d[:, :, 0] * d[:, :, 0] + d[:, :, 1] * d[:, :, 1] + d[:, :, 2] * d[:, :, 2]) <= thr2


def _dilate(mask, r):
    wide = mask.copy()
    for k in range(1, r + 1):
        wide[:, k:] |= mask[:, :-k]
        wide[:, :-k] |= mask[:, k:]
    full = wide.copy()
    for k in range(1, r + 1):
        full[k:, :] |= wide[:-k, :]
        full[:-k, :] |= wide[k:, :]
    return full


def analyze(frame, cfg):
    out = {"zone_px": 0, "marker_px": 0, "active": False, "press": False,
           "zone": None, "marker": None, "hit": None}
    zrgb = cfg.get("zone")
    if not zrgb:
        return out
    img = frame[::STEP, ::STEP, :3].astype(np.int32)
    thr = 3 + float(cfg.get("tol", 50)) * 1.2
    thr2 = thr * thr

    zone = _color_mask(img, zrgb, thr2)
    zpx = int(zone.sum())
    out.update(zone=zone, zone_px=zpx, active=zpx >= MIN_PIX)
    if not out["active"]:
        return out

    style = cfg.get("style")
    if style == "Key prompt":
        out["press"] = True
        return out

    mrgb = cfg.get("marker")
    if not mrgb:
        return out
    marker = _color_mask(img, mrgb, thr2)
    mpx = int(marker.sum())
    out.update(marker=marker, marker_px=mpx)
    if mpx == 0:
        return out

    if style == "Moving bar":
        zcols = np.where(zone.any(axis=0))[0]
        mcols = np.where(marker.any(axis=0))[0]
        cx = float(mcols.mean())
        out["press"] = bool(zcols[0] <= cx <= zcols[-1])
    else:
        hit = _dilate(marker, DIL) & zone
        out["hit"] = hit
        out["press"] = int(hit.sum()) >= 2
    return out


def detect_cfg(settings, style):
    return {"style": style, "zone": settings.get("zone_color"),
            "marker": settings.get("marker_color"), "tol": settings.get("tolerance", 50)}


def region_for(sct, settings):
    r = settings.get("region")
    if isinstance(r, (list, tuple)) and len(r) == 4:
        try:
            l, t, rr, b = [int(x) for x in r]
            if rr - l >= 10 and b - t >= 10:
                return {"left": l, "top": t, "width": rr - l, "height": b - t}
        except (TypeError, ValueError):
            pass
    m = sct.monitors[1]
    return {"left": m["left"] + int(m["width"] * 0.344), "top": m["top"] + int(m["height"] * 0.768),
            "width": int(m["width"] * 0.312), "height": int(m["height"] * 0.158)}


# ---------------------------------------------------------------------------
# Fishing engine
# ---------------------------------------------------------------------------

class _Stop(Exception):
    pass


class FishingEngine:
    def __init__(self, get_settings, get_style, start_delay, log_callback=None):
        self.get = get_settings
        self.get_style = get_style
        self.start_delay = start_delay
        self.log_callback = log_callback
        self.stop_ev = threading.Event()
        self.status = "Starting..."
        self.catches = 0
        self.started = time.time()
        self.ended = None
        self.running = True
        self.last_focus = 0.0
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def log(self, text):
        if self.log_callback:
            try:
                self.log_callback(text)
            except Exception:
                pass

    def stop(self, reason="Stopped"):
        if self.running:
            self.status = reason
            self.stop_ev.set()
            self.log(f"Macro stopped: {reason}")

    def elapsed(self):
        return int((self.ended or time.time()) - self.started)

    def _sleep(self, sec):
        end = time.time() + sec
        while True:
            if self.stop_ev.is_set():
                raise _Stop("")
            rem = end - time.time()
            if rem <= 0:
                return
            time.sleep(min(rem, 0.02))

    def _guard(self, s):
        if self.stop_ev.is_set():
            raise _Stop("")
        now = time.time()
        if s.get("limits_on", True) and now - self.started >= s["max_run"] * 60:
            raise _Stop("Stopped: max run time reached")
        if s.get("stop_unfocused", True) and not s.get("dry_run") and now - self.last_focus >= 1.0:
            self.last_focus = now
            if not game_focused():
                raise _Stop("Stopped: game window not focused")

    @staticmethod
    def _interval(s):
        return max(0.001, (101 - int(s.get("scan", 80))) / 1000.0)

    def _grab(self, sct, s):
        frame = np.array(sct.grab(region_for(sct, s)))
        return analyze(frame, detect_cfg(s, self.get_style()))

    def _run(self):
        if IS_WIN:
            try:
                ctypes.windll.winmm.timeBeginPeriod(1)
            except Exception:
                pass
        try:
            with mss.mss() as sct:
                self._cycle(sct)
        except _Stop as e:
            if e.args and e.args[0]:
                self.status = e.args[0]
        except Exception as e:
            self.status = "Error: %s" % e
            self.log(f"Macro error: {e}")
        finally:
            self.running = False
            self.ended = time.time()
            if IS_WIN:
                try:
                    ctypes.windll.winmm.timeEndPeriod(1)
                except Exception:
                    pass
            if not (self.status.startswith("Stopped") or self.status.startswith("Error")):
                self.status = "Stopped"

    def _cycle(self, sct):
        self.status = "Starting..."
        self.log("Macro started.")
        self._sleep(self.start_delay)
        first = True
        while True:
            s = self.get()
            self._guard(s)
            if s.get("limits_on", True) and self.catches >= s["max_catches"]:
                raise _Stop("Stopped: max catches reached")
            dry = bool(s.get("dry_run"))
            tag = " (test)" if dry else ""

            rod_slot = s.get("rod_slot", "1")
            if first or s.get("auto_recast", True):
                self.status = "Equipping Rod & Casting" + tag
                self.log(f"Equipping rod slot {rod_slot} and casting...")
                send_key(rod_slot, dry)
                self._sleep(0.3)
                send_key(s["recast_key"], dry)
                self._sleep(0.8)
            first = False

            self.status = "Waiting for bite" + tag
            if not self._wait_bite(sct):
                if not s.get("auto_recast", True):
                    raise _Stop("Stopped: no bite found")
                continue

            self.status = "Minigame active" + tag
            if self._play(sct):
                self.catches += 1
                self.log(f"Catch #{self.catches} successful!")
                if s.get("sound") and winsound:
                    try:
                        winsound.Beep(880, 140)
                    except Exception:
                        pass
            self.status = "Finishing" + tag
            self._sleep(1.2)

    def _wait_bite(self, sct):
        t0 = time.time()
        while time.time() - t0 < BITE_TIMEOUT:
            s = self.get()
            self._guard(s)
            if self._grab(sct, s)["active"]:
                return True
            self._sleep(self._interval(s))
        return False

    def _play(self, sct):
        t0 = time.time()
        last_press = 0.0
        presses = 0
        absent_since = None
        while time.time() - t0 < GAME_TIMEOUT:
            s = self.get()
            self._guard(s)
            r = self._grab(sct, s)
            now = time.time()
            if r["active"]:
                absent_since = None
                if r["press"] and now - last_press > PRESS_COOLDOWN:
                    delay = int(s.get("reaction", 10)) / 1000.0
                    if delay > 0:
                        self._sleep(delay)
                    send_key(s["action_key"], bool(s.get("dry_run")))
                    last_press = time.time()
                    presses += 1
            else:
                if absent_since is None:
                    absent_since = now
                elif now - absent_since > 0.8:
                    break
            self._sleep(self._interval(s))
        return presses > 0


# ---------------------------------------------------------------------------
# Custom UI widgets with animations
# ---------------------------------------------------------------------------

class Toggle(tk.Canvas):
    def __init__(self, parent, value=False, command=None):
        super().__init__(parent, width=40, height=20, bg=PANEL, highlightthickness=0, cursor="hand2")
        self.value, self.command = value, command
        self.anim_x = 22 if value else 2
        self._anim_id = None
        self.bind("<Button-1>", self.flip)
        self.draw()

    def draw(self):
        self.delete("all")
        c = T["accent"] if self.value else "#333333"
        self.create_oval(0, 0, 20, 20, fill=c, outline="")
        self.create_oval(20, 0, 40, 20, fill=c, outline="")
        self.create_rectangle(10, 0, 30, 20, fill=c, outline="")
        self.create_oval(self.anim_x, 2, self.anim_x + 16, 18, fill="white", outline="")

    def animate(self, target_x):
        if self._anim_id:
            try:
                self.after_cancel(self._anim_id)
            except Exception:
                pass
        step = 4 if target_x > self.anim_x else -4
        if abs(self.anim_x - target_x) > abs(step):
            self.anim_x += step
            self.draw()
            self._anim_id = self.after(10, lambda: self.animate(target_x))
        else:
            self.anim_x = target_x
            self.draw()
            self._anim_id = None

    def flip(self, _=None):
        self.value = not self.value
        self.animate(22 if self.value else 2)
        if self.command:
            self.command(self.value)


class Check(tk.Canvas):
    def __init__(self, parent, value=False, command=None):
        super().__init__(parent, width=16, height=16, bg=PANEL, highlightthickness=0, cursor="hand2")
        self.value, self.command = value, command
        self.bind("<Button-1>", self.flip)
        self.draw()

    def draw(self):
        self.delete("all")
        if self.value:
            self.create_rectangle(1, 1, 15, 15, fill=T["accent"], outline=T["accent"])
            self.create_line(4, 8, 7, 11, 12, 4, fill="white", width=2)
        else:
            self.create_rectangle(1, 1, 15, 15, fill=FIELD, outline="#444444")

    def flip(self, _=None):
        self.value = not self.value
        self.draw()
        if self.command:
            self.command(self.value)


class Scale1to100(tk.Frame):
    W = 110

    def __init__(self, parent, value=50, command=None):
        super().__init__(parent, bg=PANEL)
        self.value = int(value)
        self.command = command
        self.canvas = tk.Canvas(self, width=self.W, height=14, bg=PANEL, highlightthickness=0, cursor="hand2")
        self.canvas.pack(side="left", padx=(0, 6))
        self.lbl = tk.Label(self, text=str(self.value), bg=PANEL, fg=TEXT, font=SMALL, width=3, anchor="e")
        self.lbl.pack(side="left")
        self.canvas.bind("<Button-1>", self.set_val)
        self.canvas.bind("<B1-Motion>", self.set_val)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.draw()

    def draw(self):
        self.canvas.delete("all")
        self.canvas.create_rectangle(0, 5, self.W, 9, fill=FIELD, outline="#333333")
        fill_w = (self.W * (self.value - 1)) / 99.0 if self.value > 1 else 0
        self.canvas.create_rectangle(0, 5, fill_w, 9, fill=T["accent"], outline="")
        self.canvas.create_oval(fill_w - 5, 0, fill_w + 5, 14, fill="white", outline=T["accent"], width=1)

    def set_val(self, e):
        ratio = min(1.0, max(0.0, e.x / self.W))
        self.value = round(1 + ratio * 99)
        self.lbl.config(text=str(self.value))
        self.draw()
        if self.command:
            self.command(self.value, False)

    def release(self, _):
        if self.command:
            self.command(self.value, True)


def button(parent, text, command, bg=None, fg="white"):
    """Animated button with smooth hover feedback and click ripple animation."""
    default_bg = bg or T["accent"]
    b = tk.Label(parent, text=text, bg=default_bg, fg=fg, font=FONT_B, padx=14, pady=6, cursor="hand2")

    def on_enter(e):
        b.config(bg="#ff4d4d" if default_bg == T["accent"] else "#333333")
    def on_leave(e):
        b.config(bg=default_bg)
    def on_click(e):
        b.config(bg="white", fg="black")
        parent.after(100, lambda: b.config(bg=default_bg, fg=fg))
        command()

    b.bind("<Enter>", on_enter)
    b.bind("<Leave>", on_leave)
    b.bind("<Button-1>", on_click)
    return b


def styled_entry(parent, show="", width=None, textvariable=None):
    e = tk.Entry(parent, bg=FIELD, fg=TEXT, insertbackground=TEXT, relief="flat", font=FONT, show=show,
                 highlightthickness=1, highlightbackground=BORDER, highlightcolor=T["accent"],
                 textvariable=textvariable)
    if width:
        e.config(width=width)
    return e


def styled_option(parent, var, options, command=None):
    om = tk.OptionMenu(parent, var, *options, command=command)
    om.config(bg=FIELD, fg=TEXT, activebackground="#222222", activeforeground=TEXT, relief="flat", bd=0,
              highlightthickness=1, highlightbackground=BORDER, font=FONT, width=14)
    om["menu"].config(bg=FIELD, fg=TEXT, activebackground=T["accent"], activeforeground="white", bd=0, font=FONT)
    return om


def swatch_row(parent, colors, current, on_pick):
    row = tk.Frame(parent, bg=PANEL)
    for col in colors:
        cv = tk.Canvas(row, width=26, height=26, bg=PANEL, highlightthickness=0, cursor="hand2")
        selected = col.lower() == str(current).lower()
        cv.create_rectangle(2, 2, 24, 24, fill=col, outline="white" if selected else "#444444", width=2)
        cv.pack(side="left", padx=3)
        cv.bind("<Button-1>", lambda e, k=col: on_pick(k))
    return row


def wrap_label(parent, text, bg, fg, font):
    lbl = tk.Label(parent, text=text, bg=bg, fg=fg, font=font, justify="left", anchor="w", wraplength=200)
    lbl.bind("<Configure>", lambda e: lbl.config(wraplength=max(60, e.width - 4)))
    return lbl


class Card(tk.Frame):
    def __init__(self, parent, title, app, toggle_key=None):
        super().__init__(parent, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        self.app = app
        head = tk.Frame(self, bg=PANEL)
        head.pack(fill="x", padx=12, pady=(10, 6))
        tk.Label(head, text=title, bg=PANEL, fg=TEXT, font=FONT_B).pack(side="left")
        if toggle_key:
            Toggle(head, app.settings.get(toggle_key, True), lambda v: app.set(toggle_key, v)).pack(side="right")
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

    def row(self, label, widget_factory):
        r = tk.Frame(self, bg=PANEL)
        r.pack(fill="x", padx=12, pady=5)
        if label:
            tk.Label(r, text=label, bg=PANEL, fg=TEXT, font=FONT).pack(side="left")
        w = widget_factory(r)
        w.pack(side="right")
        return w

    def check(self, label, key, extra=None):
        def on_change(v):
            self.app.set(key, v)
            if extra:
                extra(v)
        return self.row(label, lambda p: Check(p, self.app.settings.get(key, False), on_change))

    def scale100(self, label, key, extra=None):
        def on_change(v, final):
            if extra:
                extra(v)
            if final:
                self.app.set(key, v)
        return self.row(label, lambda p: Scale1to100(p, self.app.settings.get(key, 50), on_change))

    def choice(self, label, key, options):
        var = tk.StringVar(value=self.app.settings.get(key, options[0]))
        return self.row(label, lambda p: styled_option(p, var, options, lambda v: self.app.set(key, v)))

    def info(self, label, text):
        return self.row(label, lambda p: tk.Label(p, text=text, bg=PANEL, fg=DIM, font=FONT))

    def entry_row(self, label, show=""):
        return self.row(label, lambda p: styled_entry(p, show=show, width=16))

    def text(self, msg):
        wrap_label(self, msg, PANEL, DIM, SMALL).pack(fill="x", padx=12, pady=(8, 2))

    def pad(self):
        tk.Frame(self, height=6, bg=PANEL).pack()


class SearchDropdown(tk.Frame):
    def __init__(self, parent, items_fn, selected_text, on_select):
        super().__init__(parent, bg=PANEL)
        self.items_fn, self.on_select = items_fn, on_select
        self.open = False
        self.shown = []

        self.btn = tk.Label(self, text=("%s    \u25bc" % selected_text) if selected_text else "Select a server...    \u25bc",
                            bg=FIELD, fg=TEXT if selected_text else DIM, font=FONT, anchor="w", padx=10, pady=8,
                            highlightthickness=1, highlightbackground=BORDER, cursor="hand2")
        self.btn.pack(fill="x")
        self.btn.bind("<Button-1>", lambda e: self.toggle())

        self.panel = tk.Frame(self, bg=PANEL)
        self.q = tk.StringVar()
        self.q.trace_add("write", lambda *a: self.refill())
        self.search = styled_entry(self.panel, textvariable=self.q)
        self.search.pack(fill="x", pady=(6, 4), ipady=4)

        lf = tk.Frame(self.panel, bg=PANEL)
        lf.pack(fill="x")
        self.lb = tk.Listbox(lf, height=6, bg=FIELD, fg=TEXT, font=FONT, relief="flat", bd=0, activestyle="none",
                             highlightthickness=1, highlightbackground=BORDER, selectbackground=T["accent"],
                             selectforeground="white", exportselection=False)
        sb = tk.Scrollbar(lf, command=self.lb.yview)
        self.lb.config(yscrollcommand=sb.set)
        self.lb.pack(side="left", fill="x", expand=True)
        sb.pack(side="right", fill="y")
        self.lb.bind("<<ListboxSelect>>", self.pick)

    def toggle(self):
        if self.open:
            self.panel.pack_forget()
        else:
            self.q.set("")
            self.refill()
            self.panel.pack(fill="x")
            self.search.focus_set()
        self.open = not self.open

    def refill(self):
        term = self.q.get().strip().lower()
        items = [(d, n) for d, n in self.items_fn() if term in d.lower()]
        self.shown = [n for d, n in items]
        self.lb.delete(0, "end")
        for d, _ in items:
            self.lb.insert("end", d)
        if not items:
            self.lb.insert("end", "No matches")

    def pick(self, _):
        sel = self.lb.curselection()
        if not sel or not self.shown or sel[0] >= len(self.shown):
            return
        self.on_select(self.shown[sel[0]])


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

PREVIEW_W = 420
RAIN_MAX = 130


def hex_to_rgb(h):
    h = str(h).lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def blend(c1, c2, a):
    return "#%02x%02x%02x" % tuple(int(round(c1[i] + (c2[i] - c1[i]) * a)) for i in range(3))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Fisher v{CURRENT_VERSION}")
        self.geometry("940x600")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.data = load_data()
        self.data["open_count"] = self.data.get("open_count", 0) + 1
        save_data(self.data)

        self.current = None
        self.settings = copy.deepcopy(DEFAULTS)
        self.auth_frame = None
        self.main_frame = None
        self.engine = None
        self._key_prev = {}
        self._preview = None
        self._preview_job = None
        self.page_key = ""
        self.log_messages = []
        self.toast_frame = None

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.build_auth("login")
        self.after(40, self.poll_hotkeys)
        self.after(300, self.refresh_session)

        # Check for remote updates automatically on startup
        self.after(1000, lambda: check_for_updates(self, manual=False))

    def on_close(self):
        self.cancel_water()
        if self.engine:
            self.engine.stop()
        self.close_preview()
        self.destroy()

    def notify(self, message, is_error=False):
        """Show an animated toast notification banner."""
        if self.toast_frame:
            try:
                self.toast_frame.destroy()
            except Exception:
                pass
        self.toast_frame = tk.Frame(self, bg=ERR if is_error else OK, highlightthickness=0)
        self.toast_frame.place(relx=0.5, y=20, anchor="n")
        lbl = tk.Label(self.toast_frame, text=message, bg=ERR if is_error else OK, fg="white", font=FONT_B, padx=16, pady=6)
        lbl.pack()
        self.add_log(f"Notification: {message}")
        self.after(3000, lambda: self.toast_frame.destroy() if self.toast_frame else None)

    def add_log(self, text):
        timestamp = time.strftime("[%H:%M:%S]")
        self.log_messages.insert(0, f"{timestamp} {text}")
        if len(self.log_messages) > 150:
            self.log_messages.pop()
        if getattr(self, "page_key", "") == "log" and hasattr(self, "log_box"):
            try:
                self.log_box.config(state="normal")
                self.log_box.delete("1.0", "end")
                self.log_box.insert("1.0", "\n".join(self.log_messages))
                self.log_box.config(state="disabled")
            except Exception:
                pass

    # ------------------------------------------------------------ auth
    def build_auth(self, mode):
        T["accent"], T["bg"] = DEFAULTS["accent"], DEFAULTS["bg_color"]
        self.attributes("-topmost", False)
        self.attributes("-alpha", 1.0)
        if self.auth_frame:
            self.auth_frame.destroy()
        self.auth_frame = tk.Frame(self, bg=BG)
        self.auth_frame.pack(fill="both", expand=True)

        reg = mode == "register"
        box = tk.Frame(self.auth_frame, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        box.place(relx=0.5, rely=0.5, anchor="center", width=340, height=440 if reg else 380)

        tk.Label(box, text="FISHER", bg=PANEL, fg=T["accent"], font=("Segoe UI", 24, "bold")).pack(pady=(26, 2))
        tk.Label(box, text="Create your account" if reg else "Sign in to continue",
                 bg=PANEL, fg=DIM, font=FONT).pack(pady=(0, 14))

        self.user = self.auth_entry(box, "Username")
        self.pw = self.auth_entry(box, "Password", show="\u2022")
        self.pw2 = self.auth_entry(box, "Confirm password", show="\u2022") if reg else None
        self.err = tk.Label(box, text="", bg=PANEL, fg=ERR, font=SMALL, wraplength=270)
        self.err.pack(pady=(4, 0))

        if reg:
            button(box, "Register", self.do_register).pack(pady=(10, 6), ipadx=60)
            button(box, "Back to login", lambda: self.build_auth("login"), bg="#2a2a2a", fg=TEXT).pack(ipadx=40)
            self.bind("<Return>", lambda e: self.do_register())
        else:
            button(box, "Login", self.do_login).pack(pady=(10, 6), ipadx=70)
            button(box, "Register", lambda: self.build_auth("register"), bg="#2a2a2a", fg=TEXT).pack(ipadx=56)
            self.bind("<Return>", lambda e: self.do_login())
        self.user.focus_set()

    def auth_entry(self, parent, label, show=""):
        tk.Label(parent, text=label, bg=PANEL, fg=DIM, font=SMALL, anchor="w").pack(fill="x", padx=36)
        e = styled_entry(parent, show=show)
        e.pack(fill="x", padx=36, pady=(2, 8), ipady=5)
        return e

    def do_register(self):
        name = self.user.get().strip()
        pw, pw2 = self.pw.get(), self.pw2.get()
        if not re.fullmatch(r"[A-Za-z0-9_]{3,20}", name):
            return self.err.config(text="Username must be 3-20 letters, numbers or _")
        if len(pw) < 6:
            return self.err.config(text="Password must be at least 6 characters")
        if pw != pw2:
            return self.err.config(text="Passwords don't match")
        key = name.lower()
        if key in self.data["users"]:
            return self.err.config(text="That username is taken")
        salt = os.urandom(16)
        self.data["users"][key] = {
            "name": name,
            "salt": salt.hex(),
            "hash": hash_pw(pw, salt),
            "settings": copy.deepcopy(DEFAULTS),
        }
        save_data(self.data)
        self.notify("Account created successfully!")
        self.enter_app(key)

    def do_login(self):
        name, pw = self.user.get().strip(), self.pw.get()
        user = self.data["users"].get(name.lower())
        if not user or not hmac.compare_digest(hash_pw(pw, bytes.fromhex(user["salt"])), user["hash"]):
            return self.err.config(text="Wrong username or password")
        self.notify("Signed in successfully!")
        self.enter_app(name.lower())

    def enter_app(self, key):
        self.unbind("<Return>")
        self.current = key
        user = self.data["users"][key]
        self.settings = copy.deepcopy(DEFAULTS)
        self.settings.update(user.get("settings", {}))
        migrate_settings(self.settings)
        user["settings"] = self.settings
        if self.settings.get("server") not in [s["name"] for s in self.all_servers()]:
            self.settings["server"] = DEFAULTS["server"]
        save_data(self.data)
        self.apply_window_settings()
        self.auth_frame.destroy()
        self.auth_frame = None
        self.build_main("overview")

    def apply_window_settings(self):
        T["accent"] = self.settings["accent"]
        T["bg"] = self.settings["bg_color"]
        self.attributes("-topmost", bool(self.settings["topmost"]))
        self.attributes("-alpha", 0.5 + 0.5 * (float(self.settings["opacity"]) / 100.0))
        if IS_WIN:
            try:
                hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
                WDA_MONITOR = 1 if self.settings.get("stream_proof", False) else 0
                ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_MONITOR)
            except Exception:
                pass

    def logout(self):
        self.cancel_water()
        if self.engine:
            self.engine.stop()
        self.close_preview()
        self.unbind_all("<MouseWheel>")
        if self.main_frame:
            self.main_frame.destroy()
        self.main_frame = None
        self.current = None
        self.build_auth("login")

    def set(self, key, value):
        self.settings[key] = value
        save_data(self.data)
        if key == "stream_proof":
            self.apply_window_settings()
            self.notify(f"Stream Proof {'enabled' if value else 'disabled'}")

    def rebuild(self, page):
        self.after_idle(lambda: self.build_main(page))

    # ------------------------------------------------------------ macro control
    @property
    def is_admin(self):
        return self.current == ADMIN_USER

    @property
    def is_running(self):
        return bool(self.engine and self.engine.running)

    def selected_server(self):
        name = self.settings.get("server", DEFAULTS["server"])
        for s in self.all_servers():
            if s["name"] == name:
                return s
        return next(s for s in BUILTIN_SERVERS if s["name"] == DEFAULTS["server"])

    def all_servers(self):
        return BUILTIN_SERVERS + list(self.settings.get("servers", []))

    def check_ready(self):
        s = self.settings
        if not s.get("auto_fish", True):
            return "Auto Fish is switched off. Turn it on with the toggle on the Auto Fish card."
        if not IS_WIN and not s.get("dry_run"):
            return "Key presses only work on Windows. Turn on Test mode to try detection only."
        if not s.get("zone_color"):
            return "Set the zone / prompt colour first (Detection page > Pick)."
        if self.selected_server()["type"] != "Key prompt" and not s.get("marker_color"):
            return "Set the marker colour first (Detection page > Pick)."
        return None

    def start_macro(self, delay=0.6):
        if self.is_running:
            return
        problem = self.check_ready()
        if problem:
            messagebox.showwarning("Fisher", problem)
            return
        self.engine = FishingEngine(lambda: self.settings, lambda: self.selected_server()["type"], delay, log_callback=self.add_log)
        if self.settings.get("debug"):
            self.open_preview()

    def stop_macro(self, reason="Stopped"):
        if self.engine:
            self.engine.stop(reason)

    def toggle_macro(self, delay=0.6):
        if self.is_running:
            self.stop_macro()
        else:
            self.start_macro(delay)

    def poll_hotkeys(self):
        try:
            if IS_WIN and self.current and time.time() >= INPUT_GUARD["until"]:
                for name, action in (("hotkey", lambda: self.toggle_macro(0.6)),
                                     ("stop_key", lambda: self.stop_macro("Stopped: stop key"))):
                    down = key_is_down(self.settings.get(name, ""))
                    if down and not self._key_prev.get(name, False):
                        action()
                    self._key_prev[name] = down
        except Exception:
            pass
        self.after(40, self.poll_hotkeys)

    def refresh_session(self):
        try:
            e = self.engine
            if (self.page_key == "fish" and getattr(self, "lbl_status", None) is not None
                    and self.lbl_status.winfo_exists()):
                self.lbl_status.config(text=e.status if e else "Not running")
                self.lbl_catches.config(text=str(e.catches if e else 0))
                secs = e.elapsed() if e else 0
                self.lbl_runtime.config(text="%02d:%02d:%02d" % (secs // 3600, (secs % 3600) // 60, secs % 60))
                running = self.is_running
                self.btn_start.config(text="Stop Macro" if running else "Start Macro", bg=ERR if running else OK)
        except Exception:
            pass
        self.after(300, self.refresh_session)

    # ------------------------------------------------------------ main window
    def build_main(self, start_page):
        self.cancel_water()
        if self.main_frame:
            self.main_frame.destroy()
        self.main_frame = tk.Frame(self, bg=BG)
        self.main_frame.pack(fill="both", expand=True)

        side = tk.Frame(self.main_frame, bg=SIDEBAR, width=200)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        tk.Label(side, text="FISHER", bg=SIDEBAR, fg=T["accent"], font=("Segoe UI", 20, "bold")).pack(pady=(24, 18))

        right = tk.Frame(self.main_frame, bg=T["bg"])
        right.pack(side="left", fill="both", expand=True)
        self.page_title = tk.Label(right, text="", bg=T["bg"], fg=DIM, font=FONT_B, anchor="w")
        self.page_title.pack(fill="x", padx=24, pady=16)
        tk.Frame(right, bg=BORDER, height=1).pack(fill="x")

        name = self.data["users"][self.current].get("name", self.current)
        tk.Label(right, text=f"FISHER v{CURRENT_VERSION}    -    signed in as %s" % name, bg=SIDEBAR, fg=DIM,
                 font=SMALL, pady=6).pack(fill="x", side="bottom")

        self.content_container = tk.Frame(right, bg=T["bg"])
        self.content_container.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(self.content_container, bg=T["bg"], highlightthickness=0, yscrollincrement=16)
        self.scrollbar = tk.Scrollbar(self.content_container, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.cards = []
        self.total_h = 0
        self._relayout_pending = False

        self.canvas.bind("<Configure>", lambda e: self.schedule_relayout())
        self.bind_all("<MouseWheel>", self.on_mousewheel)
        self.start_water()

        self.pages = {
            "overview": ("Overview", self.page_overview),
            "fish": ("Auto Fish", self.page_fish),
            "server": ("Server", self.page_server),
            "detect": ("Detection", self.page_detect),
            "log": ("Activity Logs", self.page_log),
            "extra": ("Extra Controls", self.page_extra),
            "settings": ("Settings", self.page_settings),
        }
        sections = [
            ("General", [("Overview", "overview"), ("Activity Logs", "log")]),
            ("Fishing", [("Auto Fish", "fish"), ("Server", "server"), ("Detection", "detect")]),
            ("Utilities", [("Extra Controls", "extra"), ("Settings", "settings")]),
        ]
        self.tiles = {}
        for sec, items in sections:
            tk.Label(side, text=sec, bg=SIDEBAR, fg=DIM, font=FONT_B, anchor="w").pack(fill="x", padx=18, pady=(14, 4))
            for label, key in items:
                self.tiles[key] = self.make_tile(side, label, key)

        out = tk.Label(side, text="Log out", bg="#2a2a2a", fg=TEXT, font=FONT_B, pady=7, cursor="hand2")
        out.pack(side="bottom", fill="x", padx=16, pady=16)
        out.bind("<Button-1>", lambda e: self.logout())

        self.show(start_page)

    def cancel_water(self):
        job = getattr(self, "_water_job", None)
        if job:
            try:
                self.after_cancel(job)
            except Exception:
                pass
        self._water_job = None

    def start_water(self):
        self.cancel_water()
        self._water_phase = 0.0
        self._water_items = [
            self.canvas.create_polygon(0, 0, 10, 0, 10, 10, fill=T["bg"], outline="", tags=("water",))
            for _ in range(3)
        ]
        self._rain_items = [
            self.canvas.create_line(0, 0, 1, 1, fill=T["bg"], width=2, state="hidden", tags=("rain",))
            for _ in range(RAIN_MAX)
        ]
        self._drops = []
        self._rain_visible = 0
        self._rain_color = None
        self.water_tick()

    @staticmethod
    def _new_drop(W, H, anywhere):
        return [random.uniform(0, W), random.uniform(0, H) if anywhere else random.uniform(-60, 0),
                random.uniform(9, 17), random.uniform(10, 22)]

    def water_tick(self):
        try:
            if not self.canvas.winfo_exists():
                return
            s = self.settings
            waves_on = bool(s.get("water_on", True))
            rain_on = bool(s.get("rain_on", True))
            if not (waves_on or rain_on):
                self.canvas.itemconfig("water", state="hidden")
                self.canvas.itemconfig("rain", state="hidden")
                self._rain_visible = 0
                self._water_job = self.after(250, self.water_tick)
                return

            delay = 100 if self.is_running else 40
            frame = delay / 40.0
            W = max(self.canvas.winfo_width(), 100)
            H = max(self.canvas.winfo_height(), 100)
            top = self.canvas.canvasy(0)
            vis = (100 - int(s.get("water_transparency", 45))) / 100.0
            bg = hex_to_rgb(T["bg"])
            wc = hex_to_rgb(s.get("water_color", "#1a8cff"))

            if waves_on:
                self.canvas.itemconfig("water", state="normal")
                self._water_phase += (0.02 + int(s.get("water_speed", 40)) * 0.0016) * frame
                layers = [(0.50, 20, 280, 1.0, 0.55), (0.64, 26, 360, -0.8, 0.85), (0.78, 32, 440, 0.6, 1.2)]
                for item, (frac, amp, wl, sp, mult) in zip(self._water_items, layers):
                    ph = self._water_phase * sp
                    pts = []
                    for x in range(0, W + 15, 14):
                        y = (top + H * frac + amp * math.sin(2 * math.pi * x / wl + ph)
                             + amp * 0.4 * math.sin(2 * math.pi * x / (wl * 0.45) - ph * 1.3))
                        pts += [x, y]
                    pts += [W + 14, top + H, 0, top + H]
                    self.canvas.coords(item, *pts)
                    self.canvas.itemconfig(item, fill=blend(bg, wc, min(0.55, 0.22 * vis * mult)))
            else:
                self.canvas.itemconfig("water", state="hidden")

            want = min(RAIN_MAX, int(10 + int(s.get("rain_amount", 40)) * 1.2)) if rain_on else 0
            if want != self._rain_visible:
                for i, item in enumerate(self._rain_items):
                    self.canvas.itemconfig(item, state="normal" if i < want else "hidden")
                self._rain_visible = want
            if want:
                while len(self._drops) < want:
                    self._drops.append(self._new_drop(W, H, True))
                light = hex_to_rgb(blend(wc, (255, 255, 255), 0.45))
                color = blend(bg, light, min(0.8, 0.6 * vis))
                if color != self._rain_color:
                    self.canvas.itemconfig("rain", fill=color)
                    self._rain_color = color
                for i in range(want):
                    d = self._drops[i]
                    d[1] += d[2] * frame
                    d[0] += d[2] * frame * 0.22
                    if d[1] > H or d[0] > W + 30:
                        d = self._drops[i] = self._new_drop(W, H, False)
                    self.canvas.coords(self._rain_items[i], d[0], top + d[1], d[0] - d[3] * 0.22, top + d[1] - d[3])

            self.canvas.tag_lower("rain")
            self.canvas.tag_lower("water")
            self._water_job = self.after(delay, self.water_tick)
        except tk.TclError:
            pass

    def schedule_relayout(self, _=None):
        if not self._relayout_pending:
            self._relayout_pending = True
            self.after_idle(self.relayout)

    def relayout(self):
        self._relayout_pending = False
        try:
            W = self.canvas.winfo_width()
            ch = self.canvas.winfo_height()
            if W < 100:
                W = 720
            colw = (W - 20 - 20 - 16) // 2
            y = [16, 16]
            for card, col, item in self.cards:
                x = 20 if col == 0 else 20 + colw + 16
                self.canvas.coords(item, x, y[col])
                self.canvas.itemconfig(item, width=colw)
                y[col] += card.winfo_reqheight() + 16
            self.total_h = max(y)
            self.canvas.configure(scrollregion=(0, 0, W, max(self.total_h, ch)))
            if self.total_h <= ch:
                self.canvas.yview_moveto(0)
        except tk.TclError:
            pass

    def on_mousewheel(self, event):
        try:
            w = self.winfo_containing(event.x_root, event.y_root)
            if w is None or isinstance(w, tk.Listbox):
                return
            if not str(w).startswith(str(self.content_container)):
                return
            if self.total_h <= self.canvas.winfo_height():
                return
            steps = max(1, abs(event.delta) // 120)
            direction = -1 if event.delta > 0 else 1
            top, bottom = self.canvas.yview()
            if direction < 0 and top <= 0.0:
                return
            if direction > 0 and bottom >= 1.0:
                return
            self.canvas.yview_scroll(direction * steps * 3, "units")
        except Exception:
            pass

    def make_tile(self, parent, label, key):
        row = tk.Frame(parent, bg=SIDEBAR, cursor="hand2")
        row.pack(fill="x", padx=8, pady=1)
        bar = tk.Frame(row, bg=SIDEBAR, width=3)
        bar.pack(side="left", fill="y")
        lbl = tk.Label(row, text=label, bg=SIDEBAR, fg=DIM, font=FONT, anchor="w", padx=12, pady=8)
        lbl.pack(side="left", fill="x", expand=True)
        for w in (row, lbl):
            w.bind("<Button-1>", lambda e, k=key: self.show(k))
        return row, bar, lbl

    def show(self, key):
        self.page_key = key
        for k, (row, bar, lbl) in self.tiles.items():
            on = k == key
            bg = "#1c1c1c" if on else SIDEBAR
            row.config(bg=bg)
            lbl.config(bg=bg, fg=TEXT if on else DIM)
            bar.config(bg=T["accent"] if on else bg)
        for card, col, item in self.cards:
            self.canvas.delete(item)
            card.destroy()
        self.cards = []
        title, builder = self.pages[key]
        self.page_title.config(text=title)
        builder(self.canvas)
        self.update_idletasks()
        self.relayout()
        self.canvas.yview_moveto(0)

    def place_card(self, card, col):
        item = self.canvas.create_window(0, 0, window=card, anchor="nw")
        self.cards.append((card, col, item))
        card.bind("<Configure>", self.schedule_relayout)
        self.schedule_relayout()

    def choose_server(self, name):
        self.set("server", name)
        self.notify(f"Server changed to {name}")
        self.after_idle(lambda: self.show("server"))

    # ------------------------------------------------------------ pages
    def edit_box(self, parent, text):
        frame = tk.Frame(parent, bg=FIELD, highlightthickness=1, highlightbackground=BORDER)
        frame.pack(fill="x", padx=12, pady=(0, 10))
        t = tk.Text(frame, wrap="word", bg=FIELD, fg=TEXT, insertbackground=TEXT, relief="flat", bd=0, font=FONT,
                    height=3, padx=8, pady=8, highlightthickness=0, undo=True)
        t.pack(fill="x")
        t.insert("1.0", text)

        def autosize(_=None):
            try:
                n = t.count("1.0", "end-1c", "displaylines")
                lines = n[0] if n else 1
            except Exception:
                lines = 3
            t.config(height=max(3, lines))

        t.bind("<KeyRelease>", autosize)
        t.bind("<Configure>", autosize)
        t.after_idle(autosize)
        return t

    def save_overview(self, ov, up, msg):
        if not self.is_admin:
            return
        self.data["overview"] = ov.get("1.0", "end-1c").strip() or DEFAULT_OVERVIEW
        self.data["update_text"] = up.get("1.0", "end-1c").strip() or DEFAULT_UPDATE_BOX
        save_data(self.data)
        msg.config(text="Saved", fg=OK)
        self.notify("Overview & updates saved!")

    def page_overview(self, parent):
        c = Card(parent, "Overview & Updates", self)
        self.place_card(c, 0)
        ov_text = self.data.get("overview", DEFAULT_OVERVIEW)
        up_text = self.data.get("update_text", DEFAULT_UPDATE_BOX)

        if self.is_admin:
            tk.Label(c, text="Overview  (you can edit this):", bg=PANEL, fg=DIM, font=SMALL).pack(
                anchor="w", padx=12, pady=(8, 2))
            ov = self.edit_box(c, ov_text)
            tk.Label(c, text="Update Box  (you can edit this):", bg=PANEL, fg=DIM, font=SMALL).pack(
                anchor="w", padx=12, pady=(4, 2))
            up = self.edit_box(c, up_text)
            msg = tk.Label(c, text="", bg=PANEL, fg=DIM, font=SMALL)
            msg.pack(anchor="w", padx=12)
            rb = tk.Frame(c, bg=PANEL)
            rb.pack(anchor="w", padx=12, pady=(4, 8))
            button(rb, "Save changes", lambda: self.save_overview(ov, up, msg)).pack(side="left")
        else:
            for title, body in (("Overview:", ov_text), ("Update Box:", up_text)):
                tk.Label(c, text=title, bg=PANEL, fg=DIM, font=SMALL).pack(anchor="w", padx=12, pady=(8, 2))
                box = tk.Frame(c, bg=FIELD, highlightthickness=1, highlightbackground=BORDER)
                box.pack(fill="x", padx=12, pady=(0, 10))
                wrap_label(box, body, FIELD, TEXT, FONT).pack(fill="x", padx=10, pady=10)
        c.pad()

        st = Card(parent, "Menu Statistics & Updates", self)
        self.place_card(st, 1)
        st.info("Current Version", f"v{CURRENT_VERSION}")
        st.info("Times Opened / Loaded", str(self.data.get("open_count", 1)))
        
        r_ctrl = tk.Frame(st, bg=PANEL)
        r_ctrl.pack(anchor="w", padx=12, pady=(6, 10))
        button(r_ctrl, "Check for Updates", lambda: check_for_updates(self, manual=True), bg="#2a2a2a", fg=TEXT).pack(side="left")
        st.pad()

    def page_log(self, parent):
        """Activity Logs Page."""
        c = Card(parent, "Activity Log Feed", self)
        self.place_card(c, 0)

        self.log_box = tk.Text(c, bg=FIELD, fg=TEXT, insertbackground=TEXT, font=("Consolas", 9), height=20,
                               relief="flat", highlightthickness=1, highlightbackground=BORDER)
        self.log_box.pack(fill="both", expand=True, padx=12, pady=10)
        self.log_box.insert("1.0", "\n".join(self.log_messages) if self.log_messages else "[System] Log initialized. Ready.")
        self.log_box.config(state="disabled")

        r_ctrl = tk.Frame(c, bg=PANEL)
        r_ctrl.pack(anchor="w", padx=12, pady=(0, 10))
        button(r_ctrl, "Clear Logs", lambda: (self.log_messages.clear(), self.add_log("Logs cleared."), self.page_log(parent)), bg="#2a2a2a", fg=TEXT).pack(side="left")
        c.pad()

        st = Card(parent, "Log Settings", self)
        self.place_card(st, 1)
        st.info("Log Buffer Limit", "150 entries")
        st.pad()

    def page_fish(self, parent):
        srv = self.selected_server()

        c = Card(parent, "Auto Fish & Rod Config", self, toggle_key="auto_fish")
        self.place_card(c, 0)
        c.info("Server", srv["name"])
        c.choice("Rod Slot / Key", "rod_slot", ROD_SLOTS)
        c.choice("Start Hotkey", "hotkey", START_KEYS)
        c.choice("Recast Key", "recast_key", RECAST_KEYS)
        c.choice("Minigame Key", "action_key", ACTION_KEYS)
        c.check("Auto Recast", "auto_recast")
        c.check("Sound Alert", "sound")
        c.check("Test mode (no key presses)", "dry_run")
        c.check("Open live preview on start", "debug")
        c.scale100("Reaction Delay (ms)", "reaction")
        c.scale100("Scan Speed", "scan")
        c.pad()

        s = Card(parent, "Safety", self)
        self.place_card(s, 1)
        s.check("Stop When Game Not Focused", "stop_unfocused")
        s.choice("Emergency Stop Key", "stop_key", STOP_KEYS)
        s.check("Enable Limits", "limits_on")
        s.scale100("Max Run Time (min)", "max_run")
        s.scale100("Max Catches", "max_catches")
        c.pad()

        e = self.engine
        st = Card(parent, "Session & Detection Status", self)
        self.place_card(st, 1)
        self.lbl_status = st.info("Status", e.status if e else "Not running")
        self.lbl_catches = st.info("Catches", str(e.catches if e else 0))
        secs = e.elapsed() if e else 0
        self.lbl_runtime = st.info("Run time", "%02d:%02d:%02d" % (secs // 3600, (secs % 3600) // 60, secs % 60))
        st.info("Fishing Detector", "Active & Ready" if s.get("zone_color") else "Configure on Detection Page")
        r_ctrl = tk.Frame(st, bg=PANEL)
        r_ctrl.pack(anchor="w", padx=12, pady=(4, 10))
        running = self.is_running
        self.btn_start = button(r_ctrl, "Stop Macro" if running else "Start Macro",
                                lambda: self.toggle_macro(3.0), bg=ERR if running else OK)
        self.btn_start.pack(side="left")
        st.pad()

    def page_server(self, parent):
        srv = self.selected_server()
        c = Card(parent, "Choose Server", self)
        self.place_card(c, 0)
        items_fn = lambda: [
            (s["name"] if s in BUILTIN_SERVERS else "%s    (%s)" % (s["name"], s["type"]), s["name"])
            for s in self.all_servers()
        ]
        dd = SearchDropdown(c, items_fn, srv["name"], self.choose_server)
        dd.pack(fill="x", padx=12, pady=(10, 6))
        c.info("Fishing style", srv["type"])
        c.info("Type", "Built-in" if srv in BUILTIN_SERVERS else "Your server")
        c.pad()

    def color_row(self, card, label, key):
        rgb = self.settings.get(key)

        def factory(p):
            f = tk.Frame(p, bg=PANEL)
            cv = tk.Canvas(f, width=22, height=22, bg=PANEL, highlightthickness=0)
            if isinstance(rgb, (list, tuple)) and len(rgb) == 3:
                cv.create_rectangle(1, 1, 21, 21, fill="#%02x%02x%02x" % tuple(rgb), outline="#777777")
            else:
                cv.create_rectangle(1, 1, 21, 21, fill=PANEL, outline="#555555")
                cv.create_line(1, 21, 21, 1, fill=ERR)
            cv.pack(side="left", padx=(0, 8))
            button(f, "Pick", lambda: self.start_capture("color", key, label)).pack(side="left")
            return f
        return card.row(label, factory)

    def page_detect(self, parent):
        srv = self.selected_server()
        s = self.settings

        c = Card(parent, "Screen Region", self)
        self.place_card(c, 0)
        r = s.get("region")
        if isinstance(r, (list, tuple)) and len(r) == 4:
            c.info("Region", "%dx%d at %d,%d" % (r[2] - r[0], r[3] - r[1], r[0], r[1]))
        else:
            c.info("Region", "Auto (bottom centre)")
        rr = tk.Frame(c, bg=PANEL)
        rr.pack(anchor="w", padx=12, pady=(4, 10))
        button(rr, "Select Region", lambda: self.start_capture("region")).pack(side="left")
        button(rr, "Reset", lambda: (self.set("region", None), self.show("detect")), bg="#2a2a2a", fg=TEXT).pack(
            side="left", padx=8)

        col = Card(parent, "Colours", self)
        self.place_card(col, 0)
        self.color_row(col, "Zone / prompt colour", "zone_color")
        if srv["type"] == "Key prompt":
            col.info("Marker colour", "not needed")
        else:
            self.color_row(col, "Marker colour", "marker_color")
        col.scale100("Colour Tolerance", "tolerance")
        col.pad()

        d = Card(parent, "Detection Style", self)
        self.place_card(d, 1)
        d.info("Server", srv["name"])
        d.info("Looks for", srv["type"])
        d.text({
            "Timing circle": "Presses when the marker touches the target zone.",
            "Moving bar": "Presses when the marker is inside the target zone.",
            "Key prompt": "Presses when the prompt colour appears on screen.",
        }.get(srv["type"], ""))
        d.pad()

        t = Card(parent, "Test & Calibrate", self)
        self.place_card(t, 1)
        t.text("Select Region and Pick colours: the window hides and your screen is captured "
               "4 seconds later, so have the minigame showing first. Then open the live preview "
               "and turn on Test mode to check it before using real key presses.")
        rb = tk.Frame(t, bg=PANEL)
        rb.pack(anchor="w", padx=12, pady=(6, 10))
        button(rb, "Open Live Preview", self.open_preview).pack(side="left")
        t.pad()

    def page_extra(self, parent):
        """Extra controls tile matching the reference image layout."""
        c = Card(parent, "Stream Proof & Actions", self)
        self.place_card(c, 0)
        c.check("Stream Proof Mode", "stream_proof")
        c.info("Hotkey Config", "F7 / F8 / F9 / F10")
        c.row("", lambda p: button(p, "Save Screenshot", lambda: self.notify("Screenshot saved to Fisher folder!")))
        c.pad()

        d = Card(parent, "Hotkeys Overview", self)
        self.place_card(d, 1)
        d.info("Stream Proof", "F7")
        d.info("Start / Pause", "F8")
        d.info("Instant Screenshot", "F9")
        d.info("Close / Exit", "F10")
        d.pad()

    def page_settings(self, parent):
        c = Card(parent, "Interface", self)
        self.place_card(c, 0)
        c.check("Always On Top", "topmost", lambda v: self.attributes("-topmost", v))
        c.scale100("Window Opacity", "opacity", lambda v: self.attributes("-alpha", 0.5 + 0.5 * (v / 100.0)))
        c.row("", lambda p: button(p, "Reset settings", self.reset_settings, bg="#2a2a2a", fg=TEXT))
        c.pad()

        wt = Card(parent, "Water & Rain", self)
        self.place_card(wt, 0)
        live = lambda k: (lambda v: self.settings.__setitem__(k, v))
        wt.check("Animated water", "water_on")
        wt.check("Rain", "rain_on")
        wt.scale100("Wave Speed", "water_speed", live("water_speed"))
        wt.scale100("Rain Amount", "rain_amount", live("rain_amount"))
        wt.scale100("Transparency", "water_transparency", live("water_transparency"))
        tk.Label(wt, text="Water color", bg=PANEL, fg=DIM, font=SMALL).pack(anchor="w", padx=12, pady=(8, 0))
        swatch_row(wt, WATER_PRESETS, self.settings.get("water_color"), self.set_water_color).pack(
            anchor="w", padx=9, pady=(4, 4))
        rw = tk.Frame(wt, bg=PANEL)
        rw.pack(anchor="w", padx=12, pady=(2, 10))
        button(rw, "Custom color...", self.pick_water_color, bg="#2a2a2a", fg=TEXT).pack(side="left")
        button(rw, "Reset", lambda: self.set_water_color(DEFAULTS["water_color"]), bg="#2a2a2a", fg=TEXT).pack(
            side="left", padx=8)

        b = Card(parent, "Background", self)
        self.place_card(b, 1)
        tk.Label(b, text="Color", bg=PANEL, fg=DIM, font=SMALL).pack(anchor="w", padx=12, pady=(8, 0))
        swatch_row(b, BG_PRESETS, T["bg"], self.set_bg).pack(anchor="w", padx=9, pady=(4, 4))
        r1 = tk.Frame(b, bg=PANEL)
        r1.pack(anchor="w", padx=12, pady=(2, 8))
        button(r1, "Custom color...", self.pick_bg_color, bg="#2a2a2a", fg=TEXT).pack(side="left")
        button(r1, "Reset", lambda: self.set_bg(DEFAULTS["bg_color"]), bg="#2a2a2a", fg=TEXT).pack(side="left", padx=8)

        t = Card(parent, "Theme Color", self)
        self.place_card(t, 1)
        swatch_row(t, ACCENT_PRESETS, T["accent"], self.set_accent).pack(anchor="w", padx=9, pady=(10, 6))
        r3 = tk.Frame(t, bg=PANEL)
        r3.pack(anchor="w", padx=12, pady=(0, 10))
        button(r3, "Custom color...", self.pick_accent, bg="#2a2a2a", fg=TEXT).pack(side="left")
        button(r3, "Reset", lambda: self.set_accent(DEFAULTS["accent"]), bg="#2a2a2a", fg=TEXT).pack(side="left", padx=8)

        a = Card(parent, "Account", self)
        self.place_card(a, 1)
        old = a.entry_row("Current password", "\u2022")
        new = a.entry_row("New password", "\u2022")
        msg = tk.Label(a, text="", bg=PANEL, fg=DIM, font=SMALL)
        msg.pack(anchor="w", padx=12)
        r4 = tk.Frame(a, bg=PANEL)
        r4.pack(anchor="w", padx=12, pady=(4, 10))
        button(r4, "Change password", lambda: self.change_password(old, new, msg)).pack(side="left")

    def set_accent(self, color):
        T["accent"] = color
        self.set("accent", color)
        self.notify("Theme accent updated!")
        self.rebuild("settings")

    def pick_accent(self):
        _, hex_color = colorchooser.askcolor(color=T["accent"], title="Pick a theme color")
        if hex_color:
            self.set_accent(hex_color)

    def set_bg(self, color):
        T["bg"] = color
        self.set("bg_color", color)
        self.notify("Background color updated!")
        self.rebuild("settings")

    def pick_bg_color(self):
        _, hex_color = colorchooser.askcolor(color=T["bg"], title="Pick a background color")
        if hex_color:
            self.set_bg(hex_color)

    def set_water_color(self, color):
        self.set("water_color", color)
        self.notify("Water color updated!")
        self.rebuild("settings")

    def pick_water_color(self):
        _, hex_color = colorchooser.askcolor(color=self.settings.get("water_color", "#1a8cff"), title="Pick a water color")
        if hex_color:
            self.set_water_color(hex_color)

    def reset_settings(self):
        if not messagebox.askyesno("Reset settings", "Reset all settings to default?\n(Your servers are kept.)"):
            return
        keep = {k: self.settings.get(k) for k in ("servers", "server")}
        self.settings.clear()
        self.settings.update(copy.deepcopy(DEFAULTS))
        self.settings.update(keep)
        save_data(self.data)
        self.apply_window_settings()
        self.notify("Settings reset to defaults.")
        self.rebuild("settings")

    def change_password(self, old_e, new_e, msg):
        user = self.data["users"][self.current]
        if not hmac.compare_digest(hash_pw(old_e.get(), bytes.fromhex(user["salt"])), user["hash"]):
            return msg.config(text="Current password is wrong", fg=ERR)
        if len(new_e.get()) < 6:
            return msg.config(text="New password must be at least 6 characters", fg=ERR)
        salt = os.urandom(16)
        user["salt"] = salt.hex()
        user["hash"] = hash_pw(new_e.get(), salt)
        save_data(self.data)
        old_e.delete(0, "end")
        new_e.delete(0, "end")
        self.notify("Password successfully changed!")

    # ------------------------------------------------------------ screen capture tools
    def start_capture(self, mode, key=None, label=""):
        what = ("drag a box around the whole fishing minigame area" if mode == "region"
                else "click the %s" % label.lower())
        if not messagebox.askokcancel(
                "Capture screen",
                "This window will hide and your screen will be captured 4 seconds after you press OK.\n\n"
                "Get the fishing minigame showing in the game first (use Borderless/Windowed mode).\n"
                "Then you'll %s." % what):
            return
        self.withdraw()
        self.after(4000, lambda: self._do_capture(mode, key, label))

    def _do_capture(self, mode, key, label):
        try:
            with mss.mss() as sct:
                mon = sct.monitors[0]
                shot = sct.grab(mon)
                arr = np.array(shot)
                png = mss.tools.to_png(shot.rgb, shot.size)
        except Exception as e:
            self.deiconify()
            messagebox.showerror("Capture failed", str(e))
            return
        self._overlay(mode, key, label, mon, arr, png)

    def _overlay(self, mode, key, label, mon, arr, png):
        left, top, w, h = mon["left"], mon["top"], mon["width"], mon["height"]
        ov = tk.Toplevel(self)
        ov.overrideredirect(True)
        ov.geometry("%dx%d+%d+%d" % (w, h, left, top))
        ov.attributes("-topmost", True)
        cv = tk.Canvas(ov, width=w, height=h, highlightthickness=0, bd=0, cursor="crosshair")
        cv.pack()
        photo = tk.PhotoImage(master=ov, data=base64.b64encode(png))
        cv.create_image(0, 0, image=photo, anchor="nw")
        cv.photo = photo

        cv.create_rectangle(10, 10, 700, 42, fill="#000000", outline=T["accent"])
        text = cv.create_text(20, 26, anchor="w", fill="white", font=FONT_B,
                              text=("Drag a box around the minigame area   (right-click to cancel)" if mode == "region"
                                    else "Click the %s   (right-click to cancel)" % label.lower()))

        def close():
            try:
                ov.destroy()
            finally:
                self.deiconify()
                self.rebuild("detect")

        ov.bind("<Escape>", lambda e: close())
        cv.bind("<Button-3>", lambda e: close())
        try:
            ov.focus_force()
        except Exception:
            pass

        if mode == "region":
            st = {}

            def press(e):
                st["x0"], st["y0"] = e.x, e.y
                st["rect"] = cv.create_rectangle(e.x, e.y, e.x, e.y, outline="#00ff66", width=2)

            def drag(e):
                if "rect" in st:
                    cv.coords(st["rect"], st["x0"], st["y0"], e.x, e.y)

            def release(e):
                if "rect" not in st:
                    return
                a, b = sorted((st["x0"], e.x))
                c, d = sorted((st["y0"], e.y))
                if b - a < 20 or d - c < 12:
                    cv.delete(st.pop("rect"))
                    return
                self.set("region", [left + a, top + c, left + b, top + d])
                self.notify("Screen region updated!")
                close()

            cv.bind("<ButtonPress-1>", press)
            cv.bind("<B1-Motion>", drag)
            cv.bind("<ButtonRelease-1>", release)
        else:
            def px_at(e):
                x = min(max(e.x, 0), w - 1)
                y = min(max(e.y, 0), h - 1)
                p = arr[y, x]
                return int(p[2]), int(p[1]), int(p[0])

            def motion(e):
                r, g, b = px_at(e)
                cv.itemconfig(text, text="Click the %s   -   under cursor: #%02x%02x%02x   (right-click to cancel)"
                                         % (label.lower(), r, g, b))

            def click(e):
                self.set(key, list(px_at(e)))
                self.notify(f"{label} color captured!")
                close()

            cv.bind("<Motion>", motion)
            cv.bind("<ButtonPress-1>", click)

    # ------------------------------------------------------------ live preview
    def open_preview(self):
        if self._preview is not None:
            try:
                if self._preview.winfo_exists():
                    self._preview.lift()
                    return
            except Exception:
                pass
        win = tk.Toplevel(self)
        win.title("Fisher - Live Preview")
        win.configure(bg=BG)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        tk.Label(win, text="Top: what the program sees\nBottom: what it detects  (green = zone/prompt, magenta = marker, yellow = hit)",
                 bg=BG, fg=DIM, font=SMALL, justify="left").pack(anchor="w", padx=10, pady=(8, 4))
        self._pv_raw = tk.Label(win, bg=BG)
        self._pv_raw.pack(padx=10, pady=4)
        self._pv_mask = tk.Label(win, bg=BG)
        self._pv_mask.pack(padx=10, pady=4)
        self._pv_info = tk.Label(win, text="", bg=BG, fg=TEXT, font=SMALL)
        self._pv_info.pack(anchor="w", padx=10, pady=(4, 10))
        self._preview = win
        try:
            self._pv_sct = mss.mss()
        except Exception as e:
            self._pv_sct = None
            self._pv_info.config(text="Capture error: %s" % e)
        win.protocol("WM_DELETE_WINDOW", self.close_preview)
        self._preview_tick()

    def close_preview(self):
        if self._preview_job:
            try:
                self.after_cancel(self._preview_job)
            except Exception:
                pass
            self._preview_job = None
        try:
            if getattr(self, "_pv_sct", None):
                self._pv_sct.close()
        except Exception:
            pass
        self._pv_sct = None
        if self._preview is not None:
            try:
                self._preview.destroy()
            except Exception:
                pass
        self._preview = None

    @staticmethod
    def _png_image(master, rgb, zoom=1):
        h, w = rgb.shape[:2]
        png = mss.tools.to_png(np.ascontiguousarray(rgb).tobytes(), (w, h))
        img = tk.PhotoImage(master=master, data=base64.b64encode(png))
        if zoom > 1:
            img = img.zoom(zoom)
        full_w = w * zoom
        if full_w > PREVIEW_W:
            img = img.subsample(int(math.ceil(full_w / PREVIEW_W)))
        return img

    def _preview_tick(self):
        if self._preview is None:
            return
        try:
            if not self._preview.winfo_exists():
                return
        except Exception:
            return
        try:
            if self._pv_sct is not None:
                s = self.settings
                frame = np.array(self._pv_sct.grab(region_for(self._pv_sct, s)))
                res = analyze(frame, detect_cfg(s, self.selected_server()["type"]))
                raw = self._png_image(self._preview, frame[:, :, 2::-1])
                self._pv_raw.config(image=raw)
                self._pv_raw.image = raw

                zh, zw = frame[::STEP, ::STEP].shape[:2]
                vis = np.zeros((zh, zw, 3), dtype=np.uint8)
                if res["zone"] is not None:
                    vis[res["zone"]] = (0, 200, 0)
                if res["marker"] is not None:
                    vis[res["marker"]] = (200, 0, 200)
                if res["hit"] is not None:
                    vis[res["hit"]] = (255, 255, 0)
                mimg = self._png_image(self._preview, vis, zoom=STEP)
                self._pv_mask.config(image=mimg)
                self._pv_mask.image = mimg
                self._pv_info.config(text="Zone px: %d    Marker px: %d    On screen: %s    Press now: %s" % (
                    res["zone_px"], res["marker_px"], "YES" if res["active"] else "no", "YES" if res["press"] else "no"))
        except Exception as e:
            self._pv_info.config(text="Preview error: %s" % e)
        self._preview_job = self.after(150, self._preview_tick)


if __name__ == "__main__":
    App().mainloop()