from pyrogram import types

from ArchonMusic import app, config, lang
from ArchonMusic.core.lang import lang_codes
from pyrogram.enums import ButtonStyle
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup


class Inline:
    def __init__(self):
        self.ikm = types.InlineKeyboardMarkup
        self.ikb = types.InlineKeyboardButton

    def cancel_dl(self, text) -> types.InlineKeyboardMarkup:
        return self.ikm([[self.ikb(text=text, callback_data="cancel_dl")]])

    def controls(
        self,
        chat_id: int,
        status: str = None,
        timer: str = None,
        remove: bool = False,
        more: bool = False,
        thumb: bool = None,
        lang: dict = None,
    ) -> types.InlineKeyboardMarkup:
        keyboard = []
        if status:
            keyboard.append(
                [
                    self.ikb(
                        text=status,
                        callback_data=f"controls status {chat_id}",
                        style=ButtonStyle.PRIMARY,
                    )
                ]
            )
        elif timer:
            keyboard.append(
                [
                    self.ikb(
                        text=timer,
                        callback_data=f"controls status {chat_id}",
                        style=ButtonStyle.PRIMARY,
                    )
                ]
            )

        if not remove:
            if more:
                _on = "ᴏɴ ☜"
                _off = "ᴏғғ ☜"
                keyboard.append(
                    [
                        self.ikb(
                            text="Thumbnail",
                            callback_data="help thumb",
                            style=ButtonStyle.SUCCESS,
                        ),
                        self.ikb(
                            text=_on if thumb else _off,
                            callback_data=f"controls cthumb {chat_id}",
                            style=ButtonStyle.SUCCESS,
                        ),
                    ]
                )
                keyboard.append(
                    [
                        self.ikb(
                            text="ʙᴀᴄᴋ ⎋",
                            callback_data=f"controls back {chat_id}",
                            style=ButtonStyle.DANGER,
                        )
                    ]
                )
            else:
                keyboard.append(
                    [
                        self.ikb(text="▷", callback_data=f"controls resume {chat_id}"),
                        self.ikb(text="II", callback_data=f"controls pause {chat_id}"),
                        self.ikb(text="⥁", callback_data=f"controls replay {chat_id}"),
                        self.ikb(text="‣‣I", callback_data=f"controls skip {chat_id}"),
                        self.ikb(text="▢", callback_data=f"controls stop {chat_id}"),
                    ]
                )
                
        return self.ikm(keyboard)

    def help_markup(
        self, _lang: dict, back: bool = False
    ) -> types.InlineKeyboardMarkup:
        if back:
            rows = [
                [
                    self.ikb(
                        text=_lang["back"],
                        callback_data="help back",
                        style=ButtonStyle.DANGER,
                    ),
                ]
            ]
        else:
            rows = []
                
            cbs = [
                "admins",
                "auth",
                "blist",
                "lang",
                "ping",
                "play",
                "queue",
                "stats",
                "sudo",
                "thumb",
                "vclog",
                "autoplay",
            ]
            buttons = [
                self.ikb(
                    text=_lang[f"help_{i}"],
                    callback_data=f"help {cb}",
                    style=ButtonStyle.SUCCESS,
                )
                for i, cb in enumerate(cbs)
            ]
            rows += [buttons[i : i + 3] for i in range(0, len(buttons), 3)]
            rows.append(
                [
                    self.ikb(
                        text=_lang["back"],
                        callback_data="help home",
                        style=ButtonStyle.DANGER,
                    ),
                ]
            )

        return self.ikm(rows)

    def song_markup(self, vid_id: str) -> types.InlineKeyboardMarkup:
        return self.ikm(
            [
                [
                    self.ikb(
                        text="Audio 🎵", callback_data=f"song_download audio {vid_id}"
                    ),
                    self.ikb(
                        text="Video 🎬", callback_data=f"song_download video {vid_id}"
                    ),
                ],
                [
                    self.ikb(text="Close ✘", callback_data="help close"),
                ],
            ]
        )

    def lang_markup(self, _lang: str) -> types.InlineKeyboardMarkup:
        langs = lang.get_languages()

        buttons = [
            self.ikb(
                text=f"{name} ({code}) {'✔️' if code == _lang else ''}",
                callback_data=f"lang_change {code}",
                style=ButtonStyle.PRIMARY,
            )
            for code, name in langs.items()
        ]
        rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
        return self.ikm(rows)

    def ping_markup(self, text: str) -> types.InlineKeyboardMarkup:
        return self.ikm(
            [
                [
                    self.ikb(
                        text=text,
                        url=config.SUPPORT_CHAT,
                        style=ButtonStyle.PRIMARY,
                    )
                ]
            ]
        )

    def play_queued(
        self, chat_id: int, item_id: str, _text: str
    ) -> types.InlineKeyboardMarkup:
        return self.ikm(
            [
                [
                    self.ikb(
                        text=_text,
                        callback_data=f"controls force {chat_id} {item_id}",
                        style=ButtonStyle.SUCCESS,
                    )
                ]
            ]
        )

    def queue_markup(
        self, chat_id: int, _text: str, playing: bool
    ) -> types.InlineKeyboardMarkup:
        _action = "pause" if playing else "resume"
        return self.ikm(
            [[self.ikb(text=_text, callback_data=f"controls {_action} {chat_id} q")]]
        )

    def settings_markup(
        self,
        lang: dict,
        admin_only: bool,
        cmd_delete: bool,
        vclogger: bool,
        thumbnail: bool,
        autoplay: bool,
        language: str,
        chat_id: int,
    ) -> types.InlineKeyboardMarkup:
        _on = "ᴏɴ ☜"
        _off = "ᴏғғ ☜"
        return self.ikm(
            [
                [
                    self.ikb(
                        text=lang["play_mode"] + " ➜",
                        callback_data="settings",
                        style=ButtonStyle.SUCCESS,
                    ),
                    self.ikb(
                        text=_on if admin_only else _off,
                        callback_data="settings play",
                        style=ButtonStyle.SUCCESS,
                    ),
                ],
                [
                    self.ikb(
                        text=lang["cmd_delete"] + " ➜",
                        callback_data="settings",
                        style=ButtonStyle.SUCCESS,
                    ),
                    self.ikb(
                        text=_on if cmd_delete else _off,
                        callback_data="settings delete",
                        style=ButtonStyle.SUCCESS,
                    ),
                ],
                [
                    self.ikb(
                        text=lang["vclogger"] + " ➜",
                        callback_data="settings",
                        style=ButtonStyle.SUCCESS,
                    ),
                    self.ikb(
                        text=_on if vclogger else _off,
                        callback_data="settings vclog",
                        style=ButtonStyle.SUCCESS,
                    ),
                ],
                [
                    self.ikb(
                        text=lang["thumbnail"] + " ➜",
                        callback_data="settings",
                        style=ButtonStyle.SUCCESS,
                    ),
                    self.ikb(
                        text=_on if thumbnail else _off,
                        callback_data="settings thumb",
                        style=ButtonStyle.SUCCESS,
                    ),
                ],
                [
                    self.ikb(
                        text=lang["autoplay"] + " ➜",
                        callback_data="settings",
                        style=ButtonStyle.SUCCESS,
                    ),
                    self.ikb(
                        text=_on if autoplay else _off,
                        callback_data="settings autoplay",
                        style=ButtonStyle.SUCCESS,
                    ),
                ],
                [
                    self.ikb(
                        text=lang["language"] + " ➜",
                        callback_data="settings",
                        style=ButtonStyle.SUCCESS,
                    ),
                    self.ikb(
                        text=lang_codes[language],
                        callback_data="language",
                        style=ButtonStyle.SUCCESS,
                    ),
                ],
                [
                    self.ikb(           
                        text="Report Issue",       
                        url=config.SUPPORT_CHAT,
                        style=ButtonStyle.PRIMARY,
                        icon_custom_emoji_id="5409132617750555920",
                   ),          
                ],
                [
                    self.ikb(
                        text="close",
                        callback_data="settings close",
                        style=ButtonStyle.PRIMARY,
                    ),
                ],
            ]
        )

    def start_key(
        self, lang: dict, private: bool = False
    ) -> types.InlineKeyboardMarkup:
        rows = [
            [
                self.ikb(
                    text=lang["add_me"],
                    url=f"https://t.me/{app.username}?startgroup=true",
                    style=ButtonStyle.SUCCESS,
                    icon_custom_emoji_id=5408838292231696180,
                )
            ],            
            [
                self.ikb(
                    text=lang["help"],
                    callback_data="help",
                    style=ButtonStyle.PRIMARY,
                    icon_custom_emoji_id="5247133031235329609",
                ),
                self.ikb(
                    text="ᴏᴡɴᴇʀ",
                    user_id=config.OWNER_ID,
                    style=ButtonStyle.DANGER,
                    icon_custom_emoji_id="5247176827016847212",
                ),
            ],
        ]
        if not private:
            rows += [
                [
                    self.ikb(
                        text=lang["language"],
                        callback_data="language",
                        style=ButtonStyle.PRIMARY,
                    )
                ]
            ]
        return self.ikm(rows)

    def yt_key(self, link: str) -> types.InlineKeyboardMarkup:
        return self.ikm(
            [
                [
                    self.ikb(text="❐", copy_text=link),
                    self.ikb(text="Youtube", url=link),
                ],
            ]
        )
