#!/usr/bin/env python3
"""praetor-hands: MCP server that gives Hermes real hands on Hyprland.

Why this exists: cua-driver (Hermes's default computer-use backend) can *see* on Hyprland
(screenshots, window trees) but cannot *act*: its Wayland input needs a RemoteDesktop portal
Hyprland lacks, and its foreground route wants a Hyprland plugin it does not ship. Hyprland
does advertise wlroots virtual input, so these tools use `wtype` (keyboard) and `ydotool`
(pointer) plus `hyprctl` (windows) and `grim` (capture). Every tool call goes through the
safety envelope in `praetor-hands` (driving badge, crimson border, Super+Escape panic).

Coordinates: all tools take Hyprland *logical* pixels (what `hyprctl clients` reports).
ydotool's absolute frame is the physical resolution divided by (2 * scale) on this setup;
the factor is measured at startup from `hyprctl monitors` and `hyprctl cursorpos`.
"""
from __future__ import annotations
import base64
import io
import json
import os
import shlex
import subprocess
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP

STATE = Path.home() / ".local/state/praetor"
HANDS = str(Path.home() / ".local/bin/praetor-hands")

mcp = FastMCP("praetor-hands", instructions=(
    "Desktop hands for this Hyprland laptop. Call hands_begin first (it shows the user a driving "
    "badge), take a screenshot to see, act with click/type/key/scroll using logical pixel "
    "coordinates from the screenshot, re-screenshot to verify, and call hands_end when done. "
    "Never type passwords. Stop immediately if hands_status reports 'stopped'."))


def _env() -> dict:
    env = dict(os.environ)
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    sig_dir = Path(env["XDG_RUNTIME_DIR"]) / "hypr"
    if "HYPRLAND_INSTANCE_SIGNATURE" not in env and sig_dir.exists():
        sigs = sorted(sig_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        if sigs:
            env["HYPRLAND_INSTANCE_SIGNATURE"] = sigs[0].name
    env.setdefault("WAYLAND_DISPLAY", "wayland-1")
    return env


def _run(*argv: str, timeout: float = 20) -> subprocess.CompletedProcess:
    return subprocess.run(list(argv), capture_output=True, text=True, timeout=timeout, env=_env())


def _monitor() -> dict:
    return json.loads(_run("hyprctl", "monitors", "-j").stdout)[0]


_scale_cache: dict = {}


def _pointer_scale() -> float:
    """Logical px -> ydotool absolute units. Measured once: move to a probe point, read cursorpos."""
    if "k" in _scale_cache:
        return _scale_cache["k"]
    try:
        _run("ydotool", "mousemove", "--absolute", "-x", "100", "-y", "100"); time.sleep(0.2)
        cx, cy = [int(v) for v in _run("hyprctl", "cursorpos").stdout.strip().split(",")]
        k = 100.0 / cx if cx > 0 else 1.0
    except Exception:
        k = 1.0
    _scale_cache["k"] = k
    return k


MAX_SESSION_S = float(os.environ.get("HANDS_MAX_SESSION_S", "900"))  # a forgotten session ends itself


def _driving() -> bool:
    f = STATE / "hands.driving"
    if not f.exists():
        return False
    if time.time() - f.stat().st_mtime > MAX_SESSION_S:
        _run(HANDS, "stop")  # stale session: restore the desktop and refuse further actions
        return False
    return True


def _guard() -> dict | None:
    if not _driving():
        return {"ok": False, "error": "not driving: call hands_begin first (or the user pressed Super+Escape)"}
    return None


def _move(x: float, y: float) -> None:
    k = _pointer_scale()
    _run("ydotool", "mousemove", "--absolute", "-x", str(int(x * k)), "-y", str(int(y * k)))
    time.sleep(0.12)


@mcp.tool()
def hands_begin(reason: str = "") -> dict:
    """Start a driving session: shows the user a red border and a PRAETOR DRIVING badge. Say why in `reason`."""
    _run(HANDS, "start")
    if reason:
        _run(HANDS, "announce", f"Taking the desktop: {reason}")
    _pointer_scale()
    return {"ok": True, "driving": True}


@mcp.tool()
def hands_end(summary: str = "") -> dict:
    """End the driving session and restore the desktop look. Optionally say what was done."""
    _run(HANDS, "stop")
    if summary:
        _run(HANDS, "announce", summary)
    return {"ok": True, "driving": False}


@mcp.tool()
def hands_status() -> dict:
    """'driving' or 'stopped'. If stopped mid-task the user interrupted you: do not continue."""
    return {"status": "driving" if _driving() else "stopped"}


@mcp.tool()
def screenshot(max_width: int = 1280) -> dict:
    """Capture the whole screen. Returns PNG (base64) scaled to max_width, the logical screen size,
    and px_to_logical: multiply screenshot pixel coordinates by it to get logical coordinates."""
    mon = _monitor()
    lw, lh = int(mon["width"] / mon["scale"]), int(mon["height"] / mon["scale"])
    raw = subprocess.run(["grim", "-t", "png", "-"], capture_output=True, timeout=20, env=_env()).stdout
    png, factor = raw, lw / int(mon["width"])
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(raw))
        if im.width > max_width:
            im = im.resize((max_width, int(im.height * max_width / im.width)))
            buf = io.BytesIO(); im.save(buf, "PNG"); png = buf.getvalue()
        factor = lw / im.width
    except Exception:
        pass
    return {"png_b64": base64.b64encode(png).decode(), "logical_width": lw, "logical_height": lh,
            "px_to_logical": factor, "driving": _driving()}


