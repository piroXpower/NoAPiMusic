import re

from pyrogram import enums, errors, filters, types

from ArchonMusic import ArchonMusic, app, db, lang, queue, tg, yt
from ArchonMusic.helpers import admin_check, buttons


@app.on_callback_query(filters.regex("cancel_dl") & ~app.bl_users)
@lang.language()
async def cancel_dl(_, query: types.CallbackQuery):
    await query.answer()
    await tg.cancel(query)


@app.on_callback_query(filters.regex("controls") & ~app.bl_users)
@lang.language()
async def _controls(_, query: types.CallbackQuery):
    args = query.data.split()
    action, chat_id = args[1], int(args[2])
    qaction = len(args) == 4
    user = query.from_user.mention
    user_id = query.from_user.id

    if action != "autoplay":
        if user_id not in app.sudoers and not await db.is_auth(chat_id, user_id):
            admins = await db.get_admins(chat_id)
            if user_id not in admins:
                return await query.answer(query.lang["user_no_perms"], show_alert=True)

    if not await db.get_call(chat_id):
        try:
            return await query.answer(query.lang["not_playing"], show_alert=True)
        except errors.QueryIdInvalid:
            try:
                await query.message.delete()
            except Exception:
                pass
            return

    if action == "status":
        return await query.answer()
    await query.answer(query.lang["processing"], show_alert=True)

    if action == "pause":
        if not await db.playing(chat_id):
            return await query.answer(
                query.lang["play_already_paused"], show_alert=True
            )
        await ArchonMusic.pause(chat_id)
        if qaction:
            return await query.edit_message_reply_markup(
                reply_markup=buttons.queue_markup(chat_id, query.lang["paused"], False)
            )
        status = query.lang["paused"]
        reply = query.lang["play_paused"].format(user)

    elif action == "resume":
        if await db.playing(chat_id):
            return await query.answer(query.lang["play_not_paused"], show_alert=True)
        await ArchonMusic.resume(chat_id)
        if qaction:
            return await query.edit_message_reply_markup(
                reply_markup=buttons.queue_markup(chat_id, query.lang["playing"], True)
            )
        reply = query.lang["play_resumed"].format(user)

    elif action == "skip":
        await ArchonMusic.play_next(chat_id)
        status = query.lang["skipped"]
        reply = query.lang["play_skipped"].format(user)

    elif action == "force":
        pos, media = queue.check_item(chat_id, args[3])
        if not media or pos == -1:
            return await query.edit_message_text(query.lang["play_expired"])

        m_id = queue.get_current(chat_id).message_id
        queue.force_add(chat_id, media, remove=pos)
        try:
            await app.delete_messages(
                chat_id=chat_id, message_ids=[m_id, media.message_id], revoke=True
            )
            media.message_id = None
        except Exception:
            pass

        msg = await app.send_message(chat_id=chat_id, text=query.lang["play_next"])
        if not media.file_path:
            media.file_path = await yt.stream_url(media.id, video=media.video)
            if not media.file_path:
                media.file_path, _ = await yt.download(media.id, video=media.video)
        media.message_id = msg.id
        return await ArchonMusic.play_media(chat_id, msg, media)

    elif action == "replay":
        media = queue.get_current(chat_id)
        media.user = user
        await ArchonMusic.replay(chat_id)
        status = query.lang["replayed"]
        reply = query.lang["play_replayed"].format(user)

    elif action == "stop":
        await ArchonMusic.stop(chat_id)
        status = query.lang["stopped"]
        reply = query.lang["play_stopped"].format(user)

    elif action in ["more", "cthumb", "back"]:
        if action == "cthumb":
            thumb = not await db.get_thumb_mode(chat_id)
            await db.set_thumb_mode(chat_id, thumb)

        thumb = await db.get_thumb_mode(chat_id)

        keyboard = buttons.controls(
            chat_id,
            more=action != "back",
            thumb=thumb,
            autoplay=await db.get_autoplay(chat_id),
        )
        try:
            return await query.edit_message_reply_markup(reply_markup=keyboard)
        except Exception:
            return

    elif action == "close":
        try:
            return await query.message.delete()
        except Exception:
            return

    elif action == "autoplay":
        astatus = not await db.get_autoplay(chat_id)
        await db.set_autoplay(chat_id, astatus)
        keyboard = buttons.controls(chat_id, autoplay=astatus)
        try:
            return await query.edit_message_reply_markup(reply_markup=keyboard)
        except Exception:
            return

    try:
        if action in ["skip", "replay", "stop"]:
            await query.message.reply_text(reply, quote=False)
            await query.message.delete()
        else:
            mtext = re.sub(
                r"\n\n<blockquote>.*?</blockquote>",
                "",
                query.message.caption.html or query.message.text.html,
                flags=re.DOTALL,
            )
            keyboard = buttons.controls(
                chat_id,
                status=status if action != "resume" else None,
                autoplay=await db.get_autoplay(chat_id),
            )
        await query.edit_message_text(
            f"{mtext}\n\n<blockquote>{reply}</blockquote>", reply_markup=keyboard
        )
    except Exception:
        pass


