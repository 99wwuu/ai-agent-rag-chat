class Calculator:
    def run(self, text: str):
        # 安全检查：只允许数字和 + - * / ( ) . 空格，防止执行危险代码
        allowed_chars = set("0123456789+-*/(). ")
        if not set(text) <= allowed_chars:
            return "错误：计算器只支持数字和 + - * / ( ) 运算"
        try:
            # eval 执行数学表达式；{"__builtins__": {}} 关掉内置函数，保证安全
            result = eval(text, {"__builtins__": {}}, {})
            return str(result)
        except Exception:
            return "错误：表达式格式不正确，例如正确写法 '1+2*3'"


calculator = Calculator()
