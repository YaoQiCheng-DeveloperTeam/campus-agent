"""让 `python -m agent` 能直接跑。

没有这个文件时，Python 会说「'agent' is a package and cannot be directly executed」——
这是新手最常撞的一堵墙：代码明明没问题，就是跑不起来。
"""
from .main import main

raise SystemExit(main())
