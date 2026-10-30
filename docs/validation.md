# Validación de Document Service

Validación local del 29/10/2026. Los documentos adjuntos se usaron como referencia
de arquitectura; las rutas y los campos se contrastaron con el consumidor actual
de `pdf-api-service`.

## Pruebas automatizadas

`python -m pytest -q`: **53 pruebas aprobadas**. Incluyen cinco pruebas con
MongoDB real, en bases temporales independientes: CRUD completo, 16 guardados
simultáneos del mismo checksum, normalización e idempotencia, búsqueda y
paginación, y rechazo real de un BSON mayor al límite de almacenamiento.

También se verificaron errores controlados por cada operación, validación,
correlación, OpenAPI, creación del índice único y cierre del cliente tanto en un
arranque normal como en uno fallido. La configuración base de Compose y la de
desarrollo pasaron `docker compose config --quiet`; `git diff --check` no informó
errores.

## Prueba en contenedores

Se construyó `pdf-document-service-review:local` con el Dockerfile del proyecto.
Se usaron MongoDB 7.0, Traefik 3.6 y dos réplicas del servicio, cada una limitada a
1 CPU y 1 GiB de RAM y ejecutada como `appuser`. La red, la base y los volúmenes
fueron temporales; el despliegue existente no se reemplazó.

Se cambió `PORT` a 8123 para comprobar que Uvicorn, los health checks y el puerto
del balanceador respetan la configuración. Por Traefik se verificaron creación,
búsqueda, duplicados, consulta por ID, renombrado, eliminación, validación,
OpenAPI y headers de seguimiento.

La respuesta se validó con el modelo `DocumentPayload` consultado en
[app/schemas.py del orquestador](https://github.com/Lourdesrizza/pdf-api-service/blob/main/app/schemas.py)
(SHA del archivo: `bdae144853b31eccda455938c54885dc55cf991e`). Esto verifica la
compatibilidad de la respuesta; no equivale a ejecutar el flujo completo de la
API con el extractor.

## Carga sencilla

Se ejecutó `tests/stress/documents.js` con 5 usuarios durante 15 segundos, sin
Redis y con Markdown pequeño. Cada iteración crea, busca por checksum y elimina
un documento distinto.

| Medida | Resultado de la ejecución final |
| --- | --- |
| Ciclos completos | 560 |
| Solicitudes HTTP | 1680 |
| Solicitudes por segundo | 111,02 |
| Errores HTTP durante la carga | 0 % |
| Comprobaciones correctas | 2240 de 2240 |
| Latencia HTTP p50 / p95 | 32,11 ms / 117,10 ms |
| Tráfico identificado por réplica | 840 / 840 solicitudes |

Es una comprobación local de persistencia. No es una prueba de capacidad máxima
ni una comparación de optimizaciones, y no sustituye el benchmark del extractor
con los PDFs oficiales.

## Fallas, recuperación y límite observado

Al detener una réplica se comprobó que completó el cierre de la aplicación sin
OOM ni `SIGKILL`. Uvicorn 0.54 volvió a emitir `SIGTERM` después de la limpieza y
Docker registró salida 143, comportamiento normal de esa versión.

**Durante el retiro se observó un timeout transitorio de cliente de 5 segundos.**
Luego se comprobaron diez lecturas consecutivas correctas desde la réplica
restante; la comprobación de recuperación duró 6,43 segundos. No se demostró
cero errores durante el cambio de réplicas.

Para infraestructura queda revisar el tiempo de conexión de Traefik al backend
y la actualización de sus proveedores frente al timeout de 5 segundos del
orquestador. La hipótesis es una conexión a la instancia retirada mientras el
proxy converge; no se capturó una traza suficiente para confirmar esa causa.
La [documentación de Traefik](https://doc.traefik.io/traefik/reference/install-configuration/configuration-options/)
describe `serversTransport.forwardingTimeouts.dialTimeout` (30 s por defecto) y
`providers.providersThrottleDuration` (2 s por defecto). Los reintentos por sí
solos no prueban que se pueda cumplir el plazo del consumidor. Este ajuste
corresponde al proxy compartido y debe volver a probarse con el equipo.

Al detener MongoDB, `/health/live` mantuvo 200; `/health/ready` respondió 503 en
1,68 segundos y la lectura devolvió 503 con `Retry-After: 1` y
`application/problem+json`. Al reiniciarlo, el documento seguía persistido y
volvieron a funcionar lectura y eliminación.

Se retiraron los contenedores, volúmenes y la red de pruebas. Queda pendiente la
prueba conjunta con API y Extractor reales y la validación del ajuste del proxy.
