# Resultado de integración aislada

## Intento con commit publicado (09/11/2026)

El manifiesto actual fija Documents `7469779965bc74362e8412668565e6ebc4777d59`.
La ejecución `20261109204952-9eba431f`, sin `--local-documents`, falló con
`httpx.ReadTimeout` durante autenticación. No aprobó el flujo completo.
Ver [seguimiento del cierre](../../docs/validation.md). El resultado JSON
versionado sigue correspondiendo a la ejecución aprobada anterior.

## Integración con Bearer y límites de Documents (09/11/2026)

Ejecución `20261109195805-7ad8af59`: **passed=true, cleanup_ok=true**.
API `e191097bba601efffe729b811ccbf872b483318b`, Extractor
`6720c32f21d404231da131090b9f094eaa4728f6` y Documents construido desde el árbol
local sobre `b4fd3df`, con sus hashes registrados. No es una prueba del commit
base sin modificaciones. El [resultado completo](result.json) permite comprobar
los archivos exactos probados.

Pasaron autenticación (401 sin token/incorrecto), salud pública, nuevo PDF y
repetido con el mismo ID/checksum, multipart, concurrencia, PDFs inválidos, ruta
por Traefik aislado, persistencia después del reinicio y caída de cada dependencia.
El secreto fue aleatorio y temporal; no se guardó en el informe ni en Git.
Se retiraron los recursos temporales. No valida el despliegue compartido ni el
benchmark del Extractor con PDFs oficiales.

Comando usado para probar el árbol local: `python3 scripts/integration_stack.py --local-documents`.
Sin esa opción se reconstruyen los commits del manifiesto actual; consultar el
intento más reciente al inicio de este archivo.

## Antecedente anterior a Bearer


El 08/11/2026 se aprobó el flujo real API → Extractor → Documents → MongoDB en un
entorno temporal. Los commits de esa prueba histórica se detallan a continuación; el manifiesto
actual se actualizó para Bearer y ya no representa esa ejecución.

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
