import os
import sys
import time
import pytest
import uiautomation as auto

from friday_core.system.window_manager import window_manager, ensure_interactive_desktop, run_on_interactive_desktop
from friday_core.automation.mouse_keyboard import type_real_keystrokes

TEST_1 = "Hello world"

TEST_2 = "#include <stdio.h>"

TEST_3 = """#include <stdio.h>
#include <stdlib.h>
#include <math.h>"""

TEST_4 = """int main() {
    printf("Hello <world> {test} [123] (456) % ^ & * / \\ \" ; :\\n");
    return 0;
}"""

TEST_5_C_LONG = """/*
 * Advanced Scientific Calculator in C
 * Automated Lossless Desktop Keyboard Entry Test Payload
 * 2000+ Characters Benchmark
 */

#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <string.h>

#define MAX_BUFFER_SIZE 1024
#define PI 3.14159265358979323846
#define E  2.71828182845904523536

typedef enum {
    OP_ADD = '+',
    OP_SUB = '-',
    OP_MUL = '*',
    OP_DIV = '/',
    OP_MOD = '%',
    OP_POW = '^'
} OperatorType;

typedef struct {
    double operand_a;
    double operand_b;
    OperatorType op;
    double result;
    int error_flag;
} CalculationRecord;

double evaluate_expression(double a, double b, char op, int *err) {
    *err = 0;
    switch (op) {
        case '+': return a + b;
        case '-': return a - b;
        case '*': return a * b;
        case '/':
            if (fabs(b) < 1e-9) {
                *err = 1;
                return 0.0;
            }
            return a / b;
        case '%':
            if ((long)b == 0) {
                *err = 1;
                return 0.0;
            }
            return (double)((long)a % (long)b);
        case '^':
            return pow(a, b);
        default:
            *err = 2;
            return 0.0;
    }
}

void print_banner(void) {
    printf("==================================================\\n");
    printf("      F.R.I.D.A.Y. Advanced C Calculator         \\n");
    printf("==================================================\\n");
    printf("Available Operations: [ + , - , * , / , %% , ^ ]   \\n");
    printf("Special Constants: PI = %.5f, E = %.5f          \\n", PI, E);
    printf("Punctuation Test: <brackets> {braces} (parens) #  \\n");
    printf("Escape Sequences: \\'single\\' \\\"double\\\" \\\\slash\\n");
    printf("==================================================\\n\\n");
}

int main(int argc, char *argv[]) {
    print_banner();

    CalculationRecord calc;
    calc.operand_a = 42.0;
    calc.operand_b = 3.5;
    calc.op = OP_MUL;

    int error = 0;
    calc.result = evaluate_expression(calc.operand_a, calc.operand_b, (char)calc.op, &error);
    calc.error_flag = error;

    if (!calc.error_flag) {
        printf("Expression: %.2f %c %.2f = %.4f\\n",
               calc.operand_a, (char)calc.op, calc.operand_b, calc.result);
    } else {
        printf("Calculation Error Encountered: Code %d\\n", calc.error_flag);
    }

    return 0;
}
"""

TEST_6_MULTILINE = """\t// Tabbed function header
\tint compute_total(int base, int multiplier) {
\t\t/* Blank line below */

\t\tint total = base * multiplier;
\t\t// Braces and special characters check
\t\tif (total > 0 && multiplier <= 100) {
\t\t\tprintf("Result: %d [OK] {valid}\\n", total);
\t\t}
\t\treturn total;
\t}
"""

def _execute_notepad_test(expected_text: str):
    ensure_interactive_desktop()
    ok, target, reused, msg = window_manager.get_or_launch_window("notepad", force_new=False)
    assert ok and target, f"Failed to acquire Notepad window: {msg}"

    # Verify single Notepad
    all_notepads = window_manager.find_matching_windows("notepad")
    assert len(all_notepads) >= 1

    # Verify focus
    focus_ok = window_manager.focus_window_verified(target.hwnd)
    assert focus_ok, f"Failed to focus Notepad HWND {target.hwnd}"

    # Type with real keystrokes
    success, msg, count = type_real_keystrokes(
        text=expected_text,
        mode="replace",
        typing_delay_ms=20.0,
        hwnd=target.hwnd
    )
    assert success, f"type_real_keystrokes failed: {msg}"

    # Readback from live Notepad
    time.sleep(0.8)
    win = auto.ControlFromHandle(target.hwnd)
    doc = win.DocumentControl(searchDepth=4)
    if not doc.Exists(0, 0):
        doc = win.EditControl(searchDepth=4)
    assert doc.Exists(0, 0), "Could not find Notepad DocumentControl"

    vp = doc.GetValuePattern()
    actual_text = vp.Value if (vp and vp.Value) else ""
    if not actual_text:
        tp = doc.GetTextPattern()
        if tp and tp.DocumentRange:
            actual_text = tp.DocumentRange.GetText(-1)
    if not actual_text:
        actual_text = doc.GetWindowText() or ""

    norm_exp = expected_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    norm_act = actual_text.replace("\r\n", "\n").replace("\r", "\n").strip()

    assert norm_act == norm_exp, (
        f"Text corruption detected!\n"
        f"Expected length: {len(norm_exp)}\n"
        f"Actual length:   {len(norm_act)}\n"
        f"Expected: {repr(norm_exp[:100])}\n"
        f"Actual:   {repr(norm_act[:100])}"
    )


def test_matrix_1_hello_world():
    run_on_interactive_desktop(_execute_notepad_test, TEST_1)


def test_matrix_2_stdio_h():
    run_on_interactive_desktop(_execute_notepad_test, TEST_2)


def test_matrix_3_headers():
    run_on_interactive_desktop(_execute_notepad_test, TEST_3)


def test_matrix_4_main_printf():
    run_on_interactive_desktop(_execute_notepad_test, TEST_4)


def test_matrix_5_long_2000_char_c_file():
    assert len(TEST_5_C_LONG) > 2000, f"Payload must be >2000 chars, got {len(TEST_5_C_LONG)}"
    run_on_interactive_desktop(_execute_notepad_test, TEST_5_C_LONG)


def test_matrix_6_tabs_comments_braces():
    run_on_interactive_desktop(_execute_notepad_test, TEST_6_MULTILINE)
