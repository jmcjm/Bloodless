"""hidraw access to the vendor interface (interface 2) of a Bloody mouse."""
import fcntl
import glob
import os
import select

REPORT = 72
_HIDIOCSFEATURE = (3 << 30) | (REPORT << 16) | (ord("H") << 8) | 0x06
_HIDIOCGFEATURE = (3 << 30) | (REPORT << 16) | (ord("H") << 8) | 0x07


class DeviceError(OSError):
    """No usable mouse, or talking to it failed."""


def find_devices(sys_root="/sys/class/hidraw"):
    """Paths of /dev/hidrawN nodes that are the vendor interface of an A4Tech device."""
    found = []
    for node in sorted(glob.glob(os.path.join(sys_root, "hidraw*"))):
        try:
            with open(os.path.join(node, "device", "uevent")) as f:
                uevent = f.read()
        except OSError:
            continue
        if "000009DA" in uevent and "/input2" in uevent:
            found.append("/dev/" + os.path.basename(node))
    return found


class HidrawTransport:
    def __init__(self, path):
        try:
            self.fd = os.open(path, os.O_RDWR)
        except OSError as e:
            raise DeviceError(f"cannot open {path}: {e.strerror}") from e

    def send(self, payload):
        try:
            fcntl.ioctl(self.fd, _HIDIOCSFEATURE, bytearray(bytes(payload).ljust(REPORT, b"\0")))
        except OSError as e:
            raise DeviceError(f"write to mouse failed: {e.strerror}") from e

    def query(self, payload):
        self.send(payload)
        buf = bytearray(REPORT)
        buf[0] = 0x07
        try:
            fcntl.ioctl(self.fd, _HIDIOCGFEATURE, buf)
        except OSError as e:
            raise DeviceError(f"read from mouse failed: {e.strerror}") from e
        return bytes(buf)

    def read_input(self, timeout):
        """One input report from the mouse, or None if none arrives within timeout seconds."""
        try:
            ready, _, _ = select.select([self.fd], [], [], timeout)
            return os.read(self.fd, 64) if ready else None
        except OSError as e:
            raise DeviceError(f"read from mouse failed: {e.strerror}") from e

    def close(self):
        os.close(self.fd)