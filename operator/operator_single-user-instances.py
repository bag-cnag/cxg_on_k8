import requests

from functools import cache
from subprocess import run
from datetime import datetime, timezone

import kubernetes
import kopf
from kopf._cogs.structs.patches import Patch
from kopf._cogs.clients import api


TICK = 30 # Number of seconds between refreshes
LATENCY_METRIC = 'nginx_ingress_controller_ingress_upstream_latency_seconds'


class dotdict(dict):
    """dict implementing getattr so that attributes can be accessed using 
       dict.attr syntax. Allows us to forge an object like parameter.
    """
    def __getattr__(self, name):
        return self[name]


@cache
def incluster() -> bool:
    """Check whether operator is running inside a cluster."""
    return not b'NXDOMAIN' in run(
        ['nslookup', 'kubernetes.default.svc.cluster.local'],
        capture_output=True).stdout


@kopf.on.delete('cnag.eu', 'v1', 'singleuserinstances', optional=True)
async def sui_delete(body, resource, namespace, logger, **_):
    """Explicitely removes the finalizers in case kopf has a hard time."""
    name = body.metadata.name
    logger.info(f"Deletion handler called for SingleUserInstance {name}")

    patched_body = await api.patch(
        url=resource.get_url(namespace=namespace, name=name),
        headers={'Content-Type': 'application/merge-patch+json'},
        payload=Patch({'metadata':{'finalizers': []}}),
        settings=dotdict({ # OperatorSettings mockup.
            'networking': dotdict({
                'request_timeout': TICK,
                'connect_timeout': TICK,
                'error_backoffs': 5
            })
        }),
        logger=logger,
    )
    logger.debug(patched_body)


@kopf.on.create('cnag.eu', 'v1', 'singleuserinstances')
def sui_create(body, spec, logger, namespace, **_):
    logger.info(f"A handler is called with body: {body}")
    # Get subresources
    deployment, service, ingress = map(spec.get,
                                       ["deployment", "service", "ingress"])
    # Adopt them
    kopf.adopt(deployment)
    kopf.adopt(service)
    kopf.adopt(ingress)

    # Create them
    AppsV1Api = kubernetes.client.AppsV1Api()
    obj = AppsV1Api.create_namespaced_deployment(
        namespace=namespace,
        body=deployment
    )
    logger.debug(f"Created child deployment: {obj}.")

    CoreV1Api = kubernetes.client.CoreV1Api()
    obj = CoreV1Api.create_namespaced_service(
        namespace=namespace,
        body=service
    )
    logger.debug(f"Created child service: {obj}.")

    NetworkingV1Api = kubernetes.client.NetworkingV1Api()
    obj = NetworkingV1Api.create_namespaced_ingress(
        namespace=namespace,
        body=ingress
    )
    logger.debug(f"Created child ingress: {obj}.")
    logger.info("SingleUserInstance successfully deployed.")


async def sui_self_delete_async(body, logger, motive):
    CustomObjectsApi = kubernetes.client.CustomObjectsApi()
    CustomObjectsApi.delete_namespaced_custom_object(
        group="cnag.eu",
        version="v1",
        name=body.metadata.name,
        namespace=body.metadata.namespace,
        plural="singleuserinstances"
    )
    logger.info(
        f"SingleUserInstance: {body.metadata.name} marked for deletion "+
        f"with motive: {motive}. This will also delete children resources.")


@kopf.timer('cnag.eu', 'v1', 'singleuserinstances',
             interval=TICK, initial_delay=TICK, idle=TICK)
async def sui_monitor_connection_async(body, meta, logger, **_):
    # Queries the Ingress-Nginx-Controller metrics server
    # Local testing: kubectl port-forward -n ingress-nginx svc/metrics 10254:80
    metrics_uri = ("http://metrics.ingress-nginx.svc.cluster.local" 
                   if incluster() else "http://localhost:10254") + "/metrics"

    r = None
    try:
        r = requests.get(metrics_uri)
        if r.status_code != 200:
            raise Exception()
    except:
        raise kopf.PermanentError(
            "Could not query the ingress-nginx-controller metrics server." +
            f' Request at: {metrics_uri} ' +
            (f'returned status: {r.status_code}.' 
             if r else 'raised an exception.'))

    # metric -> end of lines <=> NaN some time after connection is closed.
    lines = [
        line for line in r.text.split('\n')
        if line and line[0] != '#'
        and LATENCY_METRIC in line
        and f'{meta.name}' in line
        and LATENCY_METRIC+'_sum' not in line
        and LATENCY_METRIC+'_count' not in line
    ]
    logger.debug(f"Upstream latency: {lines}")
    lines = [line for line in lines if line[-3:] == 'NaN']

    if lines:
        await sui_self_delete_async(body, logger, 
                                    motive="detected app shutdown")


@kopf.timer('cnag.eu', 'v1', 'singleuserinstances',
             interval=TICK, initial_delay=TICK, idle=TICK)
async def sui_check_lifespan_async(spec, body, meta, logger, **_):
    lifespan = spec.get('lifespan')
    birth = datetime.fromisoformat(meta.get('creationTimestamp'))
    now = datetime.now(timezone.utc)

    if (now-birth).seconds > lifespan:
        await sui_self_delete_async(body, logger, 
                                    motive="lifespan time exceeded")
