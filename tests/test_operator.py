# import shlex
import subprocess
import time
import re
from kopf.testing import KopfRunner


def get_manifest(path):
    """Get sui manifest and change namespace to testing."""
    with open(path, 'r') as f:
        return f.read().replace(
            "namespace: cellxgene", "namespace: testing")


def run_manifest(verb, payload):
    """Runs manifest using kubectl and sleep 1s to wait for effect."""
    subprocess.run(f"cat <<EOF | kubectl {verb} -f -\n{payload}EOF",
                   shell=True, check=True)
    time.sleep(1)


def test_create_and_delete():
    with KopfRunner([
        'run', '-n', 'testing', '--verbose',
        'operator/operator_single-user-instances.py']) as runner:

        # do something while the operator is running.
        sui_manifest = get_manifest("manifests/templates/sui_cxg.yaml")
        run_manifest("create", sui_manifest)
        run_manifest("delete", sui_manifest)

    assert runner.exit_code == 0
    assert runner.exception is None
    assert 'Created child deployment:' in runner.stdout
    assert 'Created child service:' in runner.stdout
    assert 'Created child ingress:' in runner.stdout
    assert 'SingleUserInstance successfully deployed' in runner.stdout

    assert 'Handler \'sui_delete\' is invoked' in runner.stdout
    assert 'Handler \'sui_delete\' succeeded' in runner.stdout
    assert 'Deleted, really deleted, and we are notified.' in runner.stdout

def test_create_and_wait_deletion():
    with KopfRunner([
        'run', '-n', 'testing', '--verbose',
        'operator/operator_single-user-instances.py']) as runner:

        sui_manifest = get_manifest("manifests/templates/sui_cxg.yaml")
        # Set lifespan to 30s.
        sui_manifest = re.sub(r'lifespan [0-9]+', 'lifespan 30', sui_manifest)

        run_manifest("create", sui_manifest)

        # Waiting for auto deletion.
        time.sleep(60)

    assert runner.exit_code == 0
    assert runner.exception is None
    assert 'Timer \'sui_check_lifespan_async\' is invoked.' in runner.stdout
    assert 'marked for deletion with motive: lifespan time exceeded.' in runner.stdout
    assert 'This will also delete children resources' in runner.stdout
    assert 'Timer \'sui_check_lifespan_async\' succeeded.' in runner.stdout

    assert 'Handler \'sui_delete\' is invoked' in runner.stdout
    assert 'Handler \'sui_delete\' succeeded' in runner.stdout
    assert 'Deleted, really deleted, and we are notified.' in runner.stdout
