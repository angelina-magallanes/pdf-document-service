# Correspondencia con los materiales de la materia

Documents es el servicio de persistencia. Recibe JSON y guarda Markdown,
páginas y metadatos. El TP de carga exige `/extract` al Extractor: ese endpoint,
el pool de extracción y los PDFs oficiales corresponden a otro servicio.
Las diapositivas presentan principios y alternativas; no obligan a incorporar
cada patrón en cada componente.

## Arquitectura y código limpio

Presentación (`routes`, `schemas`) → aplicación (`service`) → interfaz de dominio
(`domain`) → adaptador MongoDB (`repository`, `database`). Los errores del driver
se traducen a excepciones de dominio; HTTP no importa PyMongo. Los DTO evitan
exponer ObjectId o estructuras internas de la colección. La admisión, autenticación,
correlación y observabilidad tienen funciones separadas.

El repositorio permite otro adaptador, pero no cambia de motor automáticamente:
habría que implementar consultas, conexión, índices y restricciones equivalentes.
Se usan operaciones atómicas de un documento y un índice único por checksum.
No hay una transacción de negocio que necesite Saga o Unit of Work. Redis no es
una dependencia de persistencia. Agregar estos patrones sin necesidad aumentaría
la complejidad y contradice KISS/YAGNI.

## Twelve-Factor

| Factor | Implementación o evidencia necesaria |
| --- | --- |
| I. Código base | Repositorio Git; registrar revisión e imagen por despliegue. |
| II. Dependencias | pyproject.toml, uv.lock y exportación con hashes. |
| III. Configuración | Variables de entorno; token obligatorio fuera de Git. |
| IV. Backing services | MongoDB por URI y base configurables. |
| V. Build/release/run | Docker multietapa; configuración en ejecución. Fijar imagen de la entrega. |
| VI. Procesos | Estado de negocio en MongoDB, sin sesiones locales. |
| VII. Port binding | Uvicorn y PORT configurable. |
| VIII. Concurrencia | Réplicas sin estado, pool y admisión acotados por proceso. |
| IX. Desechabilidad | Cierre del cliente y apagado con gracia; ensayar retiro en el proxy real. |
| X. Paridad | MongoDB 7 en Compose y pruebas; verificar versiones del entorno compartido. |
| XI. Logs | stdout con correlación; recolección externa. Métricas adicionales protegidas. |
| XII. Administración | Índice idempotente y herramientas puntuales; migraciones futuras deben compartir versión/configuración. |

Esta tabla distingue mecanismos del código y prácticas operativas. No constituye
una certificación del despliegue compartido.

## Pruebas y recursos

Las pruebas sin MongoDB usan dobles y se ejecutan de forma independiente. Las de
integración crean bases temporales. Hay pruebas de saturación, errores, carrera de
checksum, límites de entrada y página, plazo de recepción y autenticación.
Tener pruebas no demuestra por sí solo haber seguido TDD: el orden test/código
requiere evidencia del proceso, tal como explica el artículo 158-524-1-DR.

La recepción tiene un límite incremental y plazo total. FastAPI aún necesita
materializar un JSON válido: no se afirma memoria cero ni streaming de la extracción.
El listado está acotado por bytes estimados además de cantidad; entrega el contrato
completo o 413. La capacidad real se mide con los tamaños y concurrencia de uso.

Los perfiles k6 smoke/spike y Vegeta de lectura evalúan Documents. El equipo debe
presentar además los scripts de extracción, PDFs oficiales, límites por réplica,
comparación antes/después e investigación del cuello de botella pedidos por el TP.
El máximo de cinco réplicas no implica que todo servicio deba desplegar cinco.

## Observabilidad, seguridad y entrega

Se exportan métricas Prometheus y se incluyen plantillas de scraping, alertas y
dashboard. Infraestructura debe instalarlas y comprobar el canal de notificación.
No se afirma trazabilidad distribuida completa ni alta disponibilidad de MongoDB.
La guía operativa explica incidentes y rollback; backups y restauración siguen
siendo responsabilidades del despliegue.

Usar Conventional Commits. Los nuevos límites pueden rechazar entradas o páginas
antes aceptadas: documentarlos como cambio incompatible, por ejemplo:
`feat(resources)!: limitar memoria y completar observabilidad de Documents`.
No reescribir commits históricos para modificar su formato.
