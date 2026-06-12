from enum import Enum
from typing import List, Tuple, Dict, Optional, Any


PROPERTY_BRACKETS: List[Tuple[float, float]] = [
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

PROPERTY_FIRST_BRACKET_FIXED = 50.0


class CaseType(str, Enum):
    PROPERTY = 'property'
    DIVORCE = 'divorce'
    PERSONALITY = 'personality'
    OTHER_NON_PROPERTY = 'other_non_property'
    IP = 'ip'
    LABOR = 'labor'
    ADMIN_GENERAL = 'admin_general'
    ADMIN_PATENT = 'admin_patent'
    JURISDICTION_OBJECTION = 'jurisdiction_objection'


CASE_TYPE_LABELS: Dict[CaseType, str] = {
    CaseType.PROPERTY: '财产案件',
    CaseType.DIVORCE: '离婚案件（非财产）',
    CaseType.PERSONALITY: '侵害人格权案件（非财产）',
    CaseType.OTHER_NON_PROPERTY: '其他非财产案件',
    CaseType.IP: '知识产权民事案件',
    CaseType.LABOR: '劳动争议案件',
    CaseType.ADMIN_GENERAL: '行政案件（非商标/专利/海事）',
    CaseType.ADMIN_PATENT: '行政案件（商标/专利/海事）',
    CaseType.JURISDICTION_OBJECTION: '管辖权异议不成立',
}


DEFAULT_BASE_FEES: Dict[CaseType, float] = {
    CaseType.DIVORCE: 175.0,
    CaseType.PERSONALITY: 300.0,
    CaseType.OTHER_NON_PROPERTY: 75.0,
    CaseType.IP: 750.0,
    CaseType.JURISDICTION_OBJECTION: 75.0,
}


LEGAL_FEE_RANGES: Dict[CaseType, str] = {
    CaseType.DIVORCE: '每件 50 ~ 300 元（默认取中值175元）',
    CaseType.PERSONALITY: '每件 100 ~ 500 元（默认取中值300元）',
    CaseType.OTHER_NON_PROPERTY: '每件 50 ~ 100 元（默认取中值75元）',
    CaseType.IP: '无争议金额时每件 500 ~ 1000 元（默认取中值750元）',
    CaseType.JURISDICTION_OBJECTION: '每件 50 ~ 100 元（默认取中值75元）',
}


def _calculate_property_brackets(amount_yuan: float) -> Tuple[float, List[Dict[str, Any]]]:
    breakdown: List[Dict[str, Any]] = []
    if amount_yuan <= 0:
        return 0.0, []

    if amount_yuan <= 10000.0:
        breakdown.append({
            'range': '不超过1万元',
            'base': 0.0,
            'upper': amount_yuan,
            'rate': '50元/件',
            'portion': PROPERTY_FIRST_BRACKET_FIXED,
        })
        return PROPERTY_FIRST_BRACKET_FIXED, breakdown

    total = 0.0
    breakdown.append({
        'range': '不超过1万元',
        'base': 0.0,
        'upper': 10000.0,
        'rate': '50元/件',
        'portion': PROPERTY_FIRST_BRACKET_FIXED,
    })
    total += PROPERTY_FIRST_BRACKET_FIXED

    prev_wan = 1.0
    for i in range(1, len(PROPERTY_BRACKETS)):
        upper_wan, rate = PROPERTY_BRACKETS[i]
        upper_y = upper_wan * 10000.0
        prev_y = prev_wan * 10000.0
        if amount_yuan <= prev_y:
            break
        base_y = prev_y
        cap_y = min(amount_yuan, upper_y)
        taxable = cap_y - base_y
        portion = taxable * rate
        total += portion
        range_desc = (
            f'超过{prev_wan:.0f}万元至{upper_wan:.0f}万元'
            if upper_wan != float('inf')
            else f'超过{prev_wan:.0f}万元'
        )
        breakdown.append({
            'range': range_desc,
            'base': base_y,
            'upper': cap_y,
            'rate': f'{rate * 100:.1f}%',
            'portion': portion,
        })
        prev_wan = upper_wan
        if amount_yuan <= upper_y:
            break
    return total, breakdown


def _validate_non_negative(value: Optional[float], name: str) -> None:
    if value is not None and value < 0:
        raise ValueError(f'{name}不能为负数')


def calculate_lawsuit_fee(
    amount_in_wan: float = 0.0,
    case_type: CaseType = CaseType.PROPERTY,
    *,
    divorce_property_wan: Optional[float] = None,
    personality_damage_wan: Optional[float] = None,
    ip_has_disputed_amount: bool = False,
    base_fee: Optional[float] = None,
) -> Dict[str, Any]:
    _validate_non_negative(amount_in_wan, '标的额')
    _validate_non_negative(divorce_property_wan, '离婚财产分割总额')
    _validate_non_negative(personality_damage_wan, '人格权损害赔偿额')
    _validate_non_negative(base_fee, '基础费')

    if amount_in_wan is None:
        amount_in_wan = 0.0

    result: Dict[str, Any] = {
        'case_type': case_type.value,
        'case_type_label': CASE_TYPE_LABELS[case_type],
        'amount_wan': amount_in_wan,
        'fee_yuan': 0.0,
        'fee_wan': 0.0,
        'breakdown': [],
        'notes': [],
    }

    if case_type == CaseType.PROPERTY:
        amount_yuan = amount_in_wan * 10000.0
        if amount_yuan <= 0:
            result['breakdown'] = []
            return result
        total, breakdown = _calculate_property_brackets(amount_yuan)
        result['fee_yuan'] = round(total, 2)
        result['fee_wan'] = round(total / 10000.0, 6)
        result['breakdown'] = breakdown
        return result

    if case_type == CaseType.LABOR:
        result['fee_yuan'] = 10.0
        result['fee_wan'] = 0.001
        result['breakdown'] = [{
            'range': '劳动争议案件',
            'base': 0.0,
            'upper': 0.0,
            'rate': '10元/件',
            'portion': 10.0,
        }]
        return result

    if case_type == CaseType.ADMIN_GENERAL:
        result['fee_yuan'] = 50.0
        result['fee_wan'] = 0.005
        result['breakdown'] = [{
            'range': '除商标/专利/海事外的其他行政案件',
            'base': 0.0,
            'upper': 0.0,
            'rate': '50元/件',
            'portion': 50.0,
        }]
        return result

    if case_type == CaseType.ADMIN_PATENT:
        result['fee_yuan'] = 100.0
        result['fee_wan'] = 0.01
        result['breakdown'] = [{
            'range': '商标/专利/海事行政案件',
            'base': 0.0,
            'upper': 0.0,
            'rate': '100元/件',
            'portion': 100.0,
        }]
        return result

    if case_type == CaseType.OTHER_NON_PROPERTY:
        fee = base_fee if base_fee is not None else DEFAULT_BASE_FEES[CaseType.OTHER_NON_PROPERTY]
        result['fee_yuan'] = fee
        result['fee_wan'] = round(fee / 10000.0, 6)
        result['breakdown'] = [{
            'range': '其他非财产案件',
            'base': 0.0,
            'upper': 0.0,
            'rate': f'{fee:.2f}元/件（区间50-100元）',
            'portion': fee,
        }]
        result['notes'].append(LEGAL_FEE_RANGES[CaseType.OTHER_NON_PROPERTY])
        return result

    if case_type == CaseType.JURISDICTION_OBJECTION:
        fee = base_fee if base_fee is not None else DEFAULT_BASE_FEES[CaseType.JURISDICTION_OBJECTION]
        result['fee_yuan'] = fee
        result['fee_wan'] = round(fee / 10000.0, 6)
        result['breakdown'] = [{
            'range': '管辖权异议不成立',
            'base': 0.0,
            'upper': 0.0,
            'rate': f'{fee:.2f}元/件（区间50-100元）',
            'portion': fee,
        }]
        result['notes'].append(LEGAL_FEE_RANGES[CaseType.JURISDICTION_OBJECTION])
        return result

    if case_type == CaseType.IP:
        if ip_has_disputed_amount:
            amount_yuan = amount_in_wan * 10000.0
            if amount_yuan <= 0:
                raise ValueError('知识产权案件有争议金额时，标的额必须为正数')
            total, breakdown = _calculate_property_brackets(amount_yuan)
            result['fee_yuan'] = round(total, 2)
            result['fee_wan'] = round(total / 10000.0, 6)
            result['breakdown'] = breakdown
            result['notes'].append('知识产权案件有争议金额，按财产案件标准计算')
            return result
        fee = base_fee if base_fee is not None else DEFAULT_BASE_FEES[CaseType.IP]
        result['fee_yuan'] = fee
        result['fee_wan'] = round(fee / 10000.0, 6)
        result['breakdown'] = [{
            'range': '知识产权民事案件（无争议金额）',
            'base': 0.0,
            'upper': 0.0,
            'rate': f'{fee:.2f}元/件（区间500-1000元）',
            'portion': fee,
        }]
        result['notes'].append(LEGAL_FEE_RANGES[CaseType.IP])
        return result

    if case_type == CaseType.DIVORCE:
        base_fee_value = (
            base_fee if base_fee is not None else DEFAULT_BASE_FEES[CaseType.DIVORCE]
        )
        result['breakdown'].append({
            'range': '离婚案件基础费',
            'base': 0.0,
            'upper': 0.0,
            'rate': f'{base_fee_value:.2f}元/件（区间50-300元）',
            'portion': base_fee_value,
        })
        total = base_fee_value
        if divorce_property_wan is not None and divorce_property_wan > 0:
            property_yuan = divorce_property_wan * 10000.0
            threshold = 200000.0
            if property_yuan > threshold:
                taxable = property_yuan - threshold
                portion = taxable * 0.005
                total += portion
                result['breakdown'].append({
                    'range': '财产分割超过20万元部分',
                    'base': threshold,
                    'upper': property_yuan,
                    'rate': '0.5%',
                    'portion': portion,
                })
                result['notes'].append('财产总额不超过20万元不另行交纳，超过部分按0.5%计收')
            else:
                result['notes'].append(
                    f'涉及财产分割总额{divorce_property_wan:.4f}万元，未超过20万元，不另行交纳'
                )
        result['notes'].append(LEGAL_FEE_RANGES[CaseType.DIVORCE])
        result['fee_yuan'] = round(total, 2)
        result['fee_wan'] = round(total / 10000.0, 6)
        return result

    if case_type == CaseType.PERSONALITY:
        base_fee_value = (
            base_fee if base_fee is not None else DEFAULT_BASE_FEES[CaseType.PERSONALITY]
        )
        result['breakdown'].append({
            'range': '侵害人格权案件基础费',
            'base': 0.0,
            'upper': 0.0,
            'rate': f'{base_fee_value:.2f}元/件（区间100-500元）',
            'portion': base_fee_value,
        })
        total = base_fee_value
        if personality_damage_wan is not None and personality_damage_wan > 0:
            damage_yuan = personality_damage_wan * 10000.0
            threshold_1 = 50000.0
            threshold_2 = 100000.0
            if damage_yuan <= threshold_1:
                result['notes'].append(
                    f'损害赔偿额{personality_damage_wan:.4f}万元，未超过5万元，不另行交纳'
                )
            else:
                if damage_yuan <= threshold_2:
                    taxable = damage_yuan - threshold_1
                    portion = taxable * 0.01
                    total += portion
                    result['breakdown'].append({
                        'range': '损害赔偿超过5万元至10万元部分',
                        'base': threshold_1,
                        'upper': damage_yuan,
                        'rate': '1.0%',
                        'portion': portion,
                    })
                else:
                    taxable1 = threshold_2 - threshold_1
                    portion1 = taxable1 * 0.01
                    total += portion1
                    result['breakdown'].append({
                        'range': '损害赔偿超过5万元至10万元部分',
                        'base': threshold_1,
                        'upper': threshold_2,
                        'rate': '1.0%',
                        'portion': portion1,
                    })
                    taxable2 = damage_yuan - threshold_2
                    portion2 = taxable2 * 0.005
                    total += portion2
                    result['breakdown'].append({
                        'range': '损害赔偿超过10万元部分',
                        'base': threshold_2,
                        'upper': damage_yuan,
                        'rate': '0.5%',
                        'portion': portion2,
                    })
                result['notes'].append(
                    '损害赔偿≤5万元不另行，5万~10万部分按1%，超10万部分按0.5%计收'
                )
        result['notes'].append(LEGAL_FEE_RANGES[CaseType.PERSONALITY])
        result['fee_yuan'] = round(total, 2)
        result['fee_wan'] = round(total / 10000.0, 6)
        return result

    raise ValueError(f'未知案件类型: {case_type}')


def format_result(result: Dict[str, Any]) -> str:
    lines = []
    width = 60
    lines.append('=' * width)
    lines.append(f"案件类型：{result['case_type_label']}")
    if result['amount_wan'] and result['amount_wan'] > 0:
        lines.append(
            f"标的额：{result['amount_wan']:.6f} 万元（{result['amount_wan'] * 10000:.2f} 元）"
        )
    lines.append('-' * width)
    lines.append('计算明细：')
    for idx, item in enumerate(result['breakdown'], 1):
        lines.append(f"  {idx}. 区间：{item['range']}")
        if item['upper'] > 0 or item['base'] > 0:
            lines.append(f"     计算基数：{item['base']:.2f} 元 ~ {item['upper']:.2f} 元")
        lines.append(f"     费率：{item['rate']}")
        lines.append(f"     该段费用：{item['portion']:.2f} 元")
    if result.get('notes'):
        lines.append('-' * width)
        lines.append('说明：')
        for note in result['notes']:
            lines.append(f'  * {note}')
    lines.append('-' * width)
    lines.append(
        f"案件受理费合计：{result['fee_yuan']:.2f} 元（{result['fee_wan']:.6f} 万元）"
    )
    lines.append('=' * width)
    return '\n'.join(lines)


def _print_case_menu() -> None:
    print('请选择案件类型：')
    for idx, ct in enumerate(CaseType, 1):
        label = CASE_TYPE_LABELS[ct]
        print(f'  {idx}. {label}')


def _prompt_float(prompt_text: str, allow_empty: bool = False) -> Optional[float]:
    while True:
        raw = input(prompt_text).strip()
        if allow_empty and not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            print('输入无效，请输入数字。')


def _interactive_property() -> Dict[str, Any]:
    amount = _prompt_float('请输入标的额（万元）：')
    if amount is None:
        amount = 0.0
    return calculate_lawsuit_fee(amount, CaseType.PROPERTY)


def _interactive_divorce() -> Dict[str, Any]:
    base = _prompt_float(
        '请输入离婚案件基础费（默认175元，区间50-300，回车使用默认）：', allow_empty=True
    )
    prop = _prompt_float(
        '请输入财产分割总额（万元，无财产分割请回车）：', allow_empty=True
    )
    return calculate_lawsuit_fee(
        0.0, CaseType.DIVORCE, divorce_property_wan=prop, base_fee=base
    )


def _interactive_personality() -> Dict[str, Any]:
    base = _prompt_float(
        '请输入侵害人格权案件基础费（默认300元，区间100-500，回车使用默认）：',
        allow_empty=True,
    )
    damage = _prompt_float(
        '请输入损害赔偿额（万元，无赔偿请回车）：', allow_empty=True
    )
    return calculate_lawsuit_fee(
        0.0, CaseType.PERSONALITY, personality_damage_wan=damage, base_fee=base
    )


def _interactive_other_non_property() -> Dict[str, Any]:
    base = _prompt_float(
        '请输入基础费（默认75元，区间50-100，回车使用默认）：', allow_empty=True
    )
    return calculate_lawsuit_fee(0.0, CaseType.OTHER_NON_PROPERTY, base_fee=base)


def _interactive_ip() -> Dict[str, Any]:
    while True:
        choice = input('是否有争议金额或价额？(y/n)：').strip().lower()
        if choice in ('y', 'yes'):
            amount = _prompt_float('请输入争议金额（万元）：')
            return calculate_lawsuit_fee(
                amount or 0.0, CaseType.IP, ip_has_disputed_amount=True
            )
        if choice in ('n', 'no'):
            base = _prompt_float(
                '请输入基础费（默认750元，区间500-1000，回车使用默认）：',
                allow_empty=True,
            )
            return calculate_lawsuit_fee(0.0, CaseType.IP, base_fee=base)
        print('请输入 y 或 n。')


def _interactive_admin() -> Dict[str, Any]:
    while True:
        choice = input('是否为商标/专利/海事行政案件？(y/n)：').strip().lower()
        if choice in ('y', 'yes'):
            return calculate_lawsuit_fee(0.0, CaseType.ADMIN_PATENT)
        if choice in ('n', 'no'):
            return calculate_lawsuit_fee(0.0, CaseType.ADMIN_GENERAL)
        print('请输入 y 或 n。')


def _interactive_jurisdiction() -> Dict[str, Any]:
    base = _prompt_float(
        '请输入基础费（默认75元，区间50-100，回车使用默认）：', allow_empty=True
    )
    return calculate_lawsuit_fee(0.0, CaseType.JURISDICTION_OBJECTION, base_fee=base)


INTERACTIVE_HANDLERS = {
    CaseType.PROPERTY: _interactive_property,
    CaseType.DIVORCE: _interactive_divorce,
    CaseType.PERSONALITY: _interactive_personality,
    CaseType.OTHER_NON_PROPERTY: _interactive_other_non_property,
    CaseType.IP: _interactive_ip,
    CaseType.LABOR: lambda: calculate_lawsuit_fee(0.0, CaseType.LABOR),
    CaseType.ADMIN_GENERAL: _interactive_admin,
    CaseType.ADMIN_PATENT: _interactive_admin,
    CaseType.JURISDICTION_OBJECTION: _interactive_jurisdiction,
}


def main() -> None:
    print('=== 诉讼费计算服务（案件受理费）===')
    print('依据：《诉讼费用交纳办法》（国务院令第481号）第十三条')
    print()

    case_types = list(CaseType)
    while True:
        try:
            _print_case_menu()
            raw = input('请输入案件类型编号（输入 q 退出）：').strip()
            if raw.lower() in ('q', 'quit', 'exit'):
                print('再见。')
                break
            if not raw:
                continue
            idx = int(raw) - 1
            if idx < 0 or idx >= len(case_types):
                print('编号超出范围，请重试。')
                continue
            ct = case_types[idx]
            handler = INTERACTIVE_HANDLERS[ct]
            result = handler()
            print()
            print(format_result(result))
            print()
        except ValueError as e:
            print(f'输入错误：{e}')
        except (KeyboardInterrupt, EOFError):
            print('\n再见。')
            break


if __name__ == '__main__':
    main()
