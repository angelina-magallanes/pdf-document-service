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
- uv y `uv.lock` para resolver e instalar dependencias reproducibles.
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
| GET | `/metrics` | Métricas Prometheus; requiere Bearer. |
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

El JSON entrante tiene un límite configurable de **4 MiB** y un plazo total de
recepción de **15 segundos**. Se cuentan bytes mientras llegan, incluso sin
Content-Length, antes de acumular un cuerpo ilimitado. El límite excedido devuelve
413 y el plazo agotado 408. Estos límites corresponden al JSON de Documents, no
al PDF de entrada del Extractor.

El listado conserva todos sus campos, incluido `content`, pero tiene un presupuesto
conservador configurable de **8 MiB** por página. Si lo excede devuelve 413: reducir
`limit` o consultar por ID. No trunca contenido ni devuelve páginas parciales.
MongoDB entrega lotes de un documento y el cursor se cierra incluso al fallar.
También se conserva el rechazo por tamaño BSON de MongoDB. El servicio propaga `X-Request-ID` y `X-Audit-Id` válidos,
genera un request ID si falta y registra solicitudes en stdout sin incluir sus cuerpos.

## Autenticación entre servicios

Todas las operaciones de documentos requieren una credencial compartida:

```http
Authorization: Bearer <DOCUMENTS_API_TOKEN>
```

`DOCUMENTS_API_TOKEN` es obligatorio y no tiene valor predeterminado. Generar un
secreto aleatorio y guardarlo en el `.env` local o en el gestor de secretos del
despliegue, nunca en Git:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

El valor debe tener al menos 32 caracteres sin espacios; se admiten los caracteres
ASCII habituales de tokens Bearer. Al iniciar se valida antes de contactar a
MongoDB. Si falta o es inválido, el servicio no arranca. Cambiar la variable exige
reiniciar Documents; coordinar la misma actualización en sus consumidores.

Sin credencial o con una credencial incorrecta, la respuesta es **401** con
`WWW-Authenticate: Bearer` y `application/problem+json`. La comprobación ocurre
antes de validar el cuerpo o acceder a MongoDB. La comparación del secreto usa
`compare_digest`; el token no se incluye en logs ni en respuestas.

`/health`, `/health/live` y `/health/ready` permanecen públicas para las sondas.
También son públicas `/docs`, `/redoc` y `/openapi.json`, que muestran el contrato,
no los documentos almacenados. En Swagger usar **Authorize**, ingresar solamente
el valor del token y luego ejecutar las operaciones.

### Configuración de la API consumidora

La API orquestadora debe obtener el mismo secreto desde su propia configuración
y adjuntar `Authorization: Bearer ...` en **todas** las llamadas a `/documents`,
incluidas las búsquedas por checksum. Ejemplo con un cliente HTTP:

```python
headers = {"Authorization": f"Bearer {os.environ['DOCUMENTS_API_TOKEN']}"}
response = await client.get(
    f"{documents_url}/documents/by-checksum/{checksum}", headers=headers,
)
```

Este ejemplo se configura en el repositorio consumidor; los nombres de variables
deben acordarse allí. Infraestructura también debe pasar `DOCUMENTS_API_TOKEN`
al contenedor de Documents si usa su propio Compose. Coordinar ambos cambios
antes de desplegar esta revisión: una API que no envíe la credencial recibirá 401.

Esta autenticación identifica a los consumidores que conocen el secreto; no
implementa usuarios, roles ni permisos por documento. Transportar el token por
HTTPS si las llamadas atraviesan redes no confiables. No publicar MongoDB sin
los controles propios de la base. Los límites de cuerpo, página y BSON se aplican además de la autenticación.

## Arquitectura

| Archivo | Responsabilidad |
| --- | --- |
| `app/main.py` | Composición de la aplicación y registro de componentes. |
| `app/routers/documents.py` | Rutas HTTP de documentos y salud. |
| `app/middleware.py` | Autenticación previa al cuerpo, correlación y admisión. |
| `app/dependencies.py` | Recursos compartidos, construcción del servicio y ciclo de vida. |
| `app/auth.py` | Validación del secreto y autenticación Bearer. |
| `app/schemas/documents.py` | Modelos de entrada y salida de la API. |
| `app/models/` | Entidad de documento y errores del dominio. |
| `app/repositories/base.py` | Interfaz del repositorio del dominio. |
| `app/services/documents.py` | Lógica de creación y recuperación de duplicados. |
| `app/repositories/mongodb.py` | Adaptador de persistencia para MongoDB. |
| `app/database.py` | Conexión y configuración del pool. |
| `app/settings.py` | Límites configurables de recepción y listado. |
| `app/body_limit.py` | Conteo incremental de bytes y plazo de recepción. |
| `app/storage_errors.py` | Traducción de errores MongoDB al contrato del dominio. |
| `app/metrics.py` | Contadores, histograma y exposición Prometheus. |
| `app/errors.py` | Respuestas HTTP de error. |

