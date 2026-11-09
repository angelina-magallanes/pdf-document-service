# Integración aislada de servicios

El ejecutor construye API, Extractor y Documents desde los commits fijados en
[versions.json](versions.json). Por defecto no usa el árbol de trabajo actual: prepara copias
separadas y rechaza copias modificadas o con un commit diferente. Los repositorios
originales se indican en el manifiesto para permitir su descarga reproducible.

Requisitos: Git, Python 3, Docker y Compose. Desde la raíz del repositorio:

```bash
python3 scripts/integration_stack.py
```

En Windows se puede usar `python`. La primera ejecución descarga repositorios,
imágenes y dependencias. Para preparar las copias sin iniciar contenedores:

```bash
python3 scripts/integration_stack.py --prepare-only
```

Cada ejecución tiene una red interna, un proyecto Compose y una base MongoDB
7.0.45 exclusivos. No publica puertos, no usa `pdf-network`, el `.env` de desarrollo
ni datos compartidos. Valida la configuración antes de iniciar y retira los
contenedores, la red y los volúmenes al terminar. Los resultados y logs se guardan
en `.integration/stack/runs/<identificador>/`, carpeta ignorada por Git.

Si se interrumpe antes de limpiar, usar el identificador informado:

```bash
python3 scripts/integration_stack.py --cleanup <identificador>
```

Para ejecutar otro manifiesto, agregar `--versions <ruta>` tanto al ejecutar como
al limpiar. Existen [versiones históricas](../historical/README.md) y un escenario
[de intentos anteriores](../compatibility/README.md). Solo se deben usar hashes de
commit completos; no se ejecutan automáticamente cambios locales de los servicios.

## Alcance

El manifiesto fija API `e191097`, Extractor `6720c32` y Documents `7469779`, con
Bearer. El overlay `auth.compose.yaml` configura el mismo secreto temporal en API,
Documents y cliente. El ejecutor no usa tu token real ni lo escribe en los informes.
La comprobación de autenticación verifica salud pública, 401 sin token y con token
incorrecto, y listado autenticado.

Para construir los cambios locales de Documents sin hacer un commit:

```bash
python3 scripts/integration_stack.py --local-documents
```

Se registran hashes SHA-256 de los archivos de construcción y aplicación en
`summary.json`; la revisión base se conserva como referencia y no se presenta
el árbol modificado como si fuera ese commit. Tras publicar una nueva revisión,
actualizar el commit de Documents en el manifiesto para reproducirla sin esta opción.
Los manifiestos históricos con `--versions` conservan el escenario anterior sin
overlay Bearer. No usar esa opción para validar la autenticación actual.

Se verifican PDF nuevo y repetido, checksum y contenido, concurrencia, entradas
inválidas, ruta por Traefik aislado, persistencia tras reiniciar Documents y fallas
ante la caída de Extractor y Documents. La [ejecución registrada](validation.md)
aprobó estas comprobaciones. Usa una réplica por servicio y la caché desactivada;
no verifica Redis, el proxy compartido, dos réplicas ni el benchmark oficial.
