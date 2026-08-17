import asyncio
import speedtest
from pyrogram import filters
from pyrogram.types import Message

from ArchonMusic import app


@app.on_message(
    filters.command(["speedtest", "speed"])
    & ~app.bl_users
)
async def speedtest_cmd(_, m: Message):
    sent = await m.reply_text("⚡ <b>Running speedtest... Please wait.</b>")
    def _run_speedtest():
        st = speedtest.Speedtest()
        st.get_best_server()
        st.download()
        st.upload()
        st.results.share()
        return st.results.dict()

    try:
        results = await asyncio.to_thread(_run_speedtest)
        client_isp = results.get("client", {}).get("isp", "Unknown")
        client_country = results.get("client", {}).get("country", "IN")
        
        server_name = results.get("server", {}).get("name", "Unknown")
        server_country = f"{results.get('server', {}).get('country', 'India')}, {results.get('server', {}).get('cc', 'IN')}"
        server_sponsor = results.get("server", {}).get("sponsor", "Unknown")
        latency = results.get("server", {}).get("latency", 0.0)
        ping = results.get("ping", 0.0)
        image_url = results.get("share")

        text = (
            "<b>✯ sᴩєєᴅᴛєsᴛ ʀєsυʟᴛs ✯</b>\n\n"
            "<b>ᴄʟɪєηᴛ :</b>\n"
            f"<b>❖ ɪsᴩ :</b> {client_isp}\n"
            f"<b>❖ ᴄσυηᴛʀʏ :</b> {client_country}\n\n"
            "<b>sєʀᴠєʀ :</b>\n"
            f"<b>❖ ηᴧϻє :</b> {server_name}\n"
            f"<b>❖ ᴄσυηᴛʀʏ :</b> {server_country}\n"
            f"<b>❖ sᴩσηsσʀ :</b> {server_sponsor}\n"
            f"<b>❖ ʟᴧᴛєηᴄʏ :</b> {latency}\n"
            f"<b>❖ ᴩɪηɢ :</b> {ping}"
        )

        try:
            await sent.delete()
        except Exception:
            pass

        if image_url:
            try:
                await m.reply_photo(photo=image_url, caption=text)
                return
            except Exception:
                pass

        await m.reply_text(text)

    except Exception as ex:
        await sent.edit_text(f"❌ <b>Speedtest Error:</b> {ex}")
