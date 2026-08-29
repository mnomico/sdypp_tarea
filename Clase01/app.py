import json
import os
import platform
import signal
import socket
import sys
import threading
import time
from datetime import datetime
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler

# --- Configuración de la aplicación ---
APP_NAME = "python"
LENGUAJE = f"Python {platform.python_version()}"
EQUIPO = ["Tomás", "Salvador", "Mateo N."]  # Completar con los integrantes del equipo
VERSION = 1
MENSAJE = "hola mundo python"

# Metadatos del entorno y arranque
HOST = os.environ.get("HOST", socket.gethostname())
ARRANCADO = datetime.now().astimezone().isoformat()

class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Normalizar la ruta ignorando query params y trailing slash
        path = self.path.split("?")[0].rstrip("/")
        if path == "":
            path = "/"

        if path == "/":
            response_data = {
                "app": APP_NAME,
                "lenguaje": LENGUAJE,
                "equipo": EQUIPO,
                "version": VERSION,
                "mensaje": MENSAJE,
                "host": HOST,
                "arrancado": ARRANCADO,
            }
            self._send_json(200, response_data)
        elif path == "/health":
            response_data = {
                "status": "ok",
                "app": APP_NAME,
                "version": VERSION,
            }
            self._send_json(200, response_data)
        elif path == "/slow":
            # Endpoint para probar Graceful Shutdown y Drenado de Conexiones en la demo
            print("[/slow] Procesando petición lenta (simulando tarea de 4 segundos)...")
            time.sleep(4)
            response_data = {
                "status": "ok",
                "mensaje": "Petición lenta completada con éxito a pesar de recibir la orden de apagado.",
                "app": APP_NAME,
                "version": VERSION,
            }
            self._send_json(200, response_data)
            print("[/slow] Petición lenta finalizada.")
        else:
            self._send_json(404, {"error": "Not Found"})

    def do_POST(self):
        # Normalizar la ruta ignorando query params y trailing slash
        path = self.path.split("?")[0].rstrip("/")
        if path == "":
            path = "/"

        if path == "/echo":
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                self._send_json(400, {"error": "Cuerpo de la petición vacío"})
                return

            try:
                body = self.rfile.read(content_length)
                payload = json.loads(body.decode("utf-8"))
            except Exception:
                self._send_json(400, {"error": "JSON inválido"})
                return

            ping_value = payload.get("ping", "")
            response_data = {
                "pong": ping_value,
                "servidoPor": APP_NAME,
                "version": VERSION,
            }
            self._send_json(200, response_data)
        else:
            self._send_json(404, {"error": "Not Found"})

    def _send_json(self, status_code: int, data: dict):
        response_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {self.address_string()} - {format % args}")


def run(port: int = 8000):
    server_address = ("0.0.0.0", port)
    httpd = ThreadingHTTPServer(server_address, RequestHandler)
    
    # Manejador de señales para Graceful Shutdown (SIGINT y SIGTERM)
    def stop_server(signum, frame):
        sig_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
        print(f"\n[ Graceful Shutdown ] Recibida señal {sig_name} (señal {signum}). Drenando conexiones y apagando servidor de forma limpia...")
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, stop_server)
    signal.signal(signal.SIGTERM, stop_server)

    print(f"Servidor iniciado en http://0.0.0.0:{port} (PID: {os.getpid()}) (Arrancado: {ARRANCADO})")
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        # Esperar a que las hebras de peticiones en curso (in-flight) finalicen
        main_thread = threading.main_thread()
        for t in threading.enumerate():
            if t is not main_thread and t.is_alive():
                t.join(timeout=10)
        print("[ Graceful Shutdown ] Puerto TCP liberado y servidor detenido exitosamente.")


if __name__ == "__main__":
    # Permite pasar el puerto como argumento o variable de entorno PORT (default: 8000)
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", 8000))
    run(port)

