import ast
import math
import operator
from typing import Any


class CalculateTool:
    """Safely evaluate a mathematical expression with a small AST allowlist."""

    name = "calculate"
    description = "Safely calculate a mathematical expression."
    max_abs_value = 1e100
    max_power_exponent = 1000

    _binary_operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }
    _unary_operators = {
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
    }
    _constants = {
        "pi": math.pi,
        "e": math.e,
        "tau": math.tau,
    }
    _functions = {
        "abs": abs,
        "round": round,
        "sqrt": math.sqrt,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "log": math.log,
        "log10": math.log10,
        "ceil": math.ceil,
        "floor": math.floor,
        "pow": pow,
    }

    def run(self, expression: str) -> dict[str, Any]:
        expression = expression.strip()
        if not expression:
            raise ValueError("Expression is empty.")
        if len(expression) > 300:
            raise ValueError("Expression is too long.")

        parsed = ast.parse(expression, mode="eval")
        value = self._evaluate(parsed.body)
        self._ensure_safe_number(value)
        return {
            "expression": expression,
            "value": value,
        }

    def _evaluate(self, node: ast.AST) -> float | int:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise ValueError("Only numeric constants are allowed.")
            return node.value

        if isinstance(node, ast.Name):
            if node.id not in self._constants:
                raise ValueError(f"Unknown constant: {node.id}")
            return self._constants[node.id]

        if isinstance(node, ast.BinOp):
            operator_type = type(node.op)
            if operator_type not in self._binary_operators:
                raise ValueError("Operator is not allowed.")
            left = self._evaluate(node.left)
            right = self._evaluate(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > self.max_power_exponent:
                raise ValueError("Power exponent is too large.")
            result = self._binary_operators[operator_type](left, right)
            self._ensure_safe_number(result)
            return result

        if isinstance(node, ast.UnaryOp):
            operator_type = type(node.op)
            if operator_type not in self._unary_operators:
                raise ValueError("Unary operator is not allowed.")
            result = self._unary_operators[operator_type](self._evaluate(node.operand))
            self._ensure_safe_number(result)
            return result

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in self._functions:
                raise ValueError("Function is not allowed.")
            if node.keywords:
                raise ValueError("Keyword arguments are not allowed.")
            args = [self._evaluate(argument) for argument in node.args]
            result = self._functions[node.func.id](*args)
            self._ensure_safe_number(result)
            return result

        raise ValueError("Expression contains unsupported syntax.")

    def _ensure_safe_number(self, value: float | int) -> None:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError("Result is not numeric.")
        if not math.isfinite(value):
            raise ValueError("Result is not finite.")
        if abs(value) > self.max_abs_value:
            raise ValueError("Result is too large.")
