import socket
import select
from concurrent.futures import ThreadPoolExecutor

def extract_host_port(request):
    start = request.lower().find(b'host: ') + len(b'host: ')
    end = request.find(b'\r\n', start)
    host_line = request[start:end].decode().strip()

    if ':' in host_line:
        host, port = host_line.split(':')
        return host, int(port)
    else:
        default_port = 443 if b'https://' in request[:start] else 80
        return host_line, default_port

def modify_request_headers(request):
    lines = request.decode().split('\r\n')
    modified = []
    has_conn = has_proxy_conn = False

    for line in lines:
        if "Connection: keep-alive" in line:
            modified.append("Connection: close")
            has_conn = True
        elif "Proxy-Connection: keep-alive" in line:
            modified.append("Proxy-Connection: close")
            has_proxy_conn = True
        elif "HTTP/1.1" in line:
            modified.append(line.replace("HTTP/1.1", "HTTP/1.0"))
        else:
            modified.append(line)

    if not has_conn:
        modified.append("Connection: close")
    if not has_proxy_conn:
        modified.append("Proxy-Connection: close")

    return "\r\n".join(modified).encode()

def modify_response_headers(response):
    try:
        lines = response.decode().split('\r\n')
        modified = [
            "Connection: close" if "Connection: keep-alive" in line else line
            for line in lines
        ]
        return "\r\n".join(modified).encode()
    except UnicodeDecodeError:
        return response

def tunnel_data(client_sock, dest_sock):
    client_sock.settimeout(5)
    dest_sock.settimeout(5)

    sockets = [client_sock, dest_sock]
    try:
        while True:
            readable, _, _ = select.select(sockets, [], [])
            for sock in readable:
                data = sock.recv(4096)
                if not data:
                    return
                (dest_sock if sock == client_sock else client_sock).sendall(data)
    except Exception as e:
        print(f"[Tunnel Error] {e}")

def handle_client_request(client_sock):
    client_sock.settimeout(5)
    request = b''

    while True:
        try:
            data = client_sock.recv(1024)
            request += data
            if b"\r\n\r\n" in request:
                break
        except:
            client_sock.close()
            return

    try:
        request_line = request.split(b'\r\n')[0].decode()
        method, url, _ = request_line.split(' ')
        print(f">>> {method} {url}")
    except Exception as e:
        print(f"[Parse Error] {e}")
        client_sock.close()
        return

    if method.upper() == 'CONNECT':
        host, port = url.split(':')
        port = int(port) if port else 443

        try:
            dest_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            dest_sock.connect((host, port))
            client_sock.send(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            print(f"Established tunnel to {host}:{port}")
            tunnel_data(client_sock, dest_sock)
        except socket.timeout:
            print(f"Timeout connecting to {host}:{port}")
            client_sock.send(b"HTTP/1.1 504 Gateway Timeout\r\n\r\n")
        except Exception as e:
            print(f"[CONNECT Error] {e}")
            client_sock.send(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
        finally:
            client_sock.close()
            if 'dest_sock' in locals():
                dest_sock.close()
        return

    else:
        try:
            host, port = extract_host_port(request)
            print(f"Connecting to {host}:{port}")

            dest_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            dest_sock.connect((host, port))

            modified_req = modify_request_headers(request)
            dest_sock.sendall(modified_req)

            while True:
                data = dest_sock.recv(4096)
                if not data:
                    break
                client_sock.sendall(modify_response_headers(data))

        except Exception as e:
            print(f"[HTTP Error] {e}")
            client_sock.send(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
        finally:
            client_sock.close()
            if 'dest_sock' in locals():
                dest_sock.close()

def main():
    host = '127.0.0.1'
    port = 8080

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((host, port))
    server_sock.listen(10)
    print(f"Proxy server listening on {host}:{port}")

    pool = ThreadPoolExecutor(max_workers=15)

    try:
        while True:
            client_sock, addr = server_sock.accept()
            print(f"Accepted connection from {addr[0]}:{addr[1]}")
            pool.submit(handle_client_request, client_sock)
    except KeyboardInterrupt:
        print("Shutting down proxy server...")
    finally:
        server_sock.close()

if __name__ == "__main__":
    main()
