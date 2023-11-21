include .env
ns = cellxgene

.PHONY: venv
venv:
	/usr/local/bin/python3.11 -m venv venv
	. venv/bin/activate && pip3 install --upgrade pip && \
	pip install -r requirements.txt

run:
	. venv/bin/activate && python3 deploy_cellxgene.py

test:
	kubectl get ns testing 2>/dev/null || kubectl create ns testing
	# . venv/bin/activate && pytest tests -k 'test_create_and_delete' --cov && \
	. venv/bin/activate && pytest tests -k 'test_create_and_wait_deletion' --cov

build-docker-images:
	docker build . -f docker/Dockerfile_cellxgene -t ${REGISTRY_URL}/cellxgene:xsmall
	docker build . -f docker/Dockerfile_aws-cli -t ${REGISTRY_URL}/aws_cli:xsmall
	docker build . -f docker/Dockerfile_operator -t ${REGISTRY_URL}/sui_operator:v1

apply-manifests:
	kubectl get ns cellxgene 2>/dev/null || kubectl create ns cellxgene
	kubectl apply -f manifests/crd_single-user-instance.yaml
	kubectl apply -f manifests/serviceaccount_sui-operator.yaml
	kubectl apply -f manifests/service_ingress-nginx-controller_metrics.yaml
	kubectl apply -f manifests/deployment_sui_operator.yaml
	kubectl apply -f manifests/serviceaccount_omicsdm.yaml

apply-aws-secrets:
	@echo "Populate	the AWS secrets in the secret_aws-cred.yaml file"
	sed -e "s/\S3_ENDPOINT_URL/$$(echo -n ${AWS_ENDPOINT_URL} | base64 -w0 )/" \
	   	-e "s/\S3_ACCESS_KEY_ID/$$(echo -n ${AWS_ACCESS_KEY_ID} | base64 -w0 ) /" \
	   	-e "s/\S3_SECRET_ACCESS_KEY/$$(echo -n ${AWS_SECRET_ACCESS_KEY} | base64 -w0 ) /" \
		manifests/templates/secret_aws-cred.yaml > manifests/secret_aws-cred.yaml
	kubectl apply -f manifests/secret_aws-cred.yaml

del-aws-secrets:
	kubectl delete -f manifests/secret_aws-cred.yaml

deploy-sui-operator:
	kubectl apply -f manifests/deployment_sui_operator.yaml

logs-sui-operator:
	pod=$$(kubectl get pods -n ${ns} -l application=sui-operator -o jsonpath='{.items[0].metadata.name}') && \
	kubectl logs -f $$pod -n ${ns}

attach-sui-operator:
	pod=$$(kubectl get pods -n ${ns} -l application=sui-operator -o jsonpath='{.items[0].metadata.name}') && \
	kubectl exec -it $$pod -n ${ns} -- bin/sh

nslookup-sui-operator:
	pod=$$(kubectl get pods -n ${ns} -l application=sui-operator -o jsonpath='{.items[0].metadata.name}') && \
	kubectl exec -it $$pod -n ${ns} -- nslookup kubernetes.default.svc.cluster.local

deploy-ing-nginx-controller:
	kubectl get ns ingress-nginx 2>/dev/null || kubectl create ns ingress-nginx
	/usr/local/bin/helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
	/usr/local/bin/helm repo update
	/usr/local/bin/helm install ingress-nginx ingress-nginx/ingress-nginx --set controller.service.type=NodePort --set controller.allowSnippetAnnotations=true -n ingress-nginx

logs-ing-nginx-controller:
	pod=$$(kubectl get pods -n ingress-nginx -l app.kubernetes.io/component=controller -o jsonpath='{.items[0].metadata.name}') && \
	kubectl logs -f $$pod -n ingress-nginx

endpoints-ing-nginx-controller:
	ingress_pod_name=$$(kubectl get pods -n ingress-nginx -l app.kubernetes.io/name=ingress-nginx --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}') && \
	node_name=$$(kubectl get pod $$ingress_pod_name -n ingress-nginx -o jsonpath='{.spec.nodeName}') && \
	node_internal_ip=$$(kubectl get node $$node_name -o jsonpath='{.status.addresses[0].address}') && \
	node_port_http=$$(kubectl get svc ingress-nginx-controller -n ingress-nginx -o jsonpath='{.spec.ports[0].nodePort}') && \
	node_port_https=$$(kubectl get svc ingress-nginx-controller -n ingress-nginx -o jsonpath='{.spec.ports[1].nodePort}') && \
	echo "" && \
	echo "Ingress Nginx Controller endpoints" && \
	echo "node_name: $$node_name" && \
	echo "http://$$node_internal_ip:$$node_port_http" && \
	echo "https://$$node_internal_ip:$$node_port_https"

