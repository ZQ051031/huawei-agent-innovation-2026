import base64
import html
import subprocess
import tempfile
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
PITCH = ROOT / "ppt"
FONT = "Noto Sans CJK SC"
SLIDES = [
    ("定位 / POSITIONING", "把散落的票据变成可解释的账本", "ClearBooks Agent · 小微财务智能体",
     [("面向个人与小团队", "给独立开发者、店主和服务商一套本地财务工作台：文档进，答案出。"),
      ("不用付费 API", "文字 PDF、TXT、CSV 统一入账，默认离线。原始证据与每笔数字关联。"),
      ("2026 · 西北赛区", "华为开发者大赛 · 智能体创新赛 · OPC 组 ｜ 本地 Demo v1.0")], None),
    ("痛点 / PROBLEM", "不是缺表格，是证据分散", "At month-end, the hard part is matching every number back to a document.",
     [("人工核对", "发票、收据、银行流水格式不同。手工复制金额时，常漏掉日期、币种或来源。"),
      ("重复与漏项", "同笔付款可能出现在不同文件里；报账时很难发现一笔支出被重复算入。"),
      ("对账太晚", "预算与支出分离，异常往往在月底才被发现；只看汇总表无法快速核实原文。")], None),
    ("方案 / SOLUTION", "录入、分析、复核：同一个工作台", "One local workspace, from upload to review.",
     [("01 录入", "上传 PDF、TXT、CSV 或粘贴文本，抽取商户、日期、金额、币种、类别。普通文档可检索，不凭空入账。"),
      ("02 问答", "中英文识别意图、期间、币种及类别，执行账本查询，展示工具轨迹及原文证据。"),
      ("03 复核", "分币种展示现金流和预算。重复项跳过计账；大额或异常支出交给人复核。")], None),
    ("架构 / ARCHITECTURE", "先算清楚，再解释", "Deterministic arithmetic and traceable routing; optional AI only for narrative.",
     [("输入 → 标准化", "Web / CLI → PDF 文本或 CSV/TXT 规则 → 字段校验、分类和整数金额。"),
      ("存储 → 工具", "SQLite 存交易与证据；文件哈希与交易指纹去重。工具负责汇总、预算、排名及异常评估。"),
      ("意图 → 答案", "问题解析 → 调用本地工具 → 结果与证据。可选模型仅接收汇总指标，生成月报备注。")], None),
    ("实录 / LIVE DEMO", "一条问题，三条来源", "2026-11 · synthetic sample ledger",
     [("真实交互截图", "问：11 月办公用品花了多少？答：CNY 430.00，支持核回三条原始来源。"),
      ("多币种和异常", "CNY 净现金流 5,752.00；USD 单列。CNY 3,200.00 设备款高于阈值和历史比较规则。")],
     "clearbooks-dashboard-zh.png"),
    ("预算 / MONTH-END", "让月报说明下一步检查什么", "Budget status, net cash flow and review flags.",
     [("预算差额", "办公用品初始预算 350，支出 430；改为 500 后，报告显示剩余 CNY 70.00。"),
      ("人工复核", "保留金额、币种和证据，不把规则标记当成欺诈结论。输出中文或英文月报。")],
     "clearbooks-report-zh.png"),
    ("码道 / CODEARTS PLAN", "码道应用与价值：用真实记录证明", "Evidence pending · This build has no captured CodeArts development records.",
     [("生成 / GENERATE", "用码道完善中英票据提取及测试；保留有效 Prompt、关键对话、修改前后 diff。"),
      ("重构 / REFACTOR", "将重复判断和对账规则转成可验证的模块；复核建议并说明取舍。"),
      ("排错 / DEBUG", "记录 PDF 或预算边界失败 → 调试 → 通过的过程，关联真实 commit、日志与测试。此页待参赛者补实证。")], None),
    ("商业价值 / BUSINESS", "为 OPC 留出更有价值的时间", "Target: solo operators and small service teams; not a replacement for accounting.",
     [("价值假设", "少做重复录入；更早定位超支；减少对账时寻找证据的切换。用实测工时和纠错率验证，不预报收益。"),
      ("落地路径", "用离线开源版降低试用阻力；先验证独立开发者与工作室的真实月结流程，再探索部署支持和模板服务。"),
      ("衡量指标", "验证每组票据的输入到复核时间、提取准确率、误判去重比例及首次使用完成率。")], None),
    ("路线图 / ROADMAP", "下一步，优先提升可核对性", "Reproducible today: local UI, CLI, sample data and automated tests.",
     [("现在 · v1.0", "本地导入、查询、预算与月报。交付 Web / CLI、样例与自动化测试。"),
      ("下一阶段", "增加可编辑交易与导出、更多票据模板；用代表性语料衡量抽取准确率。"),
      ("后续", "探索可选离线 OCR、加密存储与可审计多人交接；不改变默认离线体验。")], None),
]


def color(value):
    return RGBColor.from_string(value)


def text(slide, x, y, w, h, value, size, tone="122E26", bold=False):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = value
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color(tone)
    ea = OxmlElement("a:ea")
    ea.set("typeface", FONT)
    run._r.get_or_add_rPr().append(ea)


