"""High-level operations on a mouse, built on a transport (see PROTOCOL.md)."""
import time

from .blocks import ButtonBlock, SensitivityBlock

UNLOCK = bytes.fromhex("072500005249182201")
# Sent by the vendor app after every button block write; kept verbatim.
_AFTER_BUTTONS = ["070e800000000000006464646400", "070f00000000000007",
                  "070c0000000000000280010000"]


class WriteError(RuntimeError):
    """The block read back from the mouse differs from what was written."""


class Mouse:
    def __init__(self, transport, sleep=time.sleep):
        self.t = transport
        self.sleep = sleep
        self._unlocked = False

    def info(self):
        r = self.t.query([0x07, 0x1F])
        word = r[10] | r[11] << 8
        return {"model": word & 0xFFFC, "subtype": word & 3, "firmware": r[12]}

    def read_words(self, addr, count):
        if not self._unlocked:
            self.t.query(UNLOCK)
            self._unlocked = True
        words = []
        for a in range(addr, addr + count, 32):
            r = self.t.query([0x07, 0x02, 0x00, a >> 8, a & 0xFF, 0x60])
            words += [r[8 + i] | r[9 + i] << 8 for i in range(0, 64, 2)]
        return words[:count]

    def _read_block(self, base, count):
        words = self.read_words(base, count)
        words[0] = words[1] = 0xFFFF
        return words

    def read_buttons(self):
        return ButtonBlock(self._read_block(ButtonBlock.BASE, ButtonBlock.MAX_WORDS))

    def read_sensitivity(self):
        return SensitivityBlock(self._read_block(SensitivityBlock.BASE, SensitivityBlock.WORDS))

    def write_block(self, base, words):
        """Write a finished block (output of to_words()) and verify it by reading it back."""
        self.t.query([0x07, 0x2F, 0x00, base >> 8])
        self.t.query([0x07, 0x20, 0, 0, 0, 0, 0, 0x01])
        self.sleep(0.04)
        for off in range(0, len(words), 16):
            a = base + off
            data = b"".join(w.to_bytes(2, "little") for w in words[off:off + 16])
            self.t.send(bytes([0x07, 0x2F, 0x79, a >> 8, a & 0xFF, 0x80, 0, 0]) + data)
            self.sleep(0.04)
        self.t.send([0x07, 0x2F, 0x01, base >> 8, base & 0xFF, 0, 0, 0, 0xA4, 0xA4])
        self.sleep(0.02)
        self.t.query([0x07, 0x20])
        self.sleep(0.2)
        back = self.read_words(base, len(words))
        if back[2:] != list(words[2:]):
            raise WriteError(f"readback of block 0x{base:04x} differs from what was written")

    def write_buttons(self, block):
        self.write_block(ButtonBlock.BASE, block.to_words())
        self.t.query([0x07, 0x0E])
        for frame in _AFTER_BUTTONS:
            self.t.send(bytes.fromhex(frame))
            self.sleep(0.01)

    def write_sensitivity(self, block):
        self.write_block(SensitivityBlock.BASE, block.to_words())
        a, r = block.get_level(block.selected)
        self.t.send([0x07, 0x0D, 0, 0, 0, 0, 0, 0, block.count - 1, block.selected, a, a,
                     0x80 | r, block.rate])

    def get_backlight(self):
        return self.t.query([0x07, 0x11])[8]

    def set_backlight(self, level):
        if level not in (0, 1, 2, 3):
            raise ValueError("backlight level must be 0-3")
        self.t.send([0x07, 0x11, 0, 0, 0x80, 0, 0, 0, level])
        self.t.send([0x07, 0x0A])