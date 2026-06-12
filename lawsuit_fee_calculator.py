from typing import List, Tuple, Dict


BRACKETS: List[Tuple[float, float]] = [
    (1.0, 0.0),
    (10.0, 0.025),
    (20.0, 0.02),
    (50.0, 0.015),
    (100.0, 0.01),
    (200.0, 0.009),
    (500.0, 0.008),
    (1000.0, 0.007),
    (2000.0, 0.006),
    (float('inf'), 0.005),
]

FIXED_FEE_FIRST_BRACKET = 50.0


def calculate_lawsuit_fee(amount_in_wan: float) -> Dict:
    if amount_in_wan is None:
        raise ValueError("标的额不能为空")
    if amount_in_wan < 0:
        raise ValueError("标的额不能为负数")

    amount_yuan = amount_in_wan * 10000.0

    if amount_yuan <= 10000.0:
        return {
            "amount_wan": amount_in_wan,
            "fee_yuan": FIXED_FEE_FIRST_BRACKET if amount_yuan > 0 else 0.0,
            "fee_wan": (FIXED_FEE_FIRST_BRACKET if amount_yuan > 0 else 0.0) / 10000.0,
            "breakdown": [
                {
                    "range": "不超过1万元",
                    "base": 0.0,
                    "upper": min(amount_yuan, 10000.0),
                    "rate": "50元/件",
                    "portion": FIXED_FEE_FIRST_BRACKET if amount_yuan > 0 else 0.0,
                }
            ],
        }

    total_fee = 0.0
    breakdown = []

    first_upper = 10000.0
    breakdown.append({
        "range": "不超过1万元",
        "base": 0.0,
        "upper": first_upper,
        "rate": "50元/件",
        "portion": FIXED_FEE_FIRST_BRACKET,
    })
    total_fee += FIXED_FEE_FIRST_BRACKET

    prev_bracket_wan = 1.0

    for i in range(1, len(BRACKETS)):
        bracket_upper_wan, rate = BRACKETS[i]
        bracket_upper_yuan = bracket_upper_wan * 10000.0
        prev_upper_yuan = prev_bracket_wan * 10000.0

        if amount_yuan <= prev_upper_yuan:
            break

        applicable_base = prev_upper_yuan
        applicable_upper = min(amount_yuan, bracket_upper_yuan)
        taxable = applicable_upper - applicable_base
        portion = taxable * rate

        total_fee += portion
        breakdown.append({
            "range": f"超过{prev_bracket_wan:.0f}万元至{bracket_upper_wan:.0f}万元"
            if bracket_upper_wan != float('inf')
            else f"超过{prev_bracket_wan:.0f}万元",
            "base": applicable_base,
            "upper": applicable_upper,
            "rate": f"{rate * 100:.1f}%",
            "portion": portion,
        })

        prev_bracket_wan = bracket_upper_wan
        if amount_yuan <= bracket_upper_yuan:
            break

    return {
        "amount_wan": amount_in_wan,
        "fee_yuan": round(total_fee, 2),
        "fee_wan": round(total_fee / 10000.0, 6),
        "breakdown": breakdown,
    }


def format_result(result: Dict) -> str:
    lines = []
    lines.append("=" * 50)
    lines.append(f"标的额：{result['amount_wan']:.6f} 万元（{result['amount_wan'] * 10000:.2f} 元）")
    lines.append("-" * 50)
    lines.append("分段计算明细：")
    for idx, item in enumerate(result["breakdown"], 1):
        lines.append(f"  {idx}. 区间：{item['range']}")
        lines.append(f"     计算基数：{item['base']:.2f} 元 ~ {item['upper']:.2f} 元")
        lines.append(f"     费率：{item['rate']}")
        lines.append(f"     该段费用：{item['portion']:.2f} 元")
    lines.append("-" * 50)
    lines.append(f"案件受理费合计：{result['fee_yuan']:.2f} 元（{result['fee_wan']:.6f} 万元）")
    lines.append("=" * 50)
    return "\n".join(lines)


def main():
    print("=== 诉讼费计算服务（案件受理费 - 财产案件）===")
    print("依据：《诉讼费用交纳办法》（国务院令第481号）第十三条")
    print()

    while True:
        try:
            user_input = input("请输入标的额（万元），输入 q 退出：").strip()
            if user_input.lower() in ('q', 'quit', 'exit'):
                print("再见。")
                break
            if not user_input:
                continue
            amount = float(user_input)
            result = calculate_lawsuit_fee(amount)
            print()
            print(format_result(result))
            print()
        except ValueError as e:
            print(f"输入错误：{e}")
        except (KeyboardInterrupt, EOFError):
            print("\n再见。")
            break


if __name__ == "__main__":
    main()
