import subprocess
import threading
import os
import sys
import logging

logger = logging.getLogger("decryptor")
logging.basicConfig(level=logging.INFO)

class Decryptor:
    def __init__(self, worker_path=None):
        if worker_path is None:
            # Default to the same directory as this file
            current_dir = os.path.dirname(os.path.abspath(__file__))
            worker_path = os.path.join(current_dir, "DecryptWorker.exe")
        
        self.worker_path = worker_path
        self._lock = threading.Lock()
        self._proc = None
        self._start_worker()

    def _start_worker(self):
        with self._lock:
            if self._proc is not None:
                try:
                    self._proc.terminate()
                except:
                    pass
                self._proc = None

            logger.info(f"Starting decryption worker: {self.worker_path}")
            if not os.path.exists(self.worker_path):
                raise FileNotFoundError(f"DecryptWorker.exe not found at: {self.worker_path}")

            self._proc = subprocess.Popen(
                [self.worker_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1 # Line buffered
            )

            # Wait for READY signal, ignoring any DLL debug outputs that may precede it
            try:
                ready_line = ""
                while True:
                    line = self._proc.stdout.readline()
                    if not line:
                        break
                    line_str = line.strip()
                    if line_str == "READY":
                        ready_line = "READY"
                        break
                    else:
                        logger.warning(f"DecryptWorker startup output: {line_str}")

                if ready_line != "READY":
                    # Check if process exited early
                    stderr_content = self._proc.stderr.read() if self._proc.stderr else ""
                    self._proc.terminate()
                    self._proc = None
                    raise RuntimeError(f"DecryptWorker failed to initialize. Stderr: {stderr_content}")
                logger.info("Decryption worker initialized and ready.")
            except Exception as e:
                if self._proc:
                    try: self._proc.terminate()
                    except: pass
                    self._proc = None
                raise RuntimeError(f"Failed to start DecryptWorker: {e}")

    def decrypt(self, ciphertext: str) -> str:
        if not ciphertext:
            return ""
        
        ciphertext = ciphertext.strip()
        # Basic check: patient RRNs are encrypted with AES and base64 encoded.
        # If it doesn't look like base64, or is short, return as-is (e.g. empty or unencrypted legacy data)
        if len(ciphertext) < 10 or " " in ciphertext:
            return ciphertext

        # Acquire lock to ensure thread safety
        with self._lock:
            # Check if subprocess is still running
            if self._proc is None or self._proc.poll() is not None:
                logger.warning("Decryption worker process died. Restarting...")
                try:
                    self._proc = subprocess.Popen(
                        [self.worker_path],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        bufsize=1
                    )
                    ready_line = ""
                    while True:
                        line = self._proc.stdout.readline()
                        if not line:
                            break
                        line_str = line.strip()
                        if line_str == "READY":
                            ready_line = "READY"
                            break
                        else:
                            logger.warning(f"DecryptWorker restart output: {line_str}")

                    if ready_line != "READY":
                        raise RuntimeError("Did not receive READY signal")
                except Exception as e:
                    self._proc = None
                    logger.error(f"Failed to restart DecryptWorker: {e}")
                    return f"ERROR: DecryptWorker restart failed ({e})"

            try:
                # Write ciphertext to stdin
                self._proc.stdin.write(ciphertext + "\n")
                self._proc.stdin.flush()
                
                # Read result from stdout, filtering out DLL debug statements
                while True:
                    line = self._proc.stdout.readline()
                    if not line:
                        return "ERROR: Subprocess closed stdout"
                    response_str = line.strip()
                    if response_str.startswith("OK:"):
                        return response_str[3:]
                    elif response_str.startswith("ERROR:"):
                        logger.error(f"Worker decryption error: {response_str}")
                        return f"ERROR: {response_str[6:]}"
                    else:
                        # Log native prints from the DLL to warning and keep reading
                        logger.warning(f"DecryptWorker native print: {response_str}")
            except Exception as e:
                logger.error(f"Exception during IPC decryption: {e}")
                return f"ERROR: Exception ({e})"

    def close(self):
        with self._lock:
            if self._proc is not None:
                try:
                    self._proc.stdin.close()
                    self._proc.terminate()
                except:
                    pass
                self._proc = None

# Singleton instance
_decryptor_instance = None
_instance_lock = threading.Lock()

def get_decryptor():
    global _decryptor_instance
    if _decryptor_instance is None:
        with _instance_lock:
            if _decryptor_instance is None:
                _decryptor_instance = Decryptor()
    return _decryptor_instance
