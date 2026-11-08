# Validación del Extractor actualizado con Documents

Fecha: 08/11/2026. **Resultado de estos intentos: integración no aprobada; detenida por el arranque
del Extractor.** No se llegó a enviar el PDF por la API.

## Versiones y configuración

| Servicio | Commit probado |
| --- | --- |
| API | `354926f584470ce2ce83867d36c159a501f94211` |
| Extractor | `dab2c4d54bf5cecbc36b3b319db432c85da7ae59` |
| Documents | `97efb83503baaa952327bcddf70435f16642a1bf` |

Se usó el Compose histórico de la API con una réplica por servicio, caché
desactivada, MongoDB 7.0.45, Traefik 3.6.25 y red interna exclusiva. El Extractor
está limitado a 1 CPU y 1 GiB en este escenario; Documents y MongoDB a 0,5 CPU y
1 GiB cada uno. No es el despliegue compartido ni el escenario de dos
réplicas de 768 MiB del Extractor.

## Qué se comprobó

- Las imágenes de los tres servicios se construyeron desde los commits fijados.
- Documents actual y MongoDB alcanzaron estado `healthy` en ambos intentos.
- La suite local sin servicios externos aprobó **67 pruebas**; incluye dos
  pruebas del nuevo selector de manifiesto. Las cinco pruebas con MongoDB real
  de esa suite no se ejecutaron.
- El comando con `--versions` prepara las revisiones nuevas sin modificar el
  manifiesto histórico ni el código de los servicios descargados.

## Falla reproducida

| Ejecución UTC | Resultado | Limpieza |
| --- | --- | --- |
| `20261108212830-134eb5ff` | Falló el arranque del Extractor después de construir imágenes. | `cleanup_ok: true` |
| `20261108214211-a18a572a` | Mismo fallo usando las capas de construcción en caché. | `cleanup_ok: true` |

Los logs muestran:

```text
File "/service/app/main.py", line 59, in lifespan
    await asyncio.wait_for(...)
TimeoutError
ERROR: Application startup failed. Exiting.
dependency failed to start: container ...-extractor-1 is unhealthy
```

En ese commit, `app/main.py` espera con `timeout=15` que un trabajo `os.getpid`
termine en el pool de procesos del worker antes de completar el arranque. Esa
espera venció en ambas ejecuciones. Por eso la API, que depende del health del
Extractor, no pudo iniciar el flujo integrado.

La VM tiene aproximadamente 1,6 GiB de RAM total y mostró carga elevada y uso de
swap durante la comprobación. Esto puede influir, pero **no se confirmó la causa
del retraso del worker**. No se puede atribuir la falla a Documents ni demostrar
que suceda en otro entorno. Tampoco basta con aumentar las esperas de
Compose: el plazo de 15 s está dentro del proceso del Extractor.

## Qué falta y a quién corresponde

1. Infraestructura y Extractor: reproducir con la imagen de este commit y revisar el inicio del
   proceso hijo bajo los recursos reales disponibles. Evaluar hacer configurable
   el plazo de inicio y asegurar limpieza y recuperación ante su vencimiento.
2. Acordar cualquier nueva revisión del Extractor, actualizar el manifiesto de
   este escenario y repetirlo. No se modificó su fuente para hacer pasar la prueba.
3. Una vez que arranque, completar PDF nuevo/repetido, concurrencia, persistencia,
   errores, Redis y escenarios de réplicas en el entorno que corresponda.

No hay evidencia nueva de extracción/guardado, deduplicación, recuperación del
worker o solución del timeout al retirar una réplica. La
[prueba histórica aprobada](../historical/validation.md) conserva su alcance y no
se reemplaza por este resultado.

Los dos proyectos de prueba retiraron sus contenedores, redes y volúmenes. No se
usó `pdf-network` ni `pdf_extractext_integration`; los contenedores preexistentes
se conservaron. Logs y resúmenes completos permanecen en
`.integration/stack/runs/<identificador>/`, ignorados por Git.

El [README del escenario](README.md) contiene el comando reproducible y la
limpieza manual en caso de una futura interrupción.

Una ejecución posterior con otras revisiones aprobó el flujo completo. Sus versiones y alcance están en el [informe actual](../current/validation.md).
