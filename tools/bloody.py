#!/usr/bin/env python3
"""Talk to an A4Tech Bloody mouse over hidraw (see PROTOCOL.md).

Usage:
  bloody.py info
  bloody.py read-block <base_hex> <nwords>
  bloody.py write-block <base_hex> <dump_file> <nwords>   # block taken from a memory dump
"""
import fcntl
import glob
import os
import sys
import time

REPORT = 72
HIDIOCSFEATURE = (3 << 30) | (REPORT << 16) | (ord("H") << 8) | 0x06
HIDIOCGFEATURE = (3 << 30) | (REPORT << 16) | (ord("H") << 8) | 0x07
PAGE = 16  # words per write packet


def find_device():
    for h in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        uevent = open(h + "/device/uevent").read()
        if "000009DA" in uevent and "/input2" in uevent:
            return "/dev/" + os.path.basename(h)
    sys.exit("no Bloody mouse found")


class Mouse:
    def __init__(self, path=None):
        self.fd = os.open(path or find_device(), os.O_RDWR)
        self.unlocked = False

    def send(self, payload):
        fcntl.ioctl(self.fd, HIDIOCSFEATURE, bytearray(bytes(payload).ljust(REPORT, b"\0")))

    def query(self, payload):
        self.send(payload)
        buf = bytearray(REPORT)
        buf[0] = 0x07
        fcntl.ioctl(self.fd, HIDIOCGFEATURE, buf)
        return bytes(buf)

    def info(self):
        r = self.query([0x07, 0x1F])
        word = r[10] | r[11] << 8
        return {"model": word & 0xFFFC, "subtype": word & 3, "firmware": r[12]}

    def read_words(self, addr, count):
        if not self.unlocked:
            self.query(bytes.fromhex("072500005249182201"))
            self.unlocked = True
        words = []
        for a in range(addr, addr + count, 32):
            r = self.query([0x07, 0x02, 0x00, a >> 8, a & 0xFF, 0x60])
            words += [r[8 + i] | r[9 + i] << 8 for i in range(0, 64, 2)]
        return words[:count]

    def write_block(self, base, words):
        """Write a whole config block the way BloodyWorkShop8 does."""
        words = list(words)
        words[0] = words[1] = 0xFFFF
        if checksum(words) != (words[2], words[3]):
            raise ValueError("block checksum mismatch, refusing to write")
        words += [0] * (-len(words) % PAGE)
        self.query([0x07, 0x2F, 0x00, base >> 8])
        self.query([0x07, 0x20, 0, 0, 0, 0, 0, 0x01])
        time.sleep(0.04)
        for off in range(0, len(words), PAGE):
            a = base + off
            data = b"".join(w.to_bytes(2, "little") for w in words[off:off + PAGE])
            self.send(bytes([0x07, 0x2F, 0x79, a >> 8, a & 0xFF, 0x80, 0, 0]) + data)
            time.sleep(0.04)
        self.send([0x07, 0x2F, 0x01, base >> 8, base & 0xFF, 0, 0, 0, 0xA4, 0xA4])
        time.sleep(0.02)
        self.query([0x07, 0x20])
        # Trailing commands the vendor app sends after every block write.
        self.query([0x07, 0x0E])
        self.send(bytes.fromhex("070e800000000000006464646400"))
        time.sleep(0.01)
        self.send(bytes.fromhex("070f00000000000007"))
        time.sleep(0.01)
        self.send(bytes.fromhex("070c0000000000000280010000"))


def checksum(words):
    body = list(enumerate(words))[4:]
    return sum(w for _, w in body) & 0xFFFF, sum(i * w for i, w in body) & 0xFFFF


def block_from_dump(path, base, count):
    mem = {}
    for line in open(path):
        addr, _hdr, data = line.split()
        addr = int(addr[:-1], 16)
        raw = bytes.fromhex(data)
        for i in range(32):
            mem[addr + i] = raw[2 * i] | raw[2 * i + 1] << 8
    return [mem[base + i] for i in range(count)]


def main():
    cmd = sys.argv[1]
    mouse = Mouse()
    if cmd == "info":
        i = mouse.info()
        print(f"model 0x{i['model']:03x} subtype {i['subtype']} firmware {i['firmware']:02X}")
    elif cmd == "read-block":
        base, count = int(sys.argv[2], 16), int(sys.argv[3])
        words = mouse.read_words(base, count)
        for a in range(0, count, 8):
            print(f"{base + a:04x}: " + " ".join(f"{w:04x}" for w in words[a:a + 8]))
    elif cmd == "write-block":
        base, count = int(sys.argv[2], 16), int(sys.argv[4])
        words = block_from_dump(sys.argv[3], base, count)
        mouse.write_block(base, words)
        time.sleep(0.2)
        back = mouse.read_words(base, count)
        diff = [i for i in range(2, count) if back[i] != words[i]]
        print(f"written {count} words, header now {back[0]:04x} {back[1]:04x}, "
              f"readback {'OK' if not diff else f'DIFFERS at {len(diff)} words, first 0x{base + diff[0]:04x}'}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
