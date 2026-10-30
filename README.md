# PDF Document Service

Servicio de persistencia de PDF-Extractext. Es el único servicio de negocio que
accede a MongoDB: almacena Markdown, páginas y metadatos, evita duplicados por
SHA-256 y ofrece CRUD por HTTP. El orquestador calcula el checksum de los bytes
del PDF original y envía el resultado del extractor; este servicio no recibe ni
extrae PDFs y no usa Redis.

## Contrato para la API

| Método | Ruta | Resultado |
| --- | --- | --- |
| POST | `/documents` | 201 con el documento nuevo; 200 con el original si ya existe el checksum. |
| GET | `/documents/by-checksum/{checksum}` | 200 con el documento o 404. |
| GET | `/documents/{id}` | 200 con el documento o 404. |
| GET | `/documents?skip=0&limit=20` | Lista ordenada por ID, con `skip >= 0` y `1 <= limit <= 100`. |
| PATCH | `/documents/{id}` | Modifica solamente `filename`; devuelve el documento actualizado. |
| DELETE | `/documents/{id}` | 204 sin cuerpo o 404. |
| GET | `/health/live` | 200 si el proceso responde; no consulta MongoDB. |
| GET | `/health`, `/health/ready` | 200 si MongoDB responde; 503 si no está disponible. |
| GET | `/docs`, `/openapi.json` | Swagger y especificación de las rutas reales. |

`POST /documents` recibe `application/json`:

```json
{
  "checksum": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "content": "## Página 1\n\nTexto extraído.",
  "page_count": 1,
  "filename": "informe.pdf"
}
```

`checksum` debe tener 64 caracteres hexadecimales y se normaliza a minúsculas.
`content` es texto Markdown; puede estar vacío si el PDF no contiene texto.
`page_count` es un entero positivo representable en BSON de 64 bits, no un
booleano ni una cadena. `filename` es
opcional: si se omite o es `null`, se usa `document.pdf`; si se envía, se recortan
espacios y debe tener entre 1 y 255 caracteres. No se aceptan campos adicionales.

La respuesta incluye esos cuatro campos más `id` (ObjectId como texto) y
`created_at` (UTC, con precisión de milisegundos). Los documentos históricos sin
nombre también se devuelven con `document.pdf`.

Un índice único de MongoDB garantiza la unicidad entre procesos y réplicas. Si se
repite el checksum, se conserva el contenido, el nombre y la fecha originales,
aunque cambie el resto del payload. Una carrera con una eliminación puede
devolver 409: el consumidor debe volver a consultar por checksum. No se calcula
el SHA-256 del Markdown ni se sobrescribe el contenido de un documento existente.

## Errores y seguimiento

Los errores HTTP, de validación y de MongoDB usan `application/problem+json`.
Mantienen un campo `detail` de texto y agregan `type`, `title`, `status`,
`instance` y `request_id`. Los errores de validación incluyen `errors` con
ubicación, mensaje y tipo; no devuelven el cuerpo del documento. Una falla de
MongoDB devuelve 503 con `Retry-After: 1`, sin direcciones ni credenciales internas.
Los IDs o checksums mal formados devuelven 422; un documento inexistente, 404.
Un documento que excede el tamaño admitido por MongoDB devuelve 413. Ese límite
se aplica al Markdown y sus metadatos; no es el límite de tamaño del PDF original.

El servicio conserva `X-Request-ID` y `X-Audit-Id` cuando contienen de 1 a 128
caracteres alfanuméricos o `._:-`. Si el request ID falta o es inválido, genera
uno nuevo; el audit ID inválido se omite. Los identificadores aparecen en las
respuestas, incluidos los errores controlados, y en los logs de la solicitud.
Los logs salen a stdout y no incluyen Markdown ni cuerpos de peticiones.

## Docker y red compartida

Requiere Docker Compose y la red externa que también usa Traefik:

```bash
cp .env.example .env
docker network create pdf-network  # solo si todavía no existe
docker compose up -d --build
```

El compose base publica el servicio mediante Traefik y no reserva puertos del
host. Traefik debe estar iniciado por `pdf-infrastructure`, conectado a
`pdf-network` y tener el entrypoint HTTP `web`. El hostname predeterminado es
`documents.universidad.localhost`; el health check del balanceador usa
`/health/ready`. El contenedor se ejecuta como usuario sin privilegios, con
1 CPU, 1 GiB de RAM y 30 segundos para detenerse; Uvicorn permite hasta 25 segundos
para terminar solicitudes antes de cerrar el cliente MongoDB.
Con Uvicorn 0.54, un cierre completo por `SIGTERM` puede terminar con código 143;
se verifica también el mensaje `Application shutdown complete.` y que no haya
terminación forzada por `SIGKILL`.