Cada proceso admite 16 solicitudes simultáneas por defecto y rechaza las adicionales
con 503. El cupo se conserva hasta completar el envío de la respuesta. El pool admite hasta 16 conexiones de aplicación por servidor y proceso;
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
| `DOCUMENTS_API_TOKEN` | Sin valor por defecto; obligatorio | Secreto compartido de acceso a los documentos. |
| `MONGODB_URI` | `mongodb://mongodb:27017` en Compose | Dirección de MongoDB. Fuera de Compose: `mongodb://127.0.0.1:27017`. |
| `MONGODB_DATABASE` | `pdf_extractext` | Base donde se almacenan los documentos. |
| `MONGODB_TIMEOUT_MS` | `1500` | Presupuesto por operación y límites de conexión, selección y socket. |
| `MONGODB_POOL_SIZE` | `16` | Máximo de conexiones de aplicación por servidor y proceso. |
| `MONGODB_WAIT_QUEUE_MS` | `200` | Espera máxima por una conexión del pool. |
| `DOCUMENTS_MAX_IN_FLIGHT` | `16` | Solicitudes de documentos y readiness admitidas por proceso. |
| `PORT` | `8000` | Puerto interno del servicio. |
| `DOCUMENTS_MAX_BODY_BYTES` | `4194304` | Máximo del cuerpo HTTP completo, en bytes. |
| `DOCUMENTS_MAX_LIST_BYTES` | `8388608` | Presupuesto conservador del listado JSON completo. |
| `DOCUMENTS_BODY_TIMEOUT_SECONDS` | `15` | Plazo total para recibir el cuerpo HTTP. |
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
# Completar DOCUMENTS_API_TOKEN en .env con el secreto generado.
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
uv sync --locked
uv run --locked pytest -q -m 'not integration'
```

Instalar previamente [uv](https://docs.astral.sh/uv/getting-started/installation/).
`uv sync` crea el entorno automáticamente, también en Windows. Las pruebas sin
integración usan dobles de MongoDB. Las pruebas marcadas `integration` necesitan un
MongoDB accesible por `MONGODB_TEST_URI`; crean y eliminan bases temporales propias:

```bash
uv run --locked pytest -q
```

Las pruebas usan una credencial ficticia propia, sin leer secretos reales. Para
iniciar Uvicorn fuera de Compose, exportar `DOCUMENTS_API_TOKEN` en la terminal:
Python no carga automáticamente el archivo `.env`.

### Integración de servicios

El escenario reproducible ejecuta API, Extractor, Documents y MongoDB con commits
fijados, una red interna y una base temporales. Requiere Git, Python 3 y Docker
Compose; no necesita activar el entorno virtual:

```bash
python3 scripts/integration_stack.py
```

El comando verifica las copias, construye las imágenes y retira los recursos
exclusivos de la prueba. El manifiesto fija API `e191097`, con soporte Bearer,
Extractor `6720c32` y Documents `b4fd3df`. Genera una credencial temporal propia,
la inyecta en los consumidores y redacta el secreto del registro de configuración.
Para verificar **los cambios de tu árbol de trabajo**, ejecutar:

```bash
python3 scripts/integration_stack.py --local-documents
```

Este modo registra hashes de los archivos construidos; no los presenta como un
commit publicado. Consultar la [guía de integración](integration/current/README.md)
y la [evidencia](integration/current/validation.md). No modifica el stack compartido.

### Carga de Documents

Con k6 y una instancia que use una **base de pruebas aislada**:

Exportar previamente `DOCUMENTS_API_TOKEN` con el secreto de esa instancia. k6 lo
lee del entorno y agrega la cabecera Authorization; falla antes de generar carga
si falta la variable.

```bash
k6 run -e RUN_ID=prueba-001 -e BASE_URL=http://documents.universidad.localhost tests/stress/documents.js
```

El script crea, consulta y elimina documentos. Usa 5 usuarios durante 15 segundos
por defecto; admite `VUS`, `DURATION`, `CONTENT_BYTES` y `P95_MS`. `PROFILE=spike`
reproduce las rampas 10/20/10 segundos hasta 100 usuarios, sobre el CRUD de Documents.
Cada iteración hace hasta tres solicitudes: no equivale a una extracción de PDF.

Para construir y probar únicamente recursos temporales, con captura de CPU/memoria:

```bash
docker build -t pdf-document-service-validation:local .
python3 scripts/load_isolated.py --image pdf-document-service-validation:local
python3 scripts/load_isolated.py --image pdf-document-service-validation:local --profile spike
```

Requiere descargar previamente la imagen de k6 fijada por digest en
`scripts/load_isolated.py` (o indicar una imagen local con `--k6-image`). Registra los IDs reales de las imágenes, métricas y recursos en
`.integration/load/`. No necesita un token real ni publica puertos.

También hay carga fija de lectura con Vegeta instalado y una base aislada:

```bash
python3 scripts/vegeta_documents.py --base-url http://127.0.0.1:8001 --isolated-test-database
```

Usa el token del entorno, crea un documento propio, ejecuta 50 lecturas/s durante
30 segundos y lo elimina al terminar. El target con credencial vive en un directorio
temporal privado y se retira. Estas pruebas no reemplazan k6/Vegeta sobre `/extract`
con los PDFs oficiales. Consultar [alcance académico](docs/cumplimiento.md).

## Evidencia

- [Resultado de integración aprobado](integration/current/validation.md).
- [Validación y carga de Documents](docs/validation.md).
- [Resumen del escaneo de seguridad de la imagen](docs/security-audit.json).
- [Ejecución histórica de integración](integration/historical/validation.md).
- [Intentos de integración previos](integration/compatibility/validation.md).

## Dependencias y contenedor

`pyproject.toml` declara las dependencias directas; `uv.lock` fija la resolución
completa. `uv sync --locked` falla si el manifiesto y el bloqueo no coinciden.
Las dependencias de pruebas están en el grupo `dev`; Docker instala solo producción
con `uv sync --locked --no-dev`. El repositorio no necesita `requirements.txt`:
`uv.lock` es la fuente de las versiones. Para auditar las dependencias de producción
con una herramienta que requiera ese formato, generar una exportación temporal:

```bash
uv lock
uv export --locked --no-dev --no-emit-project -o /tmp/documents-requirements.txt
```

La construcción tiene una etapa con uv y una etapa de ejecución sin uv, pip ni pytest.
Las imágenes base están fijadas por digest; deben actualizarse periódicamente y
volver a auditarse. El código y el entorno pertenecen a root y el proceso usa el
usuario `appuser` (UID/GID 10001) sin privilegios. Compose configura raíz de solo lectura, eliminación
de capacidades, prohibición de adquirir privilegios y un `/tmp` temporal limitado.
El secreto se recibe en ejecución y no se copia a la imagen. MongoDB necesita
escritura en su volumen; estas restricciones se aplican a Documents.

## Patrones, resiliencia y observabilidad

- **Capas y repositorio:** rutas → servicio → interfaz del dominio → adaptador MongoDB.
- **Deduplicación:** índice único por checksum y recuperación del documento existente.
- **Control de saturación:** admisión acotada por proceso y pool de conexiones limitado.
  El valor inicial 16 evita acumular trabajo sin límite y coincide con el pool
  predeterminado; no es una capacidad máxima demostrada. Ajustarlo midiendo p95,
  errores, CPU y memoria bajo carga representativa. Readiness comparte ese cupo;
  liveness permanece independiente de MongoDB y de la saturación.
- **Timeouts:** presupuesto de MongoDB de 1500 ms por operación. Los consumidores
  deben considerar también el resto del procesamiento y su propio plazo total.
- **Reintentos:** el Compose declara un middleware de Traefik de tres intentos.
  Su efectividad depende del proxy desplegado. `Retry-After` es una indicación al
  consumidor; no ejecuta un reintento. No hay un bucle de retry propio ni un circuit
  breaker explícito en esta aplicación. Los posibles reintentos del driver dependen
  de la topología y su configuración; MongoDB standalone no equivale a un replica set.
  Acordar presupuestos y operaciones reintentables para evitar amplificar carga.
- **Descubrimiento:** este Compose usa DNS de Docker (`documents`, `mongodb`) y
  etiquetas de Traefik. No registra ni consulta Consul. Si el equipo adopta Consul,
  infraestructura debe definir registro, health checks y resolución del consumidor;
  no se presenta como una integración implementada en este repositorio.
- **Factor XI:** logs como eventos a stdout, con método, ruta, estado, duración y
  correlación; no se registran cuerpos ni tokens. La recolección, retención y
  consulta centralizada pertenecen a infraestructura. `/metrics` exporta contadores,
  histograma HTTP y métricas del proceso; requiere Bearer y normaliza etiquetas.
  No hay historial persistente de auditoría ni trazas distribuidas completas.

Las plantillas de Prometheus, alertas y dashboard de Grafana están en `monitoring/`.
Su instalación en el entorno compartido y Consul se coordinan con infraestructura.
La [guía operativa](docs/operacion.md) detalla métricas, secretos, incidentes y rollback.

## Validación automática

`.github/workflows/ci.yml` ejecuta en push y pull request las pruebas con MongoDB
7 temporal, verifica el bloqueo y audita una exportación temporal de paquetes
de producción y construye la imagen. Trivy rechaza vulnerabilidades altas o críticas con arreglo
disponible; los avisos sin arreglo deben revisarse aparte. También comprueba usuario sin privilegios y
la ausencia de pytest en ejecución. La ejecución remota solo existe después de
subir estos archivos; las validaciones locales se registran en `docs/validation.md`.

Para repetir la comprobación HTTP de la imagen construida sin alterar el despliegue:

```bash
docker build -t pdf-document-service-hardened:local .
python3 scripts/validate_container.py --image pdf-document-service-hardened:local
```

El script crea MongoDB y Documents con nombres y red temporales, publica HTTP solo
en localhost y retira sus contenedores y red al finalizar. Verifica CRUD, duplicados,
autenticación, ejecución restringida, caída y recuperación de la base y rechazo de
arranque sin secreto. También se ejecuta en CI; no sustituye la integración con la
API consumidora, Extractor, Consul ni el proxy compartido.
