import asyncio
import math
import os
import colorsys
import random
import tempfile
import uuid

import aiohttp

from PIL import (
    Image,
    ImageDraw,
    ImageEnhance,
    ImageFilter,
    ImageFont,
    ImageOps,
)

from ArchonMusic import config
from ArchonMusic.helpers import Track


def _write_bytes(path: str, data: bytes) -> None:
    """Plain blocking file write, meant to be run via asyncio.to_thread
    so callers never block the event loop on disk I/O."""
    with open(path, "wb") as fw:
        fw.write(data)


FINAL_SIZE = (1920, 1080)
CANVAS_SIZE = FINAL_SIZE
W, H = CANVAS_SIZE

# All layout constants below were hand-tuned against a 1280x720 mock of
# the reference screenshot (poster card on the left, "Now Playing"
# style transport controls on the right). RATIO rescales them
# proportionally so the same layout holds at any FINAL_SIZE.
_BASE_W = 1280
RATIO = FINAL_SIZE[0] / _BASE_W


def S(v):
    """Scale a size / coordinate / tuple (designed at 1280x720) to the
    current FINAL_SIZE. Rounded to int since PIL requires integers."""
    if isinstance(v, (tuple, list)):
        return tuple(S(x) for x in v)
    return int(round(v * RATIO))


# --- Left poster card: cover art fills a tall rounded card, text is
#     overlaid on top of it (title/artist/credits), matching the
#     reference share-card's left half. ---
CARD_BOX = S((90, 90, 610, 610))
CARD_RADIUS = S(24)

# --- Right "now playing" panel: title/artist, seek bar, time row with
#     a bot-name pill, transport controls, volume bar and a bottom
#     icon row — matching the reference share-card's right half. ---
RIGHT_X = S(716)          # left edge for title / subtitle / seek bar / left time
RIGHT_X_END = S(1200)     # right edge for seek bar / volume bar / right time
RIGHT_MAX_W = RIGHT_X_END - RIGHT_X

TITLE_Y = S(149)
SUBTITLE_Y = S(211)

TOP_ICON_Y = S(168)
TOP_ICON_R = S(24)
STAR_ICON_X = S(1109)
DOTS_ICON_X = S(1181)

SEEK_Y = S(274)
SEEK_THUMB_R = S(9)

TIME_Y = S(314)
PILL_CX = S(952)
PILL_H = S(34)

CONTROLS_Y = S(434)
REWIND_X = S(791)
PLAY_CX = S(952)
PLAY_R = S(54)
FORWARD_X = S(1116)

VOLUME_Y = S(553)
VOL_SPEAKER_LOW_X = S(731)
VOL_BAR_X0 = S(766)
VOL_BAR_X1 = S(1138)
VOL_SPEAKER_HIGH_X = S(1172)
VOL_FRACTION = 0.72

BOTTOM_ICON_Y = S(635)
BOTTOM_ICON1_X = S(774)   # captions / quote
BOTTOM_ICON3_X = S(1131)  # queue / list


# --- Palette ---
COL_WHITE = (255, 255, 255)
COL_TITLE = (255, 255, 255)
COL_SUBTITLE = (222, 222, 222)
COL_MUTED = (185, 185, 185)
GOLD = (224, 176, 92)
TRACK_BG = (255, 255, 255, 80)
ACCENT_FALLBACK = (224, 176, 92)


