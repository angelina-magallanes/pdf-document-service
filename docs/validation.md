# Validación de Document Service

## Correcciones de estructura y empaquetado (10/11/2026)

Se organizaron las capas en `app/routers/`, `app/services/`, `app/repositories/`,
`app/models/` y `app/schemas/`. Se actualizaron imports y documentación. El ejecutor
de integración ahora registra también hashes de los módulos en subcarpetas.

El proyecto usa `pyproject.toml` y `uv.lock`; se retiró el `requirements.txt`
versionado. Para la auditoría se exportan temporalmente las dependencias desde el
lock. El workflow instala uv con la acción oficial y ejecuta pip-audit con `uvx`.
Se comprobó localmente que el lock está actualizado y que la auditoría no encontró
vulnerabilidades conocidas. El workflow modificado todavía no se ejecutó en GitHub.

El Dockerfile multietapa ahora declara `USER appuser`; el usuario sigue teniendo
UID/GID 10001. Trivy 0.76.2 analizó el Dockerfile y la regla DS-0002, que verifica
el usuario no root, pasó. Esta comprobación no sustituye el análisis de vulnerabilidades
de la imagen completa. La imagen construida pasó la prueba HTTP aislada de CRUD,
Bearer, persistencia y recuperación de MongoDB, y arranque sin secreto.

Se ejecutaron **154 pruebas**, incluidas cinco con MongoDB temporal. Sigue apareciendo
un aviso de deprecación de Starlette sobre el cliente de pruebas. La integración
completa API–Extractor–Documents no se repitió en esta revisión: los últimos intentos
quedaron documentados abajo y no acreditan esta estructura nueva.


## Actualización de dependencias (10/11/2026)

Se actualizaron FastAPI 0.150.0 → 0.162.3, Pydantic 2.14.1 → 2.14.3,
pydantic-core 2.50.1 → 2.50.4 y pytest 9.1.1 → 9.2.0. Se regeneraron `uv.lock`
y `requirements.txt`. Las 26 dependencias del lock, incluidas las de desarrollo,
coincidían con las últimas versiones publicadas en PyPI al consultar el 10/11/2026.

Las **153 pruebas** pasaron con MongoDB temporal; la imagen actualizada aprobó la
validación HTTP aislada, autenticación, caída y recuperación de MongoDB. La auditoría
`pip-audit` de las dependencias de producción y desarrollo no encontró vulnerabilidades
conocidas. Se mantiene un aviso de deprecación de Starlette sobre su cliente de prueba.
Un primer intento de integración completa falló durante el arranque por timeouts
en MongoDB y en el worker del Extractor; sus recursos temporales se retiraron.
Un segundo intento se interrumpió por un reinicio de la VM y también se limpiaron
sus recursos. La integración completa con estas versiones queda pendiente de repetir.


## Seguimiento del cierre de entrega (09/11/2026)

