"""Windows-only crypto with no third-party packages: DPAPI (crypt32.dll) and AES-256-GCM (bcrypt.dll).

DPAPI protects wauncher's own token store (CurrentUser scope, so only this Windows account can read it).
AES-GCM is what the official EVE launcher (a Chromium/Electron app) uses for its state.json; the key for
that lives DPAPI-protected in its "Local State" file.
"""
from __future__ import annotations

import ctypes
import struct

CRYPTPROTECT_UI_FORBIDDEN = 0x01


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.c_void_p)]


def _blob_to_bytes(blob: _DATA_BLOB) -> bytes:
    out = ctypes.string_at(blob.pbData, blob.cbData)
    kernel32 = ctypes.windll.kernel32
    kernel32.LocalFree.restype = ctypes.c_void_p
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree(blob.pbData)
    return out


def dpapi_protect(data: bytes, description: str = "wauncher") -> bytes:
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.c_void_p))
    blob_out = _DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptProtectData(ctypes.byref(blob_in), description, None, None, None,
                                                CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out))
    if not ok:
        raise ctypes.WinError()
    return _blob_to_bytes(blob_out)


def dpapi_unprotect(data: bytes) -> bytes:
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.c_void_p))
    blob_out = _DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None,
                                                  CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out))
    if not ok:
        raise ctypes.WinError()
    return _blob_to_bytes(blob_out)


# ------------------------------------------------------------------ AES-GCM (BCrypt)
class _BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong), ("dwInfoVersion", ctypes.c_ulong),
        ("pbNonce", ctypes.c_void_p), ("cbNonce", ctypes.c_ulong),
        ("pbAuthData", ctypes.c_void_p), ("cbAuthData", ctypes.c_ulong),
        ("pbTag", ctypes.c_void_p), ("cbTag", ctypes.c_ulong),
        ("pbMacContext", ctypes.c_void_p), ("cbMacContext", ctypes.c_ulong),
        ("cbAAD", ctypes.c_ulong), ("cbData", ctypes.c_ulonglong), ("dwFlags", ctypes.c_ulong),
    ]


def _status(name: str, status: int) -> None:
    if status != 0:
        raise OSError(f"{name}: 0x{status & 0xFFFFFFFF:08X}")


def _aes_gcm(key: bytes, nonce: bytes, data: bytes, tag: bytes | None) -> tuple[bytes, bytes]:
    """Encrypt (tag=None -> returns (ciphertext, tag)) or decrypt (tag given -> returns (plaintext, tag))."""
    bcrypt = ctypes.windll.bcrypt
    h_alg, h_key = ctypes.c_void_p(), ctypes.c_void_p()
    _status("BCryptOpenAlgorithmProvider", bcrypt.BCryptOpenAlgorithmProvider(ctypes.byref(h_alg), "AES", None, 0))
    try:
        mode = "ChainingModeGCM\0".encode("utf-16-le")
        _status("BCryptSetProperty", bcrypt.BCryptSetProperty(h_alg, "ChainingMode", mode, len(mode), 0))
        obj_len_buf = (ctypes.c_byte * 4)()
        cb = ctypes.c_ulong()
        bcrypt.BCryptGetProperty(h_alg, "ObjectLength", obj_len_buf, 4, ctypes.byref(cb), 0)
        obj_len = struct.unpack_from("<I", bytes(obj_len_buf))[0]
        key_object = (ctypes.c_byte * obj_len)()
        key_buf = ctypes.create_string_buffer(key, len(key))
        _status("BCryptGenerateSymmetricKey", bcrypt.BCryptGenerateSymmetricKey(
            h_alg, ctypes.byref(h_key), key_object, obj_len, key_buf, len(key), 0))
        try:
            nonce_buf = ctypes.create_string_buffer(nonce, len(nonce))
            tag_buf = ctypes.create_string_buffer(tag, 16) if tag else ctypes.create_string_buffer(16)
            info = _BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO()
            info.cbSize = ctypes.sizeof(info)
            info.dwInfoVersion = 1
            info.pbNonce, info.cbNonce = ctypes.cast(nonce_buf, ctypes.c_void_p), len(nonce)
            info.pbTag, info.cbTag = ctypes.cast(tag_buf, ctypes.c_void_p), 16
            in_buf = ctypes.create_string_buffer(data, len(data))
            out_buf = ctypes.create_string_buffer(len(data))
            n = ctypes.c_ulong()
            fn = bcrypt.BCryptDecrypt if tag else bcrypt.BCryptEncrypt
            _status("BCryptDecrypt" if tag else "BCryptEncrypt", fn(
                h_key, in_buf, len(data), ctypes.byref(info), None, 0, out_buf, len(data), ctypes.byref(n), 0))
            return out_buf.raw[:n.value], tag_buf.raw[:16]
        finally:
            bcrypt.BCryptDestroyKey(h_key)
    finally:
        bcrypt.BCryptCloseAlgorithmProvider(h_alg, 0)


def aes_gcm_encrypt(key: bytes, nonce: bytes, plaintext: bytes) -> tuple[bytes, bytes]:
    """Returns (ciphertext, 16-byte tag)."""
    return _aes_gcm(key, nonce, plaintext, None)


def aes_gcm_decrypt(key: bytes, nonce: bytes, ciphertext: bytes, tag: bytes) -> bytes:
    """Raises OSError (STATUS_AUTH_TAG_MISMATCH 0xC000A002) when the tag does not verify."""
    return _aes_gcm(key, nonce, ciphertext, tag)[0]
