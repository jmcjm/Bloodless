#!/usr/bin/env python3
"""Reconstruct config-block writes (opcode 0x2f) from decode_usbmon.py output.

Usage: decode_usbmon.py capture.pcap | write_sessions.py [--dump]

A write session starts with "07 20 .. 01" (enter write mode). Each session becomes
a word-addressed image; its checksum is verified and it is diffed word by word
against the previous session with the same base address and length.

Block header: words 0-1 = ffff ffff, word 2 = sum of words[4:], word 3 = sum of
index * word for index >= 4 (index counted from the block start), both mod 2^16.
"""
import sys


def checksum(words):
    body = list(enumerate(words))[4:]
    return sum(w for _, w in body) & 0xFFFF, sum(i * w for i, w in body) & 0xFFFF


sessions = []
cur = None
for line in sys.stdin:
    ts, _dev, kind, hexs = line.split()
    b = bytes.fromhex(hexs)
    if kind != "OUT":
        continue
    if b[1] == 0x20 and b[7] == 0x01:
        cur = None
        continue
    if b[1] != 0x2F or b[2] != 0x79:
        continue
    addr = b[3] << 8 | b[4]
    if cur is None:
        cur = {"ts": float(ts), "base": addr, "words": []}
        sessions.append(cur)
    cur["words"] += [b[8 + i] | b[9 + i] << 8 for i in range(0, 32, 2)]

prev = {}
for s in sessions:
    w, base = s["words"], s["base"]
    ok = checksum(w) == (w[2], w[3])
    print(f"# session t={s['ts']:.3f} base=0x{base:04x} words={len(w)} "
          f"checksum {w[2]:04x} {w[3]:04x} {'OK' if ok else 'MISMATCH'}")
    if "--dump" in sys.argv:
        for a in range(0, len(w), 8):
            print(f"  {base + a:04x}: " + " ".join(f"{x:04x}" for x in w[a:a + 8]))
    old = prev.get(base)
    if old and len(old) != len(w):
        print(f"  layout changed: {len(old)} -> {len(w)} words")
    elif old:
        for i, (x, y) in enumerate(zip(old, w)):
            if x != y:
                print(f"  {base + i:04x}: {x:04x} -> {y:04x}")
    prev[base] = w
