#!/usr/bin/env bash

./gradlew export

docker_image=${DOCKER_PROJECT}/gridappsd:dev

docker login -u ${DOCKER_USERNAME} -p ${DOCKER_PASSWORD} ;

docker build -t ${docker_image} .

docker push ${docker_image}