class Thumbnail:
    def __init__(self):
        base = "ArchonMusic/helpers"
        self.title_font_path = f"{base}/Poppins-ExtraBold.ttf"
        self.subtitle_font_path = f"{base}/Raleway-Bold.ttf"
        self.font_subtitle = ImageFont.truetype(self.subtitle_font_path, S(24))
        self.font_time = ImageFont.truetype(self.subtitle_font_path, S(20))
        self.font_pill = ImageFont.truetype(self.subtitle_font_path, S(17))
        # Cache for apply_grain()'s noise layer — deterministic and
        # canvas-size-dependent, computed once and reused.
        self._grain_cache_key = None
        self._grain_alpha_cache = None

    # ---------- generic helpers ----------

    async def save_thumb(self, output_path: str, url: str) -> str:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.read()
            # File writes are blocking syscalls; offload so the event
            # loop (and every other chat's playback/commands) never
            # stalls on disk I/O.
            await asyncio.to_thread(_write_bytes, output_path, data)
            return output_path

    def load_avatar(self, source):
        """Opens `source` (a local file path or a PIL Image) as a plain
        RGB image. Returns None on any failure so callers can fall back
        to the track's cover art instead."""
        try:
            img = source if isinstance(source, Image.Image) else Image.open(source)
            return img.convert("RGB")
        except Exception:
            return None

    async def fetch_avatar(self, url, tmp_path):
        """Downloads a profile-photo URL and returns it as a plain
        image, or None if the download/decode fails.

        Sends a browser-like User-Agent because hosts like graph.org /
        telegra.ph reject bare aiohttp requests with a 403 or an HTML
        error page instead of the image.
        """
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url, allow_redirects=True) as resp:
                    resp.raise_for_status()
                    content_type = resp.headers.get("Content-Type", "")
                    data = await resp.read()
                    if "image" not in content_type and not data[:4] in (
                        b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1", b"\x89PNG",
                    ):
                        print(f"[fetch_avatar] URL did not return an image "
                              f"(content-type={content_type!r}): {url}")
                        return None
                    await asyncio.to_thread(_write_bytes, tmp_path, data)
            return await asyncio.to_thread(self.load_avatar, tmp_path)
        except Exception as e:
            print(f"[fetch_avatar] failed for {url}: {e!r}")
            return None

    def fit_image(self, image, size):
        return ImageOps.fit(
            image, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5)
        )

    def add_round_corners(self, image, radius):
        rounded = image.convert("RGBA")
        w, h = rounded.size
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, w, h), radius=radius, fill=255)
        output = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        output.paste(rounded, (0, 0), mask)
        return output

    def fit_title_font(self, draw, text, max_width, base_size, min_size):
        size = base_size
        while size > min_size:
            font = ImageFont.truetype(self.title_font_path, size)
            bbox = draw.textbbox((0, 0), text, font=font)
            if bbox[2] - bbox[0] <= max_width:
                return font
            size -= 2
        return ImageFont.truetype(self.title_font_path, min_size)

    def fit_title_text_and_font(self, draw, text, max_width, base_size, min_size):
        """Like fit_title_font, but if the text is still wider than
        max_width even at min_size (a long title with no more room to
        shrink), progressively shortens the text with an ellipsis
        instead of letting it overflow past neighboring UI elements."""
        font = self.fit_title_font(draw, text, max_width, base_size, min_size)
        bbox = draw.textbbox((0, 0), text, font=font)
        while bbox[2] - bbox[0] > max_width and len(text) > 8:
            text = text[:-4].rstrip() + "..."
            bbox = draw.textbbox((0, 0), text, font=font)
        return text, font

    def truncate(self, text: str, limit: int) -> str:
        text = text or ""
        return text[: limit - 3] + "..." if len(text) > limit else text

    @staticmethod
    def _format_time(seconds):
        if seconds is None or seconds < 0:
            return None
        seconds = int(seconds)
        m, s = divmod(seconds, 60)
        return f"{m}:{s:02d}"

    def accent_from_cover(self, cover_img):
        """Pulls a vivid, legible accent color out of the cover art so
        the ambient glow behind the poster card feels designed around
        the track instead of a fixed generic color."""
        small = cover_img.convert("RGB").resize((60, 60))
        quant = small.quantize(colors=6, method=Image.MEDIANCUT)
        palette = quant.getpalette()[: 6 * 3]
        counts = sorted(quant.getcolors() or [], key=lambda c: -c[0])

        if counts:
            _, idx = counts[0]
            r, g, b = palette[idx * 3: idx * 3 + 3]
        else:
            r, g, b = ACCENT_FALLBACK

        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        s = min(max(s, 0.6), 0.92)
        v = min(max(v, 0.6), 0.88)
        rr, gg, bb = colorsys.hsv_to_rgb(h, s, v)
        return (int(rr * 255), int(gg * 255), int(bb * 255))

    # ---------- background ----------

    def build_background(self, cover_img):
        """Full-screen backdrop built from the cover art itself: zoomed
        and cropped to fill the canvas, then softly blurred and
        darkened so the poster card and the transport controls read
        clearly on top of it — matching the blurred "now playing"
        backdrop in the reference screenshot."""
        cover_rgb = cover_img.convert("RGB")

        zoom = 1.25
        big_size = (int(W * zoom), int(H * zoom))
        zoomed = ImageOps.fit(
            cover_rgb, big_size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5)
        )
        left = (big_size[0] - W) // 2
        top = (big_size[1] - H) // 2
        bg_cropped = zoomed.crop((left, top, left + W, top + H))
        zoomed.close()
        cover_rgb.close()

        tiny_w, tiny_h = max(1, W // 5), max(1, H // 5)
        tiny = bg_cropped.resize((tiny_w, tiny_h), Image.Resampling.BILINEAR)
        bg_cropped.close()
        bg_resized = tiny.resize(CANVAS_SIZE, Image.Resampling.BILINEAR)
        tiny.close()
        bg_blurred = bg_resized.filter(ImageFilter.GaussianBlur(S(20)))
        bg_resized.close()

        bg_colored = ImageEnhance.Color(bg_blurred).enhance(1.10)
        bg_blurred.close()
        bg_contrasted = ImageEnhance.Contrast(bg_colored).enhance(1.02)
        bg_colored.close()
        bg_brightened = ImageEnhance.Brightness(bg_contrasted).enhance(0.85)
        bg_contrasted.close()
        bg = bg_brightened.convert("RGBA")
        bg_brightened.close()

        # Subtle dark vignette toward the edges — downscale/blur/upscale
        # trick to keep this cheap on a full HD canvas.
        ds = 4
        small_canvas = (max(1, W // ds), max(1, H // ds))
        vignette = Image.new("L", small_canvas, 0)
        vd = ImageDraw.Draw(vignette)
        vd.ellipse(
            (-W * 0.15 / ds, -H * 0.15 / ds, W * 1.15 / ds, H * 1.15 / ds), fill=255
        )
        vignette_blurred = vignette.filter(ImageFilter.GaussianBlur(max(1, S(140) // ds)))
        vignette.close()
        vignette_resized = vignette_blurred.resize(CANVAS_SIZE, Image.Resampling.BILINEAR)
        vignette_blurred.close()
        dark = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 170))
        vign_mask = ImageOps.invert(vignette_resized)
        vignette_resized.close()
        dark.putalpha(vign_mask.point(lambda p: int(p * 0.30)))
        vign_mask.close()
        bg.alpha_composite(dark)
        dark.close()

        # Extra soft scrim over the right-hand "now playing" panel area
        # only, fading in from the poster card's edge — keeps title,
        # controls and icons legible and visually consistent no matter
        # how bright or busy the source artwork is at that spot.
        scrim = Image.new("L", (W, 1), 0)
        scrim_start = CARD_BOX[2]
        for xx in range(W):
            if xx < scrim_start:
                a = 0
            else:
                a = int(60 * min(1.0, (xx - scrim_start) / S(120)))
            scrim.putpixel((xx, 0), a)
        scrim = scrim.resize((W, H))
        scrim_layer = Image.new("RGBA", CANVAS_SIZE, (5, 5, 8, 255))
        scrim_layer.putalpha(scrim)
        bg.alpha_composite(scrim_layer)
        scrim_layer.close()

        return bg

    def draw_card_ambient_glow(self, canvas, accent):
        """Soft colored glow bleeding out from behind the poster card,
        tinted with the track's accent color. Kept tight to the card
        itself (small radius, modest blur) so it never bleeds across
        into the right-hand transport controls — a wide/bright accent
        glow used to show up as a stray colored blob over the play
        button on some cover art."""
        x0, y0, x1, y1 = CARD_BOX
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        ds = 4
        small = (max(1, W // ds), max(1, H // ds))
        glow = Image.new("RGBA", small, (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        rw, rh = (x1 - x0) * 0.55 / ds, (y1 - y0) * 0.55 / ds
        gd.ellipse(
            (cx / ds - rw, cy / ds - rh, cx / ds + rw, cy / ds + rh),
            fill=(*accent, 70),
        )
        glow = glow.filter(ImageFilter.GaussianBlur(max(1, S(55) // ds)))
        glow = glow.resize(CANVAS_SIZE, Image.Resampling.BILINEAR)
        # Hard-clip the glow to the left half of the frame so no matter
        # how it's tinted it can never touch the right-hand panel.
        clip = Image.new("L", CANVAS_SIZE, 0)
        ImageDraw.Draw(clip).rectangle((0, 0, RIGHT_X - S(40), H), fill=255)
        glow.putalpha(Image.composite(glow.split()[3], Image.new("L", CANVAS_SIZE, 0), clip))
        canvas.alpha_composite(glow)

    def draw_card_shadow(self, canvas):
        """Soft ambient shadow beneath the poster card so it reads as a
        lifted object floating over the background."""
        x0, y0, x1, y1 = CARD_BOX
        shadow = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle(
            (x0 + S(4), y0 + S(18), x1 + S(4), y1 + S(18)),
            radius=CARD_RADIUS, fill=(0, 0, 0, 140),
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(S(26)))
        canvas.alpha_composite(shadow)

    # ---------- left poster card ----------

    def draw_poster_card(self, canvas, cover_img, accent):
        """Tall rounded card on the left showing the cover art itself,
        untouched apart from rounded corners, a hairline border and a
        very light edge vignette for polish.

        Deliberately does NOT overlay a title/artist/bot-name here:
        in real-world use `cover_img` is very often the source
        platform's own video/track thumbnail, which usually already
        has its own title, artist and branding baked into the pixels.
        Drawing our own text on top of that produced duplicated,
        overlapping captions. All textual info instead lives cleanly
        in the right-hand "now playing" panel, which is drawn on our
        own backdrop and never collides with anything baked into the
        artwork."""
        self.draw_card_ambient_glow(canvas, accent)
        self.draw_card_shadow(canvas)

        x0, y0, x1, y1 = CARD_BOX
        w, h = x1 - x0, y1 - y0

        art = self.fit_image(cover_img.convert("RGB"), (w, h)).convert("RGBA")

        # Very light top/bottom edge shading, just enough to keep the
        # card from looking like a flat pasted rectangle — not meant to
        # host text, so it's much subtler than before.
        grad = Image.new("L", (1, h), 0)
        for yy in range(h):
            frac = yy / max(1, h - 1)
            top_a = int(60 * max(0, 1 - frac / 0.10)) if frac < 0.10 else 0
            bot_a = int(70 * max(0, (frac - 0.88) / 0.12)) if frac > 0.88 else 0
            grad.putpixel((0, yy), max(top_a, bot_a))
        grad = grad.resize((w, h))
        shade = Image.new("RGBA", (w, h), (6, 5, 5, 255))
        shade.putalpha(grad)
        art = Image.alpha_composite(art, shade)

        art = self.add_round_corners(art, CARD_RADIUS)
        outline = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(outline).rounded_rectangle(
            (0, 0, w - 1, h - 1), radius=CARD_RADIUS,
            outline=(255, 255, 255, 90), width=max(1, S(1)),
        )
        art.alpha_composite(outline)
        canvas.alpha_composite(art, (x0, y0))

    # ---------- right "now playing" panel ----------

    def _icon_button(self, canvas, cx, cy, r):
        """Solid-ish dark glassy circular button background shared by
        the top-right star / overflow icons — deliberately darker/more
        opaque than a plain translucent highlight so the white glyph
        drawn on top of it always has enough contrast to read clearly,
        regardless of what's behind it."""
        draw = ImageDraw.Draw(canvas, "RGBA")
        draw.ellipse(
            (cx - r, cy - r, cx + r, cy + r),
            fill=(60, 58, 56, 150), outline=(255, 255, 255, 160),
            width=max(1, S(1.5)),
        )

    def draw_star_icon(self, canvas, cx, cy, r):
        self._icon_button(canvas, cx, cy, r)
        draw = ImageDraw.Draw(canvas, "RGBA")
        pts = []
        outer, inner = r * 0.60, r * 0.24
        for i in range(10):
            ang = -math.pi / 2 + i * math.pi / 5
            rad = outer if i % 2 == 0 else inner
            pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
        # Solid fill instead of a thin outline — a 2-3px stroke on a
        # small star reads as an empty circle at a glance; a filled
        # silhouette stays clearly visible at any resolution or font
        # rendering environment.
        draw.polygon(pts, fill=COL_WHITE)

    def draw_overflow_icon(self, canvas, cx, cy, r):
        self._icon_button(canvas, cx, cy, r)
        draw = ImageDraw.Draw(canvas, "RGBA")
        dot_r = max(2, S(3))
        for dy in (-r * 0.36, 0, r * 0.36):
            draw.ellipse(
                (cx - dot_r, cy + dy - dot_r, cx + dot_r, cy + dy + dot_r),
                fill=COL_WHITE,
            )

    def draw_seekbar(self, canvas, fraction):
        draw = ImageDraw.Draw(canvas, "RGBA")
        y = SEEK_Y
        x0, x1 = RIGHT_X, RIGHT_X_END
        fraction = max(0.0, min(1.0, fraction))
        fx = x0 + (x1 - x0) * fraction
        thickness = S(9)

        # Thick flat gray pill-shaped track (rounded caps), matching
        # the volume bar's weight, with a small white thumb knob.
        draw.rounded_rectangle(
            (x0, y - thickness / 2, x1, y + thickness / 2),
            radius=thickness / 2, fill=(255, 255, 255, 150),
        )
        r = SEEK_THUMB_R
        draw.ellipse((fx - r, y - r, fx + r, y + r), fill=(255, 255, 255, 235))

    def draw_time_row(self, canvas, elapsed_text, remaining_text, bot_name, avatar_img):
        draw = ImageDraw.Draw(canvas, "RGBA")
        y = TIME_Y
        if elapsed_text:
            draw.text((RIGHT_X, y), elapsed_text, font=self.font_time,
                       fill=COL_SUBTITLE, anchor="lm")
        if remaining_text:
            draw.text((RIGHT_X_END, y), remaining_text, font=self.font_time,
                       fill=COL_SUBTITLE, anchor="rm")

        # bot-name pill, centered between the two time labels. Sized to
        # the label's actual rendered width, but capped so a long bot
        # name can never grow into the elapsed/remaining time labels —
        # it shrinks the font first, then truncates with an ellipsis.
        label = self.truncate(bot_name or "Music Bot", 22)
        has_avatar = avatar_img is not None
        avatar_d = PILL_H - S(10) if has_avatar else 0
        inner_pad = S(16)
        gap = S(8) if has_avatar else 0
        max_pill_w = S(260)

        pill_font = self.font_pill
        text_bbox = draw.textbbox((0, 0), label, font=pill_font)
        text_w = text_bbox[2] - text_bbox[0]
        budget = max_pill_w - inner_pad * 2 - avatar_d - gap
        min_pill_size = S(13)
        size = S(17)
        while text_w > budget and size > min_pill_size:
            size -= 1
            pill_font = ImageFont.truetype(self.subtitle_font_path, size)
            text_bbox = draw.textbbox((0, 0), label, font=pill_font)
            text_w = text_bbox[2] - text_bbox[0]
        while text_w > budget and len(label) > 4:
            label = label[:-4].rstrip() + "..."
            text_bbox = draw.textbbox((0, 0), label, font=pill_font)
            text_w = text_bbox[2] - text_bbox[0]

        pill_w = inner_pad * 2 + avatar_d + gap + text_w
        pill_h = PILL_H
        px0 = PILL_CX - pill_w / 2
        px1 = PILL_CX + pill_w / 2
        py0 = y - pill_h / 2
        py1 = y + pill_h / 2
        draw.rounded_rectangle((px0, py0, px1, py1), radius=pill_h / 2,
                                fill=(35, 33, 32, 170), outline=(255, 255, 255, 60),
                                width=max(1, S(1)))

        cursor_x = px0 + inner_pad
        if has_avatar:
            av = self.fit_image(avatar_img.convert("RGB"), (int(avatar_d), int(avatar_d)))
            av = self.add_round_corners(av, int(avatar_d / 2)).convert("RGBA")
            canvas.alpha_composite(av, (int(cursor_x), int(y - avatar_d / 2)))
            cursor_x += avatar_d + gap

        draw.text((cursor_x, y), label, font=pill_font, fill=COL_WHITE, anchor="lm")

    def draw_transport_controls(self, canvas, playing=True):
        draw = ImageDraw.Draw(canvas, "RGBA")
        y = CONTROLS_Y

        # play/pause — no circular ring, just the plain glyph
        r = PLAY_R
        if playing:
            bar_w, bar_h = S(17), S(65)
            gap = S(19)
            for dx in (-gap / 2 - bar_w / 2, gap / 2 + bar_w / 2):
                draw.rounded_rectangle(
                    (PLAY_CX + dx - bar_w / 2, y - bar_h / 2,
                     PLAY_CX + dx + bar_w / 2, y + bar_h / 2),
                    radius=bar_w / 3, fill=COL_WHITE,
                )
        else:
            tri = S(32)
            draw.polygon(
                [(PLAY_CX - tri * 0.5, y - tri * 0.75),
                 (PLAY_CX - tri * 0.5, y + tri * 0.75),
                 (PLAY_CX + tri * 0.75, y)],
                fill=COL_WHITE,
            )

        # rewind / forward — double-triangle "skip" glyphs
        tri_w, tri_h = S(28), S(42)
        gap = S(6)
        for cx, flip in ((REWIND_X, -1), (FORWARD_X, 1)):
            for i in (0, 1):
                off = (i - 0.5) * (tri_w + gap) * flip
                if flip > 0:
                    pts = [(cx + off - tri_w / 2, y - tri_h / 2),
                           (cx + off - tri_w / 2, y + tri_h / 2),
                           (cx + off + tri_w / 2, y)]
                else:
                    pts = [(cx + off + tri_w / 2, y - tri_h / 2),
                           (cx + off + tri_w / 2, y + tri_h / 2),
                           (cx + off - tri_w / 2, y)]
                draw.polygon(pts, fill=COL_WHITE)

    def draw_volume_row(self, canvas, fraction=VOL_FRACTION):
        draw = ImageDraw.Draw(canvas, "RGBA")
        y = VOLUME_Y
        thickness = S(9)
        x0, x1 = VOL_BAR_X0, VOL_BAR_X1

        # Thick flat pill-shaped bar (rounded caps), no progress fill
        # and no thumb — matches the reference's bold single bar.
        draw.rounded_rectangle(
            (x0, y - thickness / 2, x1, y + thickness / 2),
            radius=thickness / 2, fill=(255, 255, 255, 235),
        )

        # low-volume speaker (left)
        cx = VOL_SPEAKER_LOW_X
        body_w, body_h = S(9), S(12)
        draw.rectangle((cx - body_w, y - body_h / 2, cx, y + body_h / 2), fill=COL_WHITE)
        cone = S(11)
        draw.polygon(
            [(cx, y - body_h / 2), (cx, y + body_h / 2),
             (cx + cone, y + body_h / 2 + cone * 0.6),
             (cx + cone, y - body_h / 2 - cone * 0.6)],
            fill=COL_WHITE,
        )

        # high-volume speaker (right), with two sound-wave arcs
        cx = VOL_SPEAKER_HIGH_X
        draw.rectangle((cx - body_w, y - body_h / 2, cx, y + body_h / 2), fill=COL_WHITE)
        draw.polygon(
            [(cx, y - body_h / 2), (cx, y + body_h / 2),
             (cx + cone, y + body_h / 2 + cone * 0.6),
             (cx + cone, y - body_h / 2 - cone * 0.6)],
            fill=COL_WHITE,
        )
        for i, rad in enumerate((S(10), S(16))):
            bbox = (cx + cone - rad, y - rad, cx + cone + rad, y + rad)
            draw.arc(bbox, start=-40, end=40, fill=COL_WHITE, width=max(1, S(2)))

    def draw_bottom_icons(self, canvas):
        draw = ImageDraw.Draw(canvas, "RGBA")
        y = BOTTOM_ICON_Y

        # captions / quote bubble
        cx = BOTTOM_ICON1_X
        w, h = S(34), S(24)
        draw.rounded_rectangle((cx - w / 2, y - h / 2, cx + w / 2, y + h / 2),
                                radius=S(6), outline=COL_MUTED, width=max(1, S(2)))
        draw.polygon(
            [(cx - w * 0.18, y + h / 2), (cx - w * 0.02, y + h / 2),
             (cx - w * 0.14, y + h / 2 + S(8))],
            fill=COL_MUTED,
        )
        qf = ImageFont.truetype(self.subtitle_font_path, S(13))
        draw.text((cx, y - S(1)), '"', font=qf, fill=COL_MUTED, anchor="mm")

        # queue / list
        cx = BOTTOM_ICON3_X
        line_w = S(26)
        x0 = cx - line_w / 2 - S(6)
        for i, dy in enumerate((-S(9), 0, S(9))):
            dot_r = max(1, S(2))
            draw.ellipse((x0 - dot_r, y + dy - dot_r, x0 + dot_r, y + dy + dot_r),
                         fill=COL_MUTED)
            draw.line((x0 + S(8), y + dy, x0 + S(8) + line_w, y + dy),
                       fill=COL_MUTED, width=max(1, S(2)))

    def draw_now_playing_panel(self, canvas, title, channel_name, bot_name,
                                avatar_img=None, duration=None, elapsed=3):
        draw = ImageDraw.Draw(canvas, "RGBA")

        # Keep the title from running under the star/overflow buttons —
        # cap its width to the space actually free above the seek bar.
        title_max_w = STAR_ICON_X - TOP_ICON_R - RIGHT_X - S(24)
        title_text = self.truncate(title or "Unknown Title", 34)
        title_text, title_font = self.fit_title_text_and_font(
            draw, title_text, title_max_w, base_size=S(46), min_size=S(24)
        )
        draw.text((RIGHT_X, TITLE_Y), title_text, font=title_font, fill=COL_TITLE)
        draw.text((RIGHT_X, SUBTITLE_Y), self.truncate(channel_name or "Unknown Artist", 34),
                   font=self.font_subtitle, fill=COL_SUBTITLE)

        self.draw_star_icon(canvas, STAR_ICON_X, TOP_ICON_Y, TOP_ICON_R)
        self.draw_overflow_icon(canvas, DOTS_ICON_X, TOP_ICON_Y, TOP_ICON_R)

        fraction = 0.02
        elapsed_text = self._format_time(elapsed)
        remaining_text = None
        duration = self._parse_duration(duration)
        if duration and duration > 0:
            fraction = max(0.0, min(1.0, (elapsed or 0) / duration))
            remaining = max(0, duration - (elapsed or 0))
            remaining_text = f"-{self._format_time(remaining)}"

        self.draw_seekbar(canvas, fraction)
        self.draw_time_row(canvas, elapsed_text, remaining_text, bot_name, avatar_img)
        self.draw_transport_controls(canvas, playing=True)
        self.draw_volume_row(canvas)
        self.draw_bottom_icons(canvas)

    def apply_grain(self, canvas, opacity=8):
        """Very subtle film grain over the whole frame."""
        w, h = canvas.size
        cache_key = (w, h, opacity)
        if self._grain_cache_key != cache_key:
            small_w, small_h = max(1, w // 3), max(1, h // 3)
            noise_bytes = random.Random(7).randbytes(small_w * small_h)
            noise = Image.frombytes("L", (small_w, small_h), noise_bytes)
            noise = noise.resize((w, h), Image.Resampling.BILINEAR)
            self._grain_alpha_cache = noise.point(lambda p: int(p * opacity / 255))
            self._grain_cache_key = cache_key

        grain = Image.new("RGBA", (w, h), (128, 128, 128, 0))
        grain.putalpha(self._grain_alpha_cache)
        canvas.alpha_composite(grain)

    # ---------- full compose ----------

    def compose(
        self,
        cover_img,
        title: str,
        channel_name: str,
        bot_name: str,
        avatar_img=None,
        duration=None,
        elapsed=3,
        **_ignored,
    ) -> Image.Image:
        """Builds the full 1920x1080 thumbnail: blurred full-screen
        background -> left poster card (cover art + title/artist) ->
        right "now playing" panel (title/artist, seek bar, time row
        with a bot-name pill, transport controls, volume bar, bottom
        icon row) -> grain.

        `avatar_img`, if given, is shown as a tiny circular icon inside
        the bot-name pill (e.g. the requesting user's profile photo).
        `duration` / `elapsed` (seconds) drive the seek bar and the
        elapsed / remaining time labels; both are optional.
        """
        converted_cover = cover_img.convert("RGB")
        accent = self.accent_from_cover(converted_cover)

        canvas = self.build_background(converted_cover)

        self.draw_poster_card(canvas, converted_cover, accent)
        self.draw_now_playing_panel(
            canvas, title, channel_name, bot_name,
            avatar_img=avatar_img, duration=duration, elapsed=elapsed,
        )

        self.apply_grain(canvas, opacity=8)

        final = canvas.convert("RGB")
        canvas.close()
        converted_cover.close()
        return final

    # ---------- bot-facing async entrypoint ----------

    @staticmethod
    def _parse_duration(value):
        """Accepts a duration as numeric seconds OR as a formatted
        string like "6:47" or "1:06:47" (how many bot `Track` classes
        store it) and returns a float number of seconds, or None if it
        can't be parsed."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            text = value.strip()
            if ":" in text:
                parts = text.split(":")
                try:
                    parts = [int(p) for p in parts]
                except ValueError:
                    return None
                seconds = 0
                for p in parts:
                    seconds = seconds * 60 + p
                return float(seconds)
            try:
                return float(text)
            except ValueError:
                return None
        return None

    @staticmethod
    def _first_attr(obj, *names, default=None):
        """Returns the first non-empty attribute found on `obj` out of
        `names`, in order — tolerant of Track/Media using slightly
        different field names."""
        for name in names:
            val = getattr(obj, name, None)
            if val:
                return val
        return default

    async def generate(
        self,
        media,
        output_path: str = None,
        user_avatar=None,
    ) -> str:
        """Entrypoint used by the bot (ArchonMusic/core/calls.py):

            _thumb = await thumb.generate(media)

        Pulls the cover URL / title / channel / bot name / duration off
        of `media`, downloads the cover art, composes the full HD
        thumbnail, saves it to disk and returns the local file path.

        `user_avatar` is the tiny circular icon shown inside the
        bot-name pill — the profile photo of the user who
        requested/played the track. It's flexible on purpose:
          - pass a PIL.Image directly, or
          - pass a local file path, or
          - pass an http(s) URL to download, or
          - pass an already-running asyncio Task/Future resolving to
            one of the above, or
          - leave it as None and this will look for a photo URL already
            attached to `media` (user_photo / user_avatar /
            requester_photo / user_pic / user_dp).
        If none is available, the pill is simply shown without an icon.
        """
        cover_url = self._first_attr(
            media, "thumb", "thumbnail", "cover", "cover_url",
            "image", "photo", "photo_url", "art", "artwork",
        )
        if not cover_url:
            raise ValueError(
                "generate(): could not find a cover/thumbnail URL on the "
                f"given media object ({type(media).__name__!r}); expected "
                "one of: thumb, thumbnail, cover, cover_url, image, photo, "
                "photo_url, art, artwork"
            )

        title = self._first_attr(media, "title", "name", default="Unknown Title")
        channel_name = self._first_attr(
            media, "channel", "channel_name", "uploader", "artist", "user",
            default="Unknown",
        )
        bot_name = self._first_attr(
            config, "BOT_NAME", "NAME", "APP_NAME", default="Music Bot"
        )
        duration = self._first_attr(
            media, "duration", "duration_seconds", "length", "track_duration",
            "seconds", default=None,
        )
        duration = self._parse_duration(duration)

        avatar_source = user_avatar or self._first_attr(
            media, "user_photo", "user_photo_url", "user_avatar",
            "requester_photo", "played_by_photo", "user_pic", "user_dp",
            default=None,
        )

        if not output_path:
            media_id = self._first_attr(media, "id", default=uuid.uuid4().hex)
            output_path = os.path.join(tempfile.gettempdir(), f"thumb_{media_id}.jpg")

        tmp_cover = f"{output_path}.cover_tmp.jpg"
        tmp_avatar = f"{output_path}.avatar_tmp.jpg"
        avatar_img = cover_img = final_img = None
        try:
            # Cover-art download and avatar resolution are independent
            # network round-trips — overlap them instead of doing them
            # one after the other, so total wait is roughly
            # max(cover, avatar) instead of cover + avatar.
            cover_task = asyncio.create_task(self.save_thumb(tmp_cover, cover_url))

            if isinstance(avatar_source, Image.Image):
                avatar_img = avatar_source.convert("RGB")
            elif asyncio.isfuture(avatar_source) or isinstance(avatar_source, asyncio.Task):
                resolved = await avatar_source
                if isinstance(resolved, Image.Image):
                    avatar_img = resolved.convert("RGB")
                elif isinstance(resolved, str) and os.path.isfile(resolved):
                    avatar_img = await asyncio.to_thread(self.load_avatar, resolved)
                elif isinstance(resolved, str) and resolved.startswith(("http://", "https://")):
                    avatar_img = await self.fetch_avatar(resolved, tmp_avatar)
            elif isinstance(avatar_source, str) and os.path.isfile(avatar_source):
                avatar_img = await asyncio.to_thread(self.load_avatar, avatar_source)
            elif isinstance(avatar_source, str) and avatar_source.startswith(
                ("http://", "https://")
            ):
                avatar_img = await self.fetch_avatar(avatar_source, tmp_avatar)

            await cover_task
            cover_img = await asyncio.to_thread(self.load_avatar, tmp_cover)
            if cover_img is None:
                raise ValueError(f"Failed to load cover image from {cover_url}")

            # compose() is pure CPU-bound PIL work. Running it inline on
            # the event loop used to freeze EVERY chat's playback/
            # commands for the ~1-3s it takes — offload to a worker
            # thread to keep the bot responsive under load.
            final_img = await asyncio.to_thread(
                self.compose, cover_img, title, channel_name, bot_name,
                avatar_img=avatar_img, duration=duration,
            )
            await asyncio.to_thread(final_img.save, output_path, quality=90)
        finally:
            for img in (avatar_img, cover_img, final_img):
                if img and hasattr(img, "close"):
                    try:
                        img.close()
                    except Exception:
                        pass
            for tmp in (tmp_cover, tmp_avatar):
                try:
                    if os.path.exists(tmp):
                        os.remove(tmp)
                except Exception:
                    pass
            import gc
            gc.collect()

        return output_path
