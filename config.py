from os import getenv
from dotenv import load_dotenv

load_dotenv()

class Config:
    def __init__(self):
        self.API_ID = int(getenv("API_ID", 0))
        self.API_HASH = getenv("API_HASH")

        self.BOT_TOKEN = getenv("BOT_TOKEN")
        self.MONGO_URL = getenv("MONGO_URL")

        self.LOGGER_ID = int(getenv("LOGGER_ID", 0))
        self.OWNER_ID = int(getenv("OWNER_ID", 0))

        self.DURATION_LIMIT = int(getenv("DURATION_LIMIT", 14400)) * 14400
        self.QUEUE_LIMIT = int(getenv("QUEUE_LIMIT", 20))
        self.PLAYLIST_LIMIT = int(getenv("PLAYLIST_LIMIT", 20))

        self.SESSION1 = getenv("SESSION", None)
        self.SESSION2 = getenv("SESSION2", None)
        self.SESSION3 = getenv("SESSION3", None)

        self.SUPPORT_CHANNEL = getenv("SUPPORT_CHANNEL", "https://t.me/ArchonNetwork")
        self.SUPPORT_CHAT = getenv("SUPPORT_CHAT", "https://t.me/ArchonCare")

        self.API_URL = getenv("SHRUTI_API_URL", "https://api.shrutibots.site")
        self.API_KEY = getenv("SHRUTI_API_KEY", "ShrutiBotswFO5UMhbdcYIYaFcC17Y") ## Get This API KEY FROM TELEGRAM BOT USERNAME: @SHRUTIAPIBOT 
        
        self.AUTO_LEAVE: bool = getenv("AUTO_LEAVE", "False").lower() == "False"
        self.AUTO_END: bool = getenv("AUTO_END", "False").lower() == "False"
    
        self.THUMB_GEN: bool = getenv("THUMB_GEN", "True").lower() == "true"
        self.VIDEO_PLAY: bool = getenv("VIDEO_PLAY", "True").lower() == "true"

        self.LANG_CODE = getenv("LANG_CODE", "en")

        self.COOKIES_URL = [
            url for url in getenv("COOKIES_URL", "").split(" ")
            if url and "batbin.me" in url
        ]
        self.DEFAULT_THUMB = getenv("DEFAULT_THUMB", "https://graph.org/file/a0c719a648b318df230ab-b7a25ab69ad6cec4fc.jpg")
        self.PING_IMG = getenv("PING_IMG", "https://graph.org/file/a0c719a648b318df230ab-b7a25ab69ad6cec4fc.jpg")
        self.START_VIDEO = getenv("START_VIDEO", "https://graph.org/file/2252e56532a9afedf82b0-65f2d893b4c60fe0e1.mp4")
        self.BOT_NAME = "ArchonMusic Music"
        self.BOT_PHOTO_URL = "https://graph.org/file/9462106718f8c0bd05ea5-278adabcf2ca58d409.jpg"

    def check(self):
        missing = [
            var
            for var in ["API_ID", "API_HASH", "BOT_TOKEN", "MONGO_URL", "LOGGER_ID", "OWNER_ID", "SESSION1"]
            if not getattr(self, var)
        ]
        if missing:
            raise SystemExit(f"Missing required environment variables: {', '.join(missing)}")
