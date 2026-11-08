# PDF Document Service

Microservicio de persistencia de PDF-Extractext. Almacena en MongoDB el contenido
Markdown, la cantidad de páginas y los metadatos de los documentos. Permite
consultarlos, renombrarlos y eliminarlos; un índice único evita duplicados por
el SHA-256 del PDF original.

La API orquestadora calcula el checksum sobre los bytes originales, consulta el
servicio y, si el documento no existe, envía al Extractor el PDF y guarda su
resultado. Document Service recibe JSON; no recibe PDFs ni utiliza Redis.

## Tecnologías

- Python 3.14, FastAPI y Uvicorn para la API HTTP.
- MongoDB 7 y PyMongo para persistencia y conexiones.
- Docker Compose y Traefik para ejecución y enrutamiento.
- pytest para pruebas y k6 para una prueba de carga sencilla.

## Endpoints

| Método | Ruta | Respuesta |
| --- | --- | --- |
| POST | `/documents` | 201 si se crea; 200 con el documento original si ya existe el checksum. |
| GET | `/documents/by-checksum/{checksum}` | Documento por checksum o 404. |
| GET | `/documents/{id}` | Documento por ID o 404. |
| GET | `/documents?skip=0&limit=20` | Lista paginada; `skip >= 0` y `1 <= limit <= 100`. |
| PATCH | `/documents/{id}` | Actualiza el nombre del archivo. |
| DELETE | `/documents/{id}` | 204 sin cuerpo o 404. |
| GET | `/health/live` | Vida del proceso, sin consultar MongoDB. |
| GET | `/health`, `/health/ready` | Estado de la conexión a MongoDB. |
| GET | `/docs`, `/openapi.json` | Documentación interactiva y contrato OpenAPI. |

### Guardar un documento

`POST /documents` recibe `application/json`:

```json
{
  "checksum": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "content": "## Página 1\n\nTexto extraído.",
  "page_count": 1,
  "filename": "informe.pdf"
}
```

El checksum tiene 64 caracteres hexadecimales y se normaliza a minúsculas.
`content` contiene Markdown y puede estar vacío. `page_count` es un entero
positivo de hasta 64 bits. `filename` es opcional; si falta o es `null`, se usa
`document.pdf`. Si se envía, debe contener entre 1 y 255 caracteres después de
quitar espacios. No se aceptan campos adicionales.

La respuesta incluye esos campos, un `id` y `created_at` en UTC. Un duplicado
conserva el contenido, nombre y fecha originales. Una carrera excepcional con una
eliminación puede devolver 409; en ese caso se debe volver a consultar por checksum.

### Errores y seguimiento

Los errores usan `application/problem+json` con `detail`, `status`, `instance` y
`request_id`. Los principales son 404 para un documento inexistente, 409 para un
conflicto concurrente, 413 si el documento supera el límite BSON de MongoDB,
422 para datos inválidos y 503 si la base no está disponible o el servicio está
saturado. El 503 incluye `Retry-After: 1`.

El límite de MongoDB se aplica al Markdown y sus metadatos; es distinto del límite
sobre el PDF de entrada. El servicio propaga `X-Request-ID` y `X-Audit-Id` válidos,
genera un request ID si falta y registra solicitudes en stdout sin incluir sus cuerpos.

## Arquitectura

| Archivo | Responsabilidad |
| --- | --- |
| `app/main.py` | Rutas HTTP, correlación y límite de solicitudes. |
| `app/schemas.py` | Modelos de entrada y salida de la API. |
| `app/domain.py` | Modelo de documento, interfaz de repositorio y errores del dominio. |
| `app/service.py` | Lógica de creación y recuperación de duplicados. |
| `app/repository.py` | Adaptador de persistencia para MongoDB. |
| `app/database.py` | Conexión y configuración del pool. |
| `app/errors.py` | Respuestas HTTP de error. |

Cada proceso admite 16 solicitudes simultáneas por defecto y rechaza las adicionales
con 503. El pool admite hasta 16 conexiones de aplicación por servidor y proceso;
la espera por una conexión está limitada a 200 ms. Ambos límites son configurables
y se multiplican con los procesos y las réplicas. Se deben medir en el entorno de
uso antes de ajustarlos. `/health/live` permanece disponible cuando se alcanza el
límite de solicitudes.

La interfaz de repositorio permite implementar otro adaptador; actualmente solo
existe el de MongoDB. El índice único garantiza la deduplicación entre réplicas.

## Configuración

Copiar `.env.example` a `.env` para Docker Compose. No subir `.env` ni credenciales.
Las variables tienen estos valores predeterminados:

