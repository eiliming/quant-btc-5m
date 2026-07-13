class FeatureRegistryError(ValueError):
    """Raised when the feature research registry violates its contract."""


class FeatureNotFoundError(KeyError):
    """Raised when a requested feature definition is not registered."""
