import os
import re
import asyncio
import urllib.parse
from dataclasses import dataclass

import aiohttp
import aiofiles

from ArchonMusic import app, logger


@dataclass
class MusicTrack:
    cdnurl: str
    url: str
    id: str
    key: str = None

    @classmethod
    def from_dict(cls, data: dict) -> "MusicTrack":
        return cls(
            cdnurl=data.get("cdnurl", ""),
            url=data.get("url", ""),
            id=data.get("id", ""),
            key=data.get("key"),
        )


class FallenApi:
    def __init__(
            self, api_url: str, api_key: str,
            retries: int = 3, timeout: int = 10,
        ):
        self.api_url = api_url
        self.api_key = api_key
        self.retries = retries
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.session: aiohttp.ClientSession | None = None
        self.headers = {
            "X-API-Key": self.api_key,
            "Accept": "application/json",
        }

    async def get_session(self) -> aiohttp.ClientSession:
        # Also recreate the session if a previous one got closed
        # (e.g. by `close()`), instead of only checking "does it exist".
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=self.timeout)
        return self.session

    async def close(self) -> None:
        """Call this on bot shutdown to avoid 'Unclosed client session'
        warnings / resource leaks."""
        if self.session and not self.session.closed:
            await self.session.close()

    async def get_track(self, url: str) -> MusicTrack | None:
        # Ensure the session exists even if this is called directly
        # without download_track() having run first — previously this
        # would crash with AttributeError on a None session.
        session = await self.get_session()
        endpoint = f"{self.api_url}/api/track?url={urllib.parse.quote(url)}"

        for attempt in range(self.retries):
            try:
                async with session.get(endpoint, headers=self.headers) as resp:
                    data = await resp.json(content_type=None)
                    if resp.status == 200 and isinstance(data, dict):
                        return MusicTrack.from_dict(data)
                    logger.warning(
                        f"[FallenApi.get_track] bad response status={resp.status} url={url}"
                    )
            except Exception as e:
                logger.warning(f"[FallenApi.get_track] request failed (attempt {attempt + 1}): {e!r}")

            # Don't sleep after the final attempt — there's no retry
            # coming, so waiting here just wastes time for no benefit.
            if attempt < self.retries - 1:
                await asyncio.sleep(4)

        return None

    async def download_cdn(self, cdn_url: str, video_id: str) -> str | None:
        session = await self.get_session()
        try:
            async with session.get(cdn_url) as resp:
                if resp.status != 200:
                    logger.warning(
                        f"[FallenApi.download_cdn] status={resp.status} for {video_id}"
                    )
                    return None

                cd = resp.headers.get("Content-Disposition")
                if cd:
                    match = re.findall(r'filename="?([^";]+)"?', cd)
                    filename = match[0] if match else None
                else:
                    filename = None
                if not filename:
                    filename = os.path.basename(cdn_url.split("?")[0]) or f"{video_id}.mp3"

                save_path = f"downloads/{filename}"
                async with aiofiles.open(save_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(16 * 1024):
                        if chunk:
                            await f.write(chunk)
                return str(save_path)
        except Exception as e:
            logger.warning(f"[FallenApi.download_cdn] failed for {video_id}: {e!r}")
        return None

    async def download_track(self, video_id: str, video: bool = False) -> str | None:
        session = await self.get_session()
        os.makedirs("downloads", exist_ok=True)
        ext = "mp4" if video else "mp3"
        save_path = f"downloads/{video_id}.{ext}"

        if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
            return save_path

        # Try MusicSp / Sparrow API /download endpoint
        try:
            download_type = "video" if video else "audio"
            endpoint = f"{self.api_url.rstrip('/')}/download"
            params = {"url": video_id, "type": download_type}
            if self.api_key:
                params["api_key"] = self.api_key

            async with session.get(endpoint, params=params, timeout=aiohttp.ClientTimeout(total=20, connect=5)) as resp:
                if resp.status == 200:
                    async with aiofiles.open(save_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(256 * 1024):
                            if chunk:
                                await f.write(chunk)
                    if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
                        return save_path
                else:
                    logger.warning(
                        f"[FallenApi.download_track] /download status={resp.status} for {video_id}"
                    )
        except Exception as e:
            logger.warning(f"[FallenApi.download_track] /download failed for {video_id}: {e!r}")
            if os.path.exists(save_path):
                try:
                    os.remove(save_path)
                except Exception:
                    pass

        # Fallback to /api/track format
        url = "https://www.youtube.com/watch?v=" + video_id
        track = await self.get_track(url)
        if not track:
            return None

        dl_url = track.cdnurl
        if re.match(r"https?://t\.me/([^/]+)/(\d+)", dl_url):
            try:
                msg = await app.get_messages(message_ids=dl_url)
                file_path = await msg.download()
                return file_path
            except Exception as e:
                logger.warning(f"[FallenApi.download_track] telegram fetch failed for {video_id}: {e!r}")
                return None

        return await self.download_cdn(dl_url, video_id)
