import time
import re
import pytest

from subprocess import run, Popen, CalledProcessError
from kopf.testing import KopfRunner


TICK = 30 # Operator refreshing rate
NSTEST = 'testing'
RUNNER_CMD = ['run', '-n', 'testing', '--verbose',
               'operator/operator_single-user-instances.py', '--standalone']
PFORWARD_CMD = ['kubectl', 'port-forward', '-n', 
                   'ingress-nginx', 'svc/metrics', '10254:80']


def expose_metrics_server(func):
    """Decorator to ensure metrics server is accessible in a test.

        shell=True justification:
            if shell=False the command aliases will leave some processes open 
            after the end of the test thus the metrics server will stay exposed.
            Setting that flag to true ensures proper kill on the subprocess.

            To test on your machine:
                ps aux | grep kubectl
                curl -k -L -S http://localhost:10254/metrics
    """
    def wrapper():
        with Popen(PFORWARD_CMD, shell=True) as proc:
            func()
            proc.kill()
    return wrapper


def get_manifest(path, lifespan=None):
    """Load sui manifest, change namespace to testing and lifespan if set."""
    with open(path, 'r') as f:
        m =  re.sub(r'namespace: [a-z0-9\-]+',
                    f'namespace: {NSTEST}', f.read())
        return re.sub(r'lifespan: [0-9]+',
                      f'lifespan: {lifespan}', m) if lifespan else m


def run_manifest(verb, payload, tempo=1):
    """Runs manifest using kubectl and sleep 'tempo' to wait for effect."""
    run(f"cat <<EOF | kubectl {verb} -f -\n{payload}EOF",
        shell=True, check=True)
    time.sleep(tempo)


@expose_metrics_server
def test_create_and_delete():
    with KopfRunner(RUNNER_CMD) as runner:
        # do something while the operator is running.
        sui_manifest = get_manifest("manifests/templates/sui_cxg.yaml")
        run_manifest("create", sui_manifest)
        run_manifest("delete", sui_manifest, 5)

    assert runner.exit_code == 0
    assert runner.exception is None
    assert 'Created child deployment:' in runner.stdout
    assert 'Created child service:' in runner.stdout
    assert 'Created child ingress:' in runner.stdout
    assert 'SingleUserInstance successfully deployed' in runner.stdout

    assert 'Handler \'sui_delete\' is invoked' in runner.stdout
    assert 'Handler \'sui_delete\' succeeded' in runner.stdout
    assert 'Deleted, really deleted, and we are notified.' in runner.stdout


@expose_metrics_server
def test_create_and_wait_deletion():
    with KopfRunner(RUNNER_CMD) as runner:
        sui_manifest = get_manifest("manifests/templates/sui_cxg.yaml",
                                    lifespan=TICK)
        run_manifest("create", sui_manifest, 5)
        # Waiting for auto deletion.
        time.sleep(2*TICK)

    assert runner.exit_code == 0
    assert runner.exception is None
    assert 'Timer \'sui_check_lifespan_async\' is invoked.' in runner.stdout
    assert 'marked for deletion with motive: lifespan time exceeded.' in runner.stdout
    assert 'This will also delete children resources' in runner.stdout
    assert 'Timer \'sui_check_lifespan_async\' succeeded.' in runner.stdout
    assert 'Handler \'sui_delete\' is invoked' in runner.stdout
    assert 'Handler \'sui_delete\' succeeded' in runner.stdout
    assert 'Deleted, really deleted, and we are notified.' in runner.stdout


def test_create_without_metrics_server():
    with KopfRunner(RUNNER_CMD) as runner:
        sui_manifest = get_manifest("manifests/templates/sui_cxg.yaml",
                                    lifespan=120)
        run_manifest("create", sui_manifest, 5)
        # Wait for a pass of the timers.
        time.sleep(TICK)
        run_manifest("delete", sui_manifest, 5)

    assert runner.exit_code == 0
    assert runner.exception is None
    # Kopf is not properly reraising exceptions, we find in stdout.
    assert ('Timer \'sui_monitor_connection_async\' failed permanently: Could '+
            'not query the ingress-nginx-controller metrics server.') in runner.stdout


def test_create_with_wrong_manifest():
    with pytest.raises(CalledProcessError):
        with KopfRunner(RUNNER_CMD):
            sui_manifest = get_manifest("manifests/templates/sui_cxg.yaml")
            # Remove service from manifest
            run_manifest("create", 
                        sui_manifest[:sui_manifest.rfind('service')] + '\n')
