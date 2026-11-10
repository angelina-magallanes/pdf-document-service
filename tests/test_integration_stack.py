import json
import subprocess
import sys

import pytest

from scripts import integration_stack as runner


def test_manifiesto_alternativo_no_reemplaza_versiones_historicas():
    historical = runner.load_versions(runner.ROOT / "integration" / "historical" / "versions.json")
    updated = runner.load_versions(runner.ROOT / "integration" / "compatibility" / "versions.json")
    assert historical["extractor"]["commit"] == "5f0de842ee1bcdcd23ce1383427f6b757d8882fa"
    assert updated["extractor"]["commit"] == "dab2c4d54bf5cecbc36b3b319db432c85da7ae59"
    assert updated["documents"]["commit"] == "97efb83503baaa952327bcddf70435f16642a1bf"
    assert updated["api"] == historical["api"]


def test_manifiesto_alternativo_rechaza_revision_sin_fijar(tmp_path):
    versions = runner.load_versions()
    versions["extractor"]["commit"] = "main"
    manifest = tmp_path / "versions.json"
    manifest.write_text(json.dumps(versions))
    with pytest.raises(ValueError, match="commit completo"):
        runner.load_versions(manifest)


@pytest.fixture
def isolated_config():
    versions = runner.load_versions()
    paths = runner.source_paths(versions)
    _, values, _ = runner.environment("20261029210000-1234abcd", paths)
    services = {name: {
        "networks": {"isolated": None}, "labels": {"traefik.enable": "false"},
    } for name in ["api", "extractor", "documents", "mongodb", "traefik", "client"]}
    services["mongodb"].update({
        "image": "mongo:7.0.45",
        "environment": {"MONGO_INITDB_DATABASE": values["MONGO_DATABASE"]},
    })
    services["documents"]["environment"] = {
        "MONGODB_URI": "mongodb://mongodb:27017", "MONGODB_DATABASE": values["MONGO_DATABASE"],
    }
    return {
        "name": values["COMPOSE_PROJECT_NAME"], "services": services,
        "networks": {"isolated": {"internal": True, "name": values["COMPOSE_PROJECT_NAME"] + "_isolated"}},
    }, values


def test_configuracion_aislada_valida(isolated_config):
    config, values = isolated_config
    runner.validate_stack(config, values)


@pytest.mark.parametrize("change", [
    "shared-network", "external-network", "shared-network-name", "shared-db", "remote-db",
    "shared-volume", "mongo-mount", "public-port", "fixed-container", "shared-proxy", "docker-socket",
])
def test_rechaza_acceso_a_recursos_ajenos(isolated_config, change):
    config, values = isolated_config
    if change == "shared-network":
        config["services"]["api"]["networks"]["pdf-network"] = None
    elif change == "external-network":
        config["networks"]["isolated"]["external"] = True
    elif change == "shared-network-name":
        config["networks"]["isolated"]["name"] = "shared-network"
    elif change == "shared-db":
        config["services"]["documents"]["environment"]["MONGODB_DATABASE"] = "pdf_extractext"
    elif change == "remote-db":
        config["services"]["documents"]["environment"]["MONGODB_URI"] = "mongodb://shared:27017"
    elif change == "shared-volume":
        config["volumes"] = {"mongo7_data": {"external": True}}
    elif change == "mongo-mount":
        config["services"]["mongodb"]["volumes"] = [{"type": "bind", "source": "/data/shared", "target": "/data/db", "read_only": True}]
    elif change == "public-port":
        config["services"]["api"]["ports"] = [{"published": "8000", "target": 8000}]
    elif change == "fixed-container":
        config["services"]["documents"]["container_name"] = "documents"
    elif change == "shared-proxy":
        config["services"]["api"]["labels"]["traefik.enable"] = "true"
    elif change == "docker-socket":
        config["services"]["traefik"]["volumes"] = [{"type": "bind", "source": "/var/run/docker.sock", "target": "/var/run/docker.sock", "read_only": True}]
    with pytest.raises(ValueError):
        runner.validate_stack(config, values)


