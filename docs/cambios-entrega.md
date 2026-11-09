# Cambios para la próxima entrega

## Cambios incompatibles que hay que comunicar

El cuerpo HTTP de Documents queda limitado por defecto a 4 MiB y a 15 s de
recepción (413/408). El listado completo tiene un presupuesto conservador de
8 MiB (413; reducir `limit` o consultar por ID). Los valores se pueden configurar
por entorno. No cambian los campos del documento ni la deduplicación.
El límite de 20 MiB del PDF en el Extractor es otro contrato: no confundirlo con
el tamaño del JSON extraído.

## Implementación

- Límite incremental de entrada y timeout, incluso sin Content-Length.
- Listado acotado en memoria, cursor cerrado y lotes pequeños.
- Cupo de concurrencia retenido hasta completar la respuesta.
- Errores del driver encapsulados en acceso a datos.
- Métricas protegidas, dashboard y alertas de ejemplo; guía de recuperación.
- Integración con API Bearer y secretos temporales redactados del registro.
- Pruebas de carga reproducibles, comparación breve y límites de capacidad explícitos.

## Publicación

Revisar el diff y usar un commit como:

```bash
git diff --check
git status --short
git add app tests scripts monitoring docs integration/current .env.example docker-compose.yml README.md pyproject.toml uv.lock requirements.txt .github/workflows/ci.yml
git commit -m "feat(resources)!: limitar memoria y completar observabilidad de Documents" -m "BREAKING CHANGE: limitar el cuerpo HTTP a 4 MiB y 15 segundos, y el listado a un presupuesto de 8 MiB; limites configurables por entorno."
```

El código sigue sin commit hasta ejecutar estos comandos. Después de publicarlo,
fijar su SHA completo en `integration/current/versions.json` y repetir el escenario
sin `--local-documents`. Esa actualización necesita un commit posterior porque
un commit no puede contener su propio hash. No agregar `.env` ni el secreto real.
