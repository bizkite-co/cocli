
import subprocess

process = subprocess.Popen(["cocli", "fz"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
stdout, stderr = process.communicate(input=b'\x1b[A\n')

print(stdout.decode())
print(stderr.decode())

