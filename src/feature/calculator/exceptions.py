class FeatureError(Exception):
    """Base feature framework error."""


class CircularDependencyError(FeatureError):
    """Raised when the feature dependency graph contains a cycle."""


class CalculatorNotFoundError(FeatureError):
    """Raised when a registered calculator class cannot be discovered."""


class InvalidCalculatorOutputError(FeatureError):
    """Raised when calculator output violates its registry definition."""
