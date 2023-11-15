import asyncio
import requests

import kopf
import kubernetes

from datetime import datetime, timezone

TICK = 30 # Number of seconds between refreshes
LATENCY_METRIC = 'nginx_ingress_controller_ingress_upstream_latency_seconds'

@kopf.on.create('cnag.eu', 'v1', 'singleuserinstances')
def create_fn(body, spec, logger, namespace, **_):
    logger.info(f"A handler is called with body: {body}")

    # Get subresources
    deployment, service, ingress = map(spec.get,
                                       ["deployment", "service", "ingress"])

    if not deployment or not service or not ingress:
        raise kopf.PermanentError("Wrong SingleUserInstance definition")

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
    logger.info(f"Created child deployment: {obj}")

    CoreV1Api = kubernetes.client.CoreV1Api()
    obj = CoreV1Api.create_namespaced_service(
        namespace=namespace,
        body=service
    )
    logger.info(f"Created child service: {obj}")

    NetworkingV1Api = kubernetes.client.NetworkingV1Api()
    obj = NetworkingV1Api.create_namespaced_ingress(
        namespace=namespace,
        body=ingress
    )
    logger.info(f"Created child ingress: {obj}")
    logger.info("SingleUserInstance successfully deployed")

def self_delete(meta, logger, motive):
    api = kubernetes.client.CustomObjectsApi()
    query_dict = {
        "group": "cnag.eu",
        "version": "v1",
        "name": meta.name,
        "namespace": meta.namespace,
        "plural": "singleuserinstances"
    }
    api.delete_namespaced_custom_object(**query_dict)

    logger.info(
        f"SingleUserInstance: {meta.name} marked for deletion "+
        f"with motive: {motive}")
    logger.info(f"This will also delete children resources")

@kopf.daemon('cnag.eu', 'v1', 'singleuserinstances')
async def monitor_connection_async(stopped, meta, logger, **_):
    while not stopped:
        # Queries the Ingress-Nginx-Controller metrics server
        # Incluster:
        metrics_uri = "http://metrics.ingress-nginx.svc.cluster.local/metrics" 
        # Local testing: kubectl port-forward -n ingress-nginx svc/metrics 10254:80
        # metrics_uri = "http://localhost:10254/metrics"

        r = requests.get(metrics_uri)
        
        if r.status_code != 200:
            raise kopf.PermanentError(
                "Could not query the ingress-nginx-controller metrics server." +
                f"request at: {metrics_uri}, returned status: {r.status_code}"
            )

        # When the browser closes the connections,
        # this metric will display NaN at the end of the lines
        lines = [
            line for line in r.text.split('\n')
            if line and line[0] != '#'
            and LATENCY_METRIC in line
            and f'{meta.name}' in line
            and LATENCY_METRIC+'_sum' not in line
            and LATENCY_METRIC+'_count' not in line
            # and line[-3:] == 'NaN'
        ]
        logger.debug(f"Upstream latency: {lines}")
        lines = [line for line in lines if line[-3:] == 'NaN']

        if len(lines) > 0:
            self_delete(meta, logger, motive="detected app shutdown")

        # End
        await asyncio.sleep(TICK)

@kopf.timer('cnag.eu', 'v1', 'singleuserinstances',
             interval=TICK, initial_delay=TICK, idle=TICK)
async def check_lifespan(spec, meta, logger, **_):
    lifespan = spec.get('lifespan')
    birth = datetime.fromisoformat(meta.get('creationTimestamp'))
    now = datetime.now(timezone.utc)
    if (now-birth).seconds > lifespan:
        self_delete(meta, logger, motive="lifespan time exceeded")
