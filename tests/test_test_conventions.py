"""CLAUDE.md のテスト規約を CI で継続的に検査する。"""
from __future__ import annotations

import ast
import io
import re
import tokenize
from dataclasses import dataclass
from pathlib import Path

from conftest import REPO_ROOT

TESTS_DIR = REPO_ROOT / "tests"
PYTEST_FILE_PATTERNS = ("test_*.py", "*_test.py")
TEST_NAME_PATTERN = re.compile(r"test_.+_.+場合_.+こと")
CASE_ID_PATTERN = re.compile(r".+場合_.+こと")
AAA_MARKERS = {"# Arrange", "# Act", "# Assert", "# Act & Assert"}


@dataclass(frozen=True)
class CollectedTest:
    path: Path
    node: ast.FunctionDef | ast.AsyncFunctionDef
    source: str

    @property
    def location(self) -> str:
        return f"{self.path.relative_to(REPO_ROOT)}:{self.node.lineno}"

    @property
    def aaa_markers(self) -> list[tuple[int, str]]:
        """関数内にある完全一致の AAA comment token を返す。"""
        end = self.node.end_lineno or self.node.lineno
        nested_ranges = [
            (node.lineno, node.end_lineno or node.lineno)
            for node in ast.walk(self.node)
            if node is not self.node
            and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ]
        return [
            (token.start[0], token.string)
            for token in tokenize.generate_tokens(io.StringIO(self.source).readline)
            if token.type == tokenize.COMMENT
            and self.node.lineno <= token.start[0] <= end
            and token.string in AAA_MARKERS
            and not any(start <= token.start[0] <= stop for start, stop in nested_ranges)
        ]

    @property
    def executable_statement_lines(self) -> set[int]:
        """docstring と入れ子定義を除く、テスト本体の実行文の開始行を返す。"""
        lines: set[int] = set()

        def visit(node: ast.AST) -> None:
            if node is not self.node and isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                lines.add(node.lineno)
                return
            if isinstance(node, ast.stmt) and node is not self.node:
                is_docstring = (
                    isinstance(node, ast.Expr)
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                )
                if not is_docstring:
                    lines.add(node.lineno)
            for child in ast.iter_child_nodes(node):
                visit(child)

        visit(self.node)
        return lines


def _pytest_test_nodes(
    body: list[ast.stmt],
) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """pytest が通常収集する module / Test* class 直下の test 関数を返す。"""
    nodes: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                nodes.append(node)
            continue
        if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            nodes.extend(_pytest_test_nodes(node.body))
    return nodes


def _collect_tests() -> list[CollectedTest]:
    tests: list[CollectedTest] = []
    paths = {
        path
        for pattern in PYTEST_FILE_PATTERNS
        for path in TESTS_DIR.rglob(pattern)
    }
    for path in sorted(paths):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in _pytest_test_nodes(tree.body):
            tests.append(CollectedTest(path, node, source))
    return tests


def _is_named_call(node: ast.expr, name: str) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == name
    )


def _is_parametrize(decorator: ast.expr) -> bool:
    return _is_named_call(decorator, "parametrize")


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next(
        (keyword.value for keyword in call.keywords if keyword.arg == name),
        None,
    )


def _call_argument(call: ast.Call, position: int, keyword: str) -> ast.expr | None:
    """pytest API の位置引数・キーワード引数の両形式を解決する。"""
    value = _keyword(call, keyword)
    if value is not None:
        return value
    return call.args[position] if len(call.args) > position else None


def _id_template(expression: ast.expr) -> str | None:
    """静的文字列か f-string を、形式検査可能なテンプレートへ変換する。"""
    if isinstance(expression, ast.Constant) and isinstance(expression.value, str):
        return expression.value
    if isinstance(expression, ast.JoinedStr):
        parts: list[str] = []
        for value in expression.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                parts.append("value")
            else:
                return None
        return "".join(parts)
    return None


def _valid_case_id(expression: ast.expr) -> bool:
    template = _id_template(expression)
    return template is not None and CASE_ID_PATTERN.fullmatch(template) is not None


def _pytest_param_id(case: ast.expr) -> ast.expr | None:
    if not _is_named_call(case, "param"):
        return None
    return _keyword(case, "id")


def _parametrize_id_problem(decorator: ast.Call) -> str | None:
    """全 case の ID が規約を満たし、case 数を完全に覆うかを検査する。"""
    values = _call_argument(decorator, 1, "argvalues")
    if values is None:
        return "parameter values are missing"

    ids = _call_argument(decorator, 3, "ids")
    if ids is not None:
        if isinstance(ids, ast.Lambda):
            return None if _valid_case_id(ids.body) else "ids callable has an invalid template"

        if isinstance(ids, (ast.List, ast.Tuple)):
            if not isinstance(values, (ast.List, ast.Tuple)):
                return "static ids cannot prove coverage for dynamic parameter values"
            if len(ids.elts) != len(values.elts):
                return "ids count does not match parameter case count"
            return None if all(_valid_case_id(item) for item in ids.elts) else "an id has an invalid format"

        if isinstance(ids, ast.ListComp) and len(ids.generators) == 1:
            generator = ids.generators[0]
            same_iterable = ast.dump(generator.iter) == ast.dump(values)
            if generator.ifs or generator.is_async or not same_iterable:
                return "ids comprehension does not cover the same parameter values"
            return None if _valid_case_id(ids.elt) else "ids comprehension has an invalid template"

        return "ids expression cannot be verified statically"

    if isinstance(values, (ast.List, ast.Tuple)):
        id_expressions = [_pytest_param_id(case) for case in values.elts]
        if any(expression is None for expression in id_expressions):
            return "every parameter case must be pytest.param(..., id=...)"
        return (
            None
            if all(_valid_case_id(expression) for expression in id_expressions if expression is not None)
            else "a pytest.param id has an invalid format"
        )

    if isinstance(values, ast.ListComp):
        expression = _pytest_param_id(values.elt)
        if expression is None:
            return "parameter comprehension must yield pytest.param(..., id=...)"
        return None if _valid_case_id(expression) else "pytest.param id template has an invalid format"

    return "parameter cases and ids cannot be verified statically"


