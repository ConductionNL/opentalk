.PHONY: build push test clean

APP_ID = opentalk
REGISTRY = ghcr.io
IMAGE = conductionnl/$(APP_ID)-exapp
VERSION ?= latest

build:
	docker build -t $(REGISTRY)/$(IMAGE):$(VERSION) .

push: build
	docker push $(REGISTRY)/$(IMAGE):$(VERSION)

test:
	docker run --rm -it \
		-e APP_ID=$(APP_ID) \
		-e APP_VERSION=0.1.0 \
		-e APP_SECRET=test \
		-e NEXTCLOUD_URL=http://localhost \
		-p 9000:9000 \
		$(REGISTRY)/$(IMAGE):$(VERSION)

clean:
	docker rmi $(REGISTRY)/$(IMAGE):$(VERSION) || true
