"""reader.py — 一眼看清一段代码的结构

第 1.4 节要你把这个函数补完。平台会拿 6 段真实风格的代码考它，
真实代码比你项目这 30 行长得多，所以先练在别人写的代码上。

    python -m tools.reader agent/main.py

补完之前它只会说「看不懂」，不会瞎给答案——这也是它该有的样子：
拿不准的时候返回 None，比返回一个错的函数名有用。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path


def describe(code: str) -> dict:
    """返回这段代码里第一个顶层函数的结构。

    {
      "name": "build_messages",          # 没有函数就给 None
      "is_async": False,                 # def 还是 async def
      "decorators": ["tool"],            # 按书写顺序，@retry(...) 取 retry
      "params": ["question", "day"],     # 参数名，去掉类型注解与默认值
      "uses_with": False                 # 函数体里有没有 with / async with
    }

    TODO(1.4)：用 ast 把上面五个字段填出来。现在返回的是空壳。
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {"name": None, "is_async": False, "decorators": [],
                "params": [], "uses_with": False}

    # 提示：tree.body 里找第一个 FunctionDef / AsyncFunctionDef
    #   · 装饰器在 node.decorator_list，@retry(...) 是 Call，名字在 .func
    #   · 参数在 node.args.args，每个元素的 .arg 就是名字
    #   · with 用 ast.walk(node) 找 With / AsyncWith，别只看第一层
    _ = tree
    return {"name": None, "is_async": False,
            "decorators": [], "params": [], "uses_with": False}


def main() -> int:
    if len(sys.argv) < 2:
        print("用法：python -m tools.reader <文件>")
        return 1
    src = Path(sys.argv[1]).read_text(encoding="utf-8")
    info = describe(src)
    for k, v in info.items():
        print(f"{k:10} {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
