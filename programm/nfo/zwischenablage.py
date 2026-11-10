"""Zwischenablage lesen (Windows). Erkennt jedes neue Strg+C über die Sequenznummer von Windows."""

from __future__ import annotations

import sys
import time

CF_UNICODETEXT = 13


class Zwischenablage:
    """Unter Windows echt, sonst nicht verfügbar (dann zeigt der Assistent ein Einfügefeld)."""

    def __init__(self):
        self.ok = sys.platform == "win32"
        if self.ok:
            import ctypes
            from ctypes import wintypes
            self._c = ctypes
            u, k = ctypes.windll.user32, ctypes.windll.kernel32
            u.GetClipboardSequenceNumber.restype = wintypes.DWORD
            u.OpenClipboard.argtypes = [wintypes.HWND]
            u.OpenClipboard.restype = wintypes.BOOL
            u.GetClipboardData.argtypes = [wintypes.UINT]
            u.GetClipboardData.restype = ctypes.c_void_p
            u.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
            k.GlobalLock.argtypes = [ctypes.c_void_p]
            k.GlobalLock.restype = ctypes.c_void_p
            k.GlobalUnlock.argtypes = [ctypes.c_void_p]
            self._u, self._k = u, k

    def sequenz(self) -> int:
        return int(self._u.GetClipboardSequenceNumber()) if self.ok else 0

    def text(self) -> str | None:
        if not self.ok:
            return None
        for _ in range(10):  # die Zwischenablage kann kurz von einem anderen Programm belegt sein
            if self._u.OpenClipboard(None):
                break
            time.sleep(0.05)
        else:
            return None
        try:
            if not self._u.IsClipboardFormatAvailable(CF_UNICODETEXT):
                return None
            h = self._u.GetClipboardData(CF_UNICODETEXT)
            if not h:
                return None
            p = self._k.GlobalLock(h)
            if not p:
                return None
            try:
                return self._c.wstring_at(p)
            finally:
                self._k.GlobalUnlock(h)
        finally:
            self._u.CloseClipboard()
