#!/usr/bin/env python3
"""Generate minimal EMF/EMF+ regression fixtures for the EMF+ (-p) renderer.

Run from the repository root:
    python3 tests/resources/gen_emfplus_fixtures.py

Produces three self-contained dual EMF/EMF+ files:
  emf-ea/EA-emfplus-fill-in-open-path.emf
      Well-formed. An EMF+ FillRects (inline ARGB) sits inside an EMR_COMMENT
      that appears while a GDI path is open (BEGINPATH..ENDPATH). The renderer
      must NOT emit its own element into the open "<path d=..." attribute.
  emf-corrupted/emfplus-fillrects-huge-elements.emf
      Malformed. FillRects declares a huge Elements count; the vendored
      U_PMF_VARRECTS_get frees its buffer but leaves the pointer dangling.
      The renderer must not read or double-free it.
  emf-corrupted/emfplus-fillrects-truncated-size.emf
      Malformed. The EMF+ record declares a Size that overruns the buffer.
      The renderer must skip just that record, not abort the whole file.
"""
import os
import struct
import sys

EMR_HEADER, EMR_EOF, EMR_MOVETOEX = 1, 14, 27
EMR_LINETO, EMR_BEGINPATH, EMR_ENDPATH, EMR_STROKEPATH, EMR_COMMENT = 54, 59, 60, 64, 70
EMFPLUS_IDENT = 0x2B464D45  # "EMF+"
PMR_FILLRECTS = 0x400A      # U_PMR_FILLRECTS | U_PMR_RECFLAG
PPF_B, PPF_C = 0x8000, 0x4000  # inline ARGB brush, int16 coordinates


def rec(itype, body):
    nsize = 8 + len(body)
    assert nsize % 4 == 0, (itype, nsize)
    return struct.pack("<II", itype, nsize) + body


def header(nrec):
    b = struct.pack("<iiii", 0, 0, 200, 200)        # rclBounds (device px)
    b += struct.pack("<iiii", 0, 0, 20000, 20000)   # rclFrame (.01 mm)
    b += struct.pack("<I", 0x464D4520)              # " EMF" signature
    b += struct.pack("<I", 0x00010000)              # nVersion
    b += struct.pack("<I", 0)                       # nBytes (patched below)
    b += struct.pack("<I", nrec)                    # nRecords
    b += struct.pack("<H", 1)                       # nHandles
    b += struct.pack("<H", 0)                       # sReserved
    b += struct.pack("<I", 0)                       # nDescription
    b += struct.pack("<I", 0)                       # offDescription
    b += struct.pack("<I", 0)                       # nPalEntries
    b += struct.pack("<ii", 1000, 1000)             # szlDevice
    b += struct.pack("<ii", 200, 200)               # szlMillimeters
    h = rec(EMR_HEADER, b)
    assert len(h) == 88, len(h)
    return h


def fillrects(elements=1, size_override=None, nrects=1):
    """One EMF+ FillRects record, inline ARGB (50% red), int16 rects."""
    data = struct.pack("<I", 0x80FF0000) + struct.pack("<I", elements)
    for _ in range(nrects):
        data += struct.pack("<hhhh", 20, 20, 60, 40)
    size = size_override if size_override is not None else 12 + len(data)
    return struct.pack("<HHII", PMR_FILLRECTS, PPF_B | PPF_C, size, len(data)) + data


def emfplus_comment(pmf_bytes):
    cbData = 4 + len(pmf_bytes)  # cIdent + EMF+ data
    body = struct.pack("<I", cbData) + struct.pack("<I", EMFPLUS_IDENT) + pmf_bytes
    while (8 + len(body)) % 4:
        body += b"\x00"
    return rec(EMR_COMMENT, body)


def eof():
    return rec(EMR_EOF, struct.pack("<III", 0, 0, 0))


def assemble(body_records):
    blob = header(1 + len(body_records)) + b"".join(body_records)
    return blob[:48] + struct.pack("<I", len(blob)) + blob[52:]


def write(path, blob):
    with open(path, "wb") as f:
        f.write(blob)
    print("wrote %s (%d bytes)" % (path, len(blob)))


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(__file__)

    # FIX B: fill emitted while a GDI path is open.
    write(os.path.join(root, "emf-ea", "EA-emfplus-fill-in-open-path.emf"),
          assemble([
              rec(EMR_BEGINPATH, b""),
              rec(EMR_MOVETOEX, struct.pack("<ii", 10, 10)),
              rec(EMR_LINETO, struct.pack("<ii", 150, 150)),
              emfplus_comment(fillrects()),
              rec(EMR_ENDPATH, b""),
              rec(EMR_STROKEPATH, struct.pack("<iiii", 0, 0, 200, 200)),
              eof(),
          ]))

    # FIX A: declared Elements far exceeds the record's data.
    write(os.path.join(root, "emf-corrupted", "emfplus-fillrects-huge-elements.emf"),
          assemble([emfplus_comment(fillrects(elements=100000, nrects=1)), eof()]))

    # FIX C: declared Size overruns the buffer.
    write(os.path.join(root, "emf-corrupted", "emfplus-fillrects-truncated-size.emf"),
          assemble([emfplus_comment(fillrects(size_override=0xFFFF)), eof()]))


if __name__ == "__main__":
    main()
