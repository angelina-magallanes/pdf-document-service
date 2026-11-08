# Resultado de integración histórica

Se ejecutó el flujo real API → Extractor → Documents → MongoDB y la ruta por
Traefik exclusivo usando las versiones de [versions.json](versions.json):

| Servicio | Commit |
| --- | --- |
| API | `354926f584470ce2ce83867d36c159a501f94211` |
| Extractor | `5f0de842ee1bcdcd23ce1383427f6b757d8882fa` |
| Documents | `8e1214d0ec82df3806c096840e3dea12defe69d5` |

Ejecución: `20261030011143-967cc02d` (identificador UTC). Se usaron las imágenes
MongoDB `7.0.45` y Traefik `3.6.25`, una réplica de cada servicio, red interna y
base exclusivas. No se publicó ningún puerto ni se usó `pdf-network` o Redis.

## Comprobaciones aprobadas

| Comprobación | Resultado |
| --- | --- |
| Health y readiness de API | 200; Extractor y Documents disponibles. |
| Primer envío del PDF | 200, `source=extracted`, Markdown y una página correctos. |
| Segundo envío del mismo PDF | 200, `source=existing`, mismo ID y checksum. |
| Contador de extracción en esos envíos | `0 → 1 → 1`: el segundo envío no volvió a extraer. |
| Entrada sin firma PDF | API 400; no invocó al extractor. |
| PDF con firma válida pero corrupto | API 422 por rechazo del extractor. |
| Dos envíos concurrentes de otro PDF | Ambos 200 y mismo ID; una creación y un documento existente. |
| Ruta mediante Traefik de pruebas | Health, readiness y proceso 200; sin otra extracción del documento existente. |
| Reinicio de Documents | Documento conservado, `source=existing`, contador de extracción `4 → 4`. |
| Extractor detenido | Readiness 503 y proceso 502 con error controlado. |
| Documents detenido | Readiness 503 y proceso 502 con error controlado. |
| Limpieza del entorno | Aprobada; retirados contenedores, red y volúmenes temporales. |

El PDF principal sintético tiene SHA-256
`874290b0b155bc89c5ac083226ee5c854d2dee76f15ab0e8133d4845444cdc0f`.
El ID devuelto en el primer envío, el repetido y después del reinicio fue
`6ae3f7be2bb40cb47d5aa833`.

El informe completo, las respuestas y los logs quedaron en el directorio local
ignorado `.integration/stack/runs/20261030011143-967cc02d/`. El resumen final
registró `passed: true` y `cleanup_ok: true`. Las copias fijadas de los
repositorios y las imágenes se conservan como caché para próximas ejecuciones.

También pasaron **65 pruebas sin servicios externos** del checkout actual,
incluidas las del ejecutor, la separación entre progreso de Docker y JSON, y
el rechazo de configuraciones que apunten a redes, bases o montajes compartidos.
Las cinco pruebas de MongoDB del servicio de desarrollo se excluyeron de esa
suite; la prueba real anterior utilizó su propio MongoDB exclusivo.

Esta validación corresponde a la revisión histórica fijada. El
[informe anterior de Documents](../../docs/validation.md) corresponde al código
posterior `8be80ce` y se conserva como evidencia independiente. El despliegue y
la prueba del Traefik compartido siguen siendo otra etapa.
