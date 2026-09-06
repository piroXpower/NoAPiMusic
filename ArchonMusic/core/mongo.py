import os
import config
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = (
    getattr(config, "MONGO_DB_URI", None)
    or getattr(config, "MONGO_URL", None)
    or getattr(config, "MONGO_URI", None)
    or os.environ.get("MONGO_DB_URI")
    or os.environ.get("MONGO_URL")
    or os.environ.get("MONGO_URI")
)

if not MONGO_URI:
    _mongo_client = AsyncIOMotorClient()
else:
    _mongo_client = AsyncIOMotorClient(MONGO_URI)

bot_name = getattr(config, "BOT_NAME", "ArchonMusic")
mongodb = _mongo_client[bot_name]

chatsdb = mongodb.chats
usersdb = mongodb.users
blockeddb = mongodb.blocked
authdb = mongodb.auth
langdb = mongodb.language
cplay_db = mongodb.cplay
sudoersdb = mongodb.sudoers
adminsdb = mongodb.admins
assistantdb = mongodb.assistants


class MongoDB:
    def __init__(self):
        self.db = mongodb
        self.client = _mongo_client
        self.blacklisted = []
        self.adminlist = {}
        self.active_calls = []

    async def connect(self):
        try:
            self.blacklisted = await self.get_blacklisted()
        except Exception:
            self.blacklisted = []
        return True

    # ------------------- Assistant / Client Resolution ------------------- #
    async def get_client(self, chat_id: int):
        data = await assistantdb.find_one({"chat_id": chat_id})
        index = data.get("assistant", 1) if data else 1

        try:
            import ArchonMusic.core.userbot as ub_mod

            # Check if userbot instance with numbered attributes exists (userbot.one, etc.)
            userbot = getattr(ub_mod, "userbot", None)
            if userbot:
                attr_names = ["one", "two", "three", "four", "five"]
                selected_attr = attr_names[min(max(0, index - 1), len(attr_names) - 1)]
                client = getattr(userbot, selected_attr, None)
                if client and getattr(client, "id", None):
                    return client

            # Check if assistants list exists
            assistants = getattr(ub_mod, "assistants", None)
            if isinstance(assistants, list) and assistants:
                idx = (index - 1) % len(assistants)
                return assistants[idx]

        except Exception:
            pass

        # Fallback to the main Pyrogram bot app
        from ArchonMusic import app
        return app

    async def set_client(self, chat_id: int, assistant_id: int):
        await assistantdb.update_one(
            {"chat_id": chat_id},
            {"$set": {"assistant": assistant_id}},
            upsert=True,
        )

    # ------------------- Active Calls Tracking ------------------- #
    async def is_active_call(self, chat_id: int) -> bool:
        return chat_id in self.active_calls

    async def add_active_call(self, chat_id: int):
        if chat_id not in self.active_calls:
            self.active_calls.append(chat_id)

    async def remove_active_call(self, chat_id: int):
        if chat_id in self.active_calls:
            self.active_calls.remove(chat_id)

    # ------------------- Sudoers ------------------- #
    async def get_sudoers(self) -> list:
        sudoers = await sudoersdb.find_one({"sudo": "sudo"})
        if not sudoers:
            return []
        return sudoers.get("sudoers", [])

    async def add_sudo(self, user_id: int) -> bool:
        sudoers = await self.get_sudoers()
        sudoers.append(user_id)
        await sudoersdb.update_one(
            {"sudo": "sudo"},
            {"$set": {"sudoers": sudoers}},
            upsert=True,
        )
        return True

    async def remove_sudo(self, user_id: int) -> bool:
        sudoers = await self.get_sudoers()
        if user_id in sudoers:
            sudoers.remove(user_id)
            await sudoersdb.update_one(
                {"sudo": "sudo"},
                {"$set": {"sudoers": sudoers}},
                upsert=True,
            )
            return True
        return False

    # ------------------- Admins Cache ------------------- #
    async def get_admins(self, chat_id: int) -> list:
        if chat_id in self.adminlist:
            return self.adminlist[chat_id]
        data = await adminsdb.find_one({"chat_id": chat_id})
        if not data:
            return []
        self.adminlist[chat_id] = data.get("admins", [])
        return self.adminlist[chat_id]

    async def set_admins(self, chat_id: int, admins: list):
        self.adminlist[chat_id] = admins
        await adminsdb.update_one(
            {"chat_id": chat_id},
            {"$set": {"admins": admins}},
            upsert=True,
        )

    # ------------------- Auth Users & Permissions ------------------- #
    async def is_auth(self, chat_id: int, user_id: int) -> bool:
        doc = await authdb.find_one({"chat_id": chat_id, "user_id": user_id})
        return bool(doc)

    async def add_auth(self, chat_id: int, user_id: int):
        if await self.is_auth(chat_id, user_id):
            return
        return await authdb.insert_one({"chat_id": chat_id, "user_id": user_id})

    async def remove_auth(self, chat_id: int, user_id: int):
        if not await self.is_auth(chat_id, user_id):
            return
        return await authdb.delete_one({"chat_id": chat_id, "user_id": user_id})

    async def _get_authusers(self, chat_id: int) -> dict:
        _notes = await authdb.find_one({"chat_id": chat_id})
        if not _notes:
            return {}
        return _notes.get("notes", {})

    async def get_authuser_names(self, chat_id: int) -> list:
        _notes = await self._get_authusers(chat_id)
        return list(_notes.keys())

    async def get_authuser(self, chat_id: int, name: str) -> dict:
        _notes = await self._get_authusers(chat_id)
        return _notes.get(name, False)

    async def save_authuser(self, chat_id: int, name: str, note: dict):
        _notes = await self._get_authusers(chat_id)
        _notes[name] = note
        await authdb.update_one(
            {"chat_id": chat_id},
            {"$set": {"notes": _notes}},
            upsert=True,
        )

    async def delete_authuser(self, chat_id: int, name: str) -> bool:
        notes = await self._get_authusers(chat_id)
        if name in notes:
            del notes[name]
            await authdb.update_one(
                {"chat_id": chat_id},
                {"$set": {"notes": notes}},
                upsert=True,
            )
            return True
        return False

    # ------------------- Users (is_user / add_user) ------------------- #
    async def is_user(self, user_id: int) -> bool:
        user = await usersdb.find_one({"user_id": user_id})
        return bool(user)

    async def add_user(self, user_id: int):
        if await self.is_user(user_id):
            return
        return await usersdb.insert_one({"user_id": user_id})

    async def get_users(self) -> list:
        users = usersdb.find({"user_id": {"$gt": 0}})
        if not users:
            return []
        return [user["user_id"] async for user in users]

    is_served_user = is_user
    add_served_user = add_user
    get_served_users = get_users

    # ------------------- Chats (is_chat / add_chat) ------------------- #
    async def is_chat(self, chat_id: int) -> bool:
        chat = await chatsdb.find_one({"chat_id": chat_id})
        return bool(chat)

    async def add_chat(self, chat_id: int):
        if await self.is_chat(chat_id):
            return
        return await chatsdb.insert_one({"chat_id": chat_id})

    async def remove_chat(self, chat_id: int):
        if not await self.is_chat(chat_id):
            return
        return await chatsdb.delete_one({"chat_id": chat_id})

    async def get_chats(self) -> list:
        chats = chatsdb.find({"chat_id": {"$lt": 0}})
        if not chats:
            return []
        return [chat["chat_id"] async for chat in chats]

    is_served_chat = is_chat
    add_served_chat = add_chat
    remove_served_chat = remove_chat
    get_served_chats = get_chats

    # ------------------- Language Settings ------------------- #
    async def get_lang(self, chat_id: int) -> str:
        chat = await langdb.find_one({"chat_id": chat_id})
        if not chat:
            return "en"
        return chat.get("lang", "en")

    async def set_lang(self, chat_id: int, lang: str):
        await langdb.update_one(
            {"chat_id": chat_id},
            {"$set": {"lang": lang}},
            upsert=True,
        )

    # ------------------- Play Mode & Settings ------------------- #
    async def get_play_mode(self, chat_id: int) -> str:
        mode = await chatsdb.find_one({"chat_id": chat_id})
        if not mode:
            return "Direct"
        return mode.get("play_mode", "Direct")

    async def set_play_mode(self, chat_id: int, mode: str):
        await chatsdb.update_one(
            {"chat_id": chat_id},
            {"$set": {"play_mode": mode}},
            upsert=True,
        )

    async def get_play_type(self, chat_id: int) -> str:
        mode = await chatsdb.find_one({"chat_id": chat_id})
        if not mode:
            return "Everyone"
        return mode.get("play_type", "Everyone")

    async def set_play_type(self, chat_id: int, play_type: str):
        await chatsdb.update_one(
            {"chat_id": chat_id},
            {"$set": {"play_type": play_type}},
            upsert=True,
        )

    # ------------------- Blacklist / Blocked ------------------- #
    async def get_blacklisted(self) -> list:
        blocked = blockeddb.find()
        if not blocked:
            return []
        users = []
        async for doc in blocked:
            target = doc.get("user_id") or doc.get("chat_id")
            if target:
                users.append(target)
        self.blacklisted = users
        return users

    async def is_banned_user(self, user_id: int) -> bool:
        user = await blockeddb.find_one({"user_id": user_id})
        return bool(user)

    async def add_banned_user(self, user_id: int):
        if await self.is_banned_user(user_id):
            return
        if user_id not in self.blacklisted:
            self.blacklisted.append(user_id)
        return await blockeddb.insert_one({"user_id": user_id})

    async def remove_banned_user(self, user_id: int):
        if not await self.is_banned_user(user_id):
            return
        if user_id in self.blacklisted:
            self.blacklisted.remove(user_id)
        return await blockeddb.delete_one({"user_id": user_id})

    # ------------------- Channel Play (cplay) ------------------- #
    async def get_cmode(self, chat_id: int):
        doc = await cplay_db.find_one({"chat_id": chat_id})
        return doc.get("channel_id") if doc else None

    async def set_cmode(self, chat_id: int, channel_id: int):
        await cplay_db.update_one(
            {"chat_id": chat_id},
            {"$set": {"channel_id": channel_id}},
            upsert=True,
        )

    async def remove_cmode(self, chat_id: int):
        await cplay_db.delete_one({"chat_id": chat_id})


