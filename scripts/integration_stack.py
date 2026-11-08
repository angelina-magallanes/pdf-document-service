"""Ejecuta la integración aislada con un manifiesto de commits fijados."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".integration" / "stack"
VERSIONS_FILE = ROOT / "integration" / "current" / "versions.json"
RUN_ID = re.compile(r"^[0-9]{14}-[a-f0-9]{8}$")


def command(arguments, *, env=None, log=None):
    if log is None:
        result = subprocess.run(arguments, env=env, text=True, encoding="utf-8", errors="replace", capture_output=True)
        output, error = result.stdout, result.stderr
    else:
        # Docker escribe su progreso en stderr. Guardarlo en vivo y separado
        # permite seguir las descargas sin mezclarlo con el JSON de las pruebas.
        error_log = log.with_suffix(log.suffix + ".stderr")
        with log.open("w", encoding="utf-8") as stdout, error_log.open("w", encoding="utf-8") as stderr:
            result = subprocess.run(arguments, env=env, stdout=stdout, stderr=stderr)
        output = log.read_text(encoding="utf-8", errors="replace")
        error = error_log.read_text(encoding="utf-8", errors="replace")
    if result.returncode:
        detail = (error or output)[-2500:]
        raise RuntimeError(f"Falló {arguments[0]} (código {result.returncode}): {detail}")
    return output.strip()


def load_versions(path=None):
    versions = json.loads((Path(path) if path is not None else VERSIONS_FILE).read_text(encoding="utf-8"))
    if set(versions) != {"api", "extractor", "documents"}:
        raise ValueError("Se requieren las versiones de API, Extractor y Documents")
    for version in versions.values():
        if not re.fullmatch(r"[0-9a-f]{40}", version["commit"]):
            raise ValueError("Cada versión debe fijar un commit completo de 40 caracteres")
        if not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\.git", version["repository"]):
            raise ValueError("Se requiere un remoto HTTPS de GitHub sin credenciales")
    return versions


def source_paths(versions):
    return {name: CACHE / "sources" / f"{name}-{version['commit'][:12]}" for name, version in versions.items()}


def prepare_source(path, version):
    if not path.exists():
        path.mkdir(parents=True)
        command(["git", "init", "-q", str(path)])
        command(["git", "-C", str(path), "remote", "add", "origin", version["repository"]])
    remote = command(["git", "-C", str(path), "remote", "get-url", "origin"])
    if remote != version["repository"]:
        raise ValueError(f"Remoto inesperado en {path}; no se modifica esa copia")
    if command(["git", "-C", str(path), "status", "--porcelain", "--untracked-files=all"]):
        raise ValueError(f"Hay cambios locales en {path}; no se reemplazan")
    head = subprocess.run(["git", "-C", str(path), "rev-parse", "--verify", "HEAD"], capture_output=True, text=True)
    if head.returncode:
        # Permite continuar una primera descarga interrumpida, sin descartar archivos.
        command(["git", "-C", str(path), "fetch", "--quiet", "--depth", "1", "origin", version["commit"]])
        command(["git", "-C", str(path), "checkout", "--quiet", "--detach", version["commit"]])
    actual = command(["git", "-C", str(path), "rev-parse", "HEAD"])
    if actual != version["commit"]:
        raise ValueError(f"Commit inesperado en {path}: {actual}; no se cambia esa copia")


def environment(run_id, paths):
    if not RUN_ID.fullmatch(run_id):
        raise ValueError("Identificador de ejecución inválido")
    run_dir = CACHE / "runs" / run_id
    values = {
        "COMPOSE_PROJECT_NAME": "pdf-stack-" + run_id,
        "API_REPO_PATH": paths["api"].as_posix(),
        "EXTRACTOR_REPO_PATH": paths["extractor"].as_posix(),
        "DOCUMENTS_REPO_PATH": paths["documents"].as_posix(),
        "API_IMAGE": "pdf-stack-api:" + run_id,
        "EXTRACTOR_IMAGE": "pdf-stack-extractor:" + run_id,
        "DOCUMENTS_IMAGE": "pdf-stack-documents:" + run_id,
        "MONGO_DATABASE": "pdf_stack_" + run_id.replace("-", "_"),
        "RUN_DIRECTORY": run_dir.as_posix(),
    }
    env = os.environ.copy()
    env.pop("COMPOSE_PROFILES", None)
    env.update(values)
    return env, values, run_dir


def validate_stack(config, values):
    """Impide ejecutar pruebas sobre la red, MongoDB o los volúmenes compartidos."""
    if config.get("name") != values["COMPOSE_PROJECT_NAME"]:
        raise ValueError("El proyecto Compose no corresponde a esta prueba")
    networks = config.get("networks", {})
    if set(networks) != {"isolated"}:
        raise ValueError("La prueba solo puede usar su red isolated")
    network = networks["isolated"]
    if not network.get("internal") or network.get("external"):
        raise ValueError("La red debe ser interna y exclusiva de la prueba")
    if network.get("name") != values["COMPOSE_PROJECT_NAME"] + "_isolated":
        raise ValueError("El nombre de red debe pertenecer al proyecto temporal")
    if config.get("volumes"):
        raise ValueError("La prueba no puede usar volúmenes nombrados compartidos")
    expected = {"api", "extractor", "documents", "mongodb", "traefik", "client"}
    services = config.get("services", {})
    if set(services) != expected:
        raise ValueError("El conjunto de servicios no coincide con el escenario esperado")
    for name, service in services.items():
        if service.get("ports") or service.get("container_name"):
            raise ValueError(f"{name}: no se permiten puertos publicados ni nombres fijos")
        if set(service.get("networks", {})) != {"isolated"}:
            raise ValueError(f"{name}: hay una conexión fuera de la red de pruebas")
        if service.get("labels", {}).get("traefik.enable") != "false":
            raise ValueError(f"{name}: el Traefik compartido debe ignorar este servicio")
        for volume in service.get("volumes", []):
            if volume.get("type") != "bind" or not volume.get("read_only") or "docker.sock" in volume.get("source", ""):
                raise ValueError(f"{name}: montaje ajeno al contrato de pruebas")
    mongo = services["mongodb"]
    if mongo.get("image") != "mongo:7.0.45" or mongo.get("volumes"):
        raise ValueError("MongoDB debe ser 7.0.45 con almacenamiento nuevo para esta corrida")
    if mongo.get("environment", {}).get("MONGO_INITDB_DATABASE") != values["MONGO_DATABASE"]:
        raise ValueError("MongoDB no usa la base exclusiva de esta corrida")
    document_env = services["documents"].get("environment", {})
    if document_env.get("MONGODB_URI") != "mongodb://mongodb:27017" or document_env.get("MONGODB_DATABASE") != values["MONGO_DATABASE"]:
        raise ValueError("Documents debe apuntar únicamente al MongoDB y base temporales")


def compose_command(paths, values):
    harness = paths["api"] / "integration" / "real-stack"
    return ["docker", "compose", "--profile", "client", "-p", values["COMPOSE_PROJECT_NAME"],
            "--project-directory", str(harness), "-f", str(harness / "compose.yaml")]


def render_stack(compose, env, values, run_dir):
    output = command(compose + ["config", "--format", "json"], env=env, log=run_dir / "compose-config.json")
    validate_stack(json.loads(output), values)


def cleanup(run_id, versions):
    paths = source_paths(versions)
    env, values, run_dir = environment(run_id, paths)
    metadata = json.loads((run_dir / "versions.json").read_text(encoding="utf-8"))
    if metadata["project"] != values["COMPOSE_PROJECT_NAME"] or metadata["versions"] != versions:
        raise ValueError("La ejecución guardada no corresponde a estas versiones y proyecto")
    compose = compose_command(paths, values)
    render_stack(compose, env, values, run_dir)
    command(compose + ["down", "--volumes", "--remove-orphans"], env=env, log=run_dir / "cleanup.log")
    print(f"Recursos temporales de {run_id} retirados.", flush=True)


def run_integration(versions, paths):
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8]
    env, values, run_dir = environment(run_id, paths)
    run_dir.mkdir(parents=True)
    (run_dir / "versions.json").write_text(json.dumps({
        "project": values["COMPOSE_PROJECT_NAME"], "versions": versions,
        "mongo_database": values["MONGO_DATABASE"],
    }, indent=2), encoding="utf-8")
    compose = compose_command(paths, values)
    harness = paths["api"] / "integration" / "real-stack"
    summary = {"run_id": run_id, "project": values["COMPOSE_PROJECT_NAME"],
               "versions": versions, "mongo_database": values["MONGO_DATABASE"],
               "checks": [], "passed": False, "cleanup_ok": False}
    started = False

    def step(name, arguments):
        print(name, flush=True)
        output = command(arguments, env=env, log=run_dir / f"{name}.log")
        summary["checks"].append(name)
        return output

    def probe(name, script=None, mode=None):
        args = compose + ["run", "--rm", "--no-deps", "-T"]
        if mode:
            args += ["-e", "CHECK_MODE=" + mode]
        if script:
            args += ["--entrypoint", "python", "client", "/tmp/" + script]
        else:
            args += ["client"]
        output = step(name, args)
        summary[name] = json.loads(output)

    try:
        render_stack(compose, env, values, run_dir)
        step("generar-pdfs", [sys.executable, str(harness / "generate_fixtures.py"), "--output", str(run_dir)])
        # Construir antes de crear contenedores evita dejar un stack parcial durante las descargas.
        step("construir-imagenes", compose + ["build", "api", "extractor", "documents"])
        started = True
        step("iniciar-stack", compose + ["up", "-d", "--no-build", "--wait", "--wait-timeout", "240", "mongodb", "documents", "extractor", "api", "traefik"])
        probe("flujo-completo")
        step("reiniciar-documents", compose + ["restart", "documents"])
        step("esperar-documents", compose + ["up", "-d", "--no-build", "--wait", "--wait-timeout", "120", "documents"])
        probe("persistencia", "persistence_check.py")
        step("detener-extractor", compose + ["stop", "extractor"])
        probe("extractor-no-disponible", "dependency_check.py", "extractor-down")
        step("restaurar-extractor", compose + ["up", "-d", "--no-build", "--wait", "--wait-timeout", "120", "extractor"])
        step("detener-documents", compose + ["stop", "documents"])
        probe("documents-no-disponible", "dependency_check.py", "documents-down")
        summary["passed"] = True
    except BaseException as exc:
        summary["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        if started:
            try:
                command(compose + ["logs", "--no-color"], env=env, log=run_dir / "services.log")
            except Exception as exc:
                summary["logs_error"] = str(exc)
            try:
                command(compose + ["down", "--volumes", "--remove-orphans"], env=env, log=run_dir / "cleanup.log")
                summary["cleanup_ok"] = True
            except Exception as exc:
                summary["cleanup_error"] = str(exc)
        else:
            summary["cleanup_ok"] = True
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Resultado: {run_dir / 'summary.json'}", flush=True)
        if not summary["cleanup_ok"]:
            print(f"Limpieza pendiente: usar --cleanup {run_id} con el mismo manifiesto --versions de esta ejecución.", flush=True)
    if not summary["cleanup_ok"]:
        raise RuntimeError("La prueba terminó, pero hay recursos temporales pendientes de limpieza")
    print("Integración aprobada con las versiones fijadas. MongoDB temporal retirado.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--versions", type=Path, help="Manifiesto alternativo de commits; por defecto usa el manifiesto de integración actual")
    parser.add_argument("--prepare-only", action="store_true", help="Solo preparar las tres copias fijadas")
    parser.add_argument("--cleanup", metavar="RUN_ID", help="Retirar los recursos de una ejecución interrumpida")
    args = parser.parse_args()
    if args.prepare_only and args.cleanup:
        parser.error("Elegí preparación o limpieza")
    versions = load_versions(args.versions)
    command(["git", "--version"])
    if args.cleanup:
        cleanup(args.cleanup, versions)
        return
    if not args.prepare_only:
        command(["docker", "compose", "version"])
        command(["docker", "info", "--format", "{{.ServerVersion}}"])
    paths = source_paths(versions)
    for name, version in versions.items():
        print(f"Preparando {name}: {version['commit'][:7]}", flush=True)
        prepare_source(paths[name], version)
    if args.prepare_only:
        print("Copias listas. El árbol de trabajo actual de Documents se conserva.", flush=True)
        return
    run_integration(versions, paths)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, OSError, KeyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
