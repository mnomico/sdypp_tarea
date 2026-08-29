# Sistemas Distribuidos y Cómputo Paralelo (SDyPP) - Clase 01

Servidor HTTP liviano desarrollado en Python para la simulación de despliegues manuales, traspaso de mando y gestión de concurrencia sobre un puerto TCP compartido.

---

## 👥 Integrantes del Equipo
* **Tomás**
* **Salvador**
* **Mateo N.**

---

## 🚀 Endpoints de la Aplicación

| Método | Ruta | Descripción |
| :--- | :--- | :--- |
| `GET` | `/` | Retorna metadatos de la app (nombre, equipo, versión, timestamp de arranque y host). |
| `GET` | `/health` | Chequeo de salud del servicio (retorna `{"status": "ok"}`). |
| `POST` | `/echo` | Recibe JSON `{"ping": "mensaje"}` y responde `{"pong": "mensaje"}`. |
| `GET` | `/slow` | Endpoint simulador de peticiones en vuelo (sleep de 4s) para probar **Graceful Shutdown**. |

---

## 🌟 Aportes Propios Justificados

---

### Aporte 1: Graceful Shutdown & Drenado de Conexiones (Manejo de `SIGTERM` / `SIGINT`)

#### 📌 ¿En qué consiste?
Implementación de un manejador de señales a nivel del Sistema Operativo (`signal.SIGTERM` y `signal.SIGINT`) en el servidor `ThreadingHTTPServer`. 

Cuando el proceso recibe una señal de detención (`kill <PID>` o `Ctrl+C`):
1. **Deja de aceptar nuevas conexiones** cerrando el listener del socket TCP de inmediato (liberando el puerto para el siguiente despliegue).
2. **Drena las conexiones activas**: Espera a que las peticiones HTTP que ya se encontraban en curso (en ejecución en sus respectivas hebras) terminen de procesarse y responder al cliente.
3. **Apaga el proceso de forma limpia** sin dejar sockets colgados en estado `TIME_WAIT`.

---

#### 💡 Justificación Técnica en Sistemas Distribuidos
En un escenario donde múltiples equipos comparten un mismo servidor y puerto TCP, los despliegues implican un traspaso de mando. 

* **Toma Hostil / `kill -9` (`SIGKILL`)**: Interrumpe la memoria del proceso de forma abrupta. Si un cliente estaba enviando un paquete o esperando respuesta, recibe un error fatal de red (`Connection reset by peer`). Además, el Socket TCP puede quedar retenido por el SO en `TIME_WAIT`.
* **Traspaso Ordenado / `kill -15` (`SIGTERM`) con Graceful Shutdown**: Otorga tolerancia a fallos y consistencia. Garantiza cero pérdida de datos en los clientes en vuelo y asegura que el puerto TCP quede libre exactamente en el momento en que se libera la app anterior.

---

#### 🧪 ¿Cómo probarlo en la Demo? (Paso a Paso)

Para demostrar este aporte en vivo ante la cátedra:

1. **Iniciar el servidor en una terminal**:
   ```bash
   python3 Clase01/app.py 8000
   ```
   *Anotar el PID que imprime en pantalla (ejemplo: PID 13058).*

2. **Lanzar una petición en vuelo (lenta) desde otra terminal**:
   ```bash
   curl -i http://localhost:8000/slow
   ```
   *(Esta petición tarda 4 segundos en responder).*

3. **Inmediatamente (dentro de los 4 segundos), enviar la señal `SIGTERM` desde una tercera terminal**:
   ```bash
   # Reemplazar 13826 por el PID real de tu servidor (o usar killall)
   kill -15 13826
   
   # O directamente:
   killall python3
   ```

4. **Resultado Observado (Éxito)**:
   * **En la terminal del `curl`**: La petición **NO se corta**. Espera sus 4 segundos y recibe un `200 OK` completo con el JSON de respuesta.
   * **En la terminal del servidor**: Se observa el log:
     ```text
     [ Graceful Shutdown ] Recibida señal SIGTERM (señal 15). Drenando conexiones y apagando servidor de forma limpia...
     [/slow] Petición lenta finalizada.
     [ Graceful Shutdown ] Puerto TCP liberado y servidor detenido exitosamente.
     ```
   * El puerto 8000 queda inmediatamente disponible para que otro integrante pueda levantar su app sin sufrir la colisión pasiva (`Address already in use`).

---

## 🛠️ Ejecución Local

```bash
# Ejecutar en puerto por defecto (8000)
python3 Clase01/app.py

# O especificar un puerto personalizado
python3 Clase01/app.py 8080
```