El commit publicado `7469779965bc74362e8412668565e6ebc4777d59` se fijó en
`integration/current/versions.json`. El workflow remoto
[42723716346](https://github.com/angelina-magallanes/pdf-document-service/actions/runs/42723716346)
falló durante la colección de pruebas con `ModuleNotFoundError` para `app` y
`scripts`; las etapas posteriores no se ejecutaron. Se corrigió la invocación a
`uv run --locked python -m pytest -q` en el commit local `54725f5`.
La suite local ejecutada con `.venv/bin/python -m pytest -q` aprobó **153 pruebas**,
con el aviso de deprecación de Starlette. El push de la corrección falló por falta
de credenciales HTTPS de GitHub; no hay aprobación remota de esta corrección.

Se intentó repetir la integración sin `--local-documents`, ejecución
`20261109204952-9eba431f`. La construcción y el arranque terminaron, pero la
comprobación de autenticación falló con `httpx.ReadTimeout`. Se observó presión
de memoria y swap en la VM; no se aisló la causa del timeout. Este intento no
acredita integración aprobada del commit publicado. Los registros completos están
en `.integration/stack/runs/20261109204952-9eba431f/` (ignorado por Git).
La limpieza terminó con `cleanup_ok=true`; se retiraron los contenedores y la red
temporales. Se conserva el resultado aprobado anterior en
`integration/current/result.json`.

No se identificó acceso al despliegue compartido. Quedan pendientes su prueba de
retiro de réplicas bajo tráfico, la instalación/verificación del monitoreo y el
canal de notificación. La configuración local encontrada no permite acreditar
esas condiciones del entorno compartido.


## Límites, observabilidad e integración autenticada (09/11/2026)

Se completaron los límites incrementales del cuerpo HTTP (4 MiB, 15 s), el
presupuesto de página (8 MiB), el cierre del cursor y la retención del cupo de
admisión durante toda la respuesta. Se preservan los campos y el formato del CRUD.
Los nuevos 408/413 son cambios de comportamiento que deben comunicarse al consumidor.

Los errores de PyMongo se traducen en el adaptador; presentación usa excepciones
del dominio. Se exportan métricas Prometheus protegidas y de cardinalidad acotada.
Hay plantillas de scraping/alertas/dashboard y guía operativa, sin modificar la
infraestructura compartida. La tabla de correspondencia con los materiales está
en [cumplimiento.md](cumplimiento.md).

### Verificación realizada

- **153 pruebas aprobadas**, incluidas cinco con MongoDB 7.0.45 temporal. La suite
  sin servicios externos aprobó 148. Persiste el aviso de deprecación del cliente
  httpx de Starlette; no afecta el resultado.
- Imagen probada por HTTP real: CRUD, Bearer, usuario no privilegiado, raíz de
  solo lectura, caída/recuperación de MongoDB, persistencia y arranque sin secreto.
- Integración API–Extractor–Documents aprobada con autenticación y limpieza completa:
  `20261109195805-7ad8af59`. [Resultado versionado](../integration/current/result.json).
  Los hashes del código construido coinciden con el árbol auditado. Se probaron
  PDFs sintéticos, no el conjunto oficial del benchmark.
- Auditoría de las dependencias de producción con pip-audit: sin vulnerabilidades
  conocidas detectadas. No se repitió aquí el escaneo del sistema operativo de la
  imagen; el informe de seguridad previo conserva su alcance y su ID de imagen.
- Se incorporó carga smoke aislada al workflow de CI y almacenamiento de evidencia.
  No se observó su ejecución remota; el resultado local no demuestra aprobación remota.

Un intento encontró un montaje tmpfs mal expresado en el overlay YAML; se corrigió.
Otro intento fue interrumpido por el reinicio de la VM, después de un timeout del
consumidor. Sus recursos se retiraron y se repitió el escenario completo. Ninguno
se presenta como una ejecución aprobada.

### Comparación de carga de Documents

Misma carga CRUD pequeña (1 KiB de texto), cinco usuarios durante quince segundos,
una réplica limitada a 1 CPU/1 GiB y MongoDB temporal. Se utilizó la imagen anterior
`pdf-document-service-hardened:local` como referencia y la nueva imagen construida
por la integración. Los IDs de imagen, métricas y muestras están en
[load-results.json](load-results.json).

| Medida | Antes | Después |
| --- | --- | --- |
| Solicitudes | 2583 | 2595 |
| Solicitudes/s | 171,69 | 172,64 |
| Error HTTP | 0 % | 0 % |
| p95 HTTP | 46,22 ms | 47,11 ms |
| Memoria máxima muestreada (% de 1 GiB) | 6,69 % | 5,65 % |

Son muestras breves de una VM compartida; las diferencias no prueban una mejora
estadísticamente significativa. El objetivo fue verificar que las protecciones
no introdujeran una regresión apreciable con este tamaño. No demuestra capacidad
para documentos grandes ni sustituye una campaña de carga más extensa.

El pico k6 de 100 usuarios **no aprobó** el umbral de menos de 1 % de errores:
8200 solicitudes, 6741 respuestas 503 por admisión (82,21 %), p95 1120,33 ms.
Los contadores identificaron todos esos 503 como rechazos de concurrencia; el
cupo volvió a cero y no se registraron otros estados de error en esas solicitudes.
La memoria máxima muestreada fue 7,20 % de 1 GiB. No se afirma que una réplica
soporte 100 usuarios sin rechazos. El pico coincidió con otras verificaciones
locales, por lo que no se usa para comparar capacidad con otro sistema.

La carga fija de lectura con Vegeta 12.13.0, a 50/s durante 30 s, registró
**1498 respuestas 200 de 1498**, throughput 49,92/s y p95 18,69 ms. El generador
produjo 1498 solicitudes, no se redondea a 1500. Consultó un documento sintético
propio y lo eliminó al finalizar. No compara extracción de PDF.

Se retiraron contenedores, redes y almacenamiento temporales de estas pruebas;
el despliegue compartido permaneció separado. Los resultados anteriores del
archivo se conservan como antecedentes y no sustituyen esta evidencia.


## Revisión de estructura, dependencias y contenedor (09/11/2026)

Se migró a `pyproject.toml` y `uv.lock`, con dependencias de producción y pruebas
separadas. `requirements.txt` queda como exportación de producción con hashes.
La instalación limpia con `uv sync --locked` aprobó **139 pruebas**, incluidas
**5 con MongoDB 7.0.45 temporal**. Se observa un aviso de deprecación del cliente
httpx de Starlette en pruebas; no se silenció ni se presenta como fallo funcional.

`main.py` queda en 38 líneas de composición. Las rutas se encuentran en
`routes.py`, la autenticación/correlación/admisión en `middleware.py` y los recursos
y ciclo de vida en `dependencies.py`. Se conservan dominio, servicio, repositorio,
schemas, conexión y errores en módulos separados. Se adaptaron las fixtures para
probar los mismos contratos sobre los módulos nuevos.

Se construyó `pdf-document-service-hardened:local` con uv 0.13.7 y Python 3.14.10.
Las bases están fijadas por digest y la etapa final no incluye uv, pip, ensurepip
ni pytest. El proceso usa UID/GID 10001; código y entorno pertenecen a root.
El Compose restringe Documents con raíz de solo lectura, `cap_drop: ALL`,
`no-new-privileges` y `/tmp` temporal limitado. No se aplican esas restricciones
al almacenamiento de MongoDB.

`python3 scripts/validate_container.py` aprobó sobre la imagen final: salud pública,
401 sin token o con token incorrecto; creación 201, duplicado 200, consulta por ID y
checksum, listado, renombrado y eliminación 204 autenticados. También comprobó
usuario sin privilegios y código no escribible; liveness 200 y readiness/lectura
503 con MongoDB detenido; recuperación y persistencia al reiniciar MongoDB; y
rechazo de arranque sin secreto. Los contenedores, volúmenes de datos y red de
esta prueba se retiraron. El script queda disponible para repetir la comprobación.

Los Compose base y de desarrollo validaron con una credencial ficticia y la
configuración fue rechazada al faltar `DOCUMENTS_API_TOKEN`. El YAML de CI y
`git diff --check` también validaron. Se agregó CI para push y pull request con
pruebas MongoDB, bloqueo/exportación, auditoría de dependencias, construcción,
prueba HTTP del contenedor y escaneo de vulnerabilidades de imagen. Las acciones
y las imágenes de construcción/escaneo se fijan por commit o digest. **El código de esa revisión quedó en el commit `b4fd3df`. Este informe no acredita
una ejecución remota del workflow.**

La auditoría `pip-audit` de las **16 dependencias de producción** no encontró
vulnerabilidades conocidas. El escaneo de imagen y sus riesgos residuales se
registran a continuación; este resultado no implica ausencia de vulnerabilidades.

Trivy 0.76.2 escaneó la imagen final (ID y detalle en
[`security-audit.json`](security-audit.json)). No detectó vulnerabilidades en
paquetes Python. En Debian 12.15 registró **92 hallazgos bajos, 105 medios,
40 altos y 2 críticos**, sin versión corregida publicada en esos hallazgos.
Son hallazgos por paquete, no necesariamente CVE distintos. No se declara la
imagen libre de vulnerabilidades ni se suprimen avisos mediante excepciones.
El control de CI falla ante hallazgos altos/críticos con corrección disponible;
es necesario revisar también los avisos sin corrección, actualizar periódicamente
la base y reevaluar su exposición antes de desplegar. El informe inicial detectó
además avisos en paquetes internos de pip; se retiraron pip y ensurepip y se
repitió el escaneo sobre la imagen final. La base temporal de Trivy se retiró.

El README detalla los patrones implementados y los límites de la evidencia:
DNS de Docker/Traefik, sin integración Consul; logs a stdout con correlación,
sin métricas Prometheus ni trazas distribuidas; timeout y admisión acotada, sin
circuit breaker propio. El valor de concurrencia 16 es configurable y requiere
medición representativa para ajustar capacidad. El retry declarado en Traefik
requiere comprobarse en el proxy realmente desplegado.

Esta revisión no vuelve a validar la integración completa API–Extractor–Documents.
Sigue siendo necesario coordinar credenciales, despliegue, descubrimiento y
observabilidad con los responsables de los otros repositorios y fijar sus nuevas
revisiones antes de repetir ese escenario.

## Autenticación Bearer (09/11/2026)

El código de desarrollo ahora exige `DOCUMENTS_API_TOKEN` al iniciar y una
cabecera `Authorization: Bearer ...` para acceder a los documentos. Las sondas
de salud y la documentación OpenAPI siguen públicas. Se verificaron **134
pruebas sin servicios externos** y **5 pruebas con una instancia MongoDB 7.0.45
temporal exclusiva**, retirada al finalizar. Se cubren rechazo de credenciales
ausentes, incorrectas y duplicadas; rechazo previo al procesamiento del JSON y
al acceso a MongoDB; seguimiento de los errores; arranque sin secreto; OpenAPI;
y continuidad del CRUD autenticado y la deduplicación.

También se construyó `pdf-document-service-security:local` y se probó por HTTP
real con MongoDB y red interna temporales: health público 200; acceso sin token
o con token incorrecto 401; creación 201, duplicado 200 y eliminación 204 con
token válido. La imagen rechazó el arranque sin secreto. Los Compose base y de
desarrollo validaron con secreto y la configuración fue rechazada sin él. Los
recursos temporales se retiraron sin reemplazar el despliegue existente.

Esta revisión cambia el requisito de acceso del consumidor. La integración
aprobada con Documents `b851105` sigue siendo evidencia de esa revisión anterior,
no una validación del nuevo requisito de autenticación. Antes de desplegar la
revisión protegida, la API debe enviar la credencial y el Compose de
infraestructura debe configurar el mismo secreto en Documents. Después debe
repetirse la integración completa con las nuevas revisiones.

## Seguimiento del acuerdo con infraestructura (07/11/2026)

El entorno compartido informó MongoDB 7 y la base `pdf_extractext_integration` para integración,
y `stop_grace_period: 30s` en infraestructura. El Dockerfile de desarrollo se
ajustó de 25 a 10 segundos de espera máxima de Uvicorn. Esto no modifica los
resultados históricos de este informe ni la revisión histórica `8e1214d`.
Faltan construir/desplegar la nueva imagen y repetir la caída de réplica con
tráfico para comprobar su efecto. La atribución del timeout a keep-alive no está
confirmada. La URI y el aislamiento de la instancia deben verificarse con infraestructura;
un nombre de base separado no prueba que el servidor MongoDB sea exclusivo.

La prueba posterior con Documents `8e1214d` está registrada en
[Integración histórica](../integration/historical/validation.md).
Este informe conserva los resultados del código de desarrollo `8be80ce`.

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

Se retiraron los contenedores, volúmenes y la red de pruebas. Después se aprobó
una [integración real aislada](../integration/current/validation.md). Sigue pendiente
verificar el ajuste del proxy compartido.
