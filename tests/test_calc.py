"""
Tests for friday_core.calc (Safe AST Math Evaluator)
Verifies arithmetic correctness and malicious injection blocking.
"""

import unittest
from friday_core.calc import safe_calculate

class TestSafeCalc(unittest.TestCase):
    def test_basic_arithmetic(self):
        self.assertIn("15", safe_calculate("what is 10 + 5"))
        self.assertIn("42", safe_calculate("calculate 6 * 7"))
        self.assertIn("25", safe_calculate("50 / 2"))
        self.assertIn("100", safe_calculate("200 - 100"))

    def test_complex_expressions(self):
        self.assertIn("14", safe_calculate("(2 + 5) * 2"))
        self.assertIn("64", safe_calculate("2 ** 6"))
        self.assertIn("1", safe_calculate("10 % 3"))

    def test_float_results(self):
        res = safe_calculate("what is 7 / 2")
        self.assertIn("3.5", res)

    def test_division_by_zero(self):
        res = safe_calculate("10 / 0")
        self.assertIn("Division by zero", res)

    def test_malicious_code_injection_blocked(self):
        # Must return None or error message, never execute arbitrary Python
        self.assertIsNone(safe_calculate("__import__('os').system('dir')"))
        self.assertIsNone(safe_calculate("eval('2+2')"))
        self.assertIsNone(safe_calculate("open('C:/Windows/win.ini')"))
        self.assertIsNone(safe_calculate("exec('print(1)')"))

    def test_non_math_queries(self):
        self.assertIsNone(safe_calculate("hello friday how are you"))
        self.assertIsNone(safe_calculate("what is the weather today"))

if __name__ == "__main__":
    unittest.main()
