"""Synthetic endpoints. Only the X relay can request P on behalf of G."""
import json
import socket
import socketserver
import sys
import time

node = sys.argv[1]


class Endpoint(socketserver.StreamRequestHandler):
    def handle(self):
        while True:
            line = self.rfile.readline(4096)
            if not line:
                return
            request = json.loads(line)
            response = {"node": node, "sequence": request["sequence"], "at": time.time(), "synthetic": True}
            if node == "x":
                try:
                    with socket.create_connection(("10.77.1.2", 9300), timeout=0.3) as connection:
                        connection.sendall(line)
                        response["protected_reached"] = bool(connection.recv(4096))
                except OSError:
                    response["protected_reached"] = False
            self.wfile.write(json.dumps(response).encode() + b"\n")
            self.wfile.flush()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


Server(("0.0.0.0", 9300), Endpoint).serve_forever()
