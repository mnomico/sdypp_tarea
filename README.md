# Sistemas Distribuidos y Programación Paralela (SDyPP) - Mini-Nube

Servidor HTTP liviano desarrollado en Python para la simulación de despliegues manuales, traspaso de mando y gestión de concurrencia sobre un puerto TCP compartido.

---

## 👥 Integrantes del Equipo
* **Tomás Resnik** — Legajo 190168
* **Mateo Nomico** — Legajo 168102
* **Salvador Baez** — Legajo 195157

---

## 🚀 Endpoints de la Aplicación

| Método | Ruta | Descripción |
| :--- | :--- | :--- |
| `GET` | `/` | Retorna metadatos de la app (nombre, equipo, versión, timestamp de arranque y host). |
| `GET` | `/health` | Chequeo de salud del servicio (retorna `{"status": "ok"}`). |
| `POST` | `/echo` | Recibe JSON `{"ping": "mensaje"}` y responde `{"pong": "mensaje"}`. |
| `GET` | `/slow` | Endpoint simulador de peticiones en vuelo (sleep de 4s) para probar **Graceful Shutdown**. |

---

## 🏗️ Diagrama de Arquitectura

Tres casas, ninguna en la misma red, coordinadas por Meet/Discord. El equipo **Plataforma** monta
el servidor y reparte el acceso; **App Java** y **App Python** compiten por el mismo puerto de
producción, que es el recurso compartido en exclusión mutua.

El servidor no es una máquina expuesta a internet: es un **contenedor Docker con Ubuntu 24.04
dentro de WSL2**, en una PC hogareña detrás de NAT. Plataforma la hace alcanzable con **dos
túneles de ngrok** — uno publica el HTTP de producción, el otro publica el SSH de deploy.

```mermaid
flowchart TB
    subgraph NUBE["Internet - ngrok, region sa, cuenta free de Plataforma"]
        T1{{"TUNEL HTTP - dominio estatico<br/>publica el puerto de produccion<br/>vuelve igual tras cada reinicio"}}
        T2{{"TUNEL TCP - address aleatorio<br/>publica el SSH de deploy<br/>CAMBIA en cada arranque"}}
    end

    subgraph PLAT["Casa Plataforma - PC Windows con WSL2 - el cloud provider"]
        AG["2 agentes ngrok<br/>su inspector web guarda request y response<br/>de las dos apps, en texto plano"]
        subgraph CT["Contenedor Docker - Ubuntu 24.04"]
            APP["La app que gano el puerto<br/>java -jar tp1.jar 8080<br/>o python3 app-python.py 8080"]
            PORT{{"PUERTO 8080<br/>RECURSO EN EXCLUSION MUTUA<br/>lo escucha UN solo proceso"}}
            SSHD["sshd del contenedor<br/>cuenta de deploy COMPARTIDA<br/>mismo directorio para los dos equipos"]
            APP --> PORT
        end
        AG -->|"localhost 8080"| PORT
        AG -->|"localhost 2222 al 22 del contenedor"| SSHD
    end

    T1 -.-> AG
    T2 -.-> AG

    subgraph JAVA["Casa App Java"]
        JAR["Build con mvn<br/>produce el .jar"]
    end

    subgraph PY["Casa App Python - este repo"]
        SRC["Clase01/app.py<br/>sin Build: Python no compila"]
    end

    JAR -->|"Ship: scp por el tunel TCP"| T2
    SRC -->|"Ship: scp por el tunel TCP"| T2

    VER(("Verify DESDE OTRA CASA<br/>GET / - GET /health - POST /echo"))
    VER -->|"curl con el header de ngrok"| T1

    style PORT fill:#f96,stroke:#333,stroke-width:3px
    style T2 fill:#f7e3b5,stroke:#333
    style T1 fill:#cfe8d4,stroke:#333
```

**Qué expone cada nodo:**

- **Plataforma** expone dos cosas y ninguna es la máquina en sí: el **HTTP de producción** por el
  túnel de dominio estático, y el **acceso de deploy** (SSH) por el túnel TCP. Son los árbitros del
  recurso: si apagan un agente, el equipo que dependía de ese túnel queda afuera.
- **App Java / App Python** no exponen nada hacia afuera. Despliegan *sobre* el nodo de Plataforma,
  no corren servidor propio.
- **Recurso compartido y disputado**: el puerto `8080` del contenedor. Un puerto TCP lo escucha un
  solo proceso a la vez, así que desplegar no es "instalar al lado": es un **traspaso**.

