# Resultado de integración aislada

El 08/11/2026 se aprobó el flujo real API → Extractor → Documents → MongoDB en un
entorno temporal. El manifiesto reproducible está en [versions.json](versions.json).

| Servicio | Commit |
| --- | --- |
| API | `354926f584470ce2ce83867d36c159a501f94211` |
| Extractor | `6720c32f21d404231da131090b9f094eaa4728f6` |
| Documents | `b8511057769c7c64963550e931810f2d6f5b7a80` |

La ejecución `20261108223410-9f61d673` registró `passed: true` y
`cleanup_ok: true`. Utilizó MongoDB 7.0.45, Traefik 3.6.25, una red interna y
una réplica de cada servicio con caché desactivada.

Se verificaron el PDF nuevo (`source=extracted`), el repetido (`source=existing`)
con el mismo ID y sin una segunda extracción, dos envíos concurrentes, PDFs
inválidos, acceso por Traefik aislado, persistencia después de reiniciar Documents
y respuestas controladas cuando cada dependencia se detuvo. La ejecución retiró
los contenedores, la red y los volúmenes temporales.

El informe completo de esa ejecución está en la carpeta local ignorada
`.integration/stack/runs/20261108223410-9f61d673/summary.json`. La prueba no
valida el proxy compartido, Redis ni el balanceo de múltiples réplicas. Los
[intentos anteriores](../compatibility/validation.md) se conservan como evidencia
independiente y utilizaron commits distintos.
