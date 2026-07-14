# Epson Chip / Waste-Ink Resetter (WF-7840)

A small right-to-repair maintenance utility for Epson network printers, styled
after the classic EPSON Adjustment Program (AdjProg). It reads the internal
waste-ink pad counters and can reset them after you replace the waste pad or
maintenance box — the counter that otherwise locks the printer with a
"parts inside are near the end of their service life" error.

- `chip_resetter.py` — the SNMP EEPROM engine (no GUI, no third-party deps).
- `chip_resetter_gui.py` — the AdjProg-style `customtkinter` front-end.
- `ChipResetter.spec` — PyInstaller spec to build a standalone Windows EXE.

## How it works

Epson printers expose an EEPROM read/write control channel over **SNMP** (UDP
161). Reading a byte and writing a byte use these OIDs under
`1.3.6.1.4.1.1248.1.2.2.44.1.1.2.1`:

```
read : …124.124.7.0.<pw0>.<pw1>.65.190.160.<addr>.0
write: …124.124.16.0.<pw0>.<pw1>.66.189.33.<addr>.0.<value>.<write_key…>
```

The reply is an octet string containing `EE:AABBVV`, where `VV` is the byte.
This is the same mechanism the open-source `epson_print_conf` and
`epson-printer-snmp` projects document.

## Important: the WF-7840 needs verified keys

Each model has its own 2-byte **read key** (password) and a **write key**.
These are model-specific and are **not published for the WF-7840** in any
open-source database at the time of writing. Writing to the wrong EEPROM
address with the wrong key can permanently damage a printer, so this tool is
deliberately conservative:

| Profile   | Status       | What works                                   |
|-----------|--------------|----------------------------------------------|
| WF-7525   | **verified** | Printer info, counter check, counter reset   |
| WF-7840   | unverified   | Printer info only — reset is **blocked**      |

For the WF-7840, "Printer information check" works out of the box (it uses
generic SNMP and needs no key). To enable counter read/reset you must enter
verified key material via the **Keys…** button — supply it only from a source
you trust (e.g. a WICReset key you own, or a confirmed community value). The
tool refuses every EEPROM write until a profile is verified or you have
explicitly supplied keys, and it reads a cell back to confirm each write.

The WF-7525 profile is included as a known-good reference so you can see the
full read → check → reset flow against real, documented values.

## Usage

```bash
pip install customtkinter
python chip_resetter_gui.py
```

1. Set the printer's **IP address** and pick the model.
2. Use **Particular adjustment mode → Printer information check → Check** to
   confirm the printer is reachable.
3. Select **Waste ink pad counter** and press **Check** to read usage.
4. After replacing the pad/maintenance box, press **Initialization (reset)**,
   confirm, then power-cycle the printer.

Run the engine self-test (no printer needed):

```bash
python chip_resetter.py --selftest
```

## Build a Windows EXE

```bash
pyinstaller ChipResetter.spec
```