@mcp.tool()
def list_windows() -> list[dict]:
    """Open windows with pid, class, title, workspace, position and size in logical pixels."""
    out = json.loads(_run("hyprctl", "clients", "-j").stdout)
    return [{"pid": w["pid"], "class": w["class"], "title": w["title"], "workspace": w["workspace"]["name"],
             "x": w["at"][0], "y": w["at"][1], "w": w["size"][0], "h": w["size"][1],
             "focused": w.get("focusHistoryID") == 0}
            for w in out if w.get("mapped")]


@mcp.tool()
def focus_window(pid: int | None = None, title_contains: str | None = None) -> dict:
    """Focus (and raise) a window by pid or by a substring of its title."""
    if (g := _guard()):
        return g
    if pid is None and title_contains:
        for w in list_windows():
            if title_contains.lower() in w["title"].lower():
                pid = w["pid"]; break
    if pid is None:
        return {"ok": False, "error": "no matching window"}
    r = _run("hyprctl", "dispatch", "focuswindow", f"pid:{pid}")
    # Hyprland's keyboard focus for virtual-input clients follows the pointer, so also park the
    # pointer inside the window and click once on its title area, the way a person would.
    win = next((w for w in list_windows() if w["pid"] == pid), None)
    if win:
        # Park the pointer in the window body (not the header bar: clicking there opens app menus).
        _move(win["x"] + win["w"] // 2, win["y"] + win["h"] // 2)
        time.sleep(0.15)
        try:
            if json.loads(_run("hyprctl", "activewindow", "-j").stdout).get("pid") != pid:
                _run("ydotool", "click", "0xC0")  # only click if hovering did not grant focus
        except Exception:
            pass
    for _ in range(20):
        try:
            if json.loads(_run("hyprctl", "activewindow", "-j").stdout).get("pid") == pid:
                break
        except Exception:
            pass
        time.sleep(0.05)
    time.sleep(0.2)
    active = json.loads(_run("hyprctl", "activewindow", "-j").stdout or "{}").get("pid")
    return {"ok": active == pid, "pid": pid, "active_pid": active, "detail": r.stdout.strip()}


@mcp.tool()
def launch(command: str) -> dict:
    """Launch a desktop app or URL, e.g. 'firefox https://archlinux.org' or 'nautilus'."""
    if (g := _guard()):
        return g
    subprocess.Popen(["uwsm-app", "--"] + shlex.split(command), stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, env=_env())
    time.sleep(1.5)
    return {"ok": True, "launched": command}


@mcp.tool()
def move_mouse(x: int, y: int) -> dict:
    """Move the pointer to logical coordinates."""
    if (g := _guard()):
        return g
    _move(x, y)
    return {"ok": True, "cursor": _run("hyprctl", "cursorpos").stdout.strip()}


@mcp.tool()
def click(x: int, y: int, button: str = "left", count: int = 1) -> dict:
    """Click at logical coordinates. button: left|right|middle. count=2 for double-click."""
    if (g := _guard()):
        return g
    code = {"left": "0xC0", "right": "0xC1", "middle": "0xC2"}.get(button, "0xC0")
    _move(x, y)
    for _ in range(max(1, min(count, 3))):
        _run("ydotool", "click", code); time.sleep(0.08)
    return {"ok": True, "at": [x, y], "button": button, "count": count}


@mcp.tool()
def drag(from_x: int, from_y: int, to_x: int, to_y: int) -> dict:
    """Press-drag-release with the left button between two logical points."""
    if (g := _guard()):
        return g
    _move(from_x, from_y); _run("ydotool", "click", "0x40"); time.sleep(0.1)   # press
    steps = 12
    for i in range(1, steps + 1):
        _move(from_x + (to_x - from_x) * i / steps, from_y + (to_y - from_y) * i / steps)
    _run("ydotool", "click", "0x80")                                            # release
    return {"ok": True}


@mcp.tool()
def scroll(direction: str = "down", amount: int = 3, x: int | None = None, y: int | None = None) -> dict:
    """Scroll up/down/left/right by `amount` notches, optionally at a position first."""
    if (g := _guard()):
        return g
    if x is not None and y is not None:
        _move(x, y)
    dx = {"left": -amount, "right": amount}.get(direction, 0)
    dy = {"up": amount, "down": -amount}.get(direction, 0)
    _run("ydotool", "mousemove", "--wheel", "-x", str(dx), "-y", str(dy))
    return {"ok": True}


@mcp.tool()
def type_text(text: str, delay_ms: int = 12) -> dict:
    """Type text into the focused window (virtual keyboard; handles Unicode). Never type secrets."""
    if (g := _guard()):
        return g
    if not text:
        return {"ok": False, "error": "empty text"}
    if text.startswith("-"):  # wtype has no `--`; a leading dash would be parsed as an option
        text = "​" + text  # zero-width space keeps the argument literal
    active = json.loads(_run("hyprctl", "activewindow", "-j").stdout or "{}")
    r = _run("wtype", "-d", str(delay_ms), text, timeout=120)
    return {"ok": r.returncode == 0, "chars": len(text), "typed_into": active.get("title", ""),
            "detail": r.stderr.strip()[:200]}


@mcp.tool()
def key(combo: str) -> dict:
    """Press a key or chord: 'Return', 'Escape', 'Tab', 'ctrl+l', 'super+2', 'alt+F4', 'ctrl+shift+t'."""
    if (g := _guard()):
        return g
    parts = [p.strip() for p in combo.replace(" ", "").split("+") if p.strip()]
    mods, main = parts[:-1], parts[-1]
    names = {"ctrl": "ctrl", "control": "ctrl", "alt": "alt", "shift": "shift",
             "super": "logo", "win": "logo", "logo": "logo"}
    argv = ["wtype"]
    for m in mods:
        argv += ["-M", names.get(m.lower(), m)]
    argv += ["-k", main]
    for m in reversed(mods):
        argv += ["-m", names.get(m.lower(), m)]
    r = _run(*argv)
    return {"ok": r.returncode == 0, "combo": combo, "detail": r.stderr.strip()[:200]}


@mcp.tool()
def wait(seconds: float = 1.0) -> dict:
    """Wait for the UI to settle (max 10 s)."""
    time.sleep(min(max(seconds, 0), 10))
    return {"ok": True}


if __name__ == "__main__":
    mcp.run()