def _aaa_problem(test: CollectedTest) -> str | None:
    markers = test.aaa_markers
    if not markers:
        return "exact AAA comment tokens are required"

    expects_action = True
    arrange_open = False
    for _, marker in markers:
        if expects_action:
            if marker == "# Arrange":
                if arrange_open:
                    return "# Arrange cannot be repeated before an action"
                arrange_open = True
            elif marker == "# Act":
                expects_action = False
                arrange_open = False
            elif marker == "# Act & Assert":
                arrange_open = False
            else:
                return "an action marker must precede # Assert"
        elif marker == "# Assert":
            expects_action = True
        else:
            return "# Assert must immediately follow an # Act section"
    if arrange_open:
        return "# Arrange must be followed by an action marker"
    if not expects_action:
        return "# Act must be followed by # Assert"

    statement_lines = test.executable_statement_lines
    end = (test.node.end_lineno or test.node.lineno) + 1
    for index, (lineno, marker) in enumerate(markers):
        next_line = markers[index + 1][0] if index + 1 < len(markers) else end
        if not any(lineno < statement_line < next_line for statement_line in statement_lines):
            return f"{marker} section must not be empty"
    return None


def _collected_test(source: str) -> CollectedTest:
    node = ast.parse(source).body[0]
    assert isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    return CollectedTest(REPO_ROOT / "tests" / "synthetic_test.py", node, source)


def _parametrize_call(source: str) -> ast.Call:
    expression = ast.parse(source, mode="eval").body
    assert isinstance(expression, ast.Call)
    return expression


def test__collect_tests_全test関数を走査した場合_命名規約を満たすこと():
    # Act
    problems = [
        f"{test.location}: {test.node.name}"
        for test in _collect_tests()
        if TEST_NAME_PATTERN.fullmatch(test.node.name) is None
    ]

    # Assert
    assert not problems, "test naming violations:\n" + "\n".join(problems)


def test__collect_tests_全test関数を走査した場合_AAA区画を順序どおり明示すること():
    # Act
    problems = [
        f"{test.location}: {test.node.name}: {problem}"
        for test in _collect_tests()
        if (problem := _aaa_problem(test)) is not None
    ]

    # Assert
    assert not problems, "AAA comment violations:\n" + "\n".join(problems)


def test__parametrize_id_problem_parametrizeを使う場合_全caseに規約形式のidを明示すること():
    # Act
    problems = []
    for test in _collect_tests():
        for decorator in test.node.decorator_list:
            if not _is_parametrize(decorator):
                continue
            problem = _parametrize_id_problem(decorator)
            if problem is not None:
                problems.append(f"{test.location}: {test.node.name}: {problem}")

    # Assert
    assert not problems, "parametrize id violations:\n" + "\n".join(problems)


def test__aaa_problem_docstringや空区画で規約を装った場合_違反として検出すること():
    # Arrange
    docstring_only = _collected_test(
        '''def test_target_条件の場合_期待どおりになること():
    """説明。
    # Act
    # Assert
    """
    pass
'''
    )
    empty_act = _collected_test(
        """def test_target_条件の場合_期待どおりになること():
    # Act
    # Assert
    assert True
"""
    )

    # Act
    docstring_problem = _aaa_problem(docstring_only)
    empty_problem = _aaa_problem(empty_act)

    # Assert
    assert docstring_problem is not None
    assert empty_problem == "# Act section must not be empty"


def test__parametrize_id_problem_keywordと位置引数形式を使う場合_全caseのidを検査できること():
    # Arrange
    keyword_decorator = _parametrize_call(
        'pytest.mark.parametrize(argnames="x", argvalues=[1, 2], '
        'ids=["一の場合_okになること", "二の場合_okになること"])'
    )
    positional_decorator = _parametrize_call(
        'pytest.mark.parametrize("x", [1, 2], False, '
        '["一の場合_okになること", "二の場合_okになること"])'
    )

    # Act
    keyword_problem = _parametrize_id_problem(keyword_decorator)
    positional_problem = _parametrize_id_problem(positional_decorator)

    # Assert
    assert keyword_problem is None
    assert positional_problem is None


def test__pytest_test_nodes_入れ子helperとTest_classを走査した場合_pytest対象だけ収集すること():
    # Arrange
    tree = ast.parse(
        """def test_module_条件の場合_期待どおりになること():
    def test_nested_条件の場合_収集されないこと():
        pass

class TestSuite:
    def test_method_条件の場合_収集されること(self):
        pass

class Helper:
    def test_method_条件の場合_収集されないこと(self):
        pass
"""
    )

    # Act
    names = [node.name for node in _pytest_test_nodes(tree.body)]

    # Assert
    assert names == [
        "test_module_条件の場合_期待どおりになること",
        "test_method_条件の場合_収集されること",
    ]


def test__aaa_problem_Arrangeでlocal関数を定義した場合_定義文を実行文として数えること():
    # Arrange
    test = _collected_test(
        """def test_target_条件の場合_期待どおりになること():
    # Arrange
    def callback():
        return 1
    # Act
    result = callback()
    # Assert
    assert result == 1
"""
    )

    # Act
    problem = _aaa_problem(test)

    # Assert
    assert problem is None
