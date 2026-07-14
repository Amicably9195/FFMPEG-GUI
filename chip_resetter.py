#!/usr/bin/env python3
"""Epson Adjustment Program — waste-ink / "chip" counter tool (WF-7840 target).

Right-to-repair maintenance utility for Epson network printers. It speaks the
same SNMP EEPROM read/write control channel that the official AdjProg / WICReset
tools use, so you can read the internal waste-ink pad counters and reset them
after replacing the pad / maintenance box.

Two honesty notes baked into this code:

  * The read/write "keys" (the model password + write key) are model specific.
    They are NOT guessable and NOT public for every model. Writing to the wrong
    EEPROM address with a wrong key can brick a printer, so every model profile
    carries a ``verified`` flag and destructive resets are refused on unverified
    profiles unless you explicitly supply keys from a source you trust.

  * WF-7525 is included as a *verified* reference profile (keys are published in
    open-source projects and known-good). WF-7840 is included as a profile whose
    key material is NOT publicly known — reading printer info still works, but
    the counter read/reset needs verified keys before it will run.

Protocol reference (open source, MIT/GPL):
  * Ircama/epson_print_conf
  * Zedeldi/epson-printer-snmp
"""

import re
import random
import socket

# ── SNMP over UDP (minimal, dependency-free BER, SNMPv1) ───────────────────────
# Kept free of any GUI import so the engine is importable / testable headless
# and so a PyInstaller build has no extra runtime deps.

EPSON_OID_PREFIX = [1, 3, 6, 1, 4, 1, 1248, 1, 2, 2, 44, 1, 1, 2, 1]
SYS_DESCR_OID    = [1, 3, 6, 1, 2, 1, 1, 1, 0]           # generic "who are you"
DEVICE_DESCR_OID = [1, 3, 6, 1, 2, 1, 25, 3, 2, 1, 3, 1]  # hrDeviceDescr.1


def _enc_len(n):
    if n < 0x80:
        return bytes([n])
    out = bytearray()
    while n:
        out.insert(0, n & 0xFF)
        n >>= 8
    return bytes([0x80 | len(out)]) + bytes(out)


def _enc_base128(n):
    out = bytearray([n & 0x7F])
    n >>= 7
    while n:
        out.insert(0, (n & 0x7F) | 0x80)
        n >>= 7
    return bytes(out)


def _enc_oid(arcs):
    body = _enc_base128(40 * arcs[0] + arcs[1])
    for a in arcs[2:]:
        body += _enc_base128(a)
    return b"\x06" + _enc_len(len(body)) + body


def _enc_int(n):
    v = bytearray()
    if n == 0:
        v.append(0)
    else:
        while n:
            v.insert(0, n & 0xFF)
            n >>= 8
        if v[0] & 0x80:          # keep two's-complement positive
            v.insert(0, 0)
    return b"\x02" + _enc_len(len(v)) + bytes(v)


def _tlv(tag, value):
    return bytes([tag]) + _enc_len(len(value)) + value


def _read_tlv(data, i):
    """Return (tag, value_start, length, next_index) for the TLV at ``i``."""
    tag = data[i]
    ln = data[i + 1]
    j = i + 2
    if ln & 0x80:
        k = ln & 0x7F
        ln = int.from_bytes(data[j:j + k], "big")
        j += k
    return tag, j, ln, j + ln


def _extract_octet(data):
    """Walk an SNMPv1 GetResponse and return the first varbind's OCTET STRING."""
    _, s0, _, _ = _read_tlv(data, 0)                 # message SEQUENCE
    i = s0
    for _ in range(2):                               # version, community
        _, vs, ln, nxt = _read_tlv(data, i); i = nxt
    _, pdus, _, _ = _read_tlv(data, i); i = pdus     # response PDU (0xA2)
    for _ in range(3):                               # req-id, err-status, err-idx
        _, vs, ln, nxt = _read_tlv(data, i); i = nxt
    _, vbls, _, _ = _read_tlv(data, i); i = vbls     # varbind list
    _, vbs, _, _ = _read_tlv(data, i); i = vbs       # varbind
    _, _, _, nxt = _read_tlv(data, i); i = nxt       # skip the OID
    tag, vs, ln, _ = _read_tlv(data, i)              # the value
    if tag == 0x04:
        return data[vs:vs + ln]
    return None


def snmp_get_octet(host, oid_arcs, community="public", port=161, timeout=4.0):
    """One SNMPv1 GET; returns the OCTET STRING payload as bytes (or None)."""
    req_id = random.randint(1, 0x7FFFFFFF)
    varbind = _tlv(0x30, _enc_oid(oid_arcs) + b"\x05\x00")
    pdu = _tlv(0xA0, _enc_int(req_id) + _enc_int(0) + _enc_int(0)
               + _tlv(0x30, varbind))
    msg = _tlv(0x30, _enc_int(0) + _tlv(0x04, community.encode()) + pdu)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(msg, (host, port))
        data, _ = sock.recvfrom(4096)
    finally:
        sock.close()
    return _extract_octet(data)


