import base64
import io
import os
import uuid
from datetime import datetime
from enum import Enum
from typing import List, Tuple, Dict, Optional, Any

import qrcode


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


def _generate_payment_no() -> str:
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    suffix = uuid.uuid4().hex[:6].upper()
    return f'FY{timestamp}{suffix}'


def _generate_qr_base64(data: str) -> str:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color='#1a365d', back_color='white')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    img_bytes = buf.getvalue()
    return base64.b64encode(img_bytes).decode('ascii')


def _build_qr_payload(
    payment_no: str,
    fee_yuan: float,
    case_type_label: str,
    amount_wan: float,
) -> str:
    payload = (
        f'诉讼费缴费通知|单号:{payment_no}|'
        f'金额:{fee_yuan:.2f}元|类型:{case_type_label}|'
        f'标的:{amount_wan:.2f}万|'
        f'生成时间:{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
    )
    return payload


def _render_html_notice(
    *,
    payment_no: str,
    case_type_label: str,
    amount_wan: float,
    fee_yuan: float,
    breakdown: List[Dict[str, Any]],
    notes: List[str],
    qr_b64: str,
    payee: str = '当地人民法院诉讼费专户',
    bank: str = '中国工商银行 XX 支行',
    account: str = '1234 5678 9012 3456',
) -> str:
    amount_yuan = amount_wan * 10000.0
    fee_wan = fee_yuan / 10000.0
    now_str = datetime.now().strftime('%Y 年 %m 月 %d 日')
    due_str = datetime.now().strftime('%Y 年 %m 月 %d 日起 7 日内')

    breakdown_rows = ''
    for idx, item in enumerate(breakdown, 1):
        base = f"{item['base']:.2f}" if item['base'] > 0 else '-'
        upper = f"{item['upper']:.2f}" if item['upper'] > 0 else '-'
        breakdown_rows += f'''
        <tr>
            <td style="padding: 8px 12px; border: 1px solid #d1d5db; text-align: center;">{idx}</td>
            <td style="padding: 8px 12px; border: 1px solid #d1d5db; text-align: left;">{item['range']}</td>
            <td style="padding: 8px 12px; border: 1px solid #d1d5db; text-align: center;">{base} ~ {upper}</td>
            <td style="padding: 8px 12px; border: 1px solid #d1d5db; text-align: center;">{item['rate']}</td>
            <td style="padding: 8px 12px; border: 1px solid #d1d5db; text-align: right;">¥ {item['portion']:.2f}</td>
        </tr>'''

    notes_html = ''
    if notes:
        notes_html = '<div style="margin-top: 16px;"><strong style="color: #1f2937;">说明：</strong><ul style="margin: 8px 0 0 20px; padding: 0; color: #374151; font-size: 13px; line-height: 1.6;">'
        for note in notes:
            notes_html += f'<li>{note}</li>'
        notes_html += '</ul></div>'

    amount_display = f'{amount_wan:.2f} 万元（¥ {amount_yuan:.2f} 元）' if amount_wan > 0 else '无'

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>诉讼费缴费通知单 - {payment_no}</title>
<style>
    @page {{ size: A4; margin: 15mm; }}
    body {{
        font-family: "Microsoft YaHei", "SimHei", sans-serif;
        color: #1f2937;
        background: #f9fafb;
        margin: 0;
        padding: 30px 0;
    }}
    .notice {{
        max-width: 800px;
        margin: 0 auto;
        background: #ffffff;
        padding: 40px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.08);
        border-radius: 6px;
    }}
    .header {{
        text-align: center;
        border-bottom: 2px solid #1a365d;
        padding-bottom: 20px;
        margin-bottom: 24px;
    }}
    .header h1 {{
        margin: 0;
        color: #1a365d;
        font-size: 26px;
        letter-spacing: 4px;
    }}
    .header .sub {{
        margin-top: 8px;
        color: #6b7280;
        font-size: 13px;
    }}
    .info-grid {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 12px 24px;
        margin-bottom: 20px;
        font-size: 14px;
    }}
    .info-item {{
        display: flex;
    }}
    .info-item .label {{
        color: #6b7280;
        width: 100px;
        flex-shrink: 0;
    }}
    .info-item .value {{
        color: #111827;
        font-weight: 500;
    }}
    .total-amount {{
        background: linear-gradient(135deg, #1a365d 0%, #2c5282 100%);
        color: #ffffff;
        padding: 20px 24px;
        border-radius: 6px;
        margin: 24px 0;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }}
    .total-amount .label {{
        font-size: 15px;
        opacity: 0.9;
    }}
    .total-amount .value {{
        font-size: 28px;
        font-weight: bold;
        letter-spacing: 1px;
    }}
    .total-amount .value small {{
        font-size: 14px;
        opacity: 0.85;
        margin-left: 8px;
    }}
    table {{
        width: 100%;
        border-collapse: collapse;
        margin-top: 12px;
        font-size: 13px;
    }}
    th {{
        background: #f3f4f6;
        color: #1f2937;
        padding: 10px 12px;
        border: 1px solid #d1d5db;
        text-align: center;
        font-weight: 600;
    }}
    .section-title {{
        font-size: 16px;
        font-weight: 600;
        color: #1a365d;
        margin-top: 24px;
        padding-bottom: 6px;
        border-bottom: 1px solid #e5e7eb;
    }}
    .payment-info {{
        background: #f8fafc;
        border-left: 4px solid #1a365d;
        padding: 16px 20px;
        margin-top: 20px;
        font-size: 13px;
        line-height: 2;
    }}
    .payment-info p {{
        margin: 4px 0;
    }}
    .payment-info strong {{
        color: #1f2937;
        margin-right: 6px;
    }}
    .qr-section {{
        display: flex;
        align-items: center;
        gap: 24px;
        margin-top: 24px;
        padding: 20px;
        background: #f9fafb;
        border-radius: 6px;
        border: 1px dashed #d1d5db;
    }}
    .qr-section .qr-code {{
        width: 140px;
        height: 140px;
        background: #ffffff;
        padding: 8px;
        border: 1px solid #e5e7eb;
        border-radius: 4px;
        flex-shrink: 0;
    }}
    .qr-section .qr-code img {{
        width: 100%;
        height: 100%;
        display: block;
    }}
    .qr-section .qr-desc {{
        flex: 1;
        font-size: 13px;
        line-height: 1.8;
        color: #374151;
    }}
    .qr-section .qr-desc strong {{
        color: #1a365d;
        font-size: 14px;
    }}
    .footer {{
        margin-top: 32px;
        padding-top: 16px;
        border-top: 1px solid #e5e7eb;
        text-align: right;
        color: #6b7280;
        font-size: 12px;
        line-height: 1.8;
    }}
    .footer .stamp-area {{
        margin-top: 12px;
        height: 80px;
        width: 200px;
        margin-left: auto;
        border: 1px dashed #d1d5db;
        display: flex;
        align-items: center;
        justify-content: center;
        color: #9ca3af;
        font-size: 12px;
        border-radius: 4px;
    }}
    .warning {{
        background: #fef3c7;
        border-left: 4px solid #f59e0b;
        padding: 12px 16px;
        margin-top: 20px;
        font-size: 13px;
        color: #92400e;
        border-radius: 4px;
    }}
    @media print {{
        body {{ background: #ffffff; padding: 0; }}
        .notice {{ box-shadow: none; border-radius: 0; }}
    }}
</style>
</head>
<body>
<div class="notice">
    <div class="header">
        <h1>诉 讼 费 缴 费 通 知 单</h1>
        <div class="sub">根据《诉讼费用交纳办法》（国务院令第 481 号）第十三条规定出具</div>
    </div>

    <div class="info-grid">
        <div class="info-item"><span class="label">缴费单号：</span><span class="value">{payment_no}</span></div>
        <div class="info-item"><span class="label">开具日期：</span><span class="value">{now_str}</span></div>
        <div class="info-item"><span class="label">案件类型：</span><span class="value">{case_type_label}</span></div>
        <div class="info-item"><span class="label">缴费期限：</span><span class="value">{due_str}</span></div>
        <div class="info-item" style="grid-column: span 2;"><span class="label">诉讼标的额：</span><span class="value">{amount_display}</span></div>
    </div>

    <div class="total-amount">
        <div class="label">应缴案件受理费合计</div>
        <div class="value">¥ {fee_yuan:.2f}<small>（{fee_wan:.6f} 万元）</small></div>
    </div>

    <div class="section-title">费用分段计算明细</div>
    <table>
        <thead>
            <tr>
                <th style="width: 50px;">序号</th>
                <th>计费区间</th>
                <th style="width: 180px;">计算基数（元）</th>
                <th style="width: 100px;">费率</th>
                <th style="width: 120px;">该段费用</th>
            </tr>
        </thead>
        <tbody>{breakdown_rows}</tbody>
    </table>
    {notes_html}

    <div class="section-title">收款账户信息</div>
    <div class="payment-info">
        <p><strong>收款单位：</strong>{payee}</p>
        <p><strong>开户银行：</strong>{bank}</p>
        <p><strong>银行账号：</strong>{account}</p>
        <p><strong>款项用途：</strong>诉讼费（缴费单号 {payment_no}）</p>
    </div>

    <div class="qr-section">
        <div class="qr-code">
            <img src="data:image/png;base64,{qr_b64}" alt="缴费二维码">
        </div>
        <div class="qr-desc">
            <strong>📱 扫码支付说明</strong><br>
            扫描左侧二维码，核对缴费单号与金额无误后，即可完成在线支付。<br>
            二维码已包含：<span style="color: #1a365d;">单号 {payment_no}、金额 ¥{fee_yuan:.2f}、案件类型 {case_type_label}</span><br>
            支付成功后，请凭银行回单到立案窗口换取财政票据。
        </div>
    </div>

    <div class="warning">
        ⚠️ 重要提示：当事人应当在收到本通知次日起 7 日内交纳诉讼费用。
        逾期不交纳又不提出缓交、减交、免交申请，或者申请未获批准的，
        将按自动撤诉处理。本通知一式两份，当事人签收后一份留存。
    </div>

    <div class="footer">
        <div>开具单位：人民法院立案庭</div>
        <div>经办人：____________  联系电话：12368</div>
        <div class="stamp-area">（法院公章处）</div>
    </div>
</div>
</body>
</html>'''
    return html


def generate_payment_notice(
    fee_result: Dict[str, Any],
    *,
    output_path: Optional[str] = None,
    payee: str = '当地人民法院诉讼费专户',
    bank: str = '中国工商银行 XX 支行',
    account: str = '1234 5678 9012 3456',
) -> Dict[str, Any]:
    if not fee_result or 'fee_yuan' not in fee_result:
        raise ValueError('无效的诉讼费计算结果')

    payment_no = _generate_payment_no()
    fee_yuan = fee_result['fee_yuan']
    case_type_label = fee_result.get('case_type_label', '财产案件')
    amount_wan = fee_result.get('amount_wan', 0.0)
    breakdown = fee_result.get('breakdown', [])
    notes = fee_result.get('notes', [])

    if fee_yuan <= 0:
        raise ValueError('应缴金额为 0，无需生成缴费通知单')

    qr_payload = _build_qr_payload(payment_no, fee_yuan, case_type_label, amount_wan)
    qr_b64 = _generate_qr_base64(qr_payload)

    html = _render_html_notice(
        payment_no=payment_no,
        case_type_label=case_type_label,
        amount_wan=amount_wan,
        fee_yuan=fee_yuan,
        breakdown=breakdown,
        notes=notes,
        qr_b64=qr_b64,
        payee=payee,
        bank=bank,
        account=account,
    )

    notice_info = {
        'payment_no': payment_no,
        'fee_yuan': fee_yuan,
        'case_type_label': case_type_label,
        'amount_wan': amount_wan,
        'qr_payload': qr_payload,
        'html': html,
        'file_path': None,
    }

    if output_path:
        abs_path = os.path.abspath(output_path)
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(html)
        notice_info['file_path'] = abs_path

    return notice_info


def _prompt_save_notice(result: Dict[str, Any]) -> None:
    if result['fee_yuan'] <= 0:
        return
    while True:
        choice = input('是否生成缴费通知单？(y/n)：').strip().lower()
        if choice in ('n', 'no'):
            break
        if choice in ('y', 'yes'):
            default_name = f'payment_notice_{datetime.now().strftime("%Y%m%d_%H%M%S")}.html'
            user_name = input(
                f'请输入保存文件名（默认 {default_name}，回车使用默认）：'
            ).strip()
            file_name = user_name if user_name else default_name
            if not file_name.lower().endswith('.html'):
                file_name += '.html'
            try:
                notice = generate_payment_notice(result, output_path=file_name)
                print()
                print(f'✅ 缴费通知单已生成：{notice["file_path"]}')
                print(f'   缴费单号：{notice["payment_no"]}')
                print(f'   应缴金额：¥ {notice["fee_yuan"]:.2f}')
                print(f'   请在浏览器中打开 HTML 文件查看或打印。')
                print()
                break
            except Exception as e:
                print(f'生成失败：{e}')
                break
        else:
            print('请输入 y 或 n。')


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
            if result['fee_yuan'] > 0:
                _prompt_save_notice(result)
        except ValueError as e:
            print(f'输入错误：{e}')
        except (KeyboardInterrupt, EOFError):
            print('\n再见。')
            break


if __name__ == '__main__':
    main()
