import math
import tkinter as tk
from pathlib import Path


class FouriaAvatar(tk.Canvas):
    """Rendered Phaser-style avatar with inexpensive procedural animation."""

    def __init__(self, parent, width=146, height=146, **kwargs):
        super().__init__(parent, width=width, height=height, bg="#191923",
                         highlightthickness=0, **kwargs)
        self.w, self.h = width, height
        self.phase = 0.0
        self.frame = 0
        self.state = "idle"
        source = tk.PhotoImage(file=str(Path(__file__).with_name("assets") / "fouria-phaser.png"))
        # Keep the source alive and scale the 1086px art to a light UI sprite.
        self.source = source
        self.sprite = source.subsample(8, 8)
        self.after(33, self.animate)

    def set_state(self, state):
        self.state = state

    def animate(self):
        self.frame += 1
        self.phase += 0.10
        self.draw_avatar()
        self.after(33, self.animate)

    def draw_avatar(self):
        self.delete("all")
        cx, cy = self.w / 2, self.h / 2
        breathe = math.sin(self.phase) * 1.4
        pulse = (math.sin(self.phase * (3 if self.state == "thinking" else 1.7)) + 1) / 2

        for radius, color, width in [
            (65 + pulse * 4, "#312044", 3),
            (58 + pulse * 3, "#6d28d9", 2),
            (52 + pulse * 2, "#d946ef", 1),
        ]:
            self.create_oval(cx-radius, cy-radius, cx+radius, cy+radius,
                             outline=color, width=width)

        self.create_image(cx, cy + 14 + breathe, image=self.sprite)

        # Phaser-like scanline and holographic shimmer overlays.
        shimmer_x = int((self.phase * 22) % (self.w + 35)) - 18
        self.create_polygon(shimmer_x, 5, shimmer_x+12, 5, shimmer_x+45, self.h,
                            shimmer_x+30, self.h, fill="#8b5cf6", stipple="gray50",
                            outline="")
        for y in range(8, self.h, 7):
            self.create_line(7, y, self.w-7, y, fill="#251c31", stipple="gray50")

        if self.state == "speaking":
            energy = 5 + abs(math.sin(self.phase * 5)) * 9
            for i in range(7):
                x = cx - 30 + i * 10
                h = energy * (0.45 + abs(math.sin(self.phase*4+i)))
                self.create_line(x, self.h-7, x, self.h-7-h,
                                 fill="#e879f9", width=3)
        elif self.state == "listening":
            self.create_arc(7, 7, self.w-7, self.h-7, start=self.frame*5 % 360,
                            extent=75, style="arc", outline="#67e8f9", width=3)
        elif self.state == "thinking":
            for i in range(3):
                angle = self.phase * (1+i*.25) + i*2.1
                x = cx + math.cos(angle) * 63
                y = cy + math.sin(angle) * 63
                self.create_oval(x-2, y-2, x+2, y+2, fill="#f0abfc", outline="")