**Asimetría entre los dos túneles.** El de producción usa un dominio estático y sobrevive a los
reinicios; el de SSH recibe un address aleatorio y **cambia cada vez que Plataforma lo levanta**.
En la práctica eso significa que el canal de deploy se rompe solo y hay que pedir el puerto nuevo,
mientras que la URL que ve el mundo se mantiene.

**Lo que el diagrama deja ver sobre seguridad.** Todo el tráfico de las dos apps pasa por los
agentes de ngrok de Plataforma, cuyo inspector guarda request y response completos en texto plano.
Y el acceso de deploy es una **cuenta de sistema compartida**: no hay forma de distinguir quién
frenó qué proceso.

---

## 🔄 Diagrama de Flujo del Pipeline (Build → Ship → Stop → Start → Verify)

```mermaid
flowchart TD
    START(["Cambio trivial en local<br/>subir VERSION y cambiar mensaje"]) --> BUILD
    BUILD["1 - BUILD<br/>Java compila con mvn hasta el .jar<br/>Python NO tiene este paso"] --> SHIP
    SHIP["2 - SHIP<br/>scp del archivo por el tunel TCP<br/>con nombre propio, sin pisar el .jar de Java"] --> TUNEL

    TUNEL{"Responde el tunel de deploy?"}
    TUNEL -->|"Connection refused"| CAIDO["El address TCP cambio o el agente esta abajo<br/>pedirle el puerto nuevo a Plataforma"]
    CAIDO --> SHIP
    TUNEL -->|"Si"| CHECK

    CHECK{"CONTENCION DEL PUERTO<br/>el 8080 esta libre?"}
    CHECK -->|"No, lo tiene la otra app"| COLISION
    CHECK -->|"Si"| STARTP

    COLISION["COLISION PASIVA - se provoca a proposito en la demo<br/>arrancar sin frenar al anterior da Address already in use<br/>la app nueva NO toma el puerto y la vieja sigue sirviendo"] --> STOP

    STOP["3 - STOP coordinado<br/>identificar el PID que tiene el 8080 y mandarle SIGTERM<br/>nunca kill -9: cortaria las peticiones en vuelo<br/>el graceful shutdown drena y recien ahi libera el puerto"] --> STARTP

    STARTP["4 - START<br/>levantar con nohup en segundo plano<br/>para que sobreviva al cierre de la sesion SSH"] --> VERIFY

    VERIFY{"5 - VERIFY, DESDE OTRA CASA<br/>curl a la URL publica con el header de ngrok"}
    VERIFY -->|"404 ERR_NGROK_3200"| E404["El tunel HTTP esta caido<br/>es del lado de Plataforma"]
    VERIFY -->|"502"| E502["El tunel vive pero nadie escucha en 8080<br/>se cayo el Start"]
    E502 --> STARTP
    VERIFY -->|"Llega HTML en vez de JSON"| EHTML["Falta el header ngrok-skip-browser-warning<br/>es la pantalla de aviso del plan free"]
    EHTML --> VERIFY
    VERIFY -->|"200 con la app y la version nuevas"| OK(["Deploy verificado<br/>anotar el downtime entre el SIGTERM y el primer 200"])

    style CHECK fill:#f96,stroke:#333,stroke-width:3px
    style COLISION fill:#f66,stroke:#333,stroke-width:2px
```

Los comandos exactos de cada paso:

> **Datos de acceso.** El host y el puerto del túnel de deploy, el usuario y su contraseña **no se
> versionan**: los publica el equipo Plataforma por Discord y cambian cada vez que reinician el
> agente de ngrok. Los `<PLACEHOLDER>` de abajo se reemplazan al momento de desplegar.


```bash
# 2 · Ship
scp -P <PUERTO_NGROK> Clase01/app.py <USUARIO>@<HOST_TCP_NGROK>:/home/<USUARIO>/app-python.py

# 3 · Stop  (dentro del servidor)
ssh -p <PUERTO_NGROK> <USUARIO>@<HOST_TCP_NGROK>
ps aux | grep -E 'java|python3'
kill <PID>

# 4 · Start
nohup python3 ~/app-python.py 8080 > ~/python.log 2>&1 &

# 5 · Verify  (desde otra casa)
curl -s -H "ngrok-skip-browser-warning: 1" https://<DOMINIO>.ngrok-free.dev/
curl -s -H "ngrok-skip-browser-warning: 1" https://<DOMINIO>.ngrok-free.dev/health
```

En la demo se provoca la **colisión pasiva a propósito** (arrancar sin coordinar el Stop), se la
reconoce por el `Address already in use`, y se muestra que la app anterior siguió sirviendo sin
enterarse. Recién después va el traspaso ordenado: Stop → Start → Verify.

