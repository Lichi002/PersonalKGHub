"""一次性：生成 KGHub 桌面图标（知识图谱节点，蓝→靛渐变），多尺寸 .ico。"""
import math
import os

from PIL import Image, ImageDraw

S = 256  # 主画布，缩出多尺寸
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# 渐变色（与门户 logo 一致）：蓝 #3d7fe0 → 靛 #8a63d2
C1, C2 = (61, 127, 224), (138, 99, 210)


def grad_color(t):
    return tuple(round(a + (b - a) * t) for a, b in zip(C1, C2))


# 节点位置（相对 24 网格）：顶(12,5) 左下(5.6,17.6) 右下(18.4,17.6)
top = (S * 12 / 24, S * 5 / 24)
bl = (S * 5.6 / 24, S * 17.6 / 24)
br = (S * 18.4 / 24, S * 17.6 / 24)

# 连线（宽描边，渐变色分段画）
w = max(4, S // 42)
for a, b, t in ((top, bl, 0.3), (top, br, 0.7), (bl, br, 0.5)):
    d.line([a, b], fill=grad_color(t), width=w)

# 节点：顶大实心（渐变），下两空心（深底 + 渐变描边）
r1 = S // 9
for i in range(r1, 0, -1):
    t = i / r1
    d.ellipse([top[0] - i, top[1] - i, top[0] + i, top[1] + i],
              fill=grad_color(0.15 + 0.85 * t))
for c in (bl, br):
    r2 = S // 11
    d.ellipse([c[0] - r2, c[1] - r2, c[0] + r2, c[1] + r2], fill=(255, 255, 255, 255))
    for i in range(int(r2 * 0.55), 0, -1):
        t = i / (r2 * 0.55)
        d.ellipse([c[0] - i, c[1] - i, c[0] + i, c[1] + i],
                  outline=grad_color(0.2 + 0.8 * t), width=max(2, w // 2))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kghub.ico")
img.save(out, format="ICO",
         sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)])
print("saved:", out)
