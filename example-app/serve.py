#!/usr/bin/env python3
import http.server, socketserver, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
PORT = 3000
with socketserver.TCPServer(("", PORT), http.server.SimpleHTTPRequestHandler) as httpd:
    print(f"Serving at http://localhost:{PORT}")
    httpd.serve_forever()
