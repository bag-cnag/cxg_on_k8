include .env
ns = cellxgene

.PHONY: venv
venv:
	python3 -m venv venv
	. venv/bin/activate && pip install --upgrade pip && \
	pip install -r requirements.txt

run:
	. venv/bin/activate && python3 deploy_cellxgene.py

build-docker-images:
	docker build . -f docker/Dockerfile_cellxgene -t cellxgene:xsmall
	docker build . -f docker/Dockerfile_aws-cli -t aws_cli:xsmall
	docker build . -f docker/Dockerfile_operator -t sui_operator:test

apply-aws-secrets:
	@echo "Populate	the AWS secrets in the secret_aws-cred.yaml file"
	sed -e "s/\S3_ENDPOINT_URL/$$(echo -n ${AWS_ENDPOINT_URL} | base64 )/" \
	   	-e "s/\S3_ACCESS_KEY_ID/$$(echo -n ${AWS_ACCESS_KEY_ID} | base64 ) /" \
	   	-e "s/\S3_SECRET_ACCESS_KEY/$$(echo -n ${AWS_SECRET_ACCESS_KEY} | base64 ) /" \
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

deploy-ing-nginx-controller:
	/usr/local/bin/helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
	/usr/local/bin/helm repo update
	/usr/local/bin/helm install ingress-nginx ingress-nginx/ingress-nginx --set controller.service.type=NodePort --set controller.allowSnippetAnnotations=true -n ingress-nginx

logs-ing-nginx-controller:
	pod=$$(kubectl get pods -n ingress-nginx -l app.kubernetes.io/component=controller -o jsonpath='{.items[0].metadata.name}') && \
	kubectl logs -f $$pod -n ingress-nginx

endpoints-ing-nginx-controller:
	ingress_pod_name=$$(kubectl get pods -n ingress-nginx -l app.kubernetes.io/name=ingress-nginx --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}') && \
	node_name=$$(kubectl get pod $$ingress_pod_name -n ingress-nginx -o jsonpath='{.spec.nodeName}') && \
	node_port_http=$$(kubectl get svc ingress-nginx-controller -n ingress-nginx -o jsonpath='{.spec.ports[0].nodePort}') && \
	node_port_https=$$(kubectl get svc ingress-nginx-controller -n ingress-nginx -o jsonpath='{.spec.ports[1].nodePort}') && \
	echo "" && \
	echo "Ingress Nginx Controller endpoints" && \
	echo "http://$$node_name:$$node_port_http" && \
	echo "https://$$node_name:$$node_port_https"

del-ing-nginx-controller:
	/usr/local/bin/helm uninstall ingress-nginx -n ingress-nginx

# below should return connection refused and not timeout if timeout check the status of firewalld on the worker nodes
# port 10254 should be open
wget-ing-metrics-sever-from-sui-operator:
	pod=$$(kubectl get pods -n ${ns} -l application=sui-operator -o jsonpath='{.items[0].metadata.name}') && \
	kubectl exec -it $$pod -n ${ns} -- wget metrics.ingress-nginx.svc.cluster.local/metrics

running-suis:
	kubectl get sui -n ${ns}

ings:
	kubectl get ing -n ${ns}

del-suis:
	kubectl delete sui -n ${ns} --all

curl-cxg:
	instance=$$(kubectl get sui -n ${ns} -o jsonpath='{.items[0].metadata.labels.instance}') && \
	echo $$instance && \
	echo "curl -L http://${HOST_NAME}:${ING_CONTROLER_NODE_PORT}/$$instance/" && \
	curl -L http://${HOST_NAME}:${ING_CONTROLER_NODE_PORT}/$$instance/ --verbose

mkcert:
	/usr/local/bin/mkcert -cert-file ./certs/cxgk8.cnag.dev.pem -key-file ./certs/cxgk8.cnag.dev-key.pem cxgk8.cnag.dev

# when getting the docker images from a private registry
#copy the output of the following command to the DOCKER_CONFIG_JSON variable in the .env file
encode-docker-config-json:
	@echo "Creating docker config json"
	base64 -w 0 ~/.docker/config.json 

apply-docker-registry-secret:
	sed "s/\DOCKER_CONFIG_JSON/${DOCKER_CONFIG_JSON}/" manifests/templates/secret-docker-registry.yaml > manifests/secret-docker-registry.yaml
	kubectl apply -f manifests/secret-docker-registry.yaml

docker-registry-login:
	@echo "Logging into Docker registry $(REGISTRY_URL)"
	docker login https://$(REGISTRY_URL)/v2/

tag-docker-images:
	docker tag cellxgene:xsmall $(REGISTRY_URL)/cellxgene:xsmall
	docker tag aws_cli:xsmall $(REGISTRY_URL)/aws_cli:xsmall
	docker tag sui_operator:test $(REGISTRY_URL)/sui_operator:test

push-docker-images:
	docker push $(REGISTRY_URL)/cellxgene:xsmall
	docker push $(REGISTRY_URL)/aws_cli:xsmall
	docker push $(REGISTRY_URL)/sui_operator:test

pull-docker-images:
	docker pull $(REGISTRY_URL)/cellxgene:xsmall
	docker pull $(REGISTRY_URL)/aws_cli:xsmall
	docker pull $(REGISTRY_URL)/sui_operator:test

list-docker-images:
	curl -L -u $(REGISTRY_USER):$(REGISTRY_PW) -X GET https://$(REGISTRY_URL)/v2/_catalog 

list-docker-image-tags:
	curl -L -u $(REGISTRY_USER):$(REGISTRY_PW) -X GET https://$(REGISTRY_URL)/v2/cellxgene/tags/list
	curl -L -u $(REGISTRY_USER):$(REGISTRY_PW) -X GET https://$(REGISTRY_URL)/v2/aws_cli/tags/list
	curl -L -u $(REGISTRY_USER):$(REGISTRY_PW) -X GET https://$(REGISTRY_URL)/v2/sui_operator/tags/list


