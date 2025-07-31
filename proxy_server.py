import socket
import threading
import select
from concurrent.futures import ThreadPoolExecutor

def ExtractHostPortFromRequest(request):
    # get the value after the "Host:" string
    host_string_start = request.lower().find(b'Host: ') + len(b'Host: ')
    host_string_end = request.find(b'\r\n', host_string_start)
    host_string = request[host_string_start:host_string_end].decode('utf-8').strip()

    # if there is a specific port
    port_pos = host_string.find(":")
    if port_pos == -1:
        if b'https://' in request[:host_string_start]:
            port = 443
        else:
            port = 80
        host = host_string
    else:
        port = int(host_string[port_pos + 1:])
        host = host_string[:port_pos]        

    # #no port specified --------------------------------------------------------
    # if port_pos == -1 or webserver_pos < port_pos:
    #     #default port
    #     port = 80
    #     host = host_string[:webserver_pos]
    # else:
    #     #extract the specific port from the host string 
    #     port = int((host_string[(port_pos + 1):])[:webserver_pos - port_pos - 1])
    #     host = host_string[:port_pos] ---------------------------------------------
    
    return host,port

def ModifyRequestHeaders(request):
    request_lines = request.decode('utf-8').split('\r\n')
    modified_request = []
    connection_header_found = False
    proxy_connection_header_found = False

    for line in request_lines:
        if "Connection: keep-alive" in line:
            modified_request.append("Connection: close")
            connection_header_found = True
        elif "Proxy-Connection: keep-alive" in line:
            modified_request.append("Proxy-Connection: close")
            proxy_connection_header_found = True
        elif "HTTP/1.1" in line:
            modified_request.append(line.replace("HTTP/1.1", "HTTP/1.0"))
        else:
            modified_request.append(line)

    # in case connection: close not present in line
    if not connection_header_found:
        modified_request.append("Connection: close")

    if not proxy_connection_header_found:
        modified_request.append("Proxy-Connection: close")
    
    return "\r\n".join(modified_request).encode('utf-8')

def ModifyResponseHeaders(response):
    response_lines = response.decode('utf-8').split('\r\n')
    modified_response = []

    for line in response_lines:
        if "Connection: keep-alive" in line:
            modified_response.append("Connection: close")
        else:
            modified_response.append(line)
    
    return "\r\n".join(modified_response).encode('utf-8')

def TunnelData(client_socket, destination_socket):
    client_socket.settimeout(5)
    destination_socket.settimeout(5)

    while True:
        try:
            sockets = [client_socket, destination_socket]
            readable, _, _ = select.select(sockets, [], [])

            if client_socket in readable:
                data = client_socket.recv(1024)
                if data:
                    destination_socket.sendall(data)
                else:
                    break
            
            if destination_socket in readable:
                data = destination_socket.recv(1024)
                if data:
                    client_socket.sendall(data)
                else:
                    break
        except socket.error as e:
            print(f"Socket error: {e}")
            break
    # client_socket.setblocking(0) ------------------------------------------------
    # destination_socket.setblocking(0)

    # while True:
    #     try:
    #         data = client_socket.recv(1024)
    #         if len(data) > 0:
    #             destination_socket.sendall(data)
    #     except:
    #         pass

    #     try:
    #         data = destination_socket.recv(1024)
    #         if len(data) > 0:
    #             client_socket.sendall(data)
    #     except:
    #         pass -----------------------------------------------------------------