# ── Printer profiles ───────────────────────────────────────────────────────────
# read_key : the 2-byte model password (used for both read and write control).
# write_key: the write password; each non-zero byte is +1'd on the wire (a
#            Caesar shift of 1), exactly as the reference tools do it.
# main_waste / borderless_waste: EEPROM addresses forming the counter, plus the
#            divider that converts the raw count to a percentage-of-full.
# reset_map: {address: value} written to clear the counter after a pad change.
# verified : True only when the key material is known-good for real hardware.

def _caesar(write_key):
    return [0 if b == 0 else (b + 1) & 0xFF for b in write_key]


PRINTER_CONFIG = {
    # ---- Verified reference profile (keys published & known-good) -------------
    "WF-7525": {
        "verified": True,
        "read_key": [101, 0],
        "write_key": b"Sasanqua",
        "main_waste": {"oids": [20, 21], "divider": 196.5},
        "borderless_waste": {"oids": [22, 23], "divider": 52.05},
        "serial_number": list(range(192, 202)),
        "reset_map": {20: 0, 21: 0, 22: 0, 23: 0, 24: 0, 25: 0,
                      59: 0, 60: 94, 61: 94},
        "notes": "Verified against the open-source epson_print_conf database.",
    },

    # ---- Target profile: WF-7840 ---------------------------------------------
    # The WF-7840 uses a replaceable maintenance box PLUS an internal borderless
    # "platen" waste pad whose counter lives in EEPROM and is what actually
    # locks the printer. The SNMP mechanism below is identical for this model —
    # only the key material and addresses differ, and those are NOT published in
    # any open-source database at time of writing. They are left None on purpose:
    # reading info works, but counter read/reset stays disabled until you supply
    # keys you trust (see the Keys… dialog). Do not guess these — a wrong write
    # key/address can brick the unit.
    "WF-7840": {
        "verified": False,
        "read_key": None,
        "write_key": None,
        # Address layout below mirrors the WF-78xx family shape and is a best-
        # effort placeholder to be confirmed, NOT a guarantee.
        "main_waste": {"oids": [24, 25], "divider": 62.06},
        "borderless_waste": {"oids": [26, 27], "divider": 26.28},
        "serial_number": list(range(192, 202)),
        "reset_map": {24: 0, 25: 0, 26: 0, 27: 0, 28: 0, 30: 0},
        "notes": ("Key material for the WF-7840 is not public. Supply a verified "
                  "read/write key before using counter read or reset."),
    },
}


class PrinterError(Exception):
    pass


class EpsonPrinter:
    """SNMP EEPROM client for one printer at one address."""

    def __init__(self, host, model, community="public", port=161, timeout=4.0,
                 read_key=None, write_key=None):
        self.host = host
        self.model = model
        self.community = community
        self.port = port
        self.timeout = timeout
        cfg = dict(PRINTER_CONFIG.get(model, {}))
        # Allow the caller (GUI "Keys…" dialog) to override key material.
        if read_key is not None:
            cfg["read_key"] = read_key
            cfg["verified"] = "custom"
        if write_key is not None:
            cfg["write_key"] = write_key
        self.cfg = cfg

    # -- capability gate --------------------------------------------------------
    @property
    def keys_available(self):
        return bool(self.cfg.get("read_key")) and bool(self.cfg.get("write_key"))

    @property
    def is_verified(self):
        return self.cfg.get("verified") in (True, "custom")

    def _require_keys(self):
        if not self.keys_available:
            raise PrinterError(
                f"No verified read/write key for {self.model}. "
                "Enter one via 'Keys…' before reading or resetting counters.")

    # -- generic reachability ---------------------------------------------------
    def identify(self):
        """Return a human-readable identity string. Needs no key material."""
        for oid in (SYS_DESCR_OID, DEVICE_DESCR_OID):
            try:
                resp = snmp_get_octet(self.host, oid, self.community,
                                      self.port, self.timeout)
                if resp:
                    return resp.decode("latin-1", "replace").strip()
            except (socket.timeout, OSError):
                continue
        raise PrinterError(f"No SNMP response from {self.host}:{self.port}. "
                           "Check the IP and that the printer is on the network.")

    # -- EEPROM byte access -----------------------------------------------------
    def read_byte(self, addr):
        self._require_keys()
        pw = self.cfg["read_key"]
        oid = EPSON_OID_PREFIX + [124, 124, 7, 0, pw[0], pw[1],
                                  65, 190, 160, addr, 0]
        resp = snmp_get_octet(self.host, oid, self.community,
                              self.port, self.timeout)
        if not resp:
            raise PrinterError(f"Read of EEPROM {addr} returned no data "
                               "(wrong key or address?).")
        m = re.findall(r"EE:[0-9A-F]{6}", resp.decode("latin-1", "replace"))
        if not m:
            raise PrinterError(f"Unexpected read response for EEPROM {addr}: "
                               f"{resp[:40]!r}")
        return int(m[0][7:9], 16)

    def write_byte(self, addr, value):
        self._require_keys()
        if not self.is_verified:
            raise PrinterError("Refusing to write EEPROM on an unverified "
                               "profile. Confirm keys via 'Keys…' first.")
        pw = self.cfg["read_key"]
        wk = _caesar(self.cfg["write_key"])
        oid = (EPSON_OID_PREFIX
               + [124, 124, 16, 0, pw[0], pw[1], 66, 189, 33, addr, 0,
                  value & 0xFF]
               + wk)
        resp = snmp_get_octet(self.host, oid, self.community,
                              self.port, self.timeout)
        if not resp or b":OK;" not in resp and b"OK" not in resp:
            # Some firmwares echo the written cell rather than "OK"; verify below.
            check = self.read_byte(addr)
            if check != (value & 0xFF):
                raise PrinterError(
                    f"Write to EEPROM {addr} not confirmed (read back {check}).")
        return True

    # -- high-level operations --------------------------------------------------
    def _counter_percent(self, spec):
        raw = 0
        for i, addr in enumerate(spec["oids"]):
            raw += self.read_byte(addr) << (8 * i)
        pct = raw / spec["divider"] if spec.get("divider") else raw
        return raw, round(pct, 1)

    def read_waste_counters(self):
        """Return {label: (raw, percent)} for each configured counter."""
        self._require_keys()
        out = {}
        if "main_waste" in self.cfg:
            out["Main waste ink pad"] = self._counter_percent(self.cfg["main_waste"])
        if "borderless_waste" in self.cfg:
            out["Borderless / platen pad"] = self._counter_percent(
                self.cfg["borderless_waste"])
        return out

    def read_serial(self):
        addrs = self.cfg.get("serial_number") or []
        chars = []
        for a in addrs:
            b = self.read_byte(a)
            chars.append(chr(b) if 32 <= b < 127 else "")
        return "".join(chars).strip()

    def reset_waste_counters(self):
        """Clear the waste counters. Destructive — guarded by verification."""
        self._require_keys()
        if not self.is_verified:
            raise PrinterError("Reset blocked: profile is not verified.")
        reset_map = self.cfg.get("reset_map") or {}
        if not reset_map:
            raise PrinterError(f"No reset map defined for {self.model}.")
        for addr, val in reset_map.items():
            self.write_byte(addr, val)
        return len(reset_map)


# ── Self-test (no hardware, no GUI) ────────────────────────────────────────────
def _selftest():
    # BER length round-trips
    assert _enc_len(5) == b"\x05"
    assert _enc_len(200) == b"\x81\xc8"
    assert _enc_len(300) == b"\x82\x01\x2c"
    # base-128 sub-identifier encoding for a value > 127
    assert _enc_base128(1248) == b"\x89\x60"
    assert _enc_base128(127) == b"\x7f"
    # OID encoding: 1.3.6.1.2.1.1.1.0
    assert _enc_oid(SYS_DESCR_OID) == b"\x06\x08\x2b\x06\x01\x02\x01\x01\x01\x00"
    # A full GET packet parses back to the OCTET STRING we embed.
    payload = b"@BDC PS\r\nEE:00142A;\r\n"
    varbind = _tlv(0x30, _enc_oid(SYS_DESCR_OID) + _tlv(0x04, payload))
    pdu = _tlv(0xA2, _enc_int(1) + _enc_int(0) + _enc_int(0) + _tlv(0x30, varbind))
    msg = _tlv(0x30, _enc_int(0) + _tlv(0x04, b"public") + pdu)
    assert _extract_octet(msg) == payload
    # And the EE: value parse yields 0x2A = 42.
    m = re.findall(r"EE:[0-9A-F]{6}", payload.decode("latin-1"))
    assert int(m[0][7:9], 16) == 0x2A
    # caesar shift matches the reference (+1 per non-zero byte)
    assert _caesar(b"Sasanqua") == [84, 98, 116, 98, 111, 114, 118, 98]
    # verified/unverified gating
    p = EpsonPrinter("127.0.0.1", "WF-7840")
    assert not p.keys_available and not p.is_verified
    p2 = EpsonPrinter("127.0.0.1", "WF-7525")
    assert p2.keys_available and p2.is_verified
    print("selftest OK")


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        _selftest()
    else:
        from chip_resetter_gui import main
        main()
