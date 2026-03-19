"""
生产模式 Web 服务入口
"""

import os
import signal
import sys

from werkzeug.serving import make_server

from src.ui.web_app import app


class ProductionServer:
    """简易生产 WSGI 服务封装"""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.httpd = make_server(host, port, app, threaded=True)

    def serve_forever(self):
        print("StockQuant Pro production server starting")
        print(f"listen: http://{self.host}:{self.port}")
        self.httpd.serve_forever()

    def shutdown(self, *_args):
        print("StockQuant Pro production server stopping")
        self.httpd.shutdown()


def main():
    host = os.getenv("STOCKQUANT_HOST", "0.0.0.0")
    port = int(os.getenv("STOCKQUANT_PORT", "5004"))

    server = ProductionServer(host, port)
    signal.signal(signal.SIGTERM, server.shutdown)
    signal.signal(signal.SIGINT, server.shutdown)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