@app.on_callback_query(filters.regex("help") & ~app.bl_users)
@lang.language()
async def _help(_, query: types.CallbackQuery):
    await query.answer()
    data = query.data.split()
    is_media = bool(query.message.photo or query.message.video)

    async def _render(text: str, markup):
        try:
            if is_media:
                return await query.edit_message_caption(
                    caption=text, reply_markup=markup
                )
            return await query.edit_message_text(text=text, reply_markup=markup)
        except Exception:
            return

    if len(data) == 1:
        return await _render(query.lang["help_menu"], buttons.help_markup(query.lang))

    if data[1] == "back":
        return await _render(query.lang["help_menu"], buttons.help_markup(query.lang))
    elif data[1] == "home":
        private = query.message.chat.type == enums.ChatType.PRIVATE
        _text = (
            query.lang["start_pm"].format(query.from_user.first_name, app.name)
            if private
            else query.lang["start_gp"].format(app.name)
        )
        return await _render(_text, buttons.start_key(query.lang, private))
    elif data[1] == "close":
        try:
            await query.message.delete()
            return await query.message.reply_to_message.delete()
        except Exception:
            return

    return await _render(
        query.lang[f"help_{data[1]}"], buttons.help_markup(query.lang, True)
    )


@app.on_callback_query(filters.regex("settings") & ~app.bl_users)
@lang.language()
@admin_check
async def _settings_cb(_, query: types.CallbackQuery):
    cmd = query.data.split()
    if len(cmd) == 1:
        return await query.answer()
    await query.answer(query.lang["processing"], show_alert=True)

    chat_id = query.message.chat.id
    _admin = await db.get_play_mode(chat_id)
    _delete = await db.get_cmd_delete(chat_id)
    _vclog = await db.get_vclogger(chat_id)
    _thumbnail = await db.get_thumb_mode(chat_id)
    _autoplay = await db.get_autoplay(chat_id)
    _language = await db.get_lang(chat_id)

    if cmd[1] == "delete":
        _delete = not _delete
        await db.set_cmd_delete(chat_id, _delete)
    elif cmd[1] == "play":
        await db.set_play_mode(chat_id, _admin)
        _admin = not _admin
    elif cmd[1] == "vclog":
        _vclog = not _vclog
        await db.set_vclogger(chat_id, _vclog)
    elif cmd[1] == "thumb":
        _thumbnail = not _thumbnail
        await db.set_thumb_mode(chat_id, _thumbnail)
    elif cmd[1] == "autoplay":
        _autoplay = not _autoplay
        await db.set_autoplay(chat_id, _autoplay)

    elif cmd[1] == "close":
       try:
         return await query.message.delete()
       except Exception:
         return

    await query.edit_message_reply_markup(
        reply_markup=buttons.settings_markup(
            query.lang,
            _admin,
            _delete,
            _vclog,
            _thumbnail,
            _autoplay,
            _language,
            chat_id,
        )
    )
