from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import Type

import pandas as pd

from src.feature.calculator.base import FeatureCalculator
from src.feature.calculator.exceptions import (
    CalculatorNotFoundError,
    CircularDependencyError,
    InvalidCalculatorOutputError,
)
from src.feature.registry.registry import FeatureRegistry


class FeatureEngine:
    def __init__(self, registry: FeatureRegistry | None = None) -> None:
        self.registry = registry or FeatureRegistry()

    def calculate(self, df: pd.DataFrame, features: list[str]) -> pd.DataFrame:
        if "timestamp" not in df.columns:
            raise ValueError("feature input must contain timestamp")
        requested = list(dict.fromkeys(features))
        order = self.resolve(features=requested)
        working = df.copy(deep=True)
        result = pd.DataFrame({"timestamp": df["timestamp"].copy()})
        calculation_cache: dict[
            tuple[str, tuple[tuple[str, str], ...]], pd.DataFrame
        ] = {}

        for name in order:
            definition = self.registry.get(name)
            missing = [column for column in definition.inputs if column not in working.columns]
            if missing:
                raise ValueError(f"feature {name} missing input columns: {missing}")
            execution_key = (
                definition.calculator,
                tuple(sorted((key, repr(value)) for key, value in definition.parameters.items())),
            )
            calculated = calculation_cache.get(execution_key)
            if calculated is None:
                calculator_type = self._find_calculator(definition.calculator)
                calculator = calculator_type(**definition.parameters)
                self._validate_calculator_contract(calculator, definition.name)
                calculated = calculator.calculate(working.copy(deep=True))
                calculation_cache[execution_key] = calculated
            expected = ["timestamp", *definition.outputs]
            missing_outputs = [column for column in expected if column not in calculated.columns]
            if missing_outputs or len(calculated) != len(df):
                raise InvalidCalculatorOutputError(
                    f"calculator {definition.calculator} returned invalid output; "
                    f"missing={missing_outputs}, rows={len(calculated)}, expected_rows={len(df)}"
                )
            if not calculated["timestamp"].reset_index(drop=True).equals(
                df["timestamp"].reset_index(drop=True)
            ):
                raise InvalidCalculatorOutputError(
                    f"calculator {definition.calculator} changed timestamp alignment"
                )
            for column in definition.outputs:
                working[column] = calculated[column].to_numpy()
                result[column] = calculated[column].to_numpy()
        return result

    def resolve(self, features: list[str]) -> list[str]:
        """Return requested features and dependencies in execution order."""
        requested = list(dict.fromkeys(features))
        order: list[str] = []
        state: dict[str, int] = {}

        def visit(name: str, trail: list[str]) -> None:
            definition = self.registry.get(name)
            if state.get(name) == 1:
                cycle = " -> ".join([*trail, name])
                raise CircularDependencyError(f"circular feature dependency: {cycle}")
            if state.get(name) == 2:
                return
            state[name] = 1
            for dependency in definition.dependencies:
                visit(dependency, [*trail, name])
            state[name] = 2
            order.append(name)

        for name in requested:
            visit(name, [])
        return order

    @staticmethod
    def _find_calculator(class_name: str) -> Type[FeatureCalculator]:
        import src.feature.features as feature_package

        for module_info in pkgutil.walk_packages(
            feature_package.__path__, prefix=f"{feature_package.__name__}."
        ):
            module = importlib.import_module(module_info.name)
            candidate = getattr(module, class_name, None)
            if inspect.isclass(candidate) and issubclass(candidate, FeatureCalculator):
                return candidate
        raise CalculatorNotFoundError(f"calculator class not found: {class_name}")

    def _validate_calculator_contract(
        self, calculator: FeatureCalculator, feature_name: str
    ) -> None:
        definition = self.registry.get(feature_name)
        if calculator.version != definition.version:
            raise InvalidCalculatorOutputError(
                f"calculator version mismatch for {feature_name}: "
                f"{calculator.version} != {definition.version}"
            )
        undeclared_inputs = sorted(set(definition.inputs) - set(calculator.input_columns))
        undeclared_outputs = sorted(set(definition.outputs) - set(calculator.output_columns))
        if undeclared_inputs or undeclared_outputs:
            raise InvalidCalculatorOutputError(
                f"calculator contract mismatch for {feature_name}; "
                f"inputs={undeclared_inputs}, outputs={undeclared_outputs}"
            )
