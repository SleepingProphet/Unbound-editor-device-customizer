# platform_layer/windows.py — Windows-specific implementations

import os
import glob as _glob

VOL_STEP    = 0.02   # 2 % per jog tick
BRIGHT_STEP = 5      # 5 % per jog tick

# ---------------------------------------------------------------------------
# Volume — master uses Windows media keys so the native OSD appears
# ---------------------------------------------------------------------------

VK_VOLUME_UP   = 0xAF
VK_VOLUME_DOWN = 0xAE


def adjust_master_volume(delta: float):
    """Raise or lower master volume one Windows step, showing the native OSD."""
    try:
        import win32api, win32con
        vk = VK_VOLUME_UP if delta > 0 else VK_VOLUME_DOWN
        win32api.keybd_event(vk, 0, 0, 0)
        win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
    except Exception as e:
        print(f'[volume] {e}')


def adjust_app_volume(app_name: str, delta: float):
    """Raise or lower volume for a running app (partial name, case-insensitive)."""
    try:
        from pycaw.pycaw import AudioUtilities
        name_lower = app_name.lower().replace('.exe', '')
        matched = False
        for session in AudioUtilities.GetAllSessions():
            if session.Process:
                proc = session.Process.name().lower().replace('.exe', '')
                if name_lower in proc:
                    vol = session.SimpleAudioVolume
                    vol.SetMasterVolume(max(0.0, min(1.0, vol.GetMasterVolume() + delta)), None)
                    matched = True
        if not matched:
            print(f'[app_volume] No session found matching {app_name!r}')
    except Exception as e:
        print(f'[app_volume] {e}')


def list_audio_apps() -> list[str]:
    """Return names of apps currently producing audio."""
    try:
        from pycaw.pycaw import AudioUtilities
        names = []
        for session in AudioUtilities.GetAllSessions():
            if session.Process:
                names.append(session.Process.name().replace('.exe', ''))
        return names
    except Exception as e:
        print(f'[app_volume] {e}')
        return []


# ---------------------------------------------------------------------------
# Brightness
# ---------------------------------------------------------------------------

def adjust_brightness(delta: int):
    """Raise or lower screen brightness by delta percent."""
    try:
        import screen_brightness_control as sbc
        current = sbc.get_brightness(display=0)
        if isinstance(current, list):
            current = current[0]
        sbc.set_brightness(max(0, min(100, current + delta)), display=0)
    except Exception as e:
        print(f'[brightness] {e}')


# ---------------------------------------------------------------------------
# Window management
# ---------------------------------------------------------------------------

def switch_to(app_name: str) -> bool:
    """Bring a window matching app_name to the foreground. Returns True on success."""
    import win32gui, win32con
    app_lower = app_name.lower()
    result = None

    def callback(hwnd, _):
        nonlocal result
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd).lower()
            if app_lower in title:
                result = hwnd
        return True

    win32gui.EnumWindows(callback, None)
    if not result:
        return False
    if win32gui.IsIconic(result):
        win32gui.ShowWindow(result, win32con.SW_RESTORE)
    win32gui.SetForegroundWindow(result)
    return True


def list_windows() -> list[str]:
    """Return titles of all visible top-level windows."""
    import win32gui
    titles = []

    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title:
                titles.append(title)
        return True

    win32gui.EnumWindows(callback, None)
    return sorted(titles)


# ---------------------------------------------------------------------------
# Key hold / release (win32api so GetKeyState() is updated system-wide)
# ---------------------------------------------------------------------------

VK_CODES = {
    "ctrl":       0x11,  "shift":     0x10,  "alt":       0xA4,
    "win":        0x5B,  "enter":     0x0D,  "esc":       0x1B,
    "space":      0x20,  "tab":       0x09,  "backspace": 0x08,
    "delete":     0x2E,  "home":      0x24,  "end":       0x23,
    "page_up":    0x21,  "page_down": 0x22,
    "up":         0x26,  "down":      0x28,  "left":      0x25,  "right": 0x27,
    "f1":  0x70, "f2":  0x71, "f3":  0x72, "f4":  0x73,
    "f5":  0x74, "f6":  0x75, "f7":  0x76, "f8":  0x77,
    "f9":  0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}


def _parse_vk_codes(hotkey_str: str) -> list[int]:
    codes = []
    for part in hotkey_str.lower().split("+"):
        part = part.strip()
        if part in VK_CODES:
            codes.append(VK_CODES[part])
        elif len(part) == 1:
            codes.append(ord(part.upper()))
    return codes


def press_keys(hotkey_str: str):
    """Hold keys down via win32api so modifier-aware apps see them as held."""
    import win32api
    vks = _parse_vk_codes(hotkey_str)
    print(f'[hold] press  {hotkey_str!r}  vks={vks}')
    for vk in vks:
        win32api.keybd_event(vk, 0, 0, 0)


def release_keys(hotkey_str: str):
    """Release held keys via win32api."""
    import win32api, win32con
    vks = _parse_vk_codes(hotkey_str)
    print(f'[hold] release {hotkey_str!r}  vks={vks}')
    for vk in reversed(vks):
        win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)


# ---------------------------------------------------------------------------
# App picker — Start Menu shortcuts
# ---------------------------------------------------------------------------

def collect_installable_apps() -> list[tuple[str, str]]:
    """Return [(display_name, lnk_path), ...] from user + system Start Menu."""
    folders = [
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
        os.path.expandvars(r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs"),
    ]
    apps = {}
    for folder in folders:
        for lnk in _glob.glob(os.path.join(folder, "**", "*.lnk"), recursive=True):
            name = os.path.splitext(os.path.basename(lnk))[0]
            if name not in apps:   # user folder wins over system folder
                apps[name] = lnk
    return sorted(apps.items(), key=lambda x: x[0].lower())


# ---------------------------------------------------------------------------
# App launch
# ---------------------------------------------------------------------------

def launch_app(path: str):
    """Launch an app by path, .lnk shortcut, or URI via Windows Shell."""
    os.startfile(path)


# ---------------------------------------------------------------------------
# Foreground app detection (ctypes only; polled by platform_layer.focus.FocusWatcher)
# ---------------------------------------------------------------------------

import ctypes
from ctypes import wintypes

from .focus import ForegroundApp

_user32   = ctypes.WinDLL('user32',   use_last_error=True)
_kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def _process_name(pid: int) -> str:
    """Executable name for pid ('' if it cannot be queried, e.g. protected/elevated)."""
    h = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ''
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        if _kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value)
        return ''
    finally:
        _kernel32.CloseHandle(h)


def get_foreground_app():
    """ForegroundApp for the window in front, or None if there is none right now."""
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD(0)
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return None
    name = _process_name(pid.value)
    return ForegroundApp(ids=(name,) if name else (), pid=pid.value)


def list_running_apps() -> list[tuple[str, str]]:
    """[(display_name, match_id), ...] for processes that own a visible titled window."""
    names: set[str] = set()

    def cb(hwnd, _):
        try:
            if _user32.IsWindowVisible(hwnd) and _user32.GetWindowTextLengthW(hwnd) > 0:
                pid = wintypes.DWORD(0)
                _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                name = _process_name(pid.value) if pid.value else ''
                if name:
                    names.add(name)
        except Exception:
            pass
        return True

    _user32.EnumWindows(_EnumWindowsProc(cb), 0)
    return [(n, n) for n in sorted(names, key=str.lower)]