def build_pptx():
    deck = Presentation()
    deck.slide_width = Inches(13.3333)
    deck.slide_height = Inches(7.5)
    deck.core_properties.title = "ClearBooks Agent · 小微财务智能体"
    deck.core_properties.subject = "2026 Huawei Developer Competition · Northwest · OPC"
    for index, (tag, title, subtitle, blocks, screenshot) in enumerate(SLIDES, 1):
        slide = deck.slides.add_slide(deck.slide_layouts[6])
        dark = index == 1
        fill = slide.background.fill
        fill.solid()
        fill.fore_color.rgb = color("123830" if dark else "F3F7F1")
        ink, soft, accent = ("FFFFFF", "D3E2D8", "B5EEBF") if dark else ("122E26", "436258", "14664F")
        text(slide, .62, .40, 12, .28, tag, 13, accent, True)
        text(slide, .62, .91, 12, .75, title, 33, ink, True)
        text(slide, .62, 1.78, 12, .44, subtitle, 15, soft)
        for number, (heading, body) in enumerate(blocks):
            x = .62 if screenshot else .62 + number * 4.08
            y = 2.59 + (1.76 * number if screenshot else 0)
            w, h = (5.6, 1.54) if screenshot else (3.91, 3.85)
            card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
            card.fill.solid()
            card.fill.fore_color.rgb = color("1A463C" if dark else "FFFFFF")
            card.line.fill.background()
            text(slide, x + .24, y + .25, w - .48, .45, heading, 17, accent, True)
            text(slide, x + .24, y + .80, w - .48, h - .9, body, 13 if screenshot else 17, ink)
        if screenshot:
            slide.shapes.add_picture(str(ROOT / "docs" / screenshot), Inches(7.0), Inches(2.30), height=Inches(4.4))
        text(slide, .62, 7.10, 12, .25, f"CLEARBOOKS AGENT  /  OPC  /  NORTHWEST     ·     {index:02}/{len(SLIDES):02}", 9, soft)
    deck.save(PITCH / "ClearBooks-Agent.pptx")


STYLE = """
@page{size:13.3333in 7.5in;margin:0}
*{box-sizing:border-box}body{margin:0;font-family:"Noto Sans CJK SC",sans-serif;color:#122e26}
section{position:relative;width:13.3333in;height:7.5in;padding:.4in .62in;background:#f3f7f1;break-after:page;overflow:hidden}
section:last-child{break-after:auto}
.dark{background:#123830;color:#fff}
.tag{font-size:13pt;font-weight:bold;color:#14664f;letter-spacing:.05em}
.dark .tag,.dark h2{color:#b5eebf}
h1{margin:.21in 0 .10in;font-size:33pt;font-weight:800}
.subtitle{margin:0;color:#436258;font-size:15pt}
.dark .subtitle,.dark footer{color:#d3e2d8}
.cards{display:flex;gap:.17in;position:absolute;top:2.59in;left:.62in}
article{width:3.91in;height:3.85in;padding:.25in .24in;background:white;border-radius:.2in}
.dark article{background:#1a463c}
.with-image{display:block}
.with-image article{width:5.6in;height:1.54in;margin-bottom:.22in}
h2{font-size:17pt;color:#14664f;margin:0 0 .16in}
article p{font-size:17pt;line-height:1.55;margin:0}
.with-image p{font-size:13pt;line-height:1.45}
img{position:absolute;left:7in;top:2.30in;height:4.4in;border:.01in solid #d9e5dc;border-radius:.08in}
footer{position:absolute;bottom:.23in;font-size:9pt;color:#436258;letter-spacing:.05em}
"""


def build_pdf():
    e = html.escape
    pages = []
    for number, (tag, title, subtitle, blocks, screenshot) in enumerate(SLIDES, 1):
        cards = "".join(f"<article><h2>{e(heading)}</h2><p>{e(body)}</p></article>" for heading, body in blocks)
        image = ""
        if screenshot:
            encoded = base64.b64encode((ROOT / "docs" / screenshot).read_bytes()).decode()
            image = f'<img src="data:image/png;base64,{encoded}" alt="ClearBooks browser screenshot">'
        pages.append(f'<section class="{"dark" if number == 1 else ""}"><div class="tag">{e(tag)}</div>'
                     f'<h1>{e(title)}</h1><p class="subtitle">{e(subtitle)}</p>'
                     f'<div class="cards {"with-image" if image else ""}">{cards}</div>{image}'
                     f'<footer>CLEARBOOKS AGENT / OPC / NORTHWEST · {number:02}/{len(SLIDES):02}</footer></section>')
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        source = folder / "pitch.html"
        source.write_text('<!doctype html><html lang="zh-CN"><meta charset="UTF-8">'
                          f'<title>ClearBooks Agent · 小微财务智能体</title><style>{STYLE}</style>{"".join(pages)}', encoding="utf-8")
        subprocess.run(["google-chrome", "--headless=new", "--no-sandbox", "--no-pdf-header-footer",
                        f"--user-data-dir={folder / 'chrome'}", f"--print-to-pdf={PITCH / 'ClearBooks-Agent.pdf'}",
                        source.as_uri()], check=True)


if __name__ == "__main__":
    build_pptx()
    build_pdf()
