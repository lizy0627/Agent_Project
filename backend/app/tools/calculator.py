import ast
import math
import operator
from typing import Any

from backend.app.tools.base import BaseTool


class CalculateTool(BaseTool):
    """Safely evaluate a mathematical expression with a small AST allowlist."""

    name = "calculate"
    description = "Safely calculate a mathematical expression."
    args_schema = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Mathematical expression to evaluate.",
            },
        },
        "required": ["expression"],
    }
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
    _function_arg_counts = {
        "abs": (1, 1),
        "round": (1, 2),
        "sqrt": (1, 1),
        "sin": (1, 1),
        "cos": (1, 1),
        "tan": (1, 1),
        "log": (1, 2),
        "log10": (1, 1),
        "ceil": (1, 1),
        "floor": (1, 1),
        "pow": (2, 2),
    }

    def run(self, expression: str) -> dict[str, Any]:
        expression = expression.strip()
        if not expression:
            raise ValueError("Expression is empty.")
        if len(expression) > 300:
            raise ValueError("Expression is too long.")

        try:
            parsed = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            raise ValueError("Expression has invalid syntax.") from exc

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
            try:
                result = self._binary_operators[operator_type](left, right)
            except ZeroDivisionError as exc:
                raise ValueError("Division by zero is not allowed.") from exc
            except (ArithmeticError, OverflowError, ValueError) as exc:
                raise ValueError("Invalid arithmetic operation.") from exc
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
            self._validate_function_arg_count(node.func.id, len(node.args))
            args = [self._evaluate(argument) for argument in node.args]
            self._validate_function_args(node.func.id, args)
            try:
                result = self._functions[node.func.id](*args)
            except (ArithmeticError, TypeError, ValueError) as exc:
                raise ValueError(f"Invalid arguments for function '{node.func.id}'.") from exc
            self._ensure_safe_number(result)
            return result

        raise ValueError("Expression contains unsupported syntax.")

    def _validate_function_arg_count(self, function_name: str, count: int) -> None:
        min_args, max_args = self._function_arg_counts[function_name]
        if min_args == max_args and count != min_args:
            raise ValueError(f"Function '{function_name}' expects {min_args} argument(s).")
        if count < min_args or count > max_args:
            raise ValueError(
                f"Function '{function_name}' expects between {min_args} and {max_args} arguments."
            )

    def _validate_function_args(self, function_name: str, args: list[float | int]) -> None:
        for value in args:
            self._ensure_safe_number(value)

        if function_name == "sqrt" and args[0] < 0:
            raise ValueError("Function 'sqrt' requires a non-negative argument.")
        if function_name == "pow" and abs(args[1]) > self.max_power_exponent:
            raise ValueError("Power exponent is too large.")
        if function_name == "round" and len(args) == 2 and not isinstance(args[1], int):
            raise ValueError("Function 'round' requires an integer second argument.")
        if function_name in {"log", "log10"} and args[0] <= 0:
            raise ValueError(f"Function '{function_name}' requires a positive argument.")
        if function_name == "log" and len(args) == 2 and (args[1] <= 0 or args[1] == 1):
            raise ValueError("Function 'log' base must be positive and not equal to 1.")

    def _ensure_safe_number(self, value: float | int) -> None:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError("Result is not numeric.")
        if not math.isfinite(value):
            raise ValueError("Result is not finite.")
        if abs(value) > self.max_abs_value:
            raise ValueError("Result is too large.")
