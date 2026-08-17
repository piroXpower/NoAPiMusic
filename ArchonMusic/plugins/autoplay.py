from pyrogram import filters, types

from ArchonMusic import app, db, lang
from ArchonMusic.helpers import can_manage_vc


@app.on_message(filters.command(["autoplay"]) & filters.group & ~app.bl_users)
@lang.language()
@can_manage_vc
async def _autoplay(_, m: types.Message):
    chat_id = m.chat.id

    if len(m.command) < 2:
        status = await db.get_autoplay(chat_id)
        return await m.reply_text(
            m.lang["autoplay_status"].format(
                m.lang["autoplay_on"] if status else m.lang["autoplay_off"]
            )
        )

    arg = m.command[1].lower()
    if arg in ["on", "enable"]:
        await db.set_autoplay(chat_id, True)
        return await m.reply_text(m.lang["autoplay_enabled"])
    elif arg in ["off", "disable"]:
        await db.set_autoplay(chat_id, False)
        return await m.reply_text(m.lang["autoplay_disabled"])

    return await m.reply_text(m.lang["autoplay_usage"])
