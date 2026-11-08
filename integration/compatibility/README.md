# Intentos anteriores de compatibilidad

Este manifiesto conserva los commits de una ejecución que no llegó al flujo HTTP
por un timeout de arranque del Extractor. El [informe](validation.md) explica las
condiciones y no se aplica a otras revisiones. Para repetir esta combinación:

```bash
python3 scripts/integration_stack.py --versions integration/compatibility/versions.json
```

Una combinación posterior aprobó el flujo completo. Consultar
[Integración actual](../current/README.md) para reproducirla.