def test_rechaza_identificador_con_ruta_fuera_de_ejecuciones():
    with pytest.raises(ValueError):
        runner.environment("../otro-proyecto", {})


def test_variables_compartidas_no_entran_a_la_prueba(monkeypatch):
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "shared")
    monkeypatch.setenv("MONGO_DATABASE", "shared")
    monkeypatch.setenv("COMPOSE_PROFILES", "production")
    paths = runner.source_paths(runner.load_versions())
    env, values, _ = runner.environment("20261029210000-1234abcd", paths)
    assert env["COMPOSE_PROJECT_NAME"] != "shared"
    assert env["MONGO_DATABASE"] != "shared"
    assert env["MONGO_DATABASE"] == values["MONGO_DATABASE"]
    assert "COMPOSE_PROFILES" not in env


def test_copia_modificada_no_se_descarta(tmp_path):
    repo = tmp_path / "documents"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", "https://github.com/angelina-magallanes/pdf-document-service.git"], check=True)
    work = repo / "trabajo.txt"
    work.write_text("Cambio a conservar")
    with pytest.raises(ValueError, match="Hay cambios locales"):
        runner.prepare_source(repo, runner.load_versions()["documents"])
    assert work.read_text() == "Cambio a conservar"


def test_limpieza_rechaza_proyecto_ajeno(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "CACHE", tmp_path)
    versions = runner.load_versions()
    run_id = "20261029210000-1234abcd"
    folder = tmp_path / "runs" / run_id
    folder.mkdir(parents=True)
    (folder / "versions.json").write_text(json.dumps({"project": "shared", "versions": versions}))
    with pytest.raises(ValueError, match="no corresponde"):
        runner.cleanup(run_id, versions)


def test_logs_de_docker_no_contaminan_json_del_cliente(tmp_path):
    log = tmp_path / "probe.log"
    output = runner.command([
        sys.executable, "-c",
        "import sys; print('mensaje de Docker', file=sys.stderr); print('{\"ok\": true}')",
    ], log=log)
    assert json.loads(output) == {"ok": True}
    assert "mensaje de Docker" in (tmp_path / "probe.log.stderr").read_text()


def test_authenticated_environment_never_uses_real_secret(monkeypatch):
    monkeypatch.setenv('DOCUMENTS_API_TOKEN', 'private-user-secret')
    paths = runner.source_paths(runner.load_versions())
    env, values, _ = runner.environment('20261029210000-1234abcd', paths, authenticated=True)
    assert env['DOCUMENTS_API_TOKEN'] != 'private-user-secret'
    assert len(env['DOCUMENTS_API_TOKEN']) >= 32
    assert 'DOCUMENTS_API_TOKEN' not in values


def test_rendered_configuration_redacts_token(isolated_config, monkeypatch, tmp_path):
    config, values = isolated_config
    values['authenticated'] = True
    token = 'temporary-test-secret-only-1234567890'
    for name in ('documents', 'api', 'client'):
        config['services'][name].setdefault('environment', {})['DOCUMENTS_API_TOKEN'] = token
    monkeypatch.setattr(runner, 'command', lambda *args, **kwargs: json.dumps(config))
    runner.render_stack([], {'DOCUMENTS_API_TOKEN': token}, values, tmp_path)
    saved = (tmp_path / 'compose-config.json').read_text()
    assert token not in saved
    assert saved.count('REDACTED') == 3


def test_source_hashes_include_nested_application_modules(tmp_path):
    for name in ("Dockerfile", "pyproject.toml", "uv.lock", "app/routers/documents.py", "app/models/document.py"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name)
    hashes = runner.source_hashes(tmp_path)
    assert "app/routers/documents.py" in hashes
    assert "app/models/document.py" in hashes
    before = hashes["app/routers/documents.py"]
    (tmp_path / "app/routers/documents.py").write_text("changed")
    assert runner.source_hashes(tmp_path)["app/routers/documents.py"] != before
