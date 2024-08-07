#!/usr/bin/python3
####################################################
# Script that demonstrates use of the api handler to create an instance of cxg
# In this case a cellxgene instance is made of a joined:
#     - deployment
#     - service
#     - ingress
##########################

import uuid
from kubernetes.client.exceptions import ApiException

from k8_api_handler import K8ApiHandler
from yaml_to_py import py_to_yaml

## !! See README.md for info on how to set those variables
# Host
K8_IP = "192.168.49.2"
K8_PORT = "8443"
HOST_NAME = "minikube.local"

# Kubernetes Authentication
CLUSTER_ROOT_CERTIFICATE = "/home/ejodry/.minikube/ca.crt"
SERVICE_ACCOUNT = 'omicsdm'
ACCOUNT_TOKEN = 'eyJhbGciOiJSUzI1NiIsImtpZCI6InNBYjFyaHdDU1B5OVBNREdOenUyX3hDeWZGM0Ztb05pMnhIbkJTcUNsajgifQ.eyJpc3MiOiJrdWJlcm5ldGVzL3NlcnZpY2VhY2NvdW50Iiwia3ViZXJuZXRlcy5pby9zZXJ2aWNlYWNjb3VudC9uYW1lc3BhY2UiOiJkZWZhdWx0Iiwia3ViZXJuZXRlcy5pby9zZXJ2aWNlYWNjb3VudC9zZWNyZXQubmFtZSI6Im9taWNzZG0tdG9rZW4iLCJrdWJlcm5ldGVzLmlvL3NlcnZpY2VhY2NvdW50L3NlcnZpY2UtYWNjb3VudC5uYW1lIjoib21pY3NkbSIsImt1YmVybmV0ZXMuaW8vc2VydmljZWFjY291bnQvc2VydmljZS1hY2NvdW50LnVpZCI6IjRlMTI0NzhmLTNhM2MtNDQwNi04MmNhLTk4YzA4OGZkYmFjMiIsInN1YiI6InN5c3RlbTpzZXJ2aWNlYWNjb3VudDpkZWZhdWx0Om9taWNzZG0ifQ.UK9ISX-qOhzzyP1xdZVvJ38BDVfbYkQh1wclpIyXWMix-jQwylgCj0F5mhqNurlcFSaQhSbRCjimsXCsG-URDCnWHlmok1_lj3bU7avdwiGCefcxDBsqpqrym6PxcIAdCSHfm5DA3WQ-CVBPjx6mlNnEvwzCjueLpV94S5jvM-fDvx0-rvnwAGKZH83KjD37x57iyxjsUo00Bl5G_1dm3g5hXzToxnOuA_JV5_1tJLy80rr7pmXXdEsf-PbvIGajch6b2-_Xw29lv5vJod3X6LQjST9Q6HMHY2kFe5vx6rTwznSIoLuVQTxBW9_1AOdf-n4nipyv7aQXIxyErTPmNg'

# Oauth2 config
KEYCLOAK_ENDPOINT = 'http://host.minikube.internal:8080' # Minikube
KEYCLOAK_REALM = '3TR'

OAUTH2_IMAGE = 'quay.io/oauth2-proxy/oauth2-proxy:v7.5.1'
OAUTH2_APP_NAME = 'oauth2-proxy'

OAUTH2_CLIENT_ID = 'cellxgene'
OAUTH2_CLIENT_SECRET = 'JS2dEHmzFYaQPrfxdR3XSpQs9lxEQ17Z'
OAUTH2_NAMESPACE = 'ingress-nginx'

OAUTH2_PORT = 8091
PROXY_BUFFER_SIZE = '64k'

# Cellxgene config
CXG_APP_NAME = 'cellxgene'
CXG_IMAGE = 'cellxgene:1.1.2-python3.11-slim-bookworm' # 'cellxgene:xsmall'
AWS_CLI_IMAGE = 'aws_cli:xsmall'
CXG_PORT = 5005

# API info
SERVICE_PORT = 38005
NAMESPACE = "cellxgene"

