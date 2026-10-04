"""Check minimal Leaf configuration and SOCKS5 on MIPS 24KEc, without a remote node."""
import contextlib
import json
import pathlib
import socket
import subprocess
import sys
import tempfile
import time

binary = str(pathlib.Path(sys.argv[1]).resolve())
example = pathlib.Path(__file__).resolve().parent.parent / "leaf-oray/leaf.example.json"
qemu = ["qemu-mipsel", "-cpu", "24KEc", binary]
with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
with tempfile.TemporaryDirectory() as directory:
    config = json.loads(example.read_text())
    config["inbounds"][0]["port"] = port
    path = pathlib.Path(directory) / "leaf.json"
    path.write_text(json.dumps(config))
    subprocess.run([*qemu, "-c", str(path), "-T"], check=True, timeout=15)
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen([*qemu, "-c", str(path)], stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 15
            while True:
                if process.poll() is not None:
                    raise RuntimeError(f"Leaf exited: {process.returncode}")
                try:
                    client = socket.create_connection(("127.0.0.1", port), timeout=2)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.1)
            with client:
                client.sendall(b"\x05\x01\x00")
                response = client.recv(2)
                assert response == b"\x05\x00", response
            print("PASS: VMess configuration and SOCKS5 handshake on MIPS 24KEc")
        except Exception:
            log.seek(0)
            print(log.read().decode(errors="replace"), file=sys.stderr)
            raise
        finally:
            if process.poll() is None:
                process.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                process.wait(timeout=3)
            if process.poll() is None:
                process.kill()
                process.wait()