---

## 🌟 Aportes Propios Justificados

---

### Aporte 1: Graceful Shutdown & Drenado de Conexiones

#### ¿En qué consiste?
Implementación de un manejador de señales a nivel del Sistema Operativo (`signal.SIGTERM` y `signal.SIGINT`) en el servidor `ThreadingHTTPServer`. 

Cuando el proceso recibe una señal de detención (`kill <PID>` o `Ctrl+C`):
1. **Deja de aceptar nuevas conexiones** cerrando el listener del socket TCP de inmediato (liberando el puerto para el siguiente despliegue).
2. **Drena las conexiones activas**: Espera a que las peticiones HTTP que ya se encontraban en curso (en ejecución en sus respectivas hebras) terminen de procesarse y responder al cliente.
3. **Apaga el proceso de forma limpia**. Quedan sockets en `TIME_WAIT` — es inevitable en TCP —
   pero el servidor activa `SO_REUSEADDR`, así que el siguiente deploy toma el 8080 igual,
   sin esperar el minuto de espera del kernel.

---

#### ¿Cómo probarlo?

1. **Iniciar el servidor en una terminal**:
   ```bash
   python3 Clase01/app.py 8080
   ```
   *Anotar el PID que imprime en pantalla (ejemplo: PID 13058).*

2. **Lanzar una petición en vuelo (lenta) desde otra terminal**:
   ```bash
   curl -i http://<IP_ADDRESS>:8080/slow
   ```
   *(Esta petición tarda 4 segundos en responder).*

3. **Inmediatamente (dentro de los 4 segundos), enviar la señal `SIGTERM` desde una tercera terminal**:
   ```bash
   # Reemplazar <PID> por el PID real de tu servidor
   kill -15 <PID>
   ```

4. **Resultado Observado**:
   * **En la terminal del `curl`**: La petición **NO se corta**. Espera sus 4 segundos y recibe un `200 OK` completo con el JSON de respuesta.
   * **En la terminal del servidor**: Se observa el log:
     ```text
     [ Graceful Shutdown ] Recibida señal SIGTERM (señal 15). Drenando conexiones y apagando servidor de forma limpia...
     [/slow] Petición lenta finalizada.
     [ Graceful Shutdown ] Puerto TCP liberado y servidor detenido exitosamente.
     ```
   * El puerto 8080 queda inmediatamente disponible para que otro integrante pueda levantar su app sin sufrir la colisión pasiva (`Address already in use`).

---

### Aporte 2: Hash de Integridad del Código en Tiempo de Ejecución (SHA-256)

#### ¿En qué consiste?
Al arrancar, la aplicación lee su propio archivo fuente (`app.py`), calcula su checksum criptográfico SHA-256 utilizando la librería estándar (`hashlib`) y lo expone en el campo `"checksum"` de las respuestas `GET /` y `GET /health`.

---

#### ¿Cómo probarlo?

1. **Consultar el hash remoto desplegado**:
   ```bash
   curl -s http://<IP_ADDRESS>:8080/health
   ```
   *Respuesta recibida:*
   ```json
   {
     "status": "ok",
     "app": "python",
     "version": 1,
     "checksum": "a3f8b1c4e5..."
   }
   ```

2. **Verificar localmente con sha256sum**:
   ```bash
   sha256sum Clase01/app.py
   ```
   Comprobar que el hash obtenido localmente coincide exactamente con el valor devuelto por el servidor remoto, confirmando la integridad.

---

### Aporte 3: Rate Limiting en Memoria (Protección contra Sobrecarga)

#### ¿En qué consiste?
Implementación de un limitador de tasa mediante el algoritmo de ventana deslizante en memoria (`Sliding Window`). Cada cliente (IP) puede realizar un máximo de 5 peticiones cada 10 segundos. Al superar este límite, el servidor bloquea temporalmente al cliente respondiendo con código HTTP `429 Too Many Requests`.

---

#### ¿Cómo probarlo?

1. **Enviar ráfaga de peticiones continuas**:
   ```bash
   for i in {1..6}; do curl -s -i http://<IP_ADDRESS>:8080/health | head -n 1; done
   ```

2. **Resultado Observado**:
   * Peticiones 1 a 5: `HTTP/1.0 200 OK`
   * Petición 6: `HTTP/1.0 429 Too Many Requests` con el JSON de error:
     ```json
     {
       "error": "Demasiadas peticiones (429 Too Many Requests)",
       "mensaje": "Se superó el límite de 5 peticiones cada 10 segundos.",
       "ip": "<IP_ADDRESS>"
     }
     ```
