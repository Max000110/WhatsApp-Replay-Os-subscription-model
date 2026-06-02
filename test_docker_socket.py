import socket
import json

def query_docker_socket(path: str) -> dict:
    try:
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
        if len(parts) < 2:
            return {}
        body = parts[1]
        if b"Transfer-Encoding: chunked" in parts[0]:
            decoded_body = b""
            idx = 0
            while idx < len(body):
                line_end = body.find(b"\r\n", idx)
                if line_end == -1:
                    break
                chunk_len_str = body[idx:line_end]
                try:
                    chunk_len = int(chunk_len_str, 16)
                except ValueError:
                    break
                if chunk_len == 0:
                    break
                idx = line_end + 2
                decoded_body += body[idx:idx+chunk_len]
                idx += chunk_len + 2
            body = decoded_body
        return json.loads(body.decode('utf-8'))
    except Exception as e:
        print("[Docker Socket Query] Error:", e)
        return {}

df_data = query_docker_socket("/system/df")
print(json.dumps(df_data, indent=2))
