# Operación y recuperación de Documents

## Salud y observabilidad

`/health/live` comprueba el proceso. `/health/ready` comprueba MongoDB y comparte
el límite de admisión: puede responder 503 por saturación o caída de la base.
`/metrics` requiere el mismo Bearer que los documentos y no consulta MongoDB.

`monitoring/prometheus.yml` descubre las réplicas por DNS de Docker. Conectar
Prometheus a la red del servicio y montar el secreto como archivo de solo lectura
en `/run/secrets/documents_api_token`, fuera de Git. Montar también `alerts.yml`
en `/etc/prometheus/alerts.yml`. Nunca pegar el token en el YAML ni en un dashboard.
Importar `monitoring/dashboard.json` en Grafana y seleccionar el datasource.
Estas plantillas no despliegan ni modifican el monitoreo compartido.

Las métricas incluyen contador por método/ruta/estado, histograma de duración,
solicitudes admitidas en curso, rechazos de admisión y métricas del proceso.
Las rutas se normalizan: no se usan IDs, checksums ni tokens como etiquetas.
La duración HTTP mide hasta las cabeceras, no la descarga completa del cliente.
Ejecutar un proceso Uvicorn por contenedor, como el Dockerfile; sumar las series
por réplica en Prometheus. No se configura modo multiproceso del cliente Prometheus.
Los contadores reinician al reiniciar el proceso; Prometheus conserva el histórico.

## Respuestas y acciones

| Señal | Comprobación | Acción |
| --- | --- | --- |
| 401 | Token de Documents, consumidor y scraper | Corregir la configuración por canal privado y recrear los consumidores afectados. No desactivar autenticación. |
| 408 | Tiempo total de recepción del JSON | Revisar red y velocidad del consumidor; el cupo se libera al terminar la respuesta. |
| 413 en POST/PATCH | Cuerpo HTTP y tamaño BSON | Reducir el payload o acordar un aumento medido de `DOCUMENTS_MAX_BODY_BYTES`. No equivale al tamaño del PDF original. |
| 413 en listado | Presupuesto `DOCUMENTS_MAX_LIST_BYTES` | Reducir `limit` o consultar un documento por ID. No se devuelven páginas parciales silenciosamente. |
| 503 con liveness 200 | Readiness, rechazos de admisión y MongoDB | Restaurar MongoDB o reducir carga. Reintentar con presupuesto y respetando `Retry-After`. |
| Proceso detenido | Logs, salida del contenedor, OOMKilled | Verificar secreto, URI, memoria y arranque; restaurar una imagen conocida con configuración compatible. |

No subir automáticamente la concurrencia ante 503: aumenta la presión sobre
memoria y MongoDB. El límite HTTP se cuenta durante la recepción, también sin
Content-Length; el timeout limita el tiempo total dedicado a recibir el cuerpo.
El listado conserva el contrato, usa lotes de un documento y limita el tamaño
estimado de la página; aun así, una consulta individual carga un documento completo.

## Despliegue y rollback

1. Registrar commit, digest de imagen y variables no secretas. Construir una vez y
   desplegar esa imagen con el secreto inyectado en ejecución.
2. Comprobar salud pública y acceso autenticado. Probar un PDF nuevo y el mismo
   PDF otra vez a través de la API; comparar ID, checksum y extracted/existing.
3. Retirar una réplica bajo tráfico en un entorno aislado y registrar errores y
   tiempo de recuperación. Los límites del proxy deben encajar en los del consumidor.
4. Ante regresión, restaurar la imagen anterior compatible con Bearer y su
   configuración. No borrar volúmenes ni índices durante un rollback.

MongoDB standalone sigue siendo un punto único de falla. Para una entrega que
requiera alta disponibilidad, infraestructura debe proporcionar replicación,
backups y una restauración ensayada. Reiniciar un contenedor no sustituye un backup.
El servicio no implementa Saga porque no coordina escrituras en varias bases;
la unicidad se resuelve con índice único y operaciones atómicas de MongoDB.

## Procesos administrativos

Los índices se crean de forma idempotente al iniciar. Para mantenimiento usar
procesos puntuales del mismo entorno y versión; documentar cualquier migración
antes de ejecutarla. Los scripts de validación crean y retiran recursos propios.
No apuntar carga o integración a una base con información compartida.
