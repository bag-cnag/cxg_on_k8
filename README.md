# cxg\_on\_k8

Proof of concept about deploying cellxgene instances on a kubernetes cluster;

->[Technical presentation](https://www.overleaf.com/read/qjpwpfwvkdvw#87e263)

- *Development dependencies:*
The backend is the [kubernetes python client api](https://github.com/kubernetes-client/python/) + kopf (see below)
```bash
python3 -m pip install kubernetes kopf[uvloop]
```

- *Namespace:* Instances are deployed in a dedicated `cellxgene` namespace.
```bash
kubectl apply -f manifests/namespace_cellxgene.yaml
```

- *Tests:* Conversely for unit tests instances:
```bash
kubectl apply -f manifests/namespace_testing.yaml
```

## Docker images

Kubernetes runs containerized applications. 

For the demo, size optimized alpine images are used. To build them:

- *cellxgene alpine* - warning: takes **1000+ seconds** 
```bash
docker build . -f docker/Dockerfile_cellxgene_alpine -t cellxgene:1.1.2-python3.11-alpine3.19
```

**OR alternatively**

- *cellxgene slim* 
```bash
docker build . -f docker/Dockerfile_cellxgene_slim -t cellxgene:1.1.2-python3.11-slim-bookworm
```

__Note:__ You may set the `PYTHON__V` and `ALPINE__V` variables in the corresponding dockerfiles to build for different versions.

- *cellxgene VIP* - warning: 3x heavier than cellxgene - Supports only python3.8
```bash
docker build . -f docker/Dockerfile_cellxgene_VIP_slim -t cellxgene:1.1.2-VIP-python3.8-slim-bookworm
```

- *aws-cli*
```bash
docker build . -f docker/Dockerfile_aws-cli -t aws_cli:xsmall
```

- *sui-operator*
```bash
docker build . -f docker/Dockerfile_operator -t sui_operator:v1
```

## Authentication

### Kubernetes
To be able to query the kubernetes api, a serviceaccount needs to exist with the proper [RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/) permissions.

In our example, the file `manifests/serviceaccount_omicsdm.yaml` contains the definition of this service account.

__Note__: At the moment, for development purposes, permissions have been set loosely. For production we will need to restrict the rights of the user according to minimum permissions principle.

```bash
kubectl apply -f manifests/serviceaccount_omicsdm.yaml
```

Now to retrieve the token you may use the following
```bash
kubectl describe secrets omicsdm-token
```

Related script variables `SERVICE_ACCOUNT` and `ACCOUNT_TOKEN`

### OpenID-Connect client
For the connection between our OIDC provider (I.e. keycloak) and oauth2-proxy, we configure a client like this:

1. Client -> Create -> enter ClientID
2. Set Client protocol `openid-connect` -> save
3. Set Access Type `confidential` -> save
4. `http://*` and `https://*` in Valid Redirect URIs
5. Mappers -> Create -> Audience -> name `audience` -> select Client in Included Client Audience
6. (for groups: optional) Mappers -> Create -> `Group Membership` -> Group Membership -> name `groups` -> Token Claim Name `groups` -> Turn off full group path
7. Credentials -> Secret lets you set `OAUTH2_CLIENT_ID` and `OAUTH2_CLIENT_SECRET` variables in deployment script.
8. Populate with users (for groups: create group and add your users to it group)  


**Useful tutorial:** [here](https://freedium.cfd/https://carlosedp.medium.com/adding-authentication-to-your-kubernetes-front-end-applications-with-keycloak-6571097be090)

### AWS
For containers to access **s3 bucket** you need to populate the variables within `manifests/secret_aws-cred.yaml` (Note: values must be encoded in base64). Then add it to the cluster. Secrets are defined per namespace, so the entries of this file are duplicated for `cellxgene` and `testing` namespaces. 

```bash
kubectl apply -f manifests/secret_aws-cred.yaml
```


##  Operator and SingleUserInstances

This proof of concept is leveraging a custom Kubernetes [Operator](https://kubernetes.io/docs/concepts/extend-kubernetes/operator/) developped with [kopf](kopf.readthedocs.io/). Combined with a [custom resource](https://kubernetes.io/docs/tasks/extend-kubernetes/custom-resources/custom-resource-definitions/) it allows us to joinly create the Deployment, Service and Ingress that constitute an instance. Moreover, it handles the lifecycle through the `lifespan` field and flushes the instance after some time the user quits cellxgene - i.e. closes the tab/browser.

User termination of the instance is detected by querying the `ingress-nginx-controller`'s metrics server, thus we need a service that exposes the metrics server cluster-wide. In particular `nginx_ingress_controller_ingress_upstream_latency_seconds` monitors **per instance** the latency of the connection with the browser.

This operator needs to run inside the cluster and is essentially a Deployment. We make it monitor the events on the namespace and it also needs a service account with proper proper [RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/) permissions.

To deploy:
```bash
kubectl apply -f manifests/crd_single-user-instance.yaml
kubectl apply -f manifests/serviceaccount_sui-operator.yaml
kubectl apply -f manifests/service_ingress-nginx-controller_metrics.yaml
kubectl apply -f manifests/deployment_sui_operator.yaml
```

You may then check that the operator successfuly launched by querying the status. E.g.
```bash
kubectl -n cellxgene get pods

NAME                            READY   STATUS    RESTARTS      AGE
sui-operator-57666b6944-q4lqt   1/1     Running   2 (40m ago)   10d
```

Then the logs should look like this:

```bash
kubectl -n cellxgene logs pod/sui-operator-57666b6944-q4lqt

[2023-11-06 13:32:22,644] kopf._core.reactor.r [DEBUG   ] Starting Kopf 1.36.2.
[2023-11-06 13:32:22,644] kopf._core.engines.a [INFO    ] Initial authentication has been initiated.
[2023-11-06 13:32:22,644] kopf.activities.auth [DEBUG   ] Activity 'login_via_client' is invoked.
[2023-11-06 13:32:22,661] kopf.activities.auth [DEBUG   ] Client is configured in cluster with service account.
[2023-11-06 13:32:22,661] kopf.activities.auth [INFO    ] Activity 'login_via_client' succeeded.
[2023-11-06 13:32:22,662] kopf._core.engines.a [INFO    ] Initial authentication has finished.
[2023-11-06 13:32:22,710] kopf._cogs.clients.w [DEBUG   ] Starting the watch-stream for customresourcedefinitions.v1.apiextensions.k8s.io cluster-wide.
[2023-11-06 13:32:22,713] kopf._cogs.clients.w [DEBUG   ] Starting the watch-stream for namespaces.v1 cluster-wide.
[2023-11-06 13:32:22,715] kopf._cogs.clients.w [DEBUG   ] Starting the watch-stream for singleuserinstances.v1.cnag.eu in 'cellxgene'.
```

Once the operator is running you may submit manifests of kind `SingleUserInstance` with apiVersion `cnag.eu/v1`. If the operator is not running you might run into problems to create and especially delete resources of that type.

### Dev: run operator outside the cluster

You can also run the operator outside the cluster.

In that case you will also need to expose the metrics server in a different terminal.
```bash
kubectl -n ingress-nginx port-forward svc/metrics 10254:80
```

Then
```bash
kopf run -n {namespace} operator/operator_single-user-instances.py --debug
```

__Note:__ If an operator is running within the cluster already, then it will have priority over the operator your are running through the command line.

### Testing

**Dependencies:**
```bash
python3 -m pip install pytest pytest-cov
```

Assuming you have deployed `testing` namespace and populated it with the AWS credentials you are now able to run the Operator unit tests.
```bash
pytest -k 'test_operator'
```

Furthermore, If you want the code coverage:
```bash
pytest --cov-report [html | term] --cov=. tests/
```


## API Handler

The api handler is a layer over the kubernetes python client API to abstract some of the complexity.

E.g. the functions to create deployments, services and ingresses are respectively part of the  `AppsV1Api`, `CoreV1Api`, `NetworkingV1Api` objects

One can instanciate it like this

```python
kah = K8ApiHandler(
    host=f"https://{K8_IP}:{K8_PORT}",
    oidc_client=(SERVICE_ACCOUNT, TOKEN),
    cert=CLUSTER_ROOT_CERTIFICATE
)
```

The command `kubectl cluster-info` gives `K8_IP` and `K8_PORT`, and `HOST_NAME` can be set freely.

On a minikube install the `CLUSTER_ROOT_CERTIFICATE` is located at `~/.minikube/ca.crt` and see [authentication](#Authentication) section for the oidc client.

One may use the methods such as: 

```python
kah.create_deployment(manifest)
```

Or

```python
kah.list_pods()
```

## Scripts

### yaml\_to\_py

This small script is a helper to turn the yaml kubernetes manifests into python dicts to query the api.

**E.g.**
```bash
python3 yaml_to_py.py manifests/templates/service_cxg.yaml
```

It also includes a `py_to_yaml` function that does the inverse transformation. You may import and use it like this:
```python
from yaml_to_py import py_to_yaml

d = {'a': 1, 'b': {'c': [2, 3, 4]}}
py_to_yaml(d)
```

### Demo: deploy\_cellxgene

This script uses the api handler described above to create a `cellxgene` instance composed of a joined deployment, service and ingress that will expose the container and give an url to access it from your browser.

This also includes an `oauth2-proxy` instance that will be fired if not present on the cluster to handle authentication with keycloak.

```bash
python3 deploy_cellxgene.py
```

Output should be similar as:

```
[ No oauth2-proxy instance found in the cluster: creating it
Deployment oauth2-proxy up.
Service oauth2-proxy up.
Ingress oauth2-proxy setup.
oauth2-proxy deployed.
| An oauth2-proxy instance was found in the cluster ]

Custom object: SingleUserInstance with name: cellxgene-90afa5bf-823b-40df-a5b6-51c36827033b up.
Done.
The instance is now accessible at: http://minikube.local/cellxgene-90afa5bf-823b-40df-a5b6-51c36827033b/
```

#### Clean after demo

All ressources are tagged using the `metadata.labels.app = cellxgene` label. Then we then can peform some operations on all objects at once such as

```bash
kubectl delete all,ing,sui -l app=cellxgene
```

Ressources tied to an instance are also tagged using the `metadata.labels.instance = cellxgene-90afa5bf-823b-40df-a5b6-51c36827033b` label.

You may similarly delete like this

```bash
kubectl delete all,ing,sui -l instance=cellxgene-90afa5bf-823b-40df-a5b6-51c36827033b
```

### Debugging

You can adjoin an image to a running pod
```
kubectl debug -it <pod> --image=python:debug --target <pod> -- sh
```

## Minikube

This section provides some minikube specific details.

### Docker images

minikube runs its own docker. In consequence it cannot see local images.

The easiest solution is to use the following command to make your local images accessibles inside the cluster

```
minikube image load <local-image>:<tag>
```

then you may check if the image is present like this
```
minikube image ls --format table