db = MongoDB()

# Direct functional aliases
get_sudoers = db.get_sudoers
add_sudo = db.add_sudo
remove_sudo = db.remove_sudo

get_client = db.get_client
set_client = db.set_client

get_admins = db.get_admins
set_admins = db.set_admins

is_active_call = db.is_active_call
add_active_call = db.add_active_call
remove_active_call = db.remove_active_call

is_auth = db.is_auth
add_auth = db.add_auth
remove_auth = db.remove_auth

is_user = db.is_user
add_user = db.add_user
get_users = db.get_users
is_served_user = db.is_served_user
add_served_user = db.add_served_user
get_served_users = db.get_served_users

is_chat = db.is_chat
add_chat = db.add_chat
remove_chat = db.remove_chat
get_chats = db.get_chats
is_served_chat = db.is_served_chat
add_served_chat = db.add_served_chat
remove_served_chat = db.remove_served_chat
get_served_chats = db.get_served_chats

get_lang = db.get_lang
set_lang = db.set_lang

get_play_mode = db.get_play_mode
set_play_mode = db.set_play_mode
get_play_type = db.get_play_type
set_play_type = db.set_play_type

get_authuser_names = db.get_authuser_names
get_authuser = db.get_authuser
save_authuser = db.save_authuser
delete_authuser = db.delete_authuser

get_blacklisted = db.get_blacklisted
is_banned_user = db.is_banned_user
add_banned_user = db.add_banned_user
remove_banned_user = db.remove_banned_user

get_cmode = db.get_cmode
set_cmode = db.set_cmode
remove_cmode = db.remove_cmode
            
