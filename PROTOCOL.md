# A4Tech Bloody mouse configuration protocol — reverse engineering notes

State as of 2026-10-10. Device examined: family `V_P3305_010` (V7/V8M), Sonix SN8F2253B chip,
firmware `F5` (`EF` before the session). Sources: prior art
([maxmati](https://github.com/maxmati/a4tech-bloody-linux-driver),
[C0rn3j](https://gitlab.com/C0rn3j/a4tech_bloody_p85_driver)) and our own USB capture of
BloodyWorkShop8 2026.0723.

A second mouse (called V7M by its owner) reports the same family `V_P3305_010`, subtype 1,
firmware `F3`. Its memory dump has the same `0x1a00` / `0x1b00` block layout and the same
checksum.

Confidence marks: **[C]** confirmed on a live mouse or in the capture, **[H]** hypothesis.

## Transport [C]

- Interface 2 of the device (vendor HID, usage page `0xFF30`), report ID `0x07`.
- Feature report of 72 bytes (ID + 71), input report of 16 bytes (ID + 15).
- Request: `SET_REPORT(feature, id 7)` with 72 bytes; reply: `GET_REPORT(feature, id 7)`.
- From userspace hidraw is enough: `ioctl HIDIOCSFEATURE(72)` / `HIDIOCGFEATURE(72)`. No libusb,
  no kernel driver detach, no root once the hidraw node is writable.
- Frame: byte 0 = `07`, byte 1 = opcode, the rest depends on the opcode, zero padded.
- The USB product ID differs per unit (derived from a hardware ID). Identify the model with
  opcode `1f`, not by PID.

## Opcodes

| Opcode | Function | Confidence |
|---|---|---|
| `00` | restart firmware (used when flashing) | C |
| `01` | memory write in bootloader mode (firmware flash) | C |
| `02` | memory read: `07 02 00 <addr_hi> <addr_lo> 60` | C |
| `03` | RGB mode/effects (`03 06 ..` edit mode, `03 03 0b` after a brightness change) | H |
| `05` | mouse ID and licence data | C |
| `0a` | sent after a live setting change, probably "persist" | H |
| `0c`, `0e`, `0f`, `14`, `1e`, `09` | vendor app initialisation, meaning unknown | — |
| `0d` | set current DPI live | C |
| `11` | backlight brightness | C |
| `13` | sensor calibration | C (prior art) |
| `1f` | device information | C |
| `20` | enter (`byte 7 = 01`) / leave (`00`) config write mode | C |
| `25` | unlock reading of all memory: `07 25 00 00 52 49 18 22 01` | C |
| `28` | switch to bootloader (`07 28 01 .. f4 ee`), followed by `00` | C |
| `29` | returns 8 bytes of an identifier | C |
| `2f` | read block header / write config block | C |

### `1f` — device information [C]

Reply: byte 9 = flags (the low 2 bits are described as "core" in prior art), bytes 10–11 =
model word, little-endian (`& 0xfffc` = model ID, `& 3` = subtype), byte 12 = firmware version.

Example: `071f 0000 0000 0000 00 22 10 00 f5 00 10 00 0f 00` → model `0x010`, firmware `F5`.
Firmware file names in the vendor app: `<family>_<sensor>_<model ID>_<core>_<version>`.

### `11` — brightness [C]

- Set: `07 11 00 00 80 00 00 00 <level 0–3>`, the app follows it with `07 0a`.
- Get: `07 11 00 00 00`, level in byte 8 of the reply.

### `0d` — current DPI [C]

`07 0d 00 00 00 00 00 00 <levels-1> <selected> <a> <a> <0x80|r> <rate>`

`a` and `r` as in the sensitivity block below. `rate`: `01` = 1000 Hz, `02` = 500, `04` = 250,
`08` = 125 (prior art).

### `09` / `0c` — status report with the DPI level in use

- `07 09 00 00 00 00 00 00 01` switches reporting on, all zeros switches it off [C]. While
  it is off the mouse sends no input reports on the vendor interface.
- `07 0c 00 00 00 00 00 00 02 80 01` (and also `07 06`) makes the mouse send one input report
  [C]: `07 01 01 00 00 00 07 00 00 00 00 02 <level> 01 00 00`.
- Byte 12 is the 0-based DPI level in use [C]: it reads back levels set with `0d` and also
  follows the mouse's own DPI buttons. Byte 11 equals the polling rate code [H].
- The first report after switching reporting on had byte 2 = `f1` and byte 12 = `08`; its
  meaning is unknown, so only reports with byte 2 = `01` are used.
- Word 5 of the sensitivity block does not follow `0d`; it stays at the stored value.

## Memory

Addresses are in 16-bit little-endian words. One `02` read returns 32 words (64 bytes); the
reply header carries the address advanced by `0x20`. The address space mirrors every `0x4000`.

Without opcode `25` only the start of the firmware and a small area near `0x2700` are
readable; after `25` everything is. Unlocking does not change how the mouse behaves.

Layout [C]:

| Address | Content |
|---|---|
| `0x0000`–`0x19ff` | firmware code |
| `0x1a00` | sensitivity block (128 words) |
| `0x1b00`–`0x1d7f` | button block (512 words by default, up to 640) |
| `0x2700`–`0x27ff` | a short record marked `a4a4`, then code |

The base addresses `0x1a00` and `0x1b00` are the same on firmware `EF`, `F3` and `F5` (three
dumps, two units). On the P85 (prior art) the sensitivity block is at `0x2a00`.

The pre-flash (`EF`) dump of the first mouse contains its owner's original configuration
(Ctrl+C / Ctrl+V macros on the side buttons). After flashing, the vendor app overwrote it with
defaults. That old block has different values in header words 5–6 (`0000 000a` instead of
`0040 0001`); firmware `F5` accepts it unchanged [C — written back with our own code and
confirmed by pressing the buttons].

## Writing a config block [C]

1. `07 2f 00 <addr_hi>` — read the block header (reply: `a4a4 ffff <sum1> <sum2>`)
2. `07 20 00 00 00 00 00 01` — enter write mode
3. for every 16 words: `07 2f 79 <addr_hi> <addr_lo> 80 00 00` + 32 data bytes, address += `0x10`
4. `07 2f 01 <addr_hi> <addr_lo> 00 00 00 a4 a4` — end marker
5. `07 20` (all zeros) — leave write mode

A block is always written whole, even when one field changes. The app pauses longer every
8 packets, so flash pages are `0x80` words.

After a button block the app also sends `0e` (get), `0e 80 00.. 64 64 64 64`, `0f .. 07` and
`0c .. 02 80 01`; after a sensitivity block it sends `0d` (current DPI) and `13` (calibration).
The five steps above alone are enough for the sensitivity block [C]; for the button block we
have only ever sent the full app sequence.

### Header and checksum [C]

| Word | Value |
|---|---|
| 0, 1 | `ffff ffff` when written (in memory afterwards: `a4a4 ffff`) |
| 2 | sum of the words with index ≥ 4, mod 2^16 |
| 3 | sum of `index × word` for index ≥ 4, mod 2^16 |

The index counts from the start of the block. Verified on 7 writes from the capture, on blocks
from three memory dumps, and by writing a modified block whose checksum we computed ourselves
(`tools/write_sessions.py` checks it automatically). These are the "magic 4 bytes" that prior
art for the P85 could not explain.

## Button block (`0x1b00`)

### Structure [C on four blocks from two mice]

Offsets are in words from the start of the block. `h[n]` = header word with index `n`.

| Range | Content |
|---|---|
| `0`–`15` | header: `h[4]` = `0200`; `h[5]`, `h[6]` unknown (`0040 0001` from the new app, `0000 000a` from an old one); `h[12]` = `ffff` |
| `0x10` – `h[11]` | sequences (macros), each terminated by `262f` |
| `h[11]`, 16 words | special function table (`262e`, `c0xx` references) |
| `h[10]−6`, 12 words | two 6-word records (among them `0064 0064 0064`), meaning unknown |
| `h[10]+6` – `h[7]` | 1–3 button tables of 48 words (24 slots) each |
| `h[7]`, 3 words | offsets of the button tables of profiles 1, 2, 3 (may all point to the same one) |
| `h[7]+3`, 6 words | three pairs `262c 262b` (probably scroll) |
| `h[8]` = `h[7]+9`, 3 words | offsets of those pairs |
| `h[7]+12` – `h[9]` | a 324-word table of pairs for keyboard keys |
| `h[9]`, 3 words | offsets of that table for the three profiles |
| `h[9]+3` – `h[13]` | macro records (`0000 0000 a4a4`), may be empty |
| `h[13]`, 10 words | five (offset, 0) pairs |

Block length = `h[13] + 10`, zero padded to a multiple of 16. The area in the mouse's memory
ends at `0x1d7f`, so a block can have at most 640 words.

After the first remap the app adds a second button table (profile 1 gets its own, profiles 2
and 3 stay on the default one), hence the growth from 512 to 560 words.

Inserting `n` words of a new sequence at offset `h[11]` requires adding `n` to `h[7]`, `h[8]`,
`h[9]`, `h[10]`, `h[11]`, `h[13]` and to every offset in the small tables at `h[7]`, `h[8]`,
`h[9]` and `h[13]`. Existing `c0xx` references do not change, because they point at sequences
located earlier. [H — derived by comparing blocks, not yet verified by writing to a mouse]

### Button table

On the first mouse after the flash the profile 1 table starts at `0x1b58`. Each button is a
pair of words: the action on press and the action on release.

| Address | Slot | Button | Default | Confidence |
|---|---|---|---|---|
| `0x1b58` | 0 | left | `2501 2401` | C |
| `0x1b5a` | 1 | right | `2502 2402` | C |
| `0x1b5c` | 2 | middle | `2504 2404` | C |
| `0x1b5e` | 3 | side "back" | `2508 2408` | C |
| `0x1b60` | 4 | side "forward" | `2510 2410` | C |
| `0x1b62`–`0x1b66` | 5–7 | undescribed (`262e`, `c010`) | | H |
| `0x1b68` | 8 | top "1" | `2627 262e` (CPI+) | C |
| `0x1b6a` | 9 | top "N" | `2625 262e` (CPI−) | H |
| `0x1b6c` | 10 | top "3" | `262a 262e` ("mouse specific key") | H |

The table offset is not fixed: it is the profile's entry in the table at `h[7]`
(`0x58` on the first mouse, `0x6a` on the second) [C on two samples].

Action word = `opcode << 8 | parameter`:

| Opcode | Meaning | Confidence |
|---|---|---|
| `25` / `24` | mouse button press / release; parameter = mask (`01` L, `02` R, `04` M, `08` back, `10` forward) | C |
| `21` / `20` | key press / release; parameter = HID usage code (`04` = A, `05` = B, `06` = C) | C |
| `26` | special function; `2e` = no action, `27` = CPI+, `25` = CPI−, `2a` = special key | H |
| `23` / `22` | modifier press / release (mask, `01` = Ctrl) | C |
| `c0` | run the sequence at the word offset given by the parameter | C |
| `28` | delay inside a sequence | H |
| `39` / `38`, `34`–`36` / `30`–`32` | multimedia and other functions | H |

### Sequences (macros) [C on two mice]

Sequences of actions live before the button table, from word `0x10`. A button slot can hold
`c0xx` instead of an action — a reference to the sequence at offset `xx` words from the start
of the block (separately for press and release). `262f` ends a sequence.

Examples from the memory of the second mouse (configured by its owner years ago):

- offset `0x10`: `2301 2106 262f` = Ctrl down, C down, end; offset `0x13`: `2006 2201 262f`
  = C up, Ctrl up, end. Side button slot: `c010 c013` → Ctrl+C.
- offsets `0x16` / `0x19`: the same with code `19` → Ctrl+V.

On the first mouse offset `0x10` holds `2501 2840 2401 2840 2501 2840 2401 262f` — a double
click with delays.

Observed changes made by the app:

- forward → `A`: slot 4 = `2104 2004`
- back → `B`: slot 3 = `2105 2005`
- "1" → `C`: slot 8 = `2106 2006`

## Sensitivity block (`0x1a00`)

- word 4 = number of levels − 1
- word 5 = index of the selected level [H]
- from word 6: five triples `(a, a, 0x80 | r)`, one per DPI level
- word `0x1e` = polling rate in the encoding of the `0d` frame (matches the byte the app
  sends) [H], word `0x1f` = sensor calibration [H]
- from word `0x25`: a table of 16 words `8002 8004 … 820b`, meaning unknown

Samples from the app:

| DPI shown by the app | `a` | `r` |
|---|---|---|
| 800 | `0b` | 2 |
| 1000 | `0e` | 2 |
| 1200 | `0c` | 3 |
| 1600 (probably) | `0d` | 4 |
| 2100 | `0e` | 5 |
| 3200 | `10` | 7 |

Hypothesis that fits all samples approximately: `DPI ≈ 25 × (r + 1) × a`, i.e. `r` selects a
base resolution of `400 × (r + 1)` and `a` scales it in sixteenths. The app rounds (800 gives
825, 1000 gives 1050) [H]. Old configurations from two mice also contain the pairs `(0c, 1)`,
`(0a, 1)` and `(10, 5)`, which the formula reads as 600, 500 and 2400.

## Firmware flash [C]

The vendor app flashes **without asking** when it has newer firmware than the mouse:

1. `07 28 01 .. f4 ee`, then `07 00` — the mouse restarts as a bootloader `09da:d020`
   (one HID interface, `bcdDevice 0.02`).
2. In the bootloader: `06`, `04` (read ID), a series of `07 01 78 <addr> ..` writes, finally
   `07 00`.
3. The mouse returns under its original PID with the new firmware version.

When passing the mouse through to a VM, follow the USB port rather than the PID; otherwise the
bootloader stays on the host and the flash hangs at 0%.

## Open questions

- slots "N" and "3" and the remaining special function codes
- meaning of slots 5–7, of `h[5]`/`h[6]` and of the table at word `0x25` of the sensitivity block
- the exact DPI rounding rule
- which profile is active and how it is switched
- a block with a newly inserted sequence has not been written to a real mouse yet
