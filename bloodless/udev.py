"""Install the udev rule that lets the logged-in user open the mouse's hidraw node."""
import os
import subprocess

from .transport import DeviceError

RULE_PATH = "/etc/udev/rules.d/70-bloodless.rules"
RULE = 'KERNEL=="hidraw*", ATTRS{idVendor}=="09da", MODE="0660", TAG+="uaccess"'
# Variables an AppImage sets for its own bundled libraries; host tools must not inherit them.
_BUNDLE_PREFIXES = ("LD_", "PYTHON", "GTK_", "GDK_", "GIO_", "GI_", "GSETTINGS_", "APPDIR",
                    "APPRUN", "APPIMAGE")
HOST_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


def script(rule_path=RULE_PATH):
    """Shell commands, to be run as root: write the rule and apply it to plugged-in devices."""
    return (f"printf '%s\\n' '{RULE}' > '{rule_path}' && udevadm control --reload"
            " && udevadm trigger --subsystem-match=hidraw --settle")


def install_command():
    """argv that asks for administrator rights and installs the rule."""
    argv = ["pkexec", "sh", "-c", script()]
    if os.path.exists("/.flatpak-info"):  # inside the sandbox pkexec has to run on the host
        argv = ["flatpak-spawn", "--host"] + argv
    return argv


def host_env(environ=None):
    """The environment without what a bundle (AppImage) added for itself."""
    environ = os.environ if environ is None else environ
    env = {k: v for k, v in environ.items() if not k.startswith(_BUNDLE_PREFIXES)}
    env["PATH"] = HOST_PATH
    return env


def failure(returncode, stderr=""):
    """None if the command succeeded, otherwise a message for the user."""
    if returncode == 0:
        return None
    if returncode in (126, 127):  # pkexec: dismissed, not authorised, or no agent to ask
        return "administrator rights were not granted, the udev rule was not installed"
    detail = stderr.strip().splitlines()[-1] if stderr.strip() else f"exit code {returncode}"
    return f"installing the udev rule failed: {detail}"


def install(run=subprocess.run):
    """Install the rule, asking for a password; raises DeviceError if that does not work."""
    try:
        result = run(install_command(), env=host_env(), capture_output=True, text=True)
    except FileNotFoundError:
        raise DeviceError(
            f"pkexec is not available; as root, write this line to {RULE_PATH}: {RULE}") from None
    message = failure(result.returncode, result.stderr)
    if message:
        raise DeviceError(message)
