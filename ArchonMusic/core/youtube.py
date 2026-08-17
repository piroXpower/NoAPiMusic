import asyncio
import os
import re
from typing import Union

import aiohttp
import yt_dlp
from pyrogram.types import Message
from py_yt import Playlist, VideosSearch

from ArchonMusic import config, logger
from ArchonMusic.helpers import Track


API_URL = os.environ.get(
    "SHRUTI_API_URL",
    "https://api.shrutibots.site",
)
API_KEY = os.environ.get(
    "SHRUTI_API_KEY",
    "ShrutiBotswFO5UMhbdcYIYaFcC17Y",
)

DOWNLOAD_DIR = "downloads"
COOKIES_FILE = os.environ.get("YOUTUBE_COOKIES_FILE", "cookies.txt")


def time_to_seconds(value) -> int:
    """Convert MM:SS or HH:MM:SS to seconds."""
    if not value:
        return 0
    try:
        parts = str(value).split(":")
        return sum(int(x) * 60 ** i for i, x in enumerate(reversed(parts)))
    except (ValueError, TypeError):
        return 0


def seconds_to_time(seconds: int) -> str:
    """Convert seconds to MM:SS or HH:MM:SS."""
    seconds = int(seconds or 0)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def extract_video_id(link: str) -> str | None:
    """Extract a YouTube video ID from a URL or accept an ID directly."""
    if not link:
        return None

    link = str(link).strip()

    if "youtu.be/" in link:
        video_id = link.split("youtu.be/", 1)[1].split("?", 1)[0].split("&", 1)[0]
    elif "v=" in link:
        video_id = link.split("v=", 1)[1].split("&", 1)[0]
    else:
        video_id = link

    return video_id if len(video_id) >= 3 else None


async def _api_download(link: str, media_type: str, timeout: int) -> str | None:
    """Download media from the configured API with retries.

    The API can occasionally return HTTP 5xx or take longer than the normal
    request timeout.  Keep those failures isolated and let the caller use the
    yt-dlp fallback instead of leaving a half-written file behind.
    """
    video_id = extract_video_id(link)
    if not video_id:
        return None

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    ext = "mp4" if media_type == "video" else "mp3"
    file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")

    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        return file_path

    params = {"url": video_id, "type": media_type}
    if API_KEY:
        params["api_key"] = API_KEY

    # Separate connect/read timeouts prevent one slow socket from holding the
    # Telegram handler forever while still allowing large media files time to
    # finish downloading.
    client_timeout = aiohttp.ClientTimeout(
        total=timeout,
        connect=15,
        sock_connect=15,
        sock_read=90,
    )

    for attempt in range(3):
        try:
            async with aiohttp.ClientSession(timeout=client_timeout) as session:
                async with session.get(
                    f"{API_URL.rstrip('/')}/download",
                    params=params,
                    headers={"User-Agent": "Mozilla/5.0"},
                ) as resp:
                    if resp.status != 200:
                        logger.warning(
                            "Download API returned HTTP %s for %s (attempt %s/3)",
                            resp.status,
                            video_id,
                            attempt + 1,
                        )
                        if resp.status not in (408, 429) and resp.status < 500:
                            break
                    else:
                        ctype = (resp.headers.get("Content-Type") or "").lower()
                        if "application/json" in ctype or "text/html" in ctype:
                            logger.warning(
                                "Download API returned %s instead of media for %s",
                                ctype,
                                video_id,
                            )
                        else:
                            tmp_path = f"{file_path}.part"
                            try:
                                with open(tmp_path, "wb") as output:
                                    async for chunk in resp.content.iter_chunked(256 * 1024):
                                        if chunk:
                                            output.write(chunk)

                                if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                                    os.replace(tmp_path, file_path)
                                    return file_path
                            finally:
                                try:
                                    if os.path.exists(tmp_path):
                                        os.remove(tmp_path)
                                except OSError:
                                    pass

        except (asyncio.TimeoutError, TimeoutError) as exc:
            logger.warning(
                "Download API timeout for %s (attempt %s/3): %s",
                video_id,
                attempt + 1,
                exc,
            )
        except (aiohttp.ClientError, OSError) as exc:
            logger.warning(
                "Download API failed for %s (attempt %s/3): %s",
                video_id,
                attempt + 1,
                exc,
            )
        except Exception as exc:
            logger.warning(
                "Unexpected API download error for %s (attempt %s/3): %s",
                video_id,
                attempt + 1,
                exc,
            )

        if attempt < 2:
            await asyncio.sleep(1.5 * (attempt + 1))

    return None


