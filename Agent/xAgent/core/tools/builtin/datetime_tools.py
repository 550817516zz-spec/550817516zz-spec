"""内置工具：日期时间与基础计算。"""

from __future__ import annotations

from datetime import datetime

from core.tools.base import tool


@tool("判断给定年份是否为闰年。", name="isLeapYear")
def is_leap_year(year: int) -> str:
    """判断指定年份是否是闰年。

    规则：年份能被 4 整除且不能被 100 整除，或能被 400 整除，即为闰年。

    Args:
        year: 需要判断的年份，例如 2024、2000、1900
    """
    try:
        value = int(year)
    except (TypeError, ValueError):
        return "请输入有效的年份（整数）。"
    is_leap = (value % 4 == 0 and value % 100 != 0) or (value % 400 == 0)
    return f"{value} 年是闰年。" if is_leap else f"{value} 年不是闰年。"


@tool("获取当前的日期与时间。")
def get_current_datetime() -> str:
    """返回当前系统时间，包含日期、时间和时区。"""
    now = datetime.now().astimezone()
    return now.strftime("当前时间：%Y-%m-%d %H:%M:%S %Z（%z）")


@tool("计算两个数值的加减乘除。")
def calculate(expression: str) -> str:
    """计算简单的四则运算表达式。

    仅支持 + - * / ( ) 与数字，禁止调用任意 Python 代码。

    Args:
        expression: 表达式，例如 "(3 + 5) * 2"
    """
    allowed = set("0123456789+-*/(). ")
    if not expression or any(char not in allowed for char in expression):
        return "表达式包含非法字符，仅允许数字与 + - * / ( ) 符号。"

    import ast
    import operator

    operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    def evaluate(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in operators:
            return operators[type(node.op)](evaluate(node.left), evaluate(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in operators:
            return operators[type(node.op)](evaluate(node.operand))
        raise ValueError("不支持的表达式结构")

    try:
        tree = ast.parse(expression, mode="eval")
        result = evaluate(tree)
    except ZeroDivisionError:
        return "计算错误：除数不能为 0。"
    except (SyntaxError, ValueError) as exc:
        return f"表达式解析失败：{exc}"
    return f"{expression} = {result:g}"
