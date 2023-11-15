include .env

build-docker-images:
	docker build . -f docker/Dockerfile_cellxgene -t cellxgene:xsmall
	docker build . -f docker/Dockerfile_aws-cli -t aws_cli:xsmall
	docker build . -f docker/Dockerfile_operator -t sui_operator:test

apply-sui-operator:
	kubectl apply -f manifests/deployment_sui_operator.yaml

delete-sui-operator:
	kubectl delete -f manifests/deployment_sui_operator.yaml

# when getting the docker images from a private registry
apply-docker-registry-secret:
	sed "s/\DOCKER_CONFIG_JSON/${DOCKER_CONFIG_JSON}/" manifests/templates/secret-docker-registry.yaml > manifests/secret-docker-registry.yaml
	kubectl apply -f manifests/secret-docker-registry.yaml

docker-registry-login:
	@echo "Logging into Docker registry $(REGISTRY_URL)"
	docker login $(REGISTRY_URL)

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


