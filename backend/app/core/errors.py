"""Exceções de domínio."""
from __future__ import annotations


class FactoryError(Exception):
    """Erro base da plataforma."""

    code = "factory_error"
    retryable = False

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFound(FactoryError):
    code = "not_found"


class ValidationFailed(FactoryError):
    code = "validation_failed"


class Conflict(FactoryError):
    code = "conflict"


class BudgetExceeded(FactoryError):
    code = "budget_exceeded"


class ProviderUnavailable(FactoryError):
    code = "provider_unavailable"
    retryable = True


class ProviderError(FactoryError):
    code = "provider_error"

    def __init__(self, message: str, *, retryable: bool = True, details: dict | None = None):
        super().__init__(message, details=details)
        self.retryable = retryable


class MissingCredentials(FactoryError):
    code = "missing_credentials"


class IntegrationNotAuthorized(FactoryError):
    code = "integration_not_authorized"
