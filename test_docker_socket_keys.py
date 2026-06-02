import socket
import json

def query_docker_socket(path: str) -> dict:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect("/var/run/docker.sock")
    req = f"GET {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"
    s.sendall(req.encode('utf-8'))
    response = b""
    while True:
        chunk = s.recv(4096)
        if not chunk:
            break
        response += chunk
    s.close()
    parts = response.split(b"\r\n\r\n", 1)
    body = parts[1]
    if b"Transfer-Encoding: chunked" in parts[0]:
        decoded_body = b""
        idx = 0
        while idx < len(body):
            line_end = body.find(b"\r\n", idx)
            if line_end == -1:
                break
            chunk_len_str = body[idx:line_end]
            chunk_len = int(chunk_len_str, 16)
            if chunk_len == 0:
                break
            idx = line_end + 2
            decoded_body += body[idx:idx+chunk_len]
            idx += chunk_len + 2
        body = decoded_body
    return json.loads(body.decode('utf-8'))

data = query_docker_socket("/system/df")
print("Keys:", list(data.keys()))
if "Images" in data:
    print("Images count:", len(data["Images"]))
    print("Images Total Size:", sum(x.get("Size", 0) for x in data["Images"]))
if "Containers" in data:
    print("Containers count:", len(data["Containers"]))
    print("Containers Total Size:", sum(x.get("SizeRw", 0) for x in data["Containers"]))
if "Volumes" in data:
    print("Volumes count:", len(data["Volumes"]))
    v_sizes = []
    for v in data["Volumes"]:
        usage = v.get("UsageData")
        if usage and usage != -1:
            v_sizes.append(usage.get("Size", 0))
    print("Volumes Total Size:", sum(v_sizes))
if "BuilderSize" in data:
    print("BuilderSize:", data["BuilderSize"])
elif "BuildCache" in data:
    # BuildCache is a list of cache records or a dict
    bc = data["BuildCache"]
    if isinstance(bc, list):
        print("BuildCache Total Size:", sum(x.get("Size", 0) for x in bc))
    elif isinstance(bc, dict):
        print("BuildCache Dict:", bc.get("TotalSize", 0))