async def _ytdlp_download(link: str, media_type: str) -> str | None:
    """Fallback downloader used when the external API is unavailable."""
    video_id = extract_video_id(link)
    if not video_id:
        return None

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    output_template = os.path.join(DOWNLOAD_DIR, f"{video_id}.%(ext)s")

    def _download() -> str | None:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "retries": 2,
            "fragment_retries": 2,
            "socket_timeout": 20,
            "geo_bypass": True,
            "nocheckcertificate": True,
            "outtmpl": output_template,
        }
        if media_type == "video":
            opts.update({
                "format": "best[ext=mp4]/best",
                "merge_output_format": "mp4",
            })
        else:
            opts.update({"format": "bestaudio/best"})

        if os.path.exists(COOKIES_FILE):
            opts["cookiefile"] = COOKIES_FILE

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([link])
        except Exception as exc:
            logger.warning("yt-dlp fallback failed for %s: %s", video_id, exc)
            return None

        prefix = os.path.join(DOWNLOAD_DIR, f"{video_id}.")
        candidates = [
            path for path in (
                os.path.join(DOWNLOAD_DIR, name)
                for name in os.listdir(DOWNLOAD_DIR)
            )
            if path.startswith(prefix)
            and not path.endswith(".part")
            and os.path.isfile(path)
            and os.path.getsize(path) > 0
        ]
        if not candidates:
            return None
        return max(candidates, key=os.path.getmtime)

    return await asyncio.to_thread(_download)


async def download_song(link: str) -> str | None:
    file_path = await _api_download(link, "audio", 60)
    if file_path:
        return file_path
    return await _ytdlp_download(link, "audio")


async def download_video(link: str) -> str | None:
    file_path = await _api_download(link, "video", 90)
    if file_path:
        return file_path
    return await _ytdlp_download(link, "video")