def oauth2proxy_manifests(name: str):
    """
    Return the manifests needed to instanciate oauth2-proxy as python dictionaries
    Sets the fields depending on variables
    """
    deployment = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": name,
            "namespace": OAUTH2_NAMESPACE
        },
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": {"app": name}},
            "template": {
                "metadata": {"labels": {"app": name}},
                "spec": {
                    "containers": [{
                        "name": name,
                        "image": OAUTH2_IMAGE,
                        "ports": [{"containerPort": OAUTH2_PORT}],
                        "args": [
                            "--provider=keycloak-oidc",
                            f"--oidc-issuer-url={KEYCLOAK_ENDPOINT}/realms/{KEYCLOAK_REALM}",
                            f"--oidc-extra-audience={OAUTH2_CLIENT_ID}",
                            f"--client-id={OAUTH2_CLIENT_ID}",
                            f"--client-secret={OAUTH2_CLIENT_SECRET}",
                            "--cookie-secure=false",
                            "--cookie-secret=dca70153c0ffd68a98696b6957b26e88",
                            "--cookie-refresh=1m",
                            "--cookie-expire=30m",
                            f"--cookie-domain={HOST_NAME}",
                            f"--whitelist-domain={HOST_NAME}",
                            "--email-domain=*",
                            "--insecure-oidc-allow-unverified-email=true",
                            "--ssl-insecure-skip-verify=true",
                            "--ssl-upstream-insecure-skip-verify=true",
                            "--pass-authorization-header=true",
                            "--pass-access-token=true",
                            "--set-authorization-header=true",
                            "--set-xauthrequest=true",
                            "--code-challenge-method=S256",
                            "--upstream=file:///dev/null",
                            f"--http-address=0.0.0.0:{OAUTH2_PORT}"
                        ]
                    }]
                }
            }
        }
    }
    service = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": name,
            "namespace": OAUTH2_NAMESPACE,
            "labels": {"name": name}
        },
        "spec": {
            "type": "ClusterIP",
            "hostNetwork": "true",
            "selector": {"app": name},
            "ports": [{
                "name": "http",
                "port": OAUTH2_PORT
            }]
        }
    }
    ingress = {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "Ingress",
        "metadata": {
            "annotations": {
                "nginx.ingress.kubernetes.io/proxy-buffer-size": PROXY_BUFFER_SIZE
            },
            "name": name,
        },
        "spec": {
            "ingressClassName": "nginx",
            "rules": [{
                "host": HOST_NAME,
                "http": {
                    "paths": [{
                        "path": "/oauth2",
                        "pathType": "Prefix",
                        "backend": {
                            "service": {
                                "name": name,
                                "port": {"number": OAUTH2_PORT}
                            }
                        }
                    }]
                }
            }]
        }
    }

    return deployment, service, ingress

def cellxgene_manifest(name: str):
    """
    Return the SingleUserInstance manifest combining the deployment, service 
    and ingress with an extra field for the lifespan  
    """
    deployment, service, ingress = cellxgene_manifests(name)

    return {
        "apiVersion": "cnag.eu/v1",
        "kind": "SingleUserInstance",
        "metadata": {
            "name": name,
            "labels": {
                "app": CXG_APP_NAME,
                "instance": name
            }
        },
        "spec": {
            "lifespan": 999,
            "deployment": deployment,
            "service": service,
            "ingress": ingress
        }
    }

