#!/usr/bin/python3
####################################################
# Script that demonstrates use of the api handler to create an instance of cxg
# In this case a cellxgene instance is made of a joined:
#     - deployment
#     - service
#     - ingress
##########################

import os
from dotenv import load_dotenv

import uuid
from kubernetes.client.exceptions import ApiException

from k8_api_handler import K8ApiHandler
from yaml_to_py import py_to_yaml

## !! See README.md for info on how to set those variables
#* set the variables in the .env file

# Load environment variables from .env file
load_dotenv()

# Host
K8_IP = os.getenv("K8_IP")
K8_PORT = os.getenv("K8_PORT")
HOST_NAME = os.getenv("HOST_NAME")

# Kubernetes Authentication
CLUSTER_ROOT_CERTIFICATE = os.getenv("CLUSTER_ROOT_CERTIFICATE")
SERVICE_ACCOUNT = os.getenv("SERVICE_ACCOUNT")
ACCOUNT_TOKEN = os.getenv("ACCOUNT_TOKEN")

# Oauth2 config
KEYCLOAK_ENDPOINT = os.getenv("KEYCLOAK_ENDPOINT")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM")

# # Host
# K8_IP = "192.168.49.2"
# K8_PORT = "8443"
# HOST_NAME = "minikube.local"

# # Kubernetes Authentication
# CLUSTER_ROOT_CERTIFICATE = "/home/ejodry/.minikube/ca.crt"
# SERVICE_ACCOUNT = 'omicsdm'
# ACCOUNT_TOKEN = ''

# # # Oauth2 config
# KEYCLOAK_ENDPOINT = 'https://sso.cnag.crg.dev/auth'
# KEYCLOAK_REALM = '3TR'

OAUTH2_IMAGE = 'quay.io/oauth2-proxy/oauth2-proxy:v7.5.1'
OAUTH2_APP_NAME = 'oauth2-proxy'

OAUTH2_CLIENT_ID = 'cellxgene'
OAUTH2_CLIENT_SECRET = ''
OAUTH2_NAMESPACE = 'ingress-nginx'

OAUTH2_PORT = 8091
PROXY_BUFFER_SIZE = '64k'

# Cellxgene config
CXG_APP_NAME = 'cellxgene'
CXG_IMAGE = 'docker.vm2.dev/cellxgene:xsmall'
AWS_CLI_IMAGE = 'docker.vm2.dev/aws_cli:xsmall'
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
                    "initContainers": [{
                        "name": "init-cellxgene",
                        "image": AWS_CLI_IMAGE,
                        "command": [
                            "/bin/sh", "-c",
                            f"aws s3 sync {USER_FILES_PATH} /data/"
                        ],
                        "envFrom": [{"secretRef": {"name": "aws-cred-secret"}}],
                        "volumeMounts": [{
                            "name": "data",
                            "mountPath": "/data"
                        }],
                        "imagePullSecrets": [{"name": "docker-registry-secret"}]
                    }],
                    "containers": [{
                        "name": name,
                        "image": CXG_IMAGE,
                        "ports": [{"containerPort": CXG_PORT}],
                        "securityContext": {"runAsUser": 1000},
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
                        "imagePullSecrets": [{"name": "docker-registry-secret"}]
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
    # py_to_yaml(cellxgene_manifest(name))
    kah.create_custom_resource(cellxgene_manifest(name))

    print("Done.")
    print(f"The instance is now accessible at: http://{HOST_NAME}/{name}/")

def main():
    kah = K8ApiHandler(
        host=f"https://{K8_IP}:{K8_PORT}",
        oidc_client=(SERVICE_ACCOUNT, ACCOUNT_TOKEN),
        cert=CLUSTER_ROOT_CERTIFICATE
    )
    deploy_oauth2proxy(kah)
    deploy_cellxgene(kah)

if __name__ == '__main__':
    main()
