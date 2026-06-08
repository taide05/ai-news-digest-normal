import pytest
from ai.client import CircuitBreaker, CircuitBreakerOpenError


def test_circuit_breaker_opens_after_threshold():
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=600)
    assert cb.can_execute()
    cb.record_failure()
    cb.record_failure()
    assert cb.can_execute()
    cb.record_failure()
    assert not cb.can_execute()


def test_circuit_breaker_recovers_after_timeout():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0)
    cb.record_failure()
    cb.record_failure()
    assert cb.can_execute()


def test_circuit_breaker_record_success_resets():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=600)
    cb.record_failure()
    cb.record_success()
    assert cb.can_execute()
    cb.record_failure()
    assert cb.can_execute()
