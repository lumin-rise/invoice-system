"""伪造一批贴近真实版式的样例发票，用于端到端测试。

生成到 scripts/samples/：3 张 PDF（滴滴/高铁/火车）+ 1 张 PNG（OCR 路径）。
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

OUT = Path(__file__).parent / "samples"
OUT.mkdir(exist_ok=True)

pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))


def new_pdf(name: str):
    c = canvas.Canvas(str(OUT / name), pagesize=A4)
    return c


def text(c, x, y, s, size=11, font="STSong-Light"):
    c.setFont(font, size)
    c.drawString(x, y, s)


# 1) 滴滴打车电子发票（2026-09-11）
c = new_pdf("didi-0911.pdf")
text(c, 200, 780, "增值税电子普通发票", 16)
text(c, 80, 750, "发票号码: 24412000000123456789")
text(c, 420, 750, "开票日期: 2026年09月11日")
text(c, 80, 725, "购买方名称: 厦门卓奥企业管理有限公司")
text(c, 80, 708, "纳税人识别号: 91350200MA0000000X")
text(c, 80, 680, "销售方名称: 滴滴出行科技有限公司")
text(c, 80, 640, "项目名称")
text(c, 80, 620, "*运输服务*客运服务费    92.79    6%    5.57")
text(c, 80, 595, "合  计  ¥92.79    ¥5.57")
text(c, 80, 570, "价税合计（大写）玖拾捌元叁角陆分  （小写）¥98.36")
text(c, 80, 540, "行程时间 2026-09-11 09:32")
text(c, 80, 520, "起点：晋江住处  终点：厦门利顺添工厂")
text(c, 80, 500, "里程 23.5公里")
c.save()

# 2) 铁路电子客票（高铁，2026-09-12 乘车）
c = new_pdf("rail-0912.pdf")
text(c, 180, 780, "电子发票（铁路电子客票）", 16)
text(c, 80, 750, "发票号码: 22609120000123456789")
text(c, 420, 750, "开票日期: 2026年09月13日")
text(c, 80, 715, "from 泉州南站 to 长汀南站")
text(c, 80, 690, "车次 G1655   2026年09月12日18:23开   05车12F号")
text(c, 80, 665, "票价: ￥126.50元")
text(c, 80, 640, "旅客身份信息: 3505***********1234")
c.save()

# 3) 火车票（K 字头，2026-09-19）
c = new_pdf("train-0919.pdf")
text(c, 180, 780, "电子发票（铁路电子客票）", 16)
text(c, 80, 750, "发票号码: 22609190000987654321")
text(c, 420, 750, "开票日期: 2026年09月19日")
text(c, 80, 715, "发站: 赣州站  到站: 兴国站")
text(c, 80, 690, "车次 K1298  2026年09月19日 07:41开")
text(c, 80, 665, "票价: ￥12.50元")
c.save()

# 3b) 高铁票（赣州站-长沙站，验证 Location「A站到B站」规则）
c = new_pdf("rail-ganzhou-changsha.pdf")
text(c, 180, 780, "电子发票（铁路电子客票）", 16)
text(c, 80, 750, "发票号码: 22609230000112233445")
text(c, 420, 750, "开票日期: 2026年09月23日")
text(c, 80, 715, "赣州站-长沙站")
text(c, 80, 690, "车次 G1956  2026年09月23日14:32开  08车05F号")
text(c, 80, 665, "票价: ￥244.50元")
c.save()


# 4) PNG 图片发票（走 OCR 路径）—— 滴滴 2026-09-22
def find_font(size):
    for cand in (
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
    ):
        try:
            return ImageFont.truetype(cand, size)
        except OSError:
            continue
    raise SystemExit("未找到中文字体")


img = Image.new("RGB", (760, 560), "white")
d = ImageDraw.Draw(img)
f16, f12 = find_font(20), find_font(15)
lines = [
    (200, 20, "增值税电子普通发票", f16),
    (60, 70, "发票号码: 24412000000567890123", f12),
    (420, 70, "开票日期: 2026年09月22日", f12),
    (60, 110, "购买方名称: 厦门卓奥企业管理有限公司", f12),
    (60, 145, "销售方名称: 滴滴出行科技有限公司", f12),
    (60, 190, "项目名称", f12),
    (60, 215, "*运输服务*客运服务费   36.89   6%   2.21", f12),
    (60, 245, "合  计   ¥36.89   ¥2.21", f12),
    (60, 275, "价税合计（大写）叁拾玖元壹角整 （小写）￥39.10", f12),
    (60, 320, "行程时间 2026-09-22 08:15", f12),
    (60, 345, "起点：赣州住处  终点：赣州站", f12),
    (60, 370, "里程 8.2公里", f12),
]
for x, y, s, f in lines:
    d.text((x, y), s, fill="black", font=f)
img.save(OUT / "didi-0922.png")

print("样例已生成到", OUT)
for p in sorted(OUT.iterdir()):
    print("  -", p.name)
