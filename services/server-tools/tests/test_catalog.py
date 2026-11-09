"""Domain tests: the commands the platform builds, and the rules that reject bad arguments."""

import pytest

from server_tools.tools.domain import catalog, masking
from server_tools.tools.domain.catalog import ImagePolicy
from server_tools.tools.domain.model import RunContext, Target, ToolRejected

CTX = RunContext("r1", "c1", "superapp", "dev", "Sarinzha K.")
ALL = tuple(catalog.TOOLS)
DEV = Target("dev-docker-01", "dev", ("superapp",), ALL)


def build(tool, target=DEV, **args):
    return catalog.TOOLS[tool].build(args, CTX, target, ImagePolicy())


def test_logs_command_is_fixed_and_quoted():
    cmd = build("docker_logs", service="orders-service", since="2h", tail=100)
    assert "com.docker.compose.project=superapp-dev" in cmd.script
    assert "docker logs --since 2h --tail 100" in cmd.script
    assert cmd.keep == "tail"


@pytest.mark.parametrize("path", ["../../etc/passwd", "/etc/passwd", "/opt/superai/tiffany/dev/x", "keys/id_rsa",
                                  "certs/server.key", "a/../../b"])
def test_paths_outside_system_folder_or_secrets_are_rejected(path):
    with pytest.raises(ToolRejected):
        build("file_read", path=path)


def test_relative_path_resolves_inside_root_and_is_checked_again_on_server():
    cmd = build("file_read", path="infra/compose.yml", from_line=10, lines=5)
    assert "realpath -m -- /opt/superai/superapp/dev/infra/compose.yml" in cmd.script
    assert "sed -n '10,14p'" in cmd.script


def test_agent_cannot_inject_shell_or_flags():
    cmd = build("compose_run", service="orders-service", args=["--privileged", "; rm -rf /"], reason="migrate")
    assert "'; rm -rf /'" in cmd.script  # quoted: one literal argument, not a second command
    with pytest.raises(ToolRejected):
        build("docker_logs", service="x; reboot")


def test_write_tools_need_a_reason():
    with pytest.raises(ToolRejected, match="reason"):
        build("compose_restart", service="orders-service")


def test_env_files_cannot_be_written_and_are_read_as_names_only():
    with pytest.raises(ToolRejected, match="Vault"):
        build("file_write", path="infra/env/orders.env", content="A=1", reason="x")
    post = catalog.TOOLS["file_read"].post
    assert post("DB_PASSWORD=s3cret\n# comment", {"path": "orders.env"}) == "DB_PASSWORD=***\n# comment"


@pytest.mark.parametrize("image", ["postgres:latest", "postgres", "evil/miner:1.0", "registry/tiffany/x:1"])
def test_images_must_be_pinned_and_allowed(image):
    with pytest.raises(ToolRejected):
        build("docker_run", image=image, reason="x")


def test_docker_run_always_rm_labels_and_system_network():
    cmd = build("docker_run", image="registry/superapp/orders-service:0.1.2", args=["--migrate-only"],
                env={"DB_PASSWORD": "p"}, reason="run migration")
    assert cmd.script.startswith("docker run --rm --network superapp-dev --label superai.system=superapp")
    assert "DB_PASSWORD=***" in catalog.display(cmd, "docker_run", {})  # card never shows the value


def test_ssh_exec_command_is_wrapped_in_timeout():
    cmd = build("ssh_exec", command="journalctl -u docker | tail -5", reason="daemon restarts", timeout_s=30)
    assert cmd.script == "timeout 30 bash -c 'journalctl -u docker | tail -5'"


def test_masking():
    text = "password=hunter2 url=postgres://app:pa55@db:5432/x Authorization: Bearer abcdefghijkl"
    out = masking.mask(text)
    assert "hunter2" not in out and "pa55" not in out and "abcdefghijkl" not in out


def test_long_logs_keep_the_end():
    text = "\n".join(str(i) for i in range(1000))
    out = masking.cap(text, keep="tail")
    assert out.splitlines()[-1] == "999" and "output cut" in out
