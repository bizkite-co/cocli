
import subprocess
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

process = subprocess.Popen(["cocli", "fz"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
stdout, stderr = process.communicate(input=b'\x1b[A\n')

logger.info(stdout.decode())
logger.error(stderr.decode())

