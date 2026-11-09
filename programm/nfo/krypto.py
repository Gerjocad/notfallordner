"""Verschlüsselung.

* Kundendaten aus dem Formular: Der Browser des Kunden erzeugt einen zufälligen AES-256-GCM-Schlüssel,
  verschlüsselt damit die Daten und verschlüsselt den AES-Schlüssel mit dem öffentlichen RSA-Schlüssel
  (RSA-OAEP, SHA-256) dieses Programms. Nur der private Schlüssel auf dem PC des Beraters kann öffnen.
* Gespeicherte Daten auf dem PC: unter Windows mit DPAPI an das Windows-Konto gebunden.
* Sicherungsdatei: mit Passwort verschlüsselt (scrypt + AES-256-GCM), auf jedem PC wiederherstellbar.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
unb64 = base64.b64decode


# ---------- Schlüsselpaar für den Briefkasten ----------
def neues_schluesselpaar() -> tuple[bytes, bytes]:
    """(privater Schlüssel PEM, öffentlicher Schlüssel SPKI-DER)."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    priv = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    pub = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return priv, pub


def fingerabdruck(pub_der: bytes) -> str:
    return hashlib.sha256(pub_der).hexdigest()[:16]


def oeffnen(priv_pem: bytes, umschlag: dict) -> dict:
    """Verschlüsselte Einsendung aus dem Kundenformular entschlüsseln."""
    if umschlag.get("v") != 1:
        raise ValueError("Unbekanntes Format")
    key = serialization.load_pem_private_key(priv_pem, password=None)
    aes = key.decrypt(unb64(umschlag["key"]), padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    klar = AESGCM(aes).decrypt(unb64(umschlag["iv"]), unb64(umschlag["data"]), None)
    return json.loads(klar.decode("utf-8"))


def verschliessen_fuer_test(pub_der: bytes, daten: dict) -> dict:
    """Gegenstück zum Browser (nur für Tests)."""
    pub = serialization.load_der_public_key(pub_der)
    aes, iv = AESGCM.generate_key(256), os.urandom(12)
    enc = AESGCM(aes).encrypt(iv, json.dumps(daten).encode(), None)
    k = pub.encrypt(aes, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    return {"v": 1, "kid": fingerabdruck(pub_der), "key": b64(k), "iv": b64(iv), "data": b64(enc)}


# ---------- Schutz der lokalen Daten (Windows DPAPI) ----------
def _dpapi(data: bytes, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    buf = ctypes.create_string_buffer(data, len(data))
    inp, out = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), BLOB()
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(inp), None, None, None, None, 0x01, ctypes.byref(out))  # 0x01 = keine Rückfrage
    if not ok:
        raise OSError("Windows-Datenschutz (DPAPI) fehlgeschlagen")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def schuetzen(data: bytes) -> bytes:
    if sys.platform == "win32":
        return b"DPAPI1" + _dpapi(data, True)
    return b"PLAIN1" + data  # nur zum Entwickeln/Testen außerhalb von Windows


def entschuetzen(data: bytes) -> bytes:
    if data.startswith(b"DPAPI1"):
        return _dpapi(data[6:], False)
    if data.startswith(b"PLAIN1"):
        return data[6:]
    raise ValueError("Unbekanntes Datenformat")


# ---------- Sicherungsdatei mit Passwort ----------
def _kdf(passwort: str, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passwort.encode("utf-8"))


def mit_passwort(data: bytes, passwort: str) -> bytes:
    salt, iv = os.urandom(16), os.urandom(12)
    return b"NFOBAK1" + salt + iv + AESGCM(_kdf(passwort, salt)).encrypt(iv, data, None)


def ohne_passwort(data: bytes, passwort: str) -> bytes:
    if not data.startswith(b"NFOBAK1"):
        raise ValueError("Keine Notfallordner-Sicherung")
    salt, iv, enc = data[7:23], data[23:35], data[35:]
    return AESGCM(_kdf(passwort, salt)).decrypt(iv, enc, None)
