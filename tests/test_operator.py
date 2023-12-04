import time
import re
import pytest
import os
import threading
from signal import signal, SIGTERM, SIGKILL, SIGHUP, SIGINT

from subprocess import run, Popen, CalledProcessError, call, PIPE, STDOUT
from kopf.testing import KopfRunner


# Operator global vars.
TICK = 3
ENV = {
    'K8_SUI_OP_TICK': str(TICK),
    'K8_SUI_OP_TO_UNVIS': str(3*TICK)
}

NSTEST = 'testing'
SUI_TEST = "manifests/tests/sui_test.yaml"
RUNNER_CMD = ['run', '--verbose', '--standalone', '-n', f'{NSTEST}',
              'operator/operator_single-user-instances.py']
# Has to be in one block or will fail.
# PFORWARD_CMD = ['kubectl port-forward svc/metrics 10254:80 -n ingress-nginx']
PFORWARD_CMD = ['kubectl', 'port-forward', 'svc/metrics', '10254:80', '-n', 'ingress-nginx']



def expose_metrics_server(func):
    """Decorator to ensure metrics server is accessible in a test.

        subcall to pkill justification:
            proc.terminate()/proc.kill()/os.kill(proc.pid, signal.SIGTERM) and
            other variations are not enough to kill children processes.
            It means that the metrics server will remain exposed even after test
            termination.
            Relevant post on SO: https://stackoverflow.com/questions/77600221/properly-run-and-kill-background-process-in-a-python-script-pytest 

            To check on your machine:
                ps aux | grep kubectl
                curl -k -L -S http://localhost:10254/metrics
    """
    def wrapper():
        with Popen(PFORWARD_CMD,
                   shell=False,
                   start_new_session=True) as proc:
            func()
            call(['pkill', '-9', '-s', str(os.getsid(proc.pid))])
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
    with KopfRunner(RUNNER_CMD, env=ENV) as runner:
        # do something while the operator is running.
        sui_manifest = get_manifest(SUI_TEST)
        run_manifest("create", sui_manifest)
        run_manifest("delete", sui_manifest)

    assert runner.exit_code == 0
    assert runner.exception is None
    assert 'Created child deployment:' in runner.stdout
    assert 'Created child service:' in runner.stdout
    assert 'Created child ingress:' in runner.stdout
    assert 'SingleUserInstance successfully deployed' in runner.stdout

    assert 'Handler \'sui_delete_async\' is invoked' in runner.stdout
    assert 'Handler \'sui_delete_async\' succeeded' in runner.stdout
    assert 'Deleted, really deleted, and we are notified.' in runner.stdout

@expose_metrics_server
def test_create_and_wait_deletion():
    with KopfRunner(RUNNER_CMD, env=ENV) as runner:
        sui_manifest = get_manifest(SUI_TEST, lifespan=TICK)
        run_manifest("create", sui_manifest)
        # Waiting for auto deletion.
        time.sleep(2*TICK)

    assert runner.exit_code == 0
    assert runner.exception is None
    assert 'Timer \'sui_check_lifespan_async\' is invoked.' in runner.stdout
    assert 'marked for deletion with motive: lifespan time exceeded.' in runner.stdout
    assert 'This will also delete children resources' in runner.stdout
    assert 'Timer \'sui_check_lifespan_async\' succeeded.' in runner.stdout
    assert 'Handler \'sui_delete_async\' is invoked' in runner.stdout
    assert 'Handler \'sui_delete_async\' succeeded' in runner.stdout
    assert 'Deleted, really deleted, and we are notified.' in runner.stdout


@expose_metrics_server
def test_create_and_wait_unvisited_timeout():
    with KopfRunner(RUNNER_CMD, env=ENV) as runner:
        sui_manifest = get_manifest(SUI_TEST, lifespan=20*TICK)
        run_manifest("create", sui_manifest)
        # Waiting for timeout
        time.sleep(4*TICK)

    assert runner.exit_code == 0
    assert runner.exception is None
    assert 'Timer \'sui_check_lifespan_async\' is invoked.' in runner.stdout
    assert 'marked for deletion with motive: instance requested but not visited.' in runner.stdout
    assert 'This will also delete children resources' in runner.stdout
    assert 'Handler \'sui_delete_async\' is invoked' in runner.stdout
    assert 'Handler \'sui_delete_async\' succeeded' in runner.stdout
    assert 'Deleted, really deleted, and we are notified.' in runner.stdout


def test_create_without_metrics_server():
    with KopfRunner(RUNNER_CMD, env=ENV) as runner:
        sui_manifest = get_manifest(SUI_TEST, lifespan=10*TICK)
        run_manifest("create", sui_manifest)
        # Wait for a pass of the timers.
        time.sleep(TICK)
        run_manifest("delete", sui_manifest)

    assert runner.exit_code == 0
    assert runner.exception is None
    # Kopf is not properly reraising exceptions, we find in stdout.
    assert ('Timer \'sui_monitor_connection_async\' failed permanently: Could '+
            'not query the ingress-nginx-controller metrics server.') in runner.stdout


def test_create_with_wrong_manifest():
    with pytest.raises(CalledProcessError):
        with KopfRunner(RUNNER_CMD, env=ENV):
            sui_manifest = get_manifest(SUI_TEST)
            # Remove service from manifest
            run_manifest("create", 
                        sui_manifest[:sui_manifest.rfind('service')] + '\n')
