#!/usr/bin/env python3
"""Decode a usbmon pcap (tcpdump -i usbmonN -w file) into Bloody vendor reports.

Usage: decode_usbmon.py capture.pcap [--all] [--intr]

Prints host->device SET_REPORT payloads (OUT) and device->host GET_REPORT
payloads (IN) for report ID 0x07. --intr also prints interrupt IN reports
from the vendor interface, --all keeps consecutive duplicates.
"""
import struct
import sys

HDR = 64  # DLT_USB_LINUX_MMAPPED


def packets(path):
    with open(path, "rb") as f:
        magic = f.read(4)
        endian = "<" if magic in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1") else ">"
        f.read(20)
        while True:
            rec = f.read(16)
            if len(rec) < 16:
                return
            _, _, caplen, _ = struct.unpack(endian + "IIII", rec)
            yield f.read(caplen)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    keep_dupes = "--all" in sys.argv
    show_intr = "--intr" in sys.argv
    first_ts = None
    last = None
    for pkt in packets(args[0]):
        if len(pkt) < HDR:
            continue
        _, ev, xfer, ep, dev, _bus, _fs, _fd, sec, usec, _status, _length, lencap = struct.unpack_from(
            "<QBBBBHBBqiiII", pkt, 0
        )
        data = pkt[HDR:HDR + lencap]
        if not data or data[0] != 0x07:
            continue
        ev = chr(ev)
        if xfer == 2 and ev == "S" and not ep & 0x80:
            kind = "OUT"
        elif xfer == 2 and ev == "C" and ep & 0x80:
            kind = "IN "
        elif xfer == 1 and ev == "C" and ep & 0x80 and show_intr:
            kind = "INT"
        else:
            continue
        ts = sec + usec / 1e6
        if first_ts is None:
            first_ts = ts
        key = (kind, dev, data)
        if key == last and not keep_dupes:
            continue
        last = key
        print(f"{ts - first_ts:9.3f} dev{dev:<3} {kind} {data.hex()}")


if __name__ == "__main__":
    main()
