# How to reverse engineer another Bloody mouse model

This is the method that produced `PROTOCOL.md`. The model examined was the `V_P3305_010`
family (V7/V7M); other models may use different addresses and block layouts, but the route is
the same. The whole thing took one evening, most of it spent on the dead ends listed at the
bottom.

You need: Linux with KVM/libvirt, a Windows virtual machine, the original Bloody application
(BloodyWorkShop8 here), `tcpdump`, Python 3, and **a second mouse** to click with — the mouse
under study disappears from the host for the duration of the session.

## 0. Before you run anything: warnings

- **The vendor application flashes firmware without asking** when it has a newer version
  than the mouse. Dump the memory (step 2) before starting the application for the first
  time, because afterwards the original is gone.
- After flashing, the application **overwrites the user's configuration with defaults**. The
  dump from step 2 also contains the old configuration, so it can be restored later.
- Only write to the mouse with your own code once you have a dump and know how to put a block
  back. A config write is reversible; a firmware flash interrupted half way may not be.

## 1. Check that the mouse speaks the same transport

```sh
lsusb | grep -i 09da
python3 tools/bloody.py info
```

If `info` returns a model and a firmware version, the transport (72-byte feature reports with
ID `07` on interface 2) is the same and the rest of this guide applies. If not, look at the
report descriptor of the vendor interface
(`/sys/bus/usb/devices/<port>:1.2/*/report_descriptor`) and find the feature report's length
and ID in it.

The `/dev/hidrawN` node must be writable. If it is not, add a udev rule:

```
KERNEL=="hidraw*", ATTRS{idVendor}=="09da", MODE="0660", TAG+="uaccess"
```

## 2. Dump the mouse's memory

```sh
python3 dumps/dump.py dumps/my-mouse-before.txt unlock 4000
```

The script sends opcode `25` (unlock reading) and reads memory with opcode `02`, 32 words at a
time. Addresses are in 16-bit words. The result is the plain firmware plus the config blocks.

Config blocks are recognisable by their header `a4a4 ffff <sum1> <sum2>`. Look through the
**whole** dump, not only its tail: our first attempt ended with the wrong conclusion that the
configuration was empty, because only part of the address range had been looked at.

```sh
grep -n 'a4a4ffff' dumps/my-mouse-before.txt
```

If the mouse was ever configured, the dump alone is often enough to read the button format:
the block shows word pairs `25xx 24xx` (mouse buttons) and `21xx 20xx` (keys).

## 3. Set up the VM and the capture

The application under Wine is not usable for this — for us it needed binary patching and still
did not work properly. Windows in a virtual machine works straight away.

```sh
# let QEMU open the USB node, and load the capture module
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="09da", MODE="0666"' | sudo tee /etc/udev/rules.d/70-a4tech-bloody.rules
sudo udevadm control --reload && sudo udevadm trigger --subsystem-match=usb --attr-match=idVendor=09da
sudo modprobe usbmon

# capture the whole bus the mouse sits on (number from lsusb: "Bus 001" -> usbmon1)
sudo tcpdump -i usbmon1 -U -s 0 -Z "$USER" -w captures/session1.pcap &

# hand the mouse to the VM and keep following it across USB identity changes
tools/follow-usb-port.sh win11 1-4 &
```

The port (`1-4`) is the name of the directory in `/sys/bus/usb/devices/` whose `idVendor` is
`09da`.

The passthrough must be tied to the **port**, not to the product ID. During a flash the mouse
restarts as a bootloader (`09da:d020`) and then comes back under its old ID; an ordinary
passthrough by ID leaves the bootloader on the host while the application sits at 0% asking
for a mouse. `follow-usb-port.sh` re-attaches the device after every change.

Start the capture **before** attaching the mouse to the VM, so that initialisation and a
possible flash are captured too.

## 4. The session: one change at a time

In the application change **one setting, apply, write down** exactly what you did and in what
order. Without notes the frames are guesswork. For us these were enough:

