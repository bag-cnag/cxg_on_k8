import time

from kubernetes import client

class K8ApiHandler():
    """Small util wrapper around kubernetes python client API.

    Attributes:
        host           Address of the kubernetes cluster.
        oidc_client    tuple: (serviceaccount name, access token)
        cert           Path to kubernetes cluster root certificate
        namespace      Active namespace
        debug          Enable/Disable console output
    """
    def __init__(self, host: str, oidc_client: (str, str), cert: str, namespace: str="default", debug: bool=True) -> None:
        self.serviceaccount, token = oidc_client
        self._config = client.Configuration()
        self.authenticate(host, token, cert)
        self._client = client.ApiClient(self._config)
        self.namespace = namespace

        # Flags
        self.debug = debug

        # APIs
        self._AppsV1Api = None
        self._CoreV1Api = None
        self._NetworkingV1Api = None
        self._CustomObjectsApi = None

    def authenticate(self, host: str, token: str, cert: str) -> None:
        """Set configuration with the credentials and certificate"""
        self._config.api_key["authorization"] = token
        self._config.api_key_prefix['authorization'] = 'Bearer'
        self._config.host = host
        self._config.ssl_ca_cert = cert

    def log(self, *args) -> None:
        """Conditional print"""
        if self.debug:
            print(*args)

    def change_namespace(self, namespace: str) -> None:
        """Change active namespace"""
        self.namespace = namespace

    # The client exposes several APIs: https://github.com/kubernetes-client/python/blob/a6d44ff625b5e8d8ad380a70245d40fa3d5472b2/kubernetes/README.md?plain=1
    # Each api has access to a subset of the ressources.
    @property
    def AppsV1Api(self) -> client.AppsV1Api:
        """AppsV1 kubernetes api"""
        if self._AppsV1Api == None:
            self._AppsV1Api = client.AppsV1Api(self._client)
        return self._AppsV1Api

    @property
    def CoreV1Api(self) -> client.CoreV1Api:
        """CoreV1 kubernetes api"""
        if self._CoreV1Api == None:
            self._CoreV1Api = client.CoreV1Api(self._client)
        return self._CoreV1Api

    @property
    def NetworkingV1Api(self) -> client.NetworkingV1Api:
        """NetworkingV1 kubernetes api"""
        if self._NetworkingV1Api == None:
            self._NetworkingV1Api = client.NetworkingV1Api(self._client)
        return self._NetworkingV1Api

    @property
    def CustomObjectsApi(self) -> client.CustomObjectsApi:
        """NetworkingV1 kubernetes api"""
        if self._CustomObjectsApi == None:
            self._CustomObjectsApi = client.CustomObjectsApi(self._client)
        return self._CustomObjectsApi

    def read_deployment(self, name, **kwargs) -> list:
        return self.AppsV1Api.read_namespaced_deployment(name=name, namespace=self.namespace, **kwargs)

    def list_pods(self) -> None:
        """List all pods."""
        self.log("Listing pods with their IPs:")
        ret = self.AppsV1Api.list_pod_for_all_namespaces(watch=False)
        for i in ret.items:
            print("%s\t%s\t%s" % (i.status.pod_ip, i.metadata.namespace, i.metadata.name))

    def list_deployments(self) -> list:
        """List all deployments."""
        # TODO: improve output
        # self.log("Listing deployments:")
        ret = self.AppsV1Api.list_deployment_for_all_namespaces(watch=False)
        return [i for i in ret.items]
        # for i in ret.items:
        #     print(i)

    def list_services_ports(self, **kwargs) -> list:
        """List all service ports in use, support selectors."""
        resp = self.CoreV1Api.list_service_for_all_namespaces(
            watch=False,
            **kwargs
        )
        ret = []
        for srv in resp.items:
            for port in srv.spec.ports:
                ret.append(port.port)
        return ret

    @staticmethod
    def get_name_in_manifest(manifest: dict) -> str:
        """Try to find and return metadata.name field from a manifest"""
        metadata = manifest.get("metadata", None)
        kind = manifest.get("kind", "ressource")
        if metadata:
            name = metadata.get("name", None)
            if name:
                return name
        raise Exception(f"field metadata.name required in {kind} manifest")

    def create_deployment(self, manifest: dict) -> None:
        """Create a deployment"""
        resp = None
        name = self.get_name_in_manifest(manifest)      
        specs = manifest.get("spec") 
        nreplicas = specs.get("replicas", 1)

        resp = self.AppsV1Api.create_namespaced_deployment(
            body=manifest, 
            namespace=self.namespace
        )

        # Waiting for the instance to be up
        while True:
            resp = self.AppsV1Api.read_namespaced_deployment(
                name=name, 
                namespace=self.namespace
            )
            if resp.status.available_replicas != nreplicas:
                break
            time.sleep(1)

        self.log(f"Deployment {name} up.")

    @staticmethod
    def get_custom_resource_params(manifest: dict) -> (str, str, str):
        group, version = manifest['apiVersion'].split('/')
        plural = str(manifest['kind']).lower() + 's'
        return group, version, plural

    def create_custom_resource(self, manifest: dict) -> None:
        """Create a custom resource."""
        name = self.get_name_in_manifest(manifest)
        group, version, plural = self.get_custom_resource_params(manifest)

        resp = self.CustomObjectsApi.create_namespaced_custom_object(
            body=manifest,
            group=group,
            version=version,
            plural=plural,
            namespace=self.namespace
        )
        self.log(f"Response: ", resp)
        self.log(f"Custom object {manifest['kind']} with name: {name} up.")

    def read_ingress(self, name) -> None:
        return self.NetworkingV1Api.read_namespaced_ingress(
            name=name,
            namespace=self.namespace
        )

    def list_custom_object(self, manifest: dict, label_selector) -> []:
        group, version, plural = self.get_custom_resource_params(manifest)
        return self.CustomObjectsApi.list_namespaced_custom_object(
            group=group,
            version=version,
            plural=plural,
            namespace=self.namespace,
            label_selector=label_selector
        )

    def delete_custom_object(self, manifest: dict, name: str):
        group, version, plural = self.get_custom_resource_params(manifest)
        return self.CustomObjectsApi.delete_namespaced_custom_object(
            group=group,
            version=version,
            plural=plural,
            namespace=self.namespace,
            name=name
        )

    def create_service(self, manifest: dict) -> None:
        """Create a service"""
        name = self.get_name_in_manifest(manifest)    
        resp = self.CoreV1Api.create_namespaced_service(
            body=manifest,
            namespace=self.namespace
        )
        time.sleep(1)
        self.log(f"Service {name} up.")
    
    def read_service_status(self, name) -> None:
        resp = self.CoreV1Api.read_namespaced_service_status(
            name=name,
            namespace=self.namespace
        )
        self.log(resp)

    def create_ingress(self, manifest: dict) -> None:
        """Create an ingress"""
        name = self.get_name_in_manifest(manifest)    
        resp = self.NetworkingV1Api.create_namespaced_ingress(
            body=manifest, 
            namespace=self.namespace
        )
        time.sleep(1)
        self.log(f"Ingress {name} setup.")

    @staticmethod
    def get_custom_resource_params(manifest: dict) -> (str, str, str):
        group, version = manifest['apiVersion'].split('/')
        plural = str(manifest['kind']).lower() + 's'
        return group, version, plural

    def list_custom_object(self, manifest: dict, label_selector) -> []:
        group, version, plural = self.get_custom_resource_params(manifest)
        return self.CustomObjectsApi.list_namespaced_custom_object(
            group=group,
            version=version,
            plural=plural,
            namespace=self.namespace,
            label_selector=label_selector
        )