| Variable | Valor | Uso |
| --- | --- | --- |
| `MONGODB_URI` | `mongodb://mongodb:27017` en Compose | Dirección de MongoDB. Fuera de Compose: `mongodb://127.0.0.1:27017`. |
| `MONGODB_DATABASE` | `pdf_extractext` | Base donde se almacenan los documentos. |
| `MONGODB_TIMEOUT_MS` | `1500` | Presupuesto por operación y límites de conexión, selección y socket. |
| `MONGODB_POOL_SIZE` | `16` | Máximo de conexiones de aplicación por servidor y proceso. |
| `MONGODB_WAIT_QUEUE_MS` | `200` | Espera máxima por una conexión del pool. |
| `DOCUMENTS_MAX_IN_FLIGHT` | `16` | Solicitudes de documentos y readiness admitidas por proceso. |
| `PORT` | `8000` | Puerto interno del servicio. |
| `LOG_LEVEL` | `INFO` | Nivel de logs. |
| `TRAEFIK_DOCUMENTS_HOST` | `documents.universidad.localhost` | Host de Traefik. |
| `TRAEFIK_ENTRYPOINT` | `web` | Entry point de Traefik. |
| `DOCUMENTS_HOST_PORT` | `8001` | Puerto local usado por el Compose de desarrollo. |
| `MONGODB_HOST_PORT` | `27017` | Puerto local de MongoDB usado por el Compose de desarrollo. |
| `MONGODB_TEST_URI` | `mongodb://127.0.0.1:27017` | URI para las pruebas que requieren MongoDB. |

Los límites numéricos del pool, el tiempo de espera y la concurrencia deben ser
enteros positivos. Al iniciar, el servicio comprueba MongoDB y crea el índice único.

## Ejecutar con Docker

Requiere Docker Compose y la red externa compartida:

```bash
cp .env.example .env
# Crear solo si todavía no existe:
docker network create pdf-network
docker compose up -d --build
```

El Compose base no publica puertos en el host. Traefik debe estar conectado a
`pdf-network` y tener configurado el entry point `web`. Dentro de la red, la API
puede utilizar `DOCUMENT_SERVICE_URL=http://documents:8000`; `localhost` dentro de
un contenedor apunta al mismo contenedor. Ajustar las direcciones y TLS al despliegue.

Para acceder desde el host sin Traefik:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
curl http://127.0.0.1:8001/health/ready
```

El Compose de desarrollo publica el servicio y MongoDB solo en `127.0.0.1` y
conserva el volumen `mongo7_data`. Usar un entorno y una base de pruebas aislados
antes de ejecutar pruebas que modifiquen datos. Si otro Compose ya crea Documents
y MongoDB, elegir un único despliegue para evitar aliases o routers duplicados.

Cada contenedor de Documents tiene límites de 1 CPU y 1 GiB, y 30 s de gracia para
apagarse. Uvicorn espera hasta 10 s por solicitudes en curso. El efecto del retiro
de una réplica bajo tráfico debe comprobarse en el entorno de despliegue.

## Desarrollo y pruebas

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q -m 'not integration'
```

En Windows, activar el entorno con `.venv\Scripts\Activate.ps1`. Las pruebas sin
integración usan dobles de MongoDB. Las pruebas marcadas `integration` necesitan un
MongoDB accesible por `MONGODB_TEST_URI`; crean y eliminan bases temporales propias:

```bash
python -m pytest -q
```

### Integración de servicios

El escenario reproducible ejecuta API, Extractor, Documents y MongoDB con commits
fijados, una red interna y una base temporales. Requiere Git, Python 3 y Docker
Compose; no necesita activar el entorno virtual:

```bash
python3 scripts/integration_stack.py
```

El comando verifica las copias, construye las imágenes, ejecuta el flujo y limpia
los contenedores, red y volúmenes temporales. Los resultados quedan en
`.integration/stack/runs/<identificador>/summary.json`. Consultar la
[guía de integración](integration/current/README.md) para versiones, limpieza y
alcance. La ejecución registrada aprobó el flujo completo con el Extractor `6720c32`
y Documents `b851105`; no valida el proxy compartido ni pruebas de dos réplicas.

### Carga sencilla

Con k6 y una instancia que use una **base de pruebas aislada**:

```bash
k6 run -e RUN_ID=prueba-001 -e BASE_URL=http://documents.universidad.localhost tests/stress/documents.js
```

El script crea, consulta y elimina documentos. Usa 5 usuarios durante 15 segundos
por defecto; admite `VUS` y `DURATION`. Registrar errores, throughput, latencias,
CPU, memoria y réplicas. Esta prueba no reemplaza el benchmark del Extractor.

## Evidencia

- [Resultado de integración aprobado](integration/current/validation.md).
- [Validación y carga de Documents](docs/validation.md).
- [Ejecución histórica de integración](integration/historical/validation.md).
- [Intentos de integración previos](integration/compatibility/validation.md).
