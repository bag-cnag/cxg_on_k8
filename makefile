include .env
ns = cellxgene

build-docker-images:
	docker build . -f docker/Dockerfile_cellxgene -t cellxgene:xsmall
	docker build . -f docker/Dockerfile_aws-cli -t aws_cli:xsmall
	docker build . -f docker/Dockerfile_operator -t sui_operator:test

deploy-sui-operator:
	kubectl apply -f manifests/deployment_sui_operator.yaml

nslookup-sui-operator:
	pod=$$(kubectl get pods -n ${ns} -l application=sui-operator -o jsonpath='{.items[0].metadata.name}') && \
	kubectl exec -it $$pod -n ${ns} -- nslookup metrics.ingress-nginx.svc.cluster.local

del-sui-operator:
	kubectl delete -f manifests/deployment_sui_operator.yaml


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


