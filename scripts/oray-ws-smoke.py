"""Verify the real MIPS SOCKS -> WebSocket -> VMess chain against a local mock."""
import base64
import contextlib
import hashlib
import json
import pathlib
import queue
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time


def exact(sock, size):
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise EOFError("connection closed before complete WebSocket frame")
        data.extend(chunk)
    return bytes(data)


def websocket_peer(listener, result):
    try:
        with listener.accept()[0] as sock:
            sock.settimeout(12)
            request = bytearray()
            while not request.endswith(b"\r\n\r\n"):
                request.extend(exact(sock, 1))
                if len(request) > 8192:
                    raise ValueError("WebSocket upgrade request too large")
            lines = request.decode("ascii").split("\r\n")
            assert lines[0] == "GET /oray/ws?test=1 HTTP/1.1", lines[0]
            headers = dict(line.split(":", 1) for line in lines[1:] if ":" in line)
            headers = {key.lower(): value.strip() for key, value in headers.items()}
            assert headers["host"] == "oray-ws.test", headers
            assert headers["upgrade"].lower() == "websocket", headers
            accept = base64.b64encode(hashlib.sha1(
                (headers["sec-websocket-key"] + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()
            ).digest())
            sock.sendall(b"HTTP/1.1 101 Switching Protocols\r\n"
                         b"Upgrade: websocket\r\nConnection: Upgrade\r\n"
                         b"Sec-WebSocket-Accept: " + accept + b"\r\n\r\n")
            head = exact(sock, 2)
            assert head[0] & 15 == 2, head  # Binary VMess transport, not plain HTTP.
            assert head[1] & 128, head  # Clients must mask frames.
            size = head[1] & 127
            if size == 126:
                size = struct.unpack(">H", exact(sock, 2))[0]
            elif size == 127:
                size = struct.unpack(">Q", exact(sock, 8))[0]
            assert 16 < size < 65536, size
            mask = exact(sock, 4)
            payload = exact(sock, size)
            payload = bytes(value ^ mask[i % 4] for i, value in enumerate(payload))
            assert not payload.startswith(b"GET "), payload[:16]
            result.put(None)
    except BaseException as error:
        result.put(error)


binary = str(pathlib.Path(sys.argv[1]).resolve())
root = pathlib.Path(__file__).resolve().parent.parent
qemu = ["qemu-mipsel", "-cpu", "24KEc", binary]
with socket.socket() as listener, socket.socket() as reserve:
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(15)
    reserve.bind(("127.0.0.1", 0))
    port = reserve.getsockname()[1]
    reserve.close()
    config = json.loads((root / "leaf-oray/leaf.vmess-ws.example.json").read_text())
    config["inbounds"][0]["port"] = port
    config["outbounds"][1]["settings"] = {
        "path": "/oray/ws?test=1", "headers": {"Host": "oray-ws.test"}
    }
    config["outbounds"][2]["settings"]["address"] = "127.0.0.1"
    config["outbounds"][2]["settings"]["port"] = listener.getsockname()[1]
    with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryFile() as log:
        path = pathlib.Path(directory) / "leaf.json"
        path.write_text(json.dumps(config))
        subprocess.run([*qemu, "-c", str(path), "-T"], check=True, timeout=15)
        result = queue.Queue()
        peer = threading.Thread(target=websocket_peer, args=(listener, result), daemon=True)
        peer.start()
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
                client.settimeout(12)
                client.sendall(b"\x05\x01\x00")
                assert exact(client, 2) == b"\x05\x00"
                host = b"example.com"
                client.sendall(b"\x05\x01\x00\x03" + bytes([len(host)]) + host + b"\x00\x50")
                client.sendall(b"GET / HTTP/1.1\r\nHost: example.com\r\n\r\n")
                error = result.get(timeout=15)
                if error is not None:
                    raise error
            print("PASS: MIPS 24KEc SOCKS5, WS path/Host upgrade and binary VMess frame")
        except BaseException:
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