def HandleClientRequest(client_socket):
    client_socket.settimeout(5)
    print("Received Request:\n")

    # read the data sent by the client in the request
    request = b''
    
    # client_socket.setblocking(False)

    while True:
        try:
            data = client_socket.recv(1024)
            request += data
            if b"\r\n\r\n" in request:
                break
        except:
            break
        # try:
        #     # receive data from web server
        #     data = client_socket.recv(1024)
        #     request = request + data

        #     # receive data from original destination server
        #     print(f"{data.decode('utf-8')}")
        # except:
        #     break
    
    # parse the request line to determine if its a CONNECT request
    request_line = request.split(b'\r\n')[0].decode('utf-8')
    method, url, _ = request_line.split(' ')

    # Log the request line
    print(f">>> {method} {url}")

    if method == 'CONNECT':
        host_port = url.split(':')
        host = host_port[0]
        port = int(host_port[1]) if len(host_port) > 1 else 443

        try:
            # create a TCP connection to the destination server
            destination_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            destination_socket.connect((host, port))
            destination_socket.settimeout(5)
            # respond with 200 OK to establish the tunnel
            client_socket.send(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            print(f"Established tunnel to {host}:{port}")
        except socket.timeout:
            print(f"Connection to {host}:{port} timed out.")
            client_socket.send(b"HTTP/1.1 504 Gateway Timeout\r\n\r\n")
            client_socket.close()
            return
        except Exception as e:
            print(f"Failed to connect to {host}:{port}")
            print(f"Error: {e}")
            client_socket.send(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            client_socket.close()
            return
        
        # relay data between client and the server
        TunnelData(client_socket, destination_socket)

        destination_socket.close()
        client_socket.close()
        return
    
    else: # Handle normal HTTP requests
        host, port = ExtractHostPortFromRequest(request)
        print(f"Connecting to {host}:{port}")

        try:
            destination_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            destination_socket.connect((host, port))

            modified_request = ModifyRequestHeaders(request)
            destination_socket.sendall(modified_request)
            print(f"Sent request to {host}:{port}")

            while True:
                data = destination_socket.recv(4096)
                if not data:
                    break

                print(f"Received response from {host}:{port}, {len(data)} bytes.")
                client_socket.sendall(ModifyResponseHeaders(data))
        except socket.error as e:
            print(f"Socket Error: {e}")

            client_socket.send(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
        finally:
            destination_socket.close()
            client_socket.close()
        # --------------------------------------------------------------------------
        # destination_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # destination_socket.connect((host, port))

        # modified_request = ModifyRequestHeaders(request)
        # destination_socket.sendall(modified_request)

        # while True:
        #     data = destination_socket.recv(4096)
        #     if len(data) > 0:
        #         modified_response = ModifyResponseHeaders(data)
        #         client_socket.sendall(modified_response)
        #     else:
        #         break
        
        # destination_socket.close()
        # client_socket.close()
    # ------------------------------------------------------------
        # extract the webserver's host and port from request
        # host, port = ExtractHostPortFromRequest(request)

        # # create a socket to connect to the original destination server
        # destination_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # # connect to the destination server
        # destination_socket.connect((host, port))

        # #send the original request
        # destination_socket.sendall(request)

        # # read the data received from the server
        # # once chunk at a time and send it to the client
        # print("Received response:\n")

        # while True:
        #     # receive data from web server
        #     data = destination_socket.recv(1024)

        #     # receive data from the original destination server
        #     print(f"{data.decode('utf-8')}")

        #     # no more data to send
        #     if len(data) > 0:
        #         #send back to the client
        #         client_socket.sendall(data)
        #     else:
        #         break

        #     # close the sockets
        #     destination_socket.close()
        #     client_socket.close()
        # --------------------------------------------------------------------------

def main():

    port = 8080

    # bind the proxy server to a specific address and port
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # accept up to 10 simultaneous connections
    server_socket.bind(('127.0.0.1', port))

    server_socket.listen(10)
    print(f"Proxy listening on Port = {port}")

    thread_pool = ThreadPoolExecutor(max_workers=15)

    # accept client requests
    while True:
        client_socket, client_address = server_socket.accept()
        print(f"Accepted connection from {client_address[0]}:{client_address[1]}")

        thread_pool.submit(HandleClientRequest, client_socket)

if __name__ == "__main__":
    main()