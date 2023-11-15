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
	sed "s/\REGISTRY_CREDS/${REGISTRY_CREDS}/" manifests/templates/secret-docker-registry.yaml > manifests/secret-docker-registry.yaml
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

list-docker-images:
	curl -L -X GET -H "Authorization: $(REGISTRY_CREDS)" $(REGISTRY_URL)/v2/_catalog
