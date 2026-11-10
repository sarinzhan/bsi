#!/usr/bin/env bash
# On your laptop: build the three BSI images for the server (linux/amd64) and push them to Docker Hub.
#
#   docker login                                        # once
#   deploy/single-vm/push-images.sh <dockerhub-user> <tag>
#   deploy/single-vm/push-images.sh sarinzhan v0.1.0
#
# Creates <user>/platform-api, <user>/web, <user>/agent-runner. Make these repositories PRIVATE on
# hub.docker.com: the images contain config/servers.yaml (internal IPs), config/users.yaml and the prompts.
# Then on the server set BSI_IMAGES=docker.io/<user> and BSI_TAG=<tag> in .env (see README.md).
set -euo pipefail
cd "$(dirname "$0")/../.."

user=${1:?usage: push-images.sh <dockerhub-user> <tag>}
tag=${2:?usage: push-images.sh <dockerhub-user> <tag>}

if [ -n "$(git status --porcelain)" ]; then
  echo "warning: uncommitted changes go into the images too; commit first so the tag matches the code" >&2
fi

export BSI_IMAGES="docker.io/$user" BSI_TAG="$tag"
export DOCKER_DEFAULT_PLATFORM=linux/amd64   # the server's CPU; a Mac with Apple silicon builds arm64 otherwise

services=(platform-api web agent-runner)
docker compose -f docker-compose.yml --profile build build "${services[@]}"
docker compose -f docker-compose.yml --profile build push "${services[@]}"

echo
echo "pushed $BSI_IMAGES/{platform-api,web,agent-runner}:$tag"
echo "server .env:  BSI_IMAGES=$BSI_IMAGES   BSI_TAG=$tag"
