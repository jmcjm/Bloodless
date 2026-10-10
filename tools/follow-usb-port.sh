#!/bin/bash
# Keep whatever A4Tech device sits on one USB port attached to a libvirt VM.
# The vendor app reboots the mouse into its bootloader and back; every reboot changes the
# USB device number and product ID, so a passthrough bound to one ID gets lost.
#
# Usage: follow-usb-port.sh <domain> <port, e.g. 1-4> [seconds, default 3600]
set -u
domain=$1
dev=/sys/bus/usb/devices/$2
end=$((SECONDS + ${3:-3600}))
last=""
while [ $SECONDS -lt $end ]; do
  if [ -r "$dev/idVendor" ] && [ "$(cat "$dev/idVendor")" = 09da ]; then
    num=$(cat "$dev/devnum"); pid=$(cat "$dev/idProduct"); bus=$(cat "$dev/busnum")
    if [ "$num" != "$last" ]; then
      xml=$(mktemp)
      printf "<hostdev mode='subsystem' type='usb' managed='yes'><source><vendor id='0x09da'/><product id='0x%s'/><address bus='%s' device='%s'/></source></hostdev>\n" "$pid" "$bus" "$num" > "$xml"
      if virsh -c qemu:///system attach-device "$domain" "$xml" --live >/dev/null 2>&1; then
        echo "$(date +%T) attached 09da:$pid (device $num)"
        last=$num
      fi
      rm -f "$xml"
    fi
  fi
  sleep 0.3
done
