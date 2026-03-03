.PHONY: test-docker test-docker-integration run-server-docker autoloop

test-docker:
	docker compose -f docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from server-tests

test-docker-integration:
	docker compose -f docker-compose.test.yml --profile integration up --build --abort-on-container-exit --exit-code-from sim-client

run-server-docker:
	docker compose -f docker-compose.runtime.yml up --build -d

autoloop:
	bash scripts/autonomous_coding_loop.sh
