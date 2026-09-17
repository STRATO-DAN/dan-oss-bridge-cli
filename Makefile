# dan-oss-bridge — developer tasks. Stdlib only, zero runtime dependencies.
# Every target uses python3 and the standard-library unittest runner.

PY := python3

# Adversarial suites: the tamper-detection tests (chain), the forged/tampered/
# unsigned/unregistered identity tests, and the corrupt-line tolerance tests.
ATTACK_TESTS := \
	test_chain.VerifyDetectsTamperingTests \
	test_identity.SignedPostVerifyTests \
	test_bus_hardening.CorruptFileToleranceTests

.DEFAULT_GOAL := help
.PHONY: help test attack demo bench

help: ## Show this help
	@echo "dan-oss-bridge — make targets:"
	@echo "  make test    Run the full test suite (python3 -m unittest discover)"
	@echo "  make attack  Run ONLY the adversarial tamper/forgery/corruption tests"
	@echo "  make demo    Reproducible tamper-evidence demo (post, verify, tamper, verify)"
	@echo "  make bench   Measure tail-bounded read latency at 1k / 10k / 100k messages"
	@echo "  make help    Show this help"

test: ## Run the full test suite
	@$(PY) -m unittest discover -s tests

attack: ## Run only the adversarial tests (must be green)
	@echo "======================================================================"
	@echo " ATTACK SUITE — adversarial tests: tamper detection, forgery/identity,"
	@echo " and corrupt-line tolerance. All must pass (the library defends itself)."
	@echo "======================================================================"
	@cd tests && $(PY) -m unittest $(ATTACK_TESTS)

demo: ## Reproducible tamper-evidence demo
	@tmp="$$(mktemp -d)"; \
	trap 'rm -rf "$$tmp"' EXIT; \
	export DAN_OSS_BRIDGE_BUS="$$tmp/bus.jsonl"; \
	export DAN_OSS_BRIDGE_KEYRING="$$tmp/agents.json"; \
	export DAN_OSS_BRIDGE_CHAIN=1; \
	echo "=== dan-oss-bridge demo: hash-chained, tamper-evident log ==="; \
	echo "--- register an agent ---"; \
	$(PY) -m dan_oss_bridge.cli register alice; \
	echo "--- post two chained messages ---"; \
	$(PY) -m dan_oss_bridge.cli post standup alice "first real message"; \
	$(PY) -m dan_oss_bridge.cli post standup alice "second real message"; \
	echo "--- verify (expect: clean, exit 0) ---"; \
	set +e; $(PY) -m dan_oss_bridge.cli verify; clean_rc=$$?; set -e; \
	echo "verify exit code: $$clean_rc"; \
	echo "--- tamper: edit the first message in the bus file on disk ---"; \
	$(PY) -c 'import sys; p=sys.argv[1]; L=open(p,encoding="utf-8").read().splitlines(); L[0]=L[0].replace("first real message","EDITED IN PLACE"); open(p,"w",encoding="utf-8").write("\n".join(L)+"\n"); print("edited line 1 in",p)' "$$DAN_OSS_BRIDGE_BUS"; \
	echo "--- verify (expect: tampering detected, exit 1) ---"; \
	set +e; $(PY) -m dan_oss_bridge.cli verify; tamper_rc=$$?; set -e; \
	echo "verify exit code: $$tamper_rc"; \
	if [ "$$clean_rc" -eq 0 ] && [ "$$tamper_rc" -eq 1 ]; then \
	  echo "DEMO OK: clean log verified (0), tampered log detected (1)."; \
	else \
	  echo "DEMO FAILED: expected clean=0 tampered=1, got clean=$$clean_rc tampered=$$tamper_rc" >&2; \
	  exit 1; \
	fi

bench: ## Measure tail-bounded read latency vs. log size
	@$(PY) tools/bench_read.py