update-env-file:
	@echo "Update the .env file with the ingress controller node port"
	node_port=$$(kubectl get svc ingress-nginx-controller -n ingress-nginx -o jsonpath='{.spec.ports[0].nodePort}') && \
	echo "ING_CONTROLLER_NODE_PORT=$$node_port" && \
	sed -i -e "s/ING_CONTROLLER_NODE_PORT=.*/ING_CONTROLLER_NODE_PORT=$$node_port/" .env

	@echo "Update the .env file with the omicsdm service account token"
	token=$$(kubectl get secret omicsdm-token -o jsonpath='{.data.token}' | base64 --decode) && \
	echo "token: $$token" && \
	sed -i -e "s/ACCOUNT_TOKEN=.*/ACCOUNT_TOKEN=$$token/" .env

del-ing-nginx-controller:
	/usr/local/bin/helm uninstall ingress-nginx -n ingress-nginx

# below should return connection refused and not timeout if timeout check the status of firewalld on the worker nodes
# port 10254 should be open
wget-ing-metrics-sever-from-sui-operator:
	pod=$$(kubectl get pods -n ${ns} -l application=sui-operator -o jsonpath='{.items[0].metadata.name}') && \
	kubectl exec -it $$pod -n ${ns} -- wget metrics.ingress-nginx.svc.cluster.local/metrics

get-suis:
	kubectl get sui -n ${ns}
	kubectl get sui -n testing

ings:
	kubectl get ing -n ${ns}

del-suis:
	kubectl delete sui -n ${ns} --all
	kubectl delete sui -n testing --all

force-del-sui:
	sui=$$(kubectl get sui -n ${ns} -o jsonpath='{.items[0].metadata.name}') && \
	echo $$sui && \
	kubectl patch -n cellxgene sui $$sui -p '{"metadata":{"finalizers":[]}}' --type=merge
	kubectl delete sui -n ${ns} --all

	testing_sui=$$(kubectl get sui -n testing -o jsonpath='{.items[0].metadata.name}') && \
	echo $$testing_sui && \
	kubectl patch -n testing sui $$testing_sui -p '{"metadata":{"finalizers":[]}}' --type=merge
	kubectl delete sui -n testing --all

del-oauth2-proxy:
	kubectl delete deployment/oauth2-proxy -n ingress-nginx; \
	kubectl delete svc/oauth2-proxy -n ingress-nginx; \
	kubectl delete ing/oauth2-proxy -n ingress-nginx

try-oauth2-proxy:
	pod=$$(kubectl get pods -n ingress-nginx -l app.kubernetes.io/component=controller -o jsonpath='{.items[0].metadata.name}') && \
	kubectl exec -it $$pod -n ingress-nginx -- wget http://${OAUTH2_APP_NAME}.${OAUTH2_NAMESPACE}.svc.cluster.local:${OAUTH2_PORT}/oauth2/auth

logs-oauth2-proxy:
	pod=$$(kubectl get pods -n ingress-nginx -l app=oauth2-proxy -o jsonpath='{.items[0].metadata.name}') && \
	kubectl logs -f $$pod -n ingress-nginx

curl-cxg:
	instance=$$(kubectl get sui -n ${ns} -o jsonpath='{.items[0].metadata.labels.instance}') && \
	echo $$instance && \
	echo "curl -L http://${HOST_NAME}:${ING_CONTROLLER_NODE_PORT}/$$instance/" && \
	curl -kL http://${HOST_NAME}:${ING_CONTROLLER_NODE_PORT}/$$instance/ --verbose

# when getting the docker images from a private registry
#copy the output of the following command to the DOCKER_CONFIG_JSON variable in the .env file

apply-docker-registry-secret:
	b64_cfg=$$(cat ~/.docker/config.json | base64 -w 0) && \
	echo $$b64_cfg && \
	sed "s/\DOCKER_CONFIG_JSON/$$b64_cfg/" manifests/templates/secret-docker-registry.yaml > manifests/secret-docker-registry.yaml
	kubectl apply -f manifests/secret-docker-registry.yaml

docker-registry-login:
	@echo "Logging into Docker registry $(REGISTRY_URL)"
	docker login https://$(REGISTRY_URL)/v2/

push-docker-images:
	docker push $(REGISTRY_URL)/cellxgene:xsmall
	docker push $(REGISTRY_URL)/aws_cli:xsmall
	docker push $(REGISTRY_URL)/sui_operator:
	
pull-docker-images:
	docker pull $(REGISTRY_URL)/cellxgene:xsmall
	docker pull $(REGISTRY_URL)/aws_cli:xsmall
	docker pull $(REGISTRY_URL)/sui_operator:v1

list-docker-images:
	curl -L -u $(REGISTRY_USER):$(REGISTRY_PW) -X GET https://$(REGISTRY_URL)/v2/_catalog 

list-docker-image-tags:
	curl -L -u $(REGISTRY_USER):$(REGISTRY_PW) -X GET https://$(REGISTRY_URL)/v2/cellxgene/tags/list
	curl -L -u $(REGISTRY_USER):$(REGISTRY_PW) -X GET https://$(REGISTRY_URL)/v2/aws_cli/tags/list
	curl -L -u $(REGISTRY_USER):$(REGISTRY_PW) -X GET https://$(REGISTRY_URL)/v2/sui_operator/tags/list


