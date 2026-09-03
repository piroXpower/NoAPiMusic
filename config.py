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
        self.SUPPORT_CHAT = getenv("SUPPORT_CHAT", "https://t.me/BeMySugarBaby")

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
        self.DEFAULT_THUMB = getenv("DEFAULT_THUMB", "https://graph.org/file/916d4d3ed43fcfa4766bb-420186b24e6dc552e0.jpg")
        self.PING_IMG = getenv("PING_IMG", "https://graph.org/file/0f6a1047af20de24183af-ca71bf5f61dda70013.jpg")
        self.START_VIDEO = getenv("START_VIDEO", "https://graph.org/file/e8e15d589c6883f5e67da-abd39e5eab54f88ddb.mp4")
        self.BOT_NAME = "Subhi Music"
        self.BOT_PHOTO_URL = "https://graph.org/file/1821240927e344f84e33c-55d616099cf61471aa.jpg"

    def check(self):
        missing = [
            var
            for var in ["API_ID", "API_HASH", "BOT_TOKEN", "MONGO_URL", "LOGGER_ID", "OWNER_ID", "SESSION1"]
            if not getattr(self, var)
        ]
        if missing:
            raise SystemExit(f"Missing required environment variables: {', '.join(missing)}")
