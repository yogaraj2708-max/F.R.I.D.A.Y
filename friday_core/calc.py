"""
F.R.I.D.A.Y. 2.0 - Secure Arithmetic Calculator
Evaluates math expressions using a strict Abstract Syntax Tree (AST) parser.
Zero use of Python eval() or exec().
"""

import ast
import math
import operator
import re
from typing import Optional, Any

# Safe operators mapping
SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# Safe math functions & constants
SAFE_FUNCTIONS = {
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
    "abs": abs,
    "round": round,
    "ceil": math.ceil,
    "floor": math.floor,
}

SAFE_CONSTANTS = {
    "pi": math.pi,
    "e": math.e,
}

class SafeEvaluator(ast.NodeVisitor):
    """AST visitor that only evaluates numeric expressions."""

    def visit(self, node: ast.AST) -> Any:
        method = 'visit_' + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        return visitor(node)

    def generic_visit(self, node: ast.AST):
        raise ValueError(f"Disallowed expression syntax: {node.__class__.__name__}")

    def visit_Expression(self, node: ast.Expression):
        return self.visit(node.body)

    def visit_Constant(self, node: ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("Only numeric constants allowed")

    def visit_BinOp(self, node: ast.BinOp):
        op_type = type(node.op)
        if op_type not in SAFE_OPERATORS:
            raise ValueError(f"Operator {op_type.__name__} not permitted")
        left = self.visit(node.left)
        right = self.visit(node.right)
        # Guard against absurd power loops (e.g. 9**9**9)
        if op_type is ast.Pow and (abs(left) > 1000 or abs(right) > 1000):
            raise ValueError("Exponent exceeds safe operational bounds")
        return SAFE_OPERATORS[op_type](left, right)

    def visit_UnaryOp(self, node: ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in SAFE_OPERATORS:
            raise ValueError(f"Unary operator {op_type.__name__} not permitted")
        operand = self.visit(node.operand)
        return SAFE_OPERATORS[op_type](operand)

    def visit_Name(self, node: ast.Name):
        if node.id in SAFE_CONSTANTS:
            return SAFE_CONSTANTS[node.id]
        raise ValueError(f"Identifier '{node.id}' not permitted")

    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in SAFE_FUNCTIONS:
            func = SAFE_FUNCTIONS[node.func.id]
            args = [self.visit(arg) for arg in node.args]
            return func(*args)
        raise ValueError("Function call not permitted")

def safe_calculate(cmd: str) -> Optional[str]:
    """
    Cleanses natural language command into an arithmetic formula, parses via AST,
    and returns a formatted string answer.
    """
    for prefix in ["what is ", "what's ", "calculate ", "compute ", "tell me "]:
        if cmd.lower().startswith(prefix):
            cmd = cmd[len(prefix):]
            break

    clean_expr = cmd.strip().lower()
    # Word forms first, longest first so "multiplied by" is not half-eaten by "by".
    for word, symbol in (
        ("multiplied by", "*"),
        ("divided by", "/"),
        ("times", "*"),
        ("plus", "+"),
        ("minus", "-"),
        ("over", "/"),
    ):
        clean_expr = re.sub(rf"\b{re.escape(word)}\b", symbol, clean_expr)

    # Only a standalone "x" sitting between two numbers means multiplication.
    # A blanket .replace("x", "*") turned "max", "expression" and "sixty" into
    # nonsense and made unrelated sentences look like maths.
    clean_expr = re.sub(r"(?<=[\d\s)])\s*x\s*(?=[\d(])", "*", clean_expr)
    clean_expr = clean_expr.replace("^", "**")

    # Quick heuristic check for math characters
    if not any(c in clean_expr for c in "+-*/%()0123456789"):
        return None

    try:
        tree = ast.parse(clean_expr, mode='eval')
        evaluator = SafeEvaluator()
        result = evaluator.visit(tree)

        if isinstance(result, (int, float)):
            if isinstance(result, float) and result.is_integer():
                result = int(result)
            elif isinstance(result, float):
                result = round(result, 4)
            return f"The answer is {result}."
    except ZeroDivisionError:
        return "Division by zero is undefined, Boss."
    except Exception:
        pass

    return None
