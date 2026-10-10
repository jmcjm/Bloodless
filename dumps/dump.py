import fcntl, os, sys, glob, time
def IOC(d,t,nr,sz): return (d<<30)|(sz<<16)|(ord(t)<<8)|nr
SF=IOC(3,'H',0x06,72); GF=IOC(3,'H',0x07,72)
dev=None
for h in glob.glob('/sys/class/hidraw/hidraw*'):
    u=open(h+'/device/uevent').read()
    if '000009DA' in u and 'input2' in u: dev='/dev/'+os.path.basename(h)
fd=os.open(dev,os.O_RDWR)
def q(b):
    req=bytearray(bytes(b).ljust(72,b'\0')); fcntl.ioctl(fd,SF,req)
    buf=bytearray(72); buf[0]=7; fcntl.ioctl(fd,GF,buf); return bytes(buf)
out=sys.argv[1]; unlock=len(sys.argv)>2
if unlock:
    r=q(bytes.fromhex('072500005249182201')); print('unlock resp',r.hex())
end=int(sys.argv[3],16) if len(sys.argv)>3 else 0x4000
with open(out,'w') as f:
    for a in range(0,end,0x20):
        r=q([7,2,0,a>>8,a&0xff,0x60])
        f.write(f'{a:04x}: {r[:8].hex()} {r[8:].hex()}\n')
print('done',out)
