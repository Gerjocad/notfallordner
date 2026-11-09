"""Word-Datei in PDF umwandeln: bevorzugt mit Microsoft Word, sonst mit LibreOffice."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


class PdfFehler(Exception):
    pass


def _mit_word(docx: Path, pdf: Path) -> None:
    import pythoncom  # pywin32
    import win32com.client

    pythoncom.CoInitialize()
    word = None
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        doc = word.Documents.Open(str(docx), ReadOnly=True, AddToRecentFiles=False, ConfirmConversions=False)
        try:
            doc.SaveAs2(str(pdf), FileFormat=17)  # 17 = wdFormatPDF
        finally:
            doc.Close(SaveChanges=0)
    finally:
        if word is not None:
            word.Quit()
        pythoncom.CoUninitialize()


def _libreoffice() -> str | None:
    for name in ("soffice", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    if sys.platform == "win32":
        for base in (Path(r"C:\Program Files\LibreOffice\program"), Path(r"C:\Program Files (x86)\LibreOffice\program")):
            if (base / "soffice.exe").exists():
                return str(base / "soffice.exe")
    return None


def _mit_libreoffice(docx: Path, pdf: Path) -> None:
    exe = _libreoffice()
    if not exe:
        raise PdfFehler("Weder Microsoft Word noch LibreOffice gefunden")
    r = subprocess.run([exe, "--headless", "--convert-to", "pdf", "--outdir", str(pdf.parent), str(docx)],
                       capture_output=True, timeout=600)
    erzeugt = pdf.parent / (docx.stem + ".pdf")
    if r.returncode != 0 or not erzeugt.exists():
        raise PdfFehler("LibreOffice konnte die PDF nicht erstellen")
    if erzeugt != pdf:
        erzeugt.replace(pdf)


def word_zu_pdf(docx: Path, pdf: Path) -> str:
    """Erzeugt `pdf`. Gibt zurück, womit umgewandelt wurde."""
    docx, pdf = Path(docx).resolve(), Path(pdf).resolve()
    if sys.platform == "win32":
        try:
            _mit_word(docx, pdf)
            return "Microsoft Word"
        except Exception:  # noqa: BLE001 - Word fehlt oder Fehler: LibreOffice versuchen
            if not _libreoffice():
                raise PdfFehler("PDF konnte nicht erstellt werden: Microsoft Word ist nicht installiert oder meldet einen Fehler")
    _mit_libreoffice(docx, pdf)
    return "LibreOffice"


def verfuegbar() -> str:
    if sys.platform == "win32":
        try:
            import winreg
            winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "Word.Application").Close()
            return "Microsoft Word"
        except OSError:
            pass
    return "LibreOffice" if _libreoffice() else ""
