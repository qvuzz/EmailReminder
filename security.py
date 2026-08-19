# -*- coding: utf-8 -*-
"""
Module bảo mật và mã hóa thông tin tài khoản Email Reminder
Sử dụng Windows DPAPI (Data Protection API) kết hợp khóa định danh máy
đảm bảo mật khẩu lưu trong config.json không thể bị đọc trộm ở dạng văn bản thô.
"""

import os
import sys
import base64
import hashlib
import platform

PREFIX = "ENC:v1:"

def _get_machine_key():
    """Tạo khóa dẫn xuất từ thông tin máy tính để dự phòng mã hóa"""
    unique_parts = [
        platform.node(),
        platform.machine(),
        platform.processor(),
        os.environ.get("COMPUTERNAME", "REMINDER_MACHINE"),
        os.environ.get("USERNAME", "USER_KEY")
    ]
    raw_str = "@#VNPT_SECURE_SALT_2026!#" + "::".join(unique_parts)
    return hashlib.sha256(raw_str.encode("utf-8")).digest()

def _win_dpapi_encrypt(data_bytes: bytes) -> bytes:
    """Mã hóa qua Windows DPAPI (CryptProtectData)"""
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_byte))
        ]

    pDataIn = DATA_BLOB()
    pDataIn.cbData = len(data_bytes)
    pDataIn.pbData = ctypes.cast(ctypes.create_string_buffer(data_bytes, len(data_bytes)), ctypes.POINTER(ctypes.c_byte))

    pDataOut = DATA_BLOB()

    CryptProtectData = ctypes.windll.crypt32.CryptProtectData
    CryptProtectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),
        wintypes.LPCWSTR,
        ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(DATA_BLOB)
    ]
    CryptProtectData.restype = wintypes.BOOL

    if CryptProtectData(ctypes.byref(pDataIn), "EmailReminderSecret", None, None, None, 0, ctypes.byref(pDataOut)):
        out_len = pDataOut.cbData
        out_buf = (ctypes.c_byte * out_len).from_address(ctypes.addressof(pDataOut.pbData.contents))
        out_bytes = bytes(out_buf)
        ctypes.windll.kernel32.LocalFree(pDataOut.pbData)
        return out_bytes
    else:
        raise ctypes.WinError()

def _win_dpapi_decrypt(cipher_bytes: bytes) -> bytes:
    """Giải mã qua Windows DPAPI (CryptUnprotectData)"""
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_byte))
        ]

    pDataIn = DATA_BLOB()
    pDataIn.cbData = len(cipher_bytes)
    pDataIn.pbData = ctypes.cast(ctypes.create_string_buffer(cipher_bytes, len(cipher_bytes)), ctypes.POINTER(ctypes.c_byte))

    pDataOut = DATA_BLOB()

    CryptUnprotectData = ctypes.windll.crypt32.CryptUnprotectData
    CryptUnprotectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(DATA_BLOB)
    ]
    CryptUnprotectData.restype = wintypes.BOOL

    if CryptUnprotectData(ctypes.byref(pDataIn), None, None, None, None, 0, ctypes.byref(pDataOut)):
        out_len = pDataOut.cbData
        out_buf = (ctypes.c_byte * out_len).from_address(ctypes.addressof(pDataOut.pbData.contents))
        out_bytes = bytes(out_buf)
        ctypes.windll.kernel32.LocalFree(pDataOut.pbData)
        return out_bytes
    else:
        raise ctypes.WinError()

def _xor_stream_crypt(data_bytes: bytes, key_bytes: bytes) -> bytes:
    """Mã hóa / giải mã luồng XOR kết hợp SHA256 PRNG dự phòng"""
    res = bytearray(len(data_bytes))
    cur_hash = key_bytes
    for i in range(0, len(data_bytes), 32):
        cur_hash = hashlib.sha256(cur_hash + key_bytes + str(i).encode()).digest()
        chunk_len = min(32, len(data_bytes) - i)
        for j in range(chunk_len):
            res[i + j] = data_bytes[i + j] ^ cur_hash[j]
    return bytes(res)

def is_encrypted(text: str) -> bool:
    """Kiểm tra xem chuỗi đã được mã hóa hay chưa"""
    return isinstance(text, str) and text.startswith(PREFIX)

def encrypt_password(plain_text: str) -> str:
    """
    Mã hóa mật khẩu sang chuỗi an toàn định dạng 'ENC:v1:...'
    Nếu đã là chuỗi mã hóa thì giữ nguyên.
    """
    if not plain_text:
        return ""
    if is_encrypted(plain_text):
        return plain_text

    data_bytes = plain_text.encode("utf-8")

    # Ưu tiên mã hóa qua Windows DPAPI
    if sys.platform == "win32":
        try:
            cipher_bytes = _win_dpapi_encrypt(data_bytes)
            b64 = base64.b64encode(cipher_bytes).decode("ascii")
            return f"{PREFIX}dpapi:{b64}"
        except Exception:
            pass

    # Dự phòng mã hóa theo khóa định danh máy
    key = _get_machine_key()
    cipher_bytes = _xor_stream_crypt(data_bytes, key)
    b64 = base64.b64encode(cipher_bytes).decode("ascii")
    return f"{PREFIX}std:{b64}"

def decrypt_password(cipher_text: str) -> str:
    """
    Giải mã chuỗi mật khẩu 'ENC:v1:...' trở lại dạng văn bản gốc.
    Nếu là mật khẩu dạng thô (chưa mã hóa cũ), trả về nguyên vẹn để tương thích ngược.
    """
    if not cipher_text:
        return ""
    if not is_encrypted(cipher_text):
        return cipher_text

    raw_payload = cipher_text[len(PREFIX):]

    # Giải mã DPAPI
    if raw_payload.startswith("dpapi:") and sys.platform == "win32":
        b64_part = raw_payload[len("dpapi:"):]
        try:
            cipher_bytes = base64.b64decode(b64_part.encode("ascii"))
            plain_bytes = _win_dpapi_decrypt(cipher_bytes)
            return plain_bytes.decode("utf-8")
        except Exception:
            pass

    # Giải mã Standard Machine Key
    if raw_payload.startswith("std:"):
        b64_part = raw_payload[len("std:"):]
        try:
            cipher_bytes = base64.b64decode(b64_part.encode("ascii"))
            key = _get_machine_key()
            plain_bytes = _xor_stream_crypt(cipher_bytes, key)
            return plain_bytes.decode("utf-8")
        except Exception:
            pass

    # Thử giải mã generic nếu không có tiền tố con
    try:
        cipher_bytes = base64.b64decode(raw_payload.encode("ascii"))
        if sys.platform == "win32":
            try:
                return _win_dpapi_decrypt(cipher_bytes).decode("utf-8")
            except Exception:
                pass
        key = _get_machine_key()
        return _xor_stream_crypt(cipher_bytes, key).decode("utf-8")
    except Exception:
        # Nếu giải mã thất bại hoàn toàn, trả về chuỗi gốc
        return cipher_text
