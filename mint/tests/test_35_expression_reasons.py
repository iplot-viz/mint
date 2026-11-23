"""Why an expression of the table can't be used, said so that the user knows what to do: a module that isn't loaded,
a function it doesn't have, arguments a function doesn't take, a signal member that doesn't exist, and what computing
it said when it failed."""
import functools
import os
import sys
import tempfile
import types
import unittest

import numpy as np

from mint.models.utils.mtExpressionCheck import call_problem, why_failed, why_rejected, without_values

ALIASES = ["MT2611", "MT2611_bis", "fit"]
DEFAULTS = {"x": "${self}.time", "y": "${self}.data", "z": "${self}.data_store[2]"}


class _Probe:
    """An object whose member fails when read for another reason than not being there."""

    @property
    def broken(self):
        raise ValueError("not now")


def _module_of_the_user():
    """A module as a user writes one: slope_fit(t, y), a function that takes nothing, one behind a decorator that
    takes anything, and an object with a member that fails when read."""
    module = types.ModuleType("mctf")

    def slope_fit(t, y):
        return t, y

    def decorated(function):
        @functools.wraps(function)
        def wrapper(*args, **kwargs):
            return function(args[0])
        return wrapper

    module.slope_fit = slope_fit
    module.now = lambda: 0
    module.smoothed = decorated(lambda y: y)
    module.probe = _Probe()
    return module


