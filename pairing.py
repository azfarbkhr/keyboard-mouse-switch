"""Store remembered pairing details using Windows user-bound data protection."""
import ctypes
import ctypes.wintypes as wintypes
import json
import os
from pathlib import Path


class DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def pairing_path():
    return Path(os.environ["LOCALAPPDATA"]) / "KeyboardMouseSwitch" / "pairing.bin"


def _protect(data, decrypt=False):
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    buffer = ctypes.create_string_buffer(data, len(data))
    source = DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = DataBlob()
    operation = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    operation.argtypes = [ctypes.POINTER(DataBlob), ctypes.c_void_p, ctypes.c_void_p,
                          ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DataBlob)]
    operation.restype = wintypes.BOOL
    # CRYPTPROTECT_UI_FORBIDDEN: never trigger a credential dialog from a worker.
    if not operation(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel.LocalFree(result.pbData)


def load_pairings():
    path = pairing_path()
    if not path.exists():
        return []
    data = json.loads(_protect(path.read_bytes(), decrypt=True).decode("utf-8"))
    # Accept the original single-pairing format too.
    items = data if isinstance(data, list) else [data]
    for item in items:
        if (not isinstance(item, dict) or not isinstance(item.get("host"), str)
                or type(item.get("port")) is not int or not 1 <= item["port"] <= 65535
                or not isinstance(item.get("pin"), str) or not isinstance(item.get("secret"), str)):
            raise ValueError("Invalid saved pairing")
    return items


def save_pairing(host, port, pin, secret):
    path = pairing_path()
    # Do not overwrite a damaged store: the user can remove or recover it explicitly.
    items = load_pairings()
    normalize = lambda value: value.replace(":", "").replace(" ", "").upper()
    items = [item for item in items if normalize(item["pin"]) != normalize(pin)]
    items.insert(0, {"host": host, "port": port, "pin": pin, "secret": secret})
    encrypted = _protect(json.dumps(items).encode("utf-8"))
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_bytes(encrypted)
    temp.replace(path)
    return items