class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.status = "https://www.youtube.com/oembed?url="
        self.listbase = "https://youtube.com/playlist?list="
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    async def save_cookies(self, urls: list[str]) -> None:
        """Download Netscape-format cookies from one or more batbin.me
        paste URLs and write them into COOKIES_FILE, so yt-dlp can use a
        logged-in session and avoid YouTube's bot-check ("Sign in to
        confirm you're not a bot"). Called once at startup if
        config.COOKIES_URL is set. Silently skips on failure so a bad
        URL doesn't block the bot from starting.

        batbin.me's raw-content route isn't at a fixed, well-documented
        path, so several candidate URLs are tried per paste (in order)
        and the first one that returns a plausible cookies.txt body
        wins."""
        if not urls:
            return

        combined: list[str] = []
        timeout = aiohttp.ClientTimeout(total=15)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            for url in urls:
                url = url.rstrip("/")
                paste_id = url.rsplit("/", 1)[-1]
                candidates = [
                    f"{url}/raw",
                    f"https://batbin.me/raw/{paste_id}",
                    f"https://batbin.me/api/v2/paste/{paste_id}/raw",
                    f"https://batbin.me/api/v2/paste/{paste_id}",
                    f"{url}?raw=true",
                    url,
                ]

                text = None
                for candidate in candidates:
                    try:
                        async with session.get(candidate) as resp:
                            if resp.status != 200:
                                continue
                            body = (await resp.text()).strip()
                            if not body:
                                continue
                            ctype = (resp.headers.get("Content-Type") or "").lower()
                            if "text/html" in ctype:
                                continue
                            if "application/json" in ctype:
                                try:
                                    import json as _json
                                    parsed = _json.loads(body)
                                    body = (
                                        parsed.get("data")
                                        or parsed.get("content")
                                        or parsed.get("message")
                                        or ""
                                    ).strip()
                                except Exception:
                                    continue
                            if "Netscape HTTP Cookie" in body or "\t" in body:
                                text = body
                                break
                    except Exception:
                        continue

                if text:
                    combined.append(text)
                else:
                    logger.warning(
                        "save_cookies: none of the candidate URLs worked for %s", url
                    )

        if not combined:
            logger.warning("save_cookies: no cookies were downloaded, none of %s worked", urls)
            return

        try:
            with open(COOKIES_FILE, "w", encoding="utf-8") as f:
                f.write("\n\n".join(combined) + "\n")
            logger.info("save_cookies: wrote cookies from %s source(s) to %s", len(combined), COOKIES_FILE)
        except OSError as exc:
            logger.warning("save_cookies: failed to write %s: %s", COOKIES_FILE, exc)

    async def exists(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ):
        if videoid:
            link = self.base + link
        return bool(re.search(self.regex, link or ""))

    async def url(self, message_1: Message) -> Union[str, None]:
        messages = [message_1]

        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)

        for message in messages:
            text = message.text or message.caption or ""

            if message.entities:
                for entity in message.entities:
                    if entity.type.name == "URL":
                        return text[
                            entity.offset:entity.offset + entity.length
                        ]

            if message.caption_entities:
                for entity in message.caption_entities:
                    if entity.type.name == "TEXT_LINK":
                        return entity.url

        return None

    async def details(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ):
        if videoid:
            link = self.base + link

        link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        data = (await results.next()).get("result", [])

        if not data:
            return None

        result = data[0]
        duration = result.get("duration") or "00:00"
        thumbnail = (result.get("thumbnails") or [{}])[0].get(
            "url", ""
        ).split("?")[0]

        return (
            result.get("title"),
            duration,
            time_to_seconds(duration),
            thumbnail,
            result.get("id"),
        )

    async def title(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ):
        details = await self.details(link, videoid)
        return details[0] if details else None

    async def duration(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ):
        details = await self.details(link, videoid)
        return details[1] if details else None

    async def thumbnail(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ):
        details = await self.details(link, videoid)
        return details[3] if details else None

    async def video(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ):
        if videoid:
            link = self.base + link

        try:
            file_path = await download_video(link)
            if file_path:
                return 1, file_path
            return 0, "Video download failed"
        except Exception as exc:
            return 0, f"Video download error: {exc}"

    async def playlist(
        self,
        link,
        limit,
        user_id,
        videoid: Union[bool, str] = None,
    ):
        if videoid:
            link = self.listbase + link

        link = link.split("&")[0]

        try:
            playlist = await Playlist.get(link)
        except Exception as exc:
            logger.warning("Playlist fetch failed: %s", exc)
            return []

        videos = playlist.get("videos") or []
        return [
            data.get("id")
            for data in videos[:limit]
            if data and data.get("id")
        ]

    async def track(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ):
        if videoid:
            link = self.base + link

        link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        data = (await results.next()).get("result", [])

        if not data:
            return None, None

        result = data[0]
        thumbnail = (result.get("thumbnails") or [{}])[0].get(
            "url", ""
        ).split("?")[0]

        track_details = {
            "title": result.get("title"),
            "link": result.get("link"),
            "vidid": result.get("id"),
            "duration_min": result.get("duration"),
            "thumb": thumbnail,
        }

        return track_details, result.get("id")

    async def formats(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ):
        if videoid:
            link = self.base + link

        link = link.split("&")[0]

        ydl_opts = {"quiet": True, "no_warnings": True}
        if os.path.exists(COOKIES_FILE):
            ydl_opts["cookiefile"] = COOKIES_FILE

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(link, download=False)

            formats_available = []

            for fmt in info.get("formats", []):
                try:
                    if "dash" in str(fmt.get("format", "")).lower():
                        continue

                    formats_available.append(
                        {
                            "format": fmt.get("format"),
                            "filesize": fmt.get("filesize"),
                            "format_id": fmt.get("format_id"),
                            "ext": fmt.get("ext"),
                            "format_note": fmt.get("format_note"),
                            "yturl": link,
                        }
                    )
                except Exception:
                    continue

            return formats_available, link

        except Exception as exc:
            logger.error("Format extraction failed: %s", exc)
            return [], link

    async def slider(
        self,
        link: str,
        query_type: int,
        videoid: Union[bool, str] = None,
    ):
        if videoid:
            link = self.base + link

        link = link.split("&")[0]
        results = VideosSearch(link, limit=10)
        data = (await results.next()).get("result", [])

        if not data or query_type >= len(data):
            return None

        result = data[query_type]
        thumbnail = (result.get("thumbnails") or [{}])[0].get(
            "url", ""
        ).split("?")[0]

        return (
            result.get("title"),
            result.get("duration"),
            thumbnail,
            result.get("id"),
        )

    async def search(
        self,
        query: str,
        message_id: int = 0,
        video: bool = False,
    ):
        """Return the Track object expected by play_hndlr."""
        try:
            results = VideosSearch(query, limit=1)
            data = (await results.next()).get("result", [])

            if not data:
                return None

            result = data[0]
            duration = result.get("duration") or "00:00"
            thumbnails = result.get("thumbnails") or [{}]

            return Track(
                id=result.get("id"),
                channel_name=(result.get("channel") or {}).get("name"),
                duration=duration,
                duration_sec=time_to_seconds(duration),
                title=result.get("title"),
                url=result.get("link"),
                file_path=None,
                message_id=message_id,
                thumbnail=thumbnails[0].get("url", "").split("?")[0],
                video=video,
            )

        except Exception as exc:
            logger.error("YouTube search error: %s", exc)
            return None

    async def autoplay_track(
        self,
        video_id: str,
        video: Union[bool, str] = None,
        exclude: set | None = None,
        title: str | None = None,
    ) -> Union["Track", None]:
        """Find a track to play next for autoplay, based on the video
        that just finished. Uses YouTube's own "Mix" (radio, RD-prefixed)
        playlist to get genuinely related videos — more accurate than a
        text search on the title — and returns the first one not already
        in `exclude` (already played this session)."""
        exclude = exclude or set()
        entries = await self.related(video_id)

        for entry in entries:
            if not entry:
                continue
            entry_id = entry.get("id")
            if not entry_id or entry_id == video_id or entry_id in exclude:
                continue

            duration_sec = int(entry.get("duration") or 0)
            thumbs = entry.get("thumbnails") or []
            thumbnail = (
                thumbs[-1].get("url", "").split("?")[0]
                if thumbs and thumbs[-1].get("url")
                else f"https://i.ytimg.com/vi/{entry_id}/hqdefault.jpg"
            )

            return Track(
                id=entry_id,
                channel_name=entry.get("channel") or entry.get("uploader"),
                duration=seconds_to_time(duration_sec),
                duration_sec=duration_sec,
                title=entry.get("title") or "Unknown",
                url=self.base + entry_id,
                file_path=None,
                message_id=0,
                thumbnail=thumbnail,
                user="Autoplay",
                video=bool(video),
            )

        return None

    async def related(self, video_id: str, limit: int = 10) -> list:
        """Fetch related videos via YouTube's auto-generated Mix/radio
        playlist (RD<video_id>) — the same "up next" logic YouTube itself
        uses, so results are far more relevant than a title-based search."""
        def _fetch():
            opts = {
                "extract_flat": True,
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "geo_bypass": True,
                "nocheckcertificate": True,
                "playlistend": limit,
            }
            if os.path.exists(COOKIES_FILE):
                opts["cookiefile"] = COOKIES_FILE
            url = f"{self.base}{video_id}&list=RD{video_id}"
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    return (info or {}).get("entries") or []
            except Exception as exc:
                logger.warning("Autoplay: failed to fetch related videos: %s", exc)
                return []

        return await asyncio.to_thread(_fetch)

    async def stream_url(
        self,
        link: str,
        video: Union[bool, str] = None,
        videoid: Union[bool, str] = None,
    ) -> Union[str, None]:
        """Fast path: build a direct streamable URL from the download API
        instead of downloading the whole file to disk first. ffmpeg (used
        by pytgcalls under the hood) can play straight from an HTTP URL,
        so playback can start almost immediately instead of waiting for
        the full download. Validates the URL actually serves audio/video
        first (a quick, short-timeout check) so a bad/failed API response
        never reaches ffmpeg as "Audio source not found" — returns None
        in that case (and when a video ID can't be extracted at all) so
        callers fall back to the full download() path instead."""
        video_id = extract_video_id(link)
        if not video_id:
            return None

        params = f"url={video_id}&type={'video' if video else 'audio'}"
        if API_KEY:
            params += f"&api_key={API_KEY}"

        url = f"{API_URL.rstrip('/')}/download?{params}"

        if await self._url_has_media(url):
            return url
        return None

    @staticmethod
    async def _url_has_media(url: str) -> bool:
        """Quick sanity check that a URL actually serves audio/video
        content (not an error page/JSON) before handing it to ffmpeg.
        Short timeout so a slow/dead API fails fast into the download()
        fallback instead of hanging."""
        try:
            timeout = aiohttp.ClientTimeout(total=6)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                headers = {"Range": "bytes=0-1024"}
                async with session.get(url, headers=headers) as resp:
                    if resp.status >= 400:
                        return False
                    ctype = resp.headers.get("Content-Type", "")
                    if ctype.startswith(("text/html", "application/json")):
                        return False
                    return True
        except Exception as exc:
            logger.warning("stream_url validation failed for %s: %s", url, exc)
            return False

    async def download(
        self,
        link: str,
        mystic=None,
        video: Union[bool, str] = None,
        videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ):
        """Return (path, success), matching the caller's expected API."""
        if videoid:
            link = self.base + link

        try:
            file_path = (
                await download_video(link)
                if video
                else await download_song(link)
            )

            if file_path:
                return file_path, True

            return None, False

        except Exception as exc:
            logger.error("YouTube download error: %s", exc)
            return None, False


YouTube = YouTubeAPI()
