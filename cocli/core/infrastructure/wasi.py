import hashlib
import logging
from pathlib import Path
from typing import Optional, List, Dict
import wasmtime

logger = logging.getLogger(__name__)

class WasiRunner:
    """
    Handles execution of immutable WASI modules for data transformation.
    Ensures code-addressable integrity via module hashing.
    """
    def __init__(self, wasm_path: Path):
        self.wasm_path = wasm_path
        self._hash: Optional[str] = None
        self.engine = wasmtime.Engine()
        self.linker = wasmtime.Linker(self.engine)
        self.linker.define_wasi()

    @property
    def wasi_hash(self) -> str:
        """Returns the SHA-256 hash of the WASM binary."""
        if self._hash is None:
            sha256 = hashlib.sha256()
            with open(self.wasm_path, "rb") as f:
                while chunk := f.read(8192):
                    sha256.update(chunk)
            self._hash = sha256.hexdigest()
        return self._hash

    def run(self, 
            args: List[str], 
            dirs: Dict[str, str], 
            env: Optional[Dict[str, str]] = None) -> int:
        """
        Executes the WASI module with specific arguments and directory mappings.
        dirs: mapping of guest_path -> host_path
        """
        store = wasmtime.Store(self.engine)
        
        # Configure WASI
        wasi_config = wasmtime.WasiConfig()
        wasi_config.argv = [self.wasm_path.name] + args
        
        # Map directories for USV I/O
        for guest, host in dirs.items():
            wasi_config.preopen_dir(host, guest)
            
        if env:
            wasi_config.env = list(env.items())
            
        store.set_wasi(wasi_config)
        
        # Load and instantiate module
        module = wasmtime.Module.from_file(self.engine, self.wasm_path)
        instance = self.linker.instantiate(store, module)
        
        # Get start function
        start = instance.exports(store).get("_start")
        if not start or not isinstance(start, wasmtime.Func):
            raise RuntimeError("WASM module does not have a valid _start function.")
            
        try:
            start(store)
            return 0
        except wasmtime.WasmtimeError as e:
            # Handle non-zero exit codes (which are common in CLI tools)
            # Extract exit code if possible
            msg = str(e)
            if "exit code" in msg:
                try:
                    return int(msg.split("exit code")[-1].strip())
                except Exception:
                    pass
            logger.error(f"WASI execution failed: {e}")
            raise
