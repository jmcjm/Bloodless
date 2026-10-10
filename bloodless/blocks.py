"""Config block models: checksum, button block, sensitivity block (see PROTOCOL.md)."""

PACKET_WORDS = 16
END = 0x262E + 1  # 0x262f terminates a sequence


class BlockError(ValueError):
    """The block does not look like something this program understands."""


def checksum(words):
    body = list(enumerate(words))[4:]
    return sum(w for _, w in body) & 0xFFFF, sum(i * w for i, w in body) & 0xFFFF


def _verify(words, minimum):
    if len(words) < minimum:
        raise BlockError(f"block too short: {len(words)} words")
    if checksum(words) != (words[2], words[3]):
        raise BlockError("checksum mismatch")


def _finish(words):
    words = list(words)
    words += [0] * (-len(words) % PACKET_WORDS)
    words[0] = words[1] = 0xFFFF
    words[2], words[3] = checksum(words)
    return words


class ButtonBlock:
    BASE = 0x1B00
    MAX_WORDS = 640
    SEQ_START = 0x10
    TABLE_SLOTS = 24
    # Header words holding offsets, and the pointer cells those offsets lead to.
    H_PROFILES, H_PAIRS, H_KEYDICT, H_SETTINGS, H_SEQ_END, H_MACROS = 7, 8, 9, 10, 11, 13

    def __init__(self, words):
        words = list(words)
        if len(words) > self.H_MACROS and words[self.H_MACROS] + 10 <= len(words):
            words = words[: words[self.H_MACROS] + 10]
        _verify(words, 16)
        self.words = words
        h = words
        ok = (
            h[4] == 0x0200
            and self.SEQ_START <= h[self.H_SEQ_END] < h[self.H_SETTINGS] < h[self.H_PROFILES]
            and h[self.H_PAIRS] == h[self.H_PROFILES] + 9
            and h[self.H_PROFILES] < h[self.H_KEYDICT] < h[self.H_MACROS]
            and all(
                h[self.H_SETTINGS] < self._profile_ptr(p) < h[self.H_PROFILES] for p in (1, 2, 3)
            )
        )
        if not ok:
            raise BlockError("unexpected button block layout")

    def _profile_ptr(self, profile):
        return self.words[self.words[self.H_PROFILES] + profile - 1]

    def shares_table(self, profile):
        """True when this profile's button table is also another profile's table."""
        ptr = self._profile_ptr(profile)
        return any(self._profile_ptr(p) == ptr for p in (1, 2, 3) if p != profile)

    def _slot_index(self, profile, slot):
        if profile not in (1, 2, 3) or not 0 <= slot < self.TABLE_SLOTS:
            raise ValueError("profile must be 1-3 and slot 0-23")
        return self._profile_ptr(profile) + 2 * slot

    def get_slot(self, profile, slot):
        i = self._slot_index(profile, slot)
        return self.words[i], self.words[i + 1]

    def set_slot(self, profile, slot, press, release):
        i = self._slot_index(profile, slot)
        self.words[i], self.words[i + 1] = press, release

    def read_sequence(self, offset):
        """Words of the sequence starting at offset, without the terminator."""
        end = self.words[self.H_SEQ_END]
        if not self.SEQ_START <= offset < end:
            raise BlockError(f"sequence offset 0x{offset:x} outside sequence area")
        out = []
        for w in self.words[offset:end]:
            if w == END:
                return out
            out.append(w)
        raise BlockError("unterminated sequence")

    def add_sequence(self, seq):
        """Return the offset of seq inside the block, inserting it if it is not there yet."""
        needle = list(seq) + [END]
        w = self.words
        end = w[self.H_SEQ_END]
        for pos in range(self.SEQ_START, end - len(needle) + 1):
            starts = pos == self.SEQ_START or w[pos - 1] == END
            if starts and w[pos : pos + len(needle)] == needle:
                return pos
        n = len(needle)
        if end > 0xFF:
            raise BlockError("sequence area is full")
        if len(w) + n > self.MAX_WORDS:
            raise BlockError("button block is full")
        cells = [self.H_PROFILES, self.H_PAIRS, self.H_KEYDICT, self.H_SETTINGS, self.H_SEQ_END,
                 self.H_MACROS]
        for header in (self.H_PROFILES, self.H_PAIRS, self.H_KEYDICT):
            cells += [w[header] + i for i in range(3)]
        cells += [w[self.H_MACROS] + i for i in range(0, 10, 2)]
        for c in cells:
            if w[c] >= end:
                w[c] += n
        w[end:end] = needle
        return end

    def to_words(self):
        return _finish(self.words)


class SensitivityBlock:
    BASE = 0x1A00
    WORDS = 128
    LEVELS_AT = 6
    RATE_AT = 0x1E

    def __init__(self, words):
        words = list(words)[: self.WORDS]
        _verify(words, self.WORDS)
        if not 0 <= words[4] <= 4 or words[5] > words[4]:
            raise BlockError("unexpected sensitivity block layout")
        for i in range(self.LEVELS_AT, self.LEVELS_AT + 3 * (words[4] + 1), 3):
            if words[i] < 1 or words[i] != words[i + 1] or not words[i + 2] & 0x80:
                raise BlockError("unexpected sensitivity block layout")
        self.words = words

    @property
    def count(self):
        return self.words[4] + 1

    @property
    def selected(self):
        return self.words[5]

    @property
    def rate(self):
        return self.words[self.RATE_AT] & 0xFF

    def get_level(self, index):
        """(a, r) of level index (0-based)."""
        if not 0 <= index < self.count:
            raise ValueError(f"level must be 0-{self.count - 1}")
        i = self.LEVELS_AT + 3 * index
        return self.words[i], self.words[i + 2] & 0x7F

    def set_level(self, index, a, r):
        if not 0 <= index < self.count:
            raise ValueError(f"level must be 0-{self.count - 1}")
        i = self.LEVELS_AT + 3 * index
        self.words[i] = self.words[i + 1] = a
        self.words[i + 2] = 0x80 | r

    def to_words(self):
        return _finish(self.words)