import hashlib
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
import yaml

# --- Configuración de la aplicación ---
APP_NAME = "python"
LENGUAJE = f"Python {platform.python_version()}"
EQUIPO = [
    "Tomás Resnik (Legajo 190168)",
    "Mateo Nomico (Legajo 168102)",
    "Salvador Baez (Legajo 195157)",
]
VERSION = 1
MENSAJE = "hola mundo python"

# Metadatos del entorno y arranque
HOST = os.environ.get("HOST", socket.gethostname())
ARRANCADO = datetime.now().astimezone().isoformat()

def calculate_checksum() -> str:
    """Calcula el hash SHA-256 del propio archivo fuente en tiempo de arranque."""
    try:
        app_path = os.path.abspath(__file__)
        with open(app_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception as e:
        return f"error: {str(e)}"

CHECKSUM = calculate_checksum()

# Rate Limiting en Memoria (Sliding Window)
RATE_LIMIT_MAX = 5       # Máximo de peticiones permitidas por cliente
RATE_LIMIT_WINDOW = 10   # Ventana de tiempo en segundos
rate_limit_history = {}
rate_limit_lock = threading.Lock()

def check_rate_limit(ip: str) -> bool:
    """Retorna True si la IP superó el límite de peticiones en la ventana de tiempo."""
    now = time.time()
    with rate_limit_lock:
        timestamps = rate_limit_history.get(ip, [])
        valid_timestamps = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]
        if len(valid_timestamps) >= RATE_LIMIT_MAX:
            rate_limit_history[ip] = valid_timestamps
            return True
        valid_timestamps.append(now)
        rate_limit_history[ip] = valid_timestamps
        return False

class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self._normalize_path()
        client_ip = self._client_ip()

        # /health queda exento del rate limiting: es el chequeo del paso Verify del
        # pipeline y las otras casas lo consultan en ráfaga durante el traspaso.
        if path != "/health" and check_rate_limit(client_ip):
            self._send_json(429, {
                "error": "Demasiadas peticiones (429 Too Many Requests)",
                "mensaje": f"Se superó el límite de {RATE_LIMIT_MAX} peticiones cada {RATE_LIMIT_WINDOW} segundos.",
                "ip": client_ip
            })
            return

        if path == "/":
            response_data = {
                "app": APP_NAME,
                "lenguaje": LENGUAJE,
                "equipo": EQUIPO,
                "version": VERSION,
                "checksum": CHECKSUM,
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
                "checksum": CHECKSUM,
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
        path = self._normalize_path()
        client_ip = self._client_ip()
        if check_rate_limit(client_ip):
            self._send_json(429, {
                "error": "Demasiadas peticiones (429 Too Many Requests)",
                "mensaje": f"Se superó el límite de {RATE_LIMIT_MAX} peticiones cada {RATE_LIMIT_WINDOW} segundos.",
                "ip": client_ip
            })
            return

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

    def _normalize_path(self) -> str:
        """Normaliza la ruta ignorando query params y trailing slash."""
        path = self.path.split("?")[0].rstrip("/")
        return path if path else "/"

    def _client_ip(self) -> str:
        """IP real del cliente.

        La app se sirve detrás del túnel HTTP de ngrok, así que todas las peticiones
        llegan a la app desde la misma IP local (el proxy de Docker). Sin esto, el
        rate limiting trataría a todas las casas como un único cliente y bloquearía
        a la clase entera a la sexta petición. ngrok informa la IP de origen en
        X-Forwarded-For; nos quedamos con la primera de la cadena.
        """
        forwarded = self.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return self.client_address[0]

    def _send_json(self, status_code: int, data: dict):
        response_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {self.address_string()} - {format % args}")


def run(port: int = 80):
    server_address = ("0.0.0.0", port)
    httpd = ThreadingHTTPServer(server_address, RequestHandler)
    
    # Manejador de señales para Graceful Shutdown (SIGINT y SIGTERM)
    def stop_server(signum, frame):
        sig_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
        print(f"\n[ Graceful Shutdown ] Recibida señal {sig_name} (señal {signum}). Drenando conexiones y apagando servidor de forma limpia...")
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, stop_server)
    signal.signal(signal.SIGTERM, stop_server)

    print(f"Servidor iniciado en http://0.0.0.0:{port} (PID: {os.getpid()}) (SHA256: {CHECKSUM[:12]}...) (Arrancado: {ARRANCADO})")
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
    # Permite pasar el puerto como argumento o variable de entorno PORT (default: 80,
    # el puerto real expuesto desde el contenedor del servidor compartido)
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", 80))
    run(port)