1. backlight brightness 0 → 1 → 2 → 3 → 0 (an easily recognised sequence to warm up)
2. one side button to the letter `A`
3. the other side button to the letter `B`
4. a top button to the letter `C`
5. one DPI level to a different value

Use letters as targets: HID key codes (`04` = A, `05` = B, `06` = C) stand out immediately in
a hex dump.

If you forget to note the values, take a screenshot of the VM
(`virsh -c qemu:///system screenshot win11 screen.ppm`) — the application shows the current
state.

## 5. Decoding

```sh
python3 tools/decode_usbmon.py captures/session1.pcap            # 07.. frames, both directions
python3 tools/decode_usbmon.py captures/session1.pcap --intr     # plus interrupt reports
python3 tools/decode_usbmon.py captures/session1.pcap | python3 tools/write_sessions.py
python3 tools/decode_usbmon.py captures/session1.pcap | python3 tools/write_sessions.py --dump
```

`decode_usbmon.py` extracts the data of control transfers that start with `07` from the pcap.
The application polls the mouse continuously with opcodes `1f`, `05` and `29` — filter them out
(`grep -vE ' 07(1f|05|29)'`) to see the rest.

`write_sessions.py` assembles every block write into a memory image, verifies its checksum and
**shows the difference from the previous write of the same block**. This is the main working
tool: changing one button produces a difference in two words (press and release action) plus
the two checksum words.

If your model uses other write opcodes, adjust the condition in `write_sessions.py`
(`b[1] == 0x2F and b[2] == 0x79`); a block write is recognisable as a run of frames with an
increasing address.

## 6. The checksum

The block header contains two words that change with every edit. What worked:

1. Take two writes that differ in one field and compute how much the checksum words changed.
2. The first word changed by exactly the sum of the data changes → a plain sum of words mod
   2^16.
3. The second changed by `change × position` → a sum weighted by the word index.
4. Check the hypothesis on every write in the capture and on the blocks in the memory dumps.

Here: `sum1 = Σ word[i]`, `sum2 = Σ i × word[i]` for `i ≥ 4`, index counted from the start of
the block. Another model may differ in range or in where the index starts — loop over a few
index offsets (say −8 to 8) and see which one matches on all blocks.

## 7. Block structure

Compare **several blocks at once**: the application's default, one after a remap, and blocks
from dumps of other units. Pointers inside a block give themselves away: between blocks of
different length they grow by exactly the length of the inserted part. That is how it turned
out that the button table has no fixed address but an offset stored in the block, and that
macros live in front of it.

## 8. The first write of your own

1. Replay, byte for byte, a write that is already in the mouse (a test that changes nothing)
   and compare the readback.
2. Write a block with one field changed and the checksum recomputed; compare the readback, and
   compare your checksum with what the application sent for the same content.
3. Only then check by hand that the mouse behaves as written.

```sh
python3 tools/bloody.py read-block 1b00 560
python3 tools/bloody.py write-block 1b00 dumps/my-mouse-before.txt 602
```

A matching readback only means the data is in memory. Whether the firmware understands it
shows only when you press the buttons.

## What did not work

- **The application under Wine (Bottles).** It needed two start-up failures patched out of the
  exe, then drew an empty window and quit on its own. The white window was caused by one of
  the patches. Hours lost; a VM solves it in fifteen minutes.
- **Identifying the model by PID or by firmware file name.** The PID is different for every
  unit. Opcode `1f` gives the model.
- **Carrying addresses over from another model.** Prior art for the P85 has the sensitivity
  block at `0x2a00` and writes with opcode `01`; the V7 uses `0x1a00` and `2f`. The "live"
  opcodes (brightness, current DPI) did match.
- **USB passthrough by product ID.** See step 3.

## What not to publish

Memory dumps contain the vendor's firmware, and captured sessions contain firmware and serial
numbers. In this repository `dumps/*.txt` and `captures/` are in `.gitignore`. Only the bare
config blocks are committed, as test data (`tests/fixtures/`).
