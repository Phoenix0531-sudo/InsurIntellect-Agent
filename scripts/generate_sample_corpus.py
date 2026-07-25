#!/usr/bin/env python3
"""Generate public fake insurance-clause PDFs for local demo (not real policies)."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

try:
    import fitz  # PyMuPDF
except Exception as e:  # pragma: no cover
    raise SystemExit(f"PyMuPDF required: {e}")


ROOT = Path(__file__).resolve().parents[1]
SAMPLES_DIR = ROOT / "samples"
PDF_DIR = ROOT / "data" / "documents" / "pdfs"

TERM_PAGES = [
    (
        "示例终身寿险条款（演示假数据）",
        [
            "文档名称：示例终身寿险条款（演示假数据）",
            "产品名称：安康示例终身寿险",
            "文档类型：保险条款",
            "生效日期：2024-01-01",
            "状态：演示样本，非真实保单，不构成任何保险合同。",
            "",
            "第一条 合同构成",
            "本保险合同由保险单、条款、投保单及与合同有关的其他文件构成。",
            "本合同仅为作品集检索演示使用，所有数字与条款均为虚构。",
        ],
    ),
    (
        "等待期与犹豫期",
        [
            "第二条 等待期",
            "自本合同生效之日起，被保险人因疾病导致的保险事故，等待期为 90 天。",
            "因意外伤害导致的保险事故，无等待期。",
            "等待期内发生保险事故的，保险公司不承担给付保险金的责任，但无息退还已交保险费。",
            "",
            "第三条 犹豫期",
            "自投保人签收本合同之日起，有 15 日的犹豫期。",
            "在犹豫期内，投保人可以书面通知解除本合同，保险公司将无息退还投保人已交的保险费。",
        ],
    ),
    (
        "保险责任与免赔额",
        [
            "第四条 保险责任",
            "在本合同有效期内，被保险人身故或全残的，保险公司按基本保险金额给付保险金，本合同终止。",
            "基本保险金额以保险单载明为准（演示样本中示例为人民币 500,000 元）。",
            "",
            "第五条 免赔额",
            "本合同约定的年免赔额为人民币 10,000 元。",
            "对于同一保险年度内累计合理医疗费用，保险公司仅对超过免赔额的部分按约定比例给付。",
        ],
    ),
    (
        "责任免除",
        [
            "第六条 责任免除",
            "因下列情形之一导致被保险人身故或全残的，保险公司不承担给付保险金的责任：",
            "（一）投保人对被保险人的故意杀害、故意伤害；",
            "（二）被保险人故意犯罪或者抗拒依法采取的刑事强制措施；",
            "（三）被保险人自本合同成立或者合同效力恢复之日起 2 年内自杀，但被保险人自杀时为无民事行为能力人的除外；",
            "（四）被保险人酒后驾驶、无合法有效驾驶证驾驶，或驾驶无合法有效行驶证的机动车；",
            "（五）战争、军事冲突、暴乱或武装叛乱；",
            "（六）核爆炸、核辐射或核污染。",
            "发生上述情形的，本合同终止；投保人已交足 2 年以上保险费的，保险公司退还本合同的现金价值。",
        ],
    ),
    (
        "理赔与边界说明",
        [
            "第七条 保险金申请",
            "申请人申请保险金时，应提供保险合同、身份证明、保险事故证明及保险公司要求的其他材料。",
            "保险公司在收到完整申请材料后，将在约定时间内作出核定。",
            "",
            "第八条 重要提示（演示）",
            "本系统基于已入库条款片段进行检索与引用，不构成保险销售、核保、理赔承诺或任何受监管建议。",
            "是否购买保险、能否获赔取决于真实合同、健康告知、核保结论与事故事实，演示语料不能替代正式条款。",
        ],
    ),
]

HEALTH_PAGES = [
    (
        "示例重大疾病保险条款（演示假数据）",
        [
            "文档名称：示例重大疾病保险条款（演示假数据）",
            "产品名称：安康示例重大疾病保险",
            "文档类型：保险条款",
            "生效日期：2024-06-01",
            "状态：演示样本，非真实保单。",
        ],
    ),
    (
        "重疾等待期",
        [
            "第一条 等待期",
            "本合同自生效之日起，重大疾病保险金的等待期为 180 天。",
            "被保险人因意外伤害导致确诊本合同约定重大疾病的，无等待期。",
            "等待期内确诊本合同约定重大疾病的，保险公司不承担给付保险金责任，无息退还已交保险费，本合同终止。",
        ],
    ),
    (
        "重疾责任免除摘要",
        [
            "第二条 责任免除摘要",
            "因下列情形导致被保险人确诊重大疾病的，保险公司不承担保险责任：",
            "（一）被保险人故意自伤或自杀（无民事行为能力人除外）；",
            "（二）被保险人酒后驾驶；",
            "（三）遗传性疾病、先天性畸形、变形或染色体异常（条款另有约定的除外）；",
            "（四）感染艾滋病病毒或患艾滋病（条款另有约定的除外）。",
            "",
            "第三条 犹豫期",
            "投保人签收本合同后 15 日内为犹豫期，犹豫期内解除合同可无息退还已交保险费。",
        ],
    ),
]


def _write_pdf(path: Path, pages: list[tuple[str, list[str]]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    for title, lines in pages:
        page = doc.new_page(width=595, height=842)  # A4
        y = 56
        page.insert_text((56, y), title, fontsize=14, fontname="china-s")
        y += 28
        for line in lines:
            # wrap long lines roughly
            text = line
            while text:
                chunk = text[:42]
                page.insert_text((56, y), chunk, fontsize=11, fontname="china-s")
                text = text[42:]
                y += 18
                if y > 800:
                    page = doc.new_page(width=595, height=842)
                    y = 56
            y += 4
    doc.save(path)
    doc.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate demo insurance clause PDFs")
    parser.add_argument(
        "--copy-to-data",
        action="store_true",
        help="Also copy generated PDFs into data/documents/pdfs",
    )
    args = parser.parse_args()

    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    term_path = SAMPLES_DIR / "sample_term_life.pdf"
    health_path = SAMPLES_DIR / "sample_critical_illness.pdf"
    _write_pdf(term_path, TERM_PAGES)
    _write_pdf(health_path, HEALTH_PAGES)
    print(f"generated {term_path}")
    print(f"generated {health_path}")

    if args.copy_to_data:
        PDF_DIR.mkdir(parents=True, exist_ok=True)
        for src in (term_path, health_path):
            dst = PDF_DIR / src.name
            shutil.copy2(src, dst)
            print(f"copied {dst}")


if __name__ == "__main__":
    main()