Dirección entre contenedores: `http://documents:8000`. Para Lourdes:
`DOCUMENT_SERVICE_URL=http://documents:8000`. MongoDB se resuelve como
`mongodb:27017`; no usar `localhost` para llamar a otro contenedor.

Para probar desde el host sin Traefik, usar la configuración de desarrollo:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
curl http://127.0.0.1:8001/health/ready
```

Esa configuración publica Document Service en `127.0.0.1:8001` y MongoDB en
`127.0.0.1:27017`. Conserva el volumen existente `mongo7_data`.
La red `pdf-network` también debe existir en desarrollo.

Para comprobar la ruta real del proxy:

```bash
curl -H 'Host: documents.universidad.localhost' http://127.0.0.1/health/ready
```

Se pueden crear réplicas con `docker compose up -d --scale documents=2` al usar
el compose base. No hay `container_name` ni puertos fijos de host que colisionen.
Si se usa el compose de integración de `pdf-infrastructure`, ese compose ya crea
`documents` y `mongodb`: elegir ese despliegue o el de este repositorio para
evitar instancias con los mismos aliases y routers. La URI y la base configuradas
deben apuntar a la persistencia que se quiera conservar.

## Variables de entorno

| Variable | Valor por defecto | Uso |
| --- | --- | --- |
| `MONGODB_URI` | `mongodb://127.0.0.1:27017` en Python; `mongodb://mongodb:27017` en Compose | Conexión a MongoDB. |
| `MONGODB_DATABASE` | `pdf_extractext` | Base de documentos. |
| `MONGODB_TIMEOUT_MS` | `1500` | Presupuesto por operación y límites de conexión, selección, socket y espera de pool. Entero mayor que cero. |
| `PORT` | `8000` | Puerto de Uvicorn en Docker y de sus health checks. |
| `LOG_LEVEL` | `INFO` | Nivel de logging. |
| `TRAEFIK_DOCUMENTS_HOST` | `documents.universidad.localhost` | Host del router HTTP. |
| `TRAEFIK_ENTRYPOINT` | `web` | Entry point de Traefik. Configurar TLS en infraestructura si corresponde. |
| `DOCUMENTS_HOST_PORT` | `8001` | Puerto de desarrollo en el host. |
| `MONGODB_HOST_PORT` | `27017` | Puerto de MongoDB en desarrollo. |
| `MONGODB_TEST_URI` | `mongodb://127.0.0.1:27017` | Conexión para las pruebas de integración. |

El timeout predeterminado es menor que los 2 segundos usados por la API para
readiness. Si se ajusta, revisar también los timeouts de la API y los health
checks. El arranque comprueba MongoDB y crea el índice único; si falla, la
aplicación no comienza a servir solicitudes y cierra el cliente.

## Desarrollo y pruebas

Para ejecutar fuera de Docker se usa Python 3.14 y MongoDB 7.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -m 'not integration' -q
```

En PowerShell, activar con `.\.venv\Scripts\Activate.ps1`; usar `curl.exe` en
lugar del alias `curl`. Compose lee `.env`; al ejecutar Python directamente,
exportar las variables en la terminal. Con MongoDB accesible en el host:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
python -m pytest -q
```

La suite sin integración verifica contratos, validación, errores, correlación,
OpenAPI y apertura/cierre de recursos sin una base real. Las pruebas marcadas
`integration` necesitan MongoDB: crean una base temporal distinta para cada caso
y la eliminan al finalizar. Verifican CRUD, paginación, normalización y guardados
simultáneos del mismo checksum contra el índice único real.

## Prueba de carga sencilla

`tests/stress/documents.js` crea un documento, lo consulta por checksum y lo
elimina en cada iteración. Requiere k6 y una instancia con **base de pruebas
aislada**. `RUN_ID` debe ser distinto en cada ejecución:

```bash
k6 run -e RUN_ID=prueba-001 -e BASE_URL=http://documents.universidad.localhost tests/stress/documents.js
```

Por defecto usa 5 usuarios durante 15 segundos; acepta `VUS` y `DURATION`.
Cada iteración usa un checksum distinto; si hay fallas pueden quedar documentos
de prueba en esa base. Registrar throughput, errores y percentiles junto con
CPU/RAM, réplicas y configuración del proxy. Esta prueba de persistencia es
independiente del benchmark oficial del extractor y no lo reemplaza.

Los resultados locales y el timeout transitorio observado al retirar una réplica
están registrados en [Validación y límites de integración](docs/validation.md).
