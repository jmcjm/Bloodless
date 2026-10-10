"""In-memory stand-in for a mouse, used by tests and by the GUI demo mode."""
from .transport import REPORT


class FakeTransport:
    def __init__(self, buttons, sensitivity, firmware=0xF5):
        self.memory = {}
        self.load(0x1B00, buttons)
        self.load(0x1A00, sensitivity)
        self.firmware = firmware
        self.backlight = 3
        self.sent = []
        self.writing = False
        self.corrupt_writes = False
        self.level = sensitivity[5]  # DPI level in use; a real mouse changes it on button press
        self.reporting = False
        self.silent = False  # a mouse that never sends status reports
        self.inputs = []
        self._reply = bytes(REPORT)

    def load(self, base, words):
        for i, w in enumerate(words):
            self.memory[base + i] = w
        self.memory[base] = 0xA4A4

    def send(self, payload):
        p = bytes(payload).ljust(REPORT, b"\0")
        self.sent.append(p)
        op = p[1]
        reply = bytearray(p)
        if op == 0x1F:
            reply[9:13] = bytes([0x22, 0x10, 0x00, self.firmware])
        elif op == 0x02:
            addr = p[3] << 8 | p[4]
            for i in range(32):
                reply[8 + 2 * i:10 + 2 * i] = self.memory.get(addr + i, 0).to_bytes(2, "little")
        elif op == 0x11:
            if p[4] == 0x80:
                self.backlight = p[8]
            reply[8] = self.backlight
        elif op == 0x09:
            self.reporting = p[8] == 0x01
        elif op == 0x0D:
            self.level = p[9]
        elif op == 0x0C and self.reporting and not self.silent:
            self.inputs.append(bytes([7, 1, 1, 0, 0, 0, 7, 0, 0, 0, 0, 2, self.level, 1, 0, 0]))
        elif op == 0x20:
            self.writing = p[7] == 0x01
        elif op == 0x2F and p[2] == 0x79 and self.writing:
            addr = p[3] << 8 | p[4]
            for i in range(16):
                word = int.from_bytes(p[8 + 2 * i:10 + 2 * i], "little")
                if self.corrupt_writes and i == 5:
                    word ^= 1
                self.memory[addr + i] = word
        elif op == 0x2F and p[2] == 0x01:
            self.memory[p[3] << 8 | p[4]] = 0xA4A4
        self._reply = bytes(reply)

    def query(self, payload):
        self.send(payload)
        return self._reply

    def read_input(self, timeout):
        return self.inputs.pop(0) if self.inputs else None

    def close(self):
        pass