class WhyRejectedTest(unittest.TestCase):
    """What the parser refuses, said with what puts it right."""

    def setUp(self):
        self.known = {"np": np, "numpy": np, "diff": np.diff}

    def rejected(self, expression, error=""):
        return why_rejected(expression, error, self.known, ALIASES)

    def test_a_module_of_this_computer_that_isnt_loaded(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        with open(os.path.join(folder.name, "mint_test_mctf.py"), "w") as f:
            f.write("def slope(t, y, window):\n    return t\n")
        sys.path.insert(0, folder.name)
        self.addCleanup(sys.path.remove, folder.name)
        self.assertEqual(self.rejected("mint_test_mctf.slope(${self}.time,${self}.data,3600)[0]",
                                       "Undefined name mint_test_mctf"),
                         "mint_test_mctf is a Python module that isn't loaded (add it with Load new module)")
        self.assertNotIn("mint_test_mctf", sys.modules, "looked for, not imported")

    def test_a_module_that_isnt_anywhere(self):
        self.assertEqual(self.rejected("mint_no_module.slope(${self}.data)", "Undefined name mint_no_module"),
                         "MINT doesn't know mint_no_module (if it is a module of yours, add it with Load new module)")

    def test_a_name_close_to_one_it_knows(self):
        self.assertEqual(self.rejected("npp.diff(${self}.data)", "Undefined name npp"),
                         "MINT doesn't know npp (did you mean np?)")

    def test_an_alias_without_its_marks(self):
        self.assertEqual(self.rejected("MT2611.data - ${self}.data", "Undefined name MT2611"),
                         "MT2611 is the alias of a row (write it as ${MT2611})")
        self.assertEqual(self.rejected("MT2611"), "MT2611 is the alias of a row (write it as ${MT2611})")

    def test_a_member_a_signal_doesnt_have(self):
        self.assertEqual(self.rejected("${self}.tme", "Undefined name tme"),
                         "a signal has no tme (did you mean .time?)")
        self.assertEqual(self.rejected("${self}.data_stor[2]", "Undefined name data_stor"),
                         "a signal has no data_stor (did you mean .data_store?)")

    def test_a_function_a_loaded_module_doesnt_have(self):
        self.known["mctf"] = _module_of_the_user()
        self.assertEqual(self.rejected("mctf.slope(${self}.time,${self}.data,3600)[0]", "Undefined name slope"),
                         "mctf has no slope (did you mean mctf.slope_fit?)")

    def test_how_it_is_written(self):
        self.assertEqual(self.rejected("np.diff(${self}.data", "Syntax error '(' was never closed"),
                         "it isn't written right ('(' was never closed)")
        self.assertEqual(self.rejected("${self}.data ** 2", "Invalid expression"), "expressions can't use **")
        self.assertEqual(self.rejected("${self.data", "Invalid expression"), "a ${ isn't closed with }")
        self.assertEqual(self.rejected("np.arange(10)"), "it names no signal (write those it uses as ${alias})")

    def test_a_time_written_with_its_unit_is_no_mistake(self):
        self.assertEqual(self.rejected("${self}.time + 10s + mctf.offset", "Undefined name mctf"),
                         "MINT doesn't know mctf (if it is a module of yours, add it with Load new module)")

    def test_what_it_cant_tell_it_doesnt_guess(self):
        # Rejected for what the parser alone knows: nothing is made up about the names it uses.
        self.assertEqual(self.rejected("${self}.data_store[2] + ${self}.tme", "Invalid expression syntax"), "")
        self.assertEqual(self.rejected("${self}.data.foo", "Undefined name foo"), "MINT doesn't know foo")


class CallProblemTest(unittest.TestCase):
    """What an expression the parser accepts would fail at for certain once computed, found before it is."""

    def setUp(self):
        self.known = {"np": np, "numpy": np, "mctf": _module_of_the_user()}

    def problem(self, expression):
        return call_problem(expression, self.known)

    def test_arguments_a_function_doesnt_take(self):
        self.assertEqual(self.problem("mctf.slope_fit(${self}.time,${self}.data,3600)[0]"),
                         "mctf.slope_fit takes 2 arguments (t, y), not 3")
        self.assertEqual(self.problem("mctf.slope_fit(${self}.time)"), "mctf.slope_fit also needs y")
        self.assertEqual(self.problem("mctf.slope_fit(${self}.time, ${self}.data, window=3)"),
                         "mctf.slope_fit has no argument window")
        self.assertEqual(self.problem("mctf.slope_fit(${self}.time, t=${self}.data)"), "mctf.slope_fit gets t twice")
        self.assertEqual(self.problem("${self}.data * mctf.now(${self}.time)"), "mctf.now takes no arguments, not 1")

    def test_a_function_the_module_doesnt_have(self):
        self.assertEqual(self.problem("mctf.slope(${self}.time,${self}.data)[0]"),
                         "mctf has no slope (did you mean mctf.slope_fit?)")

    def test_the_parameters_of_a_lambda_are_not_what_mint_knows_by_their_name(self):
        # The parser knows data, as a member of the signals; in the lambda it is the values given.
        self.known["data"] = {"idx": 1}
        self.assertEqual(self.problem("(lambda data: data.mean(0))(${self}.data)"), "")
        self.assertEqual(self.problem("(lambda mctf: mctf.slope(1, 2, 3))(${self}.data)"), "")

    def test_what_can_only_be_known_by_computing_it_is_left_to_that(self):
        for expression in ["mctf.slope_fit(${self}.time, ${self}.data)[0]", "np.diff(${MT2611}.data)",
                           "np.convolve(${self}.data, np.ones(5)/5, mode='same')", "mctf.smoothed(${self}.data, 5)",
                           "${self}.time + 10s", "np.array([${self}.time[0], ${self}.time[-1]])",
                           "mctf.slope_fit(*${self}.data)", "${MT2611}.time[0:-2:4]", "${self}.data_store[2]",
                           "${self}.data * mctf.probe.broken"]:
            with self.subTest(expression=expression):
                self.assertEqual(self.problem(expression), "")


class WhyFailedTest(unittest.TestCase):
    """What computing a row said when it failed, as its Status gives it."""

    def test_an_expression_of_x_y_or_z_says_which(self):
        self.assertEqual(why_failed("y", "the y expression failed: Value error slice step cannot be zero"),
                         "The y expression failed: slice step cannot be zero")
        self.assertEqual(why_failed("x", "the x expression failed: module 'mctf' has no attribute 'slope'"),
                         "The x expression failed: mctf has no slope")
        self.assertEqual(why_failed("y", "the y expression failed: index 5 is out of bounds for axis 0 with size 3"),
                         "The y expression failed: index 5 is out of bounds for axis 0 with size 3")

    def test_what_the_parser_says_of_a_type_error_is_said_plainly(self):
        self.assertEqual(why_failed("y", "the y expression failed: Following keys are undefined {'self'}"),
                         "The y expression failed: a function or an operation in it got values it can't take")
        self.assertEqual(why_failed("y", "the y expression failed: Undefined name slope_fit"),
                         "The y expression failed: MINT doesn't know slope_fit")

    def test_the_expression_of_the_variable_keeps_what_the_error_reference_explains(self):
        self.assertEqual(why_failed("", "Value error operands could not be broadcast together with shapes (101,) "
                                        "(5,) "),
                         "The variable expression failed: operands could not be broadcast together with shapes "
                         "(101,) (5,)")
        self.assertEqual(why_failed("", "Result of expression=np.max(${A}) is not an instance of SignalXY"),
                         "The variable expression failed: Result of expression=np.max(${A}) is not an instance of "
                         "SignalXY")

    def test_without_a_message_it_says_what_failed(self):
        self.assertEqual(why_failed("z", ""), "The z expression failed")
        self.assertEqual(why_failed("", None), "The variable expression failed")


class _Computed:
    """A signal whose x, y and z expressions give what is said."""

    def __init__(self, x_expr="${self}.time", y_expr="${self}.data", z_expr="${self}.data_store[2]", **results):
        self.x_expr, self.y_expr, self.z_expr = x_expr, y_expr, z_expr
        self.depends_on = {"self"}
        self._results, self.asked = results, []

    def compute(self, **expressions):
        self.asked.append(sorted(expressions))
        return {key: self._results.get(key) for key in expressions}


class WithoutValuesTest(unittest.TestCase):
    """What an expression gave instead of an array, which computing leaves out without a word."""

    def test_what_an_expression_gave_instead_of_an_array(self):
        for value, said in [((np.zeros(3), np.zeros(3)), "a tuple of 2"), (3.0, "a single number"),
                            (np.float64(3.0), "a single number"), ([1, 2], "a list"), (None, "None")]:
            with self.subTest(value=value):
                signal = _Computed(y_expr="mctf.fit(${self}.time, ${self}.data)", y=value)
                self.assertEqual(without_values(signal, DEFAULTS), ("y", f"it gives {said}, not an array of values"))
                self.assertEqual(signal.asked, [["y"]], "only what isn't read as it is")

    def test_arrays_say_nothing_and_what_is_read_as_it_is_isnt_computed(self):
        self.assertEqual(without_values(_Computed(x_expr="${self}.time - 5", x=np.zeros(0)), DEFAULTS), ("", ""))
        signal = _Computed()
        self.assertEqual(without_values(signal, DEFAULTS), ("", ""))
        self.assertEqual(signal.asked, [])

    def test_what_uses_other_signals_isnt_computed_again(self):
        # Computing it would read B again and line the two up, which changes the signal.
        signal = _Computed(y_expr="mctf.fit(${self}.data, ${B}.data)", y=(np.zeros(3), np.zeros(3)))
        signal.depends_on = {"self", "B"}
        self.assertEqual(without_values(signal, DEFAULTS), ("", ""))
        self.assertEqual(signal.asked, [])


if __name__ == "__main__":
    unittest.main()
