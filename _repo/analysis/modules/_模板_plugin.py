# -*- coding: utf-8 -*-
"""插件模板（以 `_` 开头，不会被执行器加载；复制改名后使用）。

用法：复制本文件为 m<编号>_<英文短名>.py，改成自己的方法，然后
  1) 在 config 的 modules 里加入该编号；
  2) 若用到新依赖，加入 analysis/requirements.txt；
  3) 云端跑一遍 → 回填 08.生信分析模块库/模块验证矩阵.md。
"""
import os

import pandas as pd


def run(ctx, out):
    """模块入口：ctx["config"] 取参数；产物写 out；返回一句话摘要。"""
    cfg = ctx["config"]
    # 阈值必须来自 config：缺失即报错（由执行器归类为"参数错误"），不要在这里给默认值
    if "my_threshold" not in cfg:
        raise ValueError("Mxx 需在 config.params.Mxx 指定 my_threshold")
    thr = float(cfg["my_threshold"])

    expr = ctx["expr"]                     # 上游（如 M03）放入的表达矩阵：基因 × 样本
    table = pd.DataFrame({"demo": [1, 2, 3]})
    table.to_csv(os.path.join(out, "Mxx_示例表.csv"), index=False, encoding="utf-8-sig")
    return f"示例模块完成（阈值 {thr}，输入 {expr.shape[1]} 样本）"


MODULES = [
    {"id": "Mxx", "name": "示例模块", "folder": "示例模块",
     "deps": ["M03"], "fn": run},
]