def cellxgene_manifests(name: str):
    """
    Return the manifests needed to instanciate cellxgene as python dictionaries
    Sets the fields depending on variables
    """
    USERNAME = "UserId"
    DATASETNAME = "DataSetId"
    DATASET = "https://github.com/chanzuckerberg/cellxgene/raw/main/example-dataset/pbmc3k.h5ad"
    BUCKET = "s3://bucketdevel3tropal"
    USER_FILES_DIR = "cxg_on_k8"
    USER_FILES_PATH = f'{BUCKET}/{USER_FILES_DIR}/{USERNAME}/{DATASETNAME}/'

    deployment = {
        "apiVersion":"apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": name,
            "labels": {
                "app": CXG_APP_NAME,
                "instance": name
            }
        },
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": {"app": CXG_APP_NAME}},
            "template": {
                "metadata": {
                    "labels": {
                        "app": CXG_APP_NAME,
                        "instance": name
                    }
                },
                "spec": {
                    "securityContext": {
                        "runAsUser": 1000,
                        "runAsGroup": 1000,
                        "fsGroup": 1000,
                    },
                    # "initContainers": [{
                    #     "name": "init-cellxgene",
                    #     "image": AWS_CLI_IMAGE,
                    #     "command": [
                    #         "/bin/sh", "-c", (
                    #             f"aws s3 sync {USER_FILES_PATH} /data && "
                    #             f"touch /data/annotations.csv /data/gene_sets.csv"
                    #         )
                    #     ],
                    #     "envFrom": [{"secretRef": {"name": "aws-cred-secret"}}],
                    #     "volumeMounts": [{
                    #         "name": "data",
                    #         "mountPath": "/data"
                    #     }]
                    # }],
                    "containers": [{
                        "name": name,
                        "image": CXG_IMAGE,
                        "ports": [{"containerPort": CXG_PORT}],
                        "args": [
                            "launch", "--verbose",
                            "-p", f"{CXG_PORT}",
                            "--host", "0.0.0.0",
                            DATASET,
                            "--annotations-file", "/data/annotations.csv",
                            "--gene-sets-file", "/data/gene_sets.csv"
                        ],
                        "envFrom": [{"secretRef": {"name": "aws-cred-secret"}}],
                        "volumeMounts": [{
                            "name": "data",
                            "mountPath": "/data"
                        }],
                        "lifecycle": { "preStop": { "exec": { "command": [
                            "/usr/local/bin/python", "-c",
                            f"from fsspec import filesystem as fs; s3 = fs('s3');    \
                            s3.upload('/data/annotations.csv', '{USER_FILES_PATH}'); \
                            s3.upload('/data/gene_sets.csv', '{USER_FILES_PATH}')"
                        ]}}},
                        # "startupProbe": {
                        #     "exec": {
                        #         "command": [
                        #             # curl https://${KUBERNETES_SERVICE_HOST}/api/v1/namespaces/default/pods/${HOSTNAME}/log?sinceSeconds=<N_seconds> -k -H "Authorization: Bearer $(cat /var/run/secrets/kubernetes.io/serviceaccount/token)"
                        #             "wget", 
                        #             "https://${KUBERNETES_SERVICE_HOST}/api/v1/namespaces/default/pods/${HOSTNAME}/log",
                        #             # "-k",
                        #             # "-H",
                        #             "--header"
                        #             "Authorization: Bearer $(cat /var/run/secrets/kubernetes.io/serviceaccount/token)",
                        #             "|",
                        #             "grep",
                        #             "* Running on all addresses"
                        #         ]
                        #     },
                        #     "failureThreshold": 30,
                        #     "periodSeconds": 10
                        # }
                    }],
                    "volumes": [{
                        "name": "data",
                        "emptyDir": {}
                    }]
                }
            }
        }
    }
    service = {
        'apiVersion': 'v1',
        'kind': 'Service',
        'metadata': {
            'name': name,
            'labels': {
                'app': CXG_APP_NAME,
                'instance': name
            },
        },
        'spec': {
            'ports': [{
                'port': SERVICE_PORT,
                'protocol': 'TCP',
                'targetPort': CXG_PORT
            }],
            'selector': {'instance': name},
            'type': 'ClusterIP'
        }
    }
    ingress = {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "Ingress",
        "metadata": {
            "name": name,
            "labels": {
                "app": CXG_APP_NAME,
                "instance": name
            },
            "annotations": {
                "nginx.ingress.kubernetes.io/rewrite-target": "/$2",
                "nginx.ingress.kubernetes.io/configuration-snippet": f"rewrite ^/{name}$ /{name}/ redirect;\n",
                "nginx.ingress.kubernetes.io/auth-response-headers": "Authorization",
                "nginx.ingress.kubernetes.io/auth-url": f"http://{OAUTH2_APP_NAME}.{OAUTH2_NAMESPACE}.svc.cluster.local:{OAUTH2_PORT}/oauth2/auth",
                "nginx.ingress.kubernetes.io/auth-signin": f"https://{HOST_NAME}/oauth2/sign_in?rd=$escaped_request_uri",
                "nginx.ingress.kubernetes.io/proxy-buffer-size": PROXY_BUFFER_SIZE,
                "nginx.org/keepalive": "1"
                # "nginx.org/max-conns": "1"
            },
            "namespace": NAMESPACE
        },
        "spec": {
            "ingressClassName": "nginx",
            "rules": [{
                "host": HOST_NAME,
                "http": {
                    "paths": [{
                        "pathType": "ImplementationSpecific",
                        "path": f"/{name}(/|$)(.*)",
                        "backend": {
                            "service": {
                                "name": name,
                                "port": {"number": SERVICE_PORT}
                            }
                        }
                    }]
                }
            }]
        }
    }

    return deployment, service, ingress

# def get_unused_port(kah: K8ApiHandler):
#     port = None
#     used_ports = kah.list_services_ports(**{"label_selector":"app=cellxgene"})
#     while port in used_ports:
#         port = randrange(*PORT_RANGE)
#     return port

def deploy_oauth2proxy(kah: K8ApiHandler):
    """
    Deploy, expose and route an oauth2-proxy instance, if not present.
    """
    name = OAUTH2_APP_NAME
    kah.change_namespace(OAUTH2_NAMESPACE)
    try:
        kah.read_deployment(name=name)
        print("An oauth2-proxy instance was found in the cluster")
    except ApiException:
        print("No oauth2-proxy instance found in the cluster: creating it")

        deployment, service, ingress = oauth2proxy_manifests(name=name)
        
        kah.create_deployment(deployment)
        kah.create_service(service)
        kah.create_ingress(ingress)

        print("oauth2-proxy deployed.")
    kah.change_namespace(NAMESPACE)

def deploy_cellxgene(kah: K8ApiHandler):
    """
    Deploy, expose and route a cellxgene instance with a unique name and url.
    """
    name = CXG_APP_NAME + '-' + str(uuid.uuid4())
    # py_to_yaml(cellxgene_manifest(name)) # To print out
    kah.create_custom_resource(cellxgene_manifest(name))

    print("Done.")
    print(f"The instance is now accessible at: http://{HOST_NAME}/{name}/")

def main():
    kah = K8ApiHandler(
        host=f"https://{K8_IP}:{K8_PORT}",
        oidc_client=(SERVICE_ACCOUNT, ACCOUNT_TOKEN),
        cert=CLUSTER_ROOT_CERTIFICATE,
        namespace=NAMESPACE
    )
    deploy_oauth2proxy(kah)
    deploy_cellxgene(kah)
    # manifest = cellxgene_manifest("cellxgene")
    # suis = kah.list_custom_object(manifest, f"user=test2")
    # print(len(suis['items']))

if __name__ == '__main__':
    main()
