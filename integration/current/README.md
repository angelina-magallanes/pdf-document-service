# Integración aislada de servicios

El ejecutor construye API, Extractor y Documents desde los commits fijados en
[versions.json](versions.json). No usa el árbol de trabajo actual: prepara copias
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

El manifiesto fija Documents `b851105`, anterior a la autenticación Bearer. Esta
prueba sigue reproduciendo esa revisión y no certifica la autenticación del
código de desarrollo posterior. Para desplegar la revisión protegida, adaptar
primero la API consumidora y el Compose para enviar/configurar el secreto,
actualizar los commits fijados y repetir el flujo. No desactivar la autenticación
para conservar compatibilidad con el consumidor anterior.

Se verifican PDF nuevo y repetido, checksum y contenido, concurrencia, entradas
inválidas, ruta por Traefik aislado, persistencia tras reiniciar Documents y fallas
ante la caída de Extractor y Documents. La [ejecución registrada](validation.md)
aprobó estas comprobaciones. Usa una réplica por servicio y la caché desactivada;
no verifica Redis, el proxy compartido, dos réplicas ni el benchmark oficial.
