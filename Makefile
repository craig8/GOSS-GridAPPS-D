IMAGE := ${DOCKER_PROJECT}/gridappsd:dev

#test:
#	true

image:
	docker build -t $(IMAGE) .

push-image:
	docker push $(IMAGE)

.PHONY: image push-image 
# test
