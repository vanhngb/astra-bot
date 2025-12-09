# bot.py
import os
import re
import sqlite3
import asyncio
from datetime import datetime, timedelta

import discord
from discord.ext import commands, tasks
from discord import Embed, ui, File
from flask import Flask
from threading import Thread
import pytz

# -----------------------
# CONFIG (Giữ nguyên từ code ban đầu)
# -----------------------
TOKEN = os.getenv('DISCORD_BOT_SECRET')
if not TOKEN:
    print("LỖI: Thiếu biến môi trường 'DISCORD_BOT_SECRET'. Không thể chạy bot.")
    exit()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# Channel / admin / role settings (theo bạn cung cấp)
WELCOME_CHANNEL_ID = 1432659040680284191
SUPPORT_CHANNEL_ID = 1432685282955755595
IMAGE_CHANNEL_FEMALE = 1432691499094769704
IMAGE_CHANNEL_MALE = 1432691597363122357
ADMIN_ID = 757555763559399424

# Channel nơi gửi IO + Donate messages
CHANNEL_IO_DNT = 1448047569421733981

# Channel gửi báo cáo hàng tháng
CHANNEL_MONTHLY_REPORT = 1448052039384043683

# ROLE name được phép dùng IO (nếu muốn đổi, chỉnh tên role này)
ALLOWED_ROLE_NAME = "Staff"

# Lương giờ cố định (VNĐ)
LUONG_GIO_RATE = 25000

# Timezone VN
VN_TZ = pytz.timezone("Asia/Ho_Chi_Minh")

# -----------------------
# Flask keep-alive (như code gốc)
# -----------------------
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

Thread(target=run).start()

# -----------------------
# SQLite DB setup
# -----------------------
DB_FILE = "luong.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        book_hours REAL DEFAULT 0,
        donate INTEGER DEFAULT 0,
        in_time TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        in_time TEXT,
        out_time TEXT,
        hours REAL,
        created_at TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS monthly_sent (
        ym TEXT PRIMARY KEY
    )
    """)
    conn.commit()
    conn.close()

def db_get_user(uid):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT user_id, book_hours, donate, in_time FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT INTO users(user_id, book_hours, donate, in_time) VALUES (?,0,0,NULL)", (uid,))
        conn.commit()
        cur.execute("SELECT user_id, book_hours, donate, in_time FROM users WHERE user_id=?", (uid,))
        row = cur.fetchone()
    conn.close()
    return {"user_id": row[0], "book_hours": float(row[1]), "donate": int(row[2]), "in_time": row[3]}

def db_update_user(uid, book_hours=None, donate=None, in_time=None):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    if book_hours is not None:
        cur.execute("UPDATE users SET book_hours=? WHERE user_id=?", (book_hours, uid))
    if donate is not None:
        cur.execute("UPDATE users SET donate=? WHERE user_id=?", (donate, uid))
    if in_time is not None:
        cur.execute("UPDATE users SET in_time=? WHERE user_id=?", (in_time, uid))
    conn.commit()
    conn.close()

def db_add_log(uid, in_time, out_time, hours):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    now = datetime.now(VN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("INSERT INTO logs(user_id, in_time, out_time, hours, created_at) VALUES (?,?,?,?,?)",
                (uid, in_time, out_time, hours, now))
    conn.commit()
    conn.close()

def db_get_logs(uid, limit=20):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT in_time, out_time, hours, created_at FROM logs WHERE user_id=? ORDER BY id DESC LIMIT ?", (uid, limit))
    rows = cur.fetchall()
    conn.close()
    return rows

def db_get_all_users():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT user_id, book_hours, donate FROM users")
    rows = cur.fetchall()
    conn.close()
    return rows

def db_monthly_sent_exists(ym):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM monthly_sent WHERE ym=?", (ym,))
    exists = cur.fetchone() is not None
    conn.close()
    return exists

def db_monthly_mark_sent(ym):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO monthly_sent(ym) VALUES (?)", (ym,))
    conn.commit()
    conn.close()

# initialize DB
init_db()

# -----------------------
# Helpers
# -----------------------
def format_vnd(amount):
    try:
        a = int(round(float(amount)))
    except:
        a = 0
    return f"{a:,} đ".replace(",", ".")

def has_io_permission(member: discord.Member):
    if member.guild_permissions.manage_guild:
        return True
    if member.id == ADMIN_ID:
        return True
    for r in member.roles:
        if r.name == ALLOWED_ROLE_NAME:
            return True
    return False

# -----------------------
# Keep-alive ping to healthchecks (from original)
# -----------------------
HC_PING_URL = os.getenv('HEALTHCHECKS_URL')

async def keep_alive_ping():
    if not HC_PING_URL:
        return
    await bot.wait_until_ready()
    import requests
    while not bot.is_closed():
        try:
            requests.get(HC_PING_URL, timeout=10)
        except Exception as e:
            print(f"Lỗi khi ping Healthchecks.io: {e}")
        await asyncio.sleep(14 * 60)

# -----------------------
# Commands: !luong, !reset, !io, !dnt
# -----------------------

@bot.command()
async def luong(ctx, member: discord.Member = None):
    """
    - !luong -> gửi embed DM cho chính user (chỉ họ thấy)
    - !luong @user -> chỉ admin (manage_guild or ADMIN_ID) có thể xem, gửi DM cho admin (không public)
    Embed fields:
    Giờ book:
    Lương giờ: (hours * 25k)
    Donate:
    Lương tổng: (Lương giờ + Donate)
    """
    # if member specified -> require admin perms
    if member:
        if not (ctx.author.guild_permissions.manage_guild or ctx.author.id == ADMIN_ID):
            await ctx.reply("Bạn không có quyền xem lương người khác.", delete_after=8)
            return
        target = member
    else:
        target = ctx.author

    u = db_get_user(str(target.id))
    hours = u["book_hours"] or 0.0
    donate = u["donate"] or 0
    luong_gio_amount = int(round(hours * LUONG_GIO_RATE))
    luong_tong = luong_gio_amount + donate

    embed = Embed(title=f"Lương của {target.display_name}", color=discord.Color.blue())
    embed.add_field(name="Giờ book:", value=f"{hours} giờ", inline=False)
    embed.add_field(name="Lương giờ:", value=f"{format_vnd(luong_gio_amount)}", inline=False)
    embed.add_field(name="Donate:", value=f"{format_vnd(donate)}", inline=False)
    embed.add_field(name="Lương tổng:", value=f"{format_vnd(luong_tong)}", inline=False)
    embed.set_footer(text=f"Lương giờ cố định: {format_vnd(LUONG_GIO_RATE)}/giờ")

    # send as DM to the command invoker (ctx.author)
    try:
        await ctx.author.send(embed=embed)
    except Exception:
        # fallback: if DM blocked, send ephemeral-style reply and delete after
        await ctx.reply("Không thể gửi DM — hãy bật tin nhắn riêng để nhận lương.", delete_after=8)

    # delete command message in channel to avoid lộ info
    try:
        if ctx.channel.type != discord.ChannelType.private:
            await ctx.message.delete()
    except Exception:
        pass

@bot.command()
@commands.has_permissions(administrator=True)
async def reset(ctx):
    """
    Reset toàn bộ lương (tất cả user). KHÔNG gửi thông báo.
    """
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("UPDATE users SET book_hours=0, donate=0, in_time=NULL")
    conn.commit()
    conn.close()
    # delete invoking message to be silent
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command()
async def io(ctx, time_str: str, member: discord.Member):
    """
    !io 2h @user
    - Kiểm tra permission: chỉ role allowed (Staff) hoặc manage_guild hoặc ADMIN_ID
    - Cộng hours vào book_hours của member
    - Gửi log vào channel CHANNEL_IO_DNT: "@user : <hours>"
    - Xóa message lệnh
    """
    # permission
    if not has_io_permission(ctx.author):
        await ctx.reply("Bạn không có quyền dùng lệnh này.", delete_after=8)
        return

    # parse format like "2h" or "2.5h"
    m = re.match(r"^(\d+(\.\d+)?)h$", time_str.lower())
    if not m:
        await ctx.reply("Sai format! Ví dụ: `!io 2h @user`", delete_after=8)
        return
    hours = float(m.group(1))

    uid = str(member.id)
    u = db_get_user(uid)
    new_hours = float(u.get("book_hours", 0.0)) + hours
    db_update_user(uid, book_hours=new_hours)

    # log into channel
    ch = bot.get_channel(CHANNEL_IO_DNT)
    if ch:
        try:
            await ch.send(f"<@{member.id}> : {hours} giờ")
        except Exception:
            pass

    # delete invoking message
    try:
        await ctx.message.delete()
    except Exception:
        pass

@bot.command()
async def dnt(ctx, amount: int, member: discord.Member):
    """
    !dnt 20000 @user
    - Cộng amount vào donate của member
    - Gửi log vào channel CHANNEL_IO_DNT: "@user donate : <amount>"
    - Xóa message lệnh
    """
    # permission: allow only admin or role? You requested that admin types used earlier.
    # We'll require the command caller has manage_guild or Staff role or is ADMIN_ID
    if not has_io_permission(ctx.author):
        await ctx.reply("Bạn không có quyền dùng lệnh này.", delete_after=8)
        return

    uid = str(member.id)
    u = db_get_user(uid)
    new_donate = int(u.get("donate", 0)) + int(amount)
    db_update_user(uid, donate=new_donate)

    ch = bot.get_channel(CHANNEL_IO_DNT)
    if ch:
        try:
            await ch.send(f"<@{member.id}> donate : {format_vnd(amount)}")
        except Exception:
            pass

    try:
        await ctx.message.delete()
    except:
        pass

# -----------------------
# Keep monthly report task
# -----------------------
@tasks.loop(minutes=10)
async def monthly_report_task():
    now = datetime.now(VN_TZ)
    # send once on day 1 at ~00:01 VN time
    if now.day == 1 and now.hour == 0 and 1 <= now.minute < 11:
        ym = now.strftime("%Y-%m")
        if db_monthly_sent_exists(ym):
            return
        rows = db_get_all_users()
        if not rows:
            db_monthly_mark_sent(ym)
            return
        ch = bot.get_channel(CHANNEL_MONTHLY_REPORT)
        if not ch:
            db_monthly_mark_sent(ym)
            return
        header = f"📊 **Báo cáo lương tháng {now.strftime('%Y-%m')}**\nLương giờ = {format_vnd(LUONG_GIO_RATE)}/giờ\n\n"
        msg = header
        for user_id, hours, donate in rows:
            pay_from_hours = int(round(float(hours) * LUONG_GIO_RATE))
            total = pay_from_hours + int(donate)
            msg += f"<@{user_id}> — Giờ: {hours} giờ | Lương giờ: {format_vnd(pay_from_hours)} | Donate: {format_vnd(donate)} | Tổng: {format_vnd(total)}\n"
            if len(msg) > 1800:
                try:
                    await ch.send(msg)
                except:
                    pass
                msg = ""
        if msg:
            try:
                await ch.send(msg)
            except:
                pass
        db_monthly_mark_sent(ym)

# -----------------------
# Keep-alive ping background (optional)
# -----------------------
@bot.event
async def on_ready():
    print(f'Bot đã đăng nhập như {bot.user} (id: {bot.user.id})')
    # start monthly report
    if not monthly_report_task.is_running():
        monthly_report_task.start()
    # start keepalive ping if provided
    if HC_PING_URL:
        bot.loop.create_task(keep_alive_ping())

# -----------------------
# Keep original helpers: post, time, qr, text (sửa lỗi view/time như yêu cầu)
# -----------------------

@bot.command()
async def text(ctx, *, content: str):
    if ctx.message.author.id == bot.user.id:
        return
    try:
        await ctx.message.delete()
    except:
        pass
    embed = Embed(description=content, color=discord.Color.from_rgb(255, 209, 220))
    try:
        avatar = ctx.author.avatar.url
    except:
        avatar = None
    if avatar:
        embed.set_footer(text=f"Sent by {ctx.author.display_name}", icon_url=avatar)
    else:
        embed.set_footer(text=f"Sent by {ctx.author.display_name}")
    await ctx.send(embed=embed)

@bot.command()
async def post(ctx, gender: str, *, caption: str = ""):
    if ctx.message.author.id == bot.user.id:
        return
    if len(ctx.message.attachments) == 0:
        await ctx.send("❌ Bạn chưa gửi ảnh kèm message!")
        return

    attachment = ctx.message.attachments[0]
    image_file = await attachment.to_file()

    if gender.lower() == "female":
        channel = bot.get_channel(IMAGE_CHANNEL_FEMALE)
    elif gender.lower() == "male":
        channel = bot.get_channel(IMAGE_CHANNEL_MALE)
    else:
        await ctx.send("❌ Giới tính không hợp lệ! Dùng `female` hoặc `male`.")
        return

    if not channel:
        await ctx.send("Lỗi: Không tìm thấy channel ảnh.")
        return

    embed = Embed(description=caption)
    embed.set_image(url=f"attachment://{attachment.filename}")

    class RentButton(ui.View):
        def __init__(self):
            super().__init__(timeout=None)

        @ui.button(label="Rent", style=discord.ButtonStyle.primary)
        async def rent(self, interaction: discord.Interaction, button: discord.ui.Button):
            guild = interaction.guild
            member = interaction.user

            if member.bot:
                await interaction.response.send_message("Bot không thể tương tác với nút này.", ephemeral=True)
                return

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                member: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.get_member(ADMIN_ID): discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            }

            temp_channel = await guild.create_text_channel(
                name="temp-rent-" + datetime.now().strftime("%H%M%S"),
                overwrites=overwrites
            )

            await temp_channel.send(f"Channel đã tạo cho {member.mention} . Bạn thuê Player nào ạ? Bạn đợi xíu bên mình phản hồi lại nhaaa.")

            class DoneButton(ui.View):
                def __init__(self):
                    super().__init__(timeout=None)

                @ui.button(label="Done", style=discord.ButtonStyle.danger)
                async def done(self, interaction2: discord.Interaction, button2: discord.ui.Button):
                    await temp_channel.delete()
                    await interaction2.response.send_message("✅ Channel đã xóa.", ephemeral=True)

            await temp_channel.send("Nhấn Done khi hoàn tất đơn nhé ạaaa.", view=DoneButton())
            await interaction.response.send_message(f"✅ Đã tạo channel : {temp_channel.mention}", ephemeral=True)

    await channel.send(embed=embed, file=image_file)
    await channel.send("Nhấn Rent để trao đổi nha khách iu ơi ⋆𐙚 ̊.", view=RentButton())
    await ctx.send("✅ Đã post bài thành công.")

@bot.command()
async def time(ctx, *, t: str):
    if ctx.message.author.id == bot.user.id:
        return

    t = t.lower().replace(" ", "")
    hours, minutes = 0, 0

    h_match = re.search(r'(\d+)h', t)
    m_match = re.search(r'(\d+)m', t)

    if h_match:
        hours = int(h_match.group(1))
    if m_match:
        minutes = int(m_match.group(1))

    if hours == 0 and minutes == 0:
        await ctx.send("Không nhận diện được thời gian! VD: !time 1h30m, !time 45m")
        return

    start_time_vn = datetime.now(VN_TZ)
    end_time_vn = start_time_vn + timedelta(hours=hours, minutes=minutes)

    await ctx.send(
        f"⏳ Oki vậy là mình bắt đầu từ **{start_time_vn.strftime('%H:%M:%S')}** (VN time) đến **{end_time_vn.strftime('%H:%M:%S')}** nha khách iu ơi ⋆𐙚 ̊."
    )

    total_seconds = hours * 3600 + minutes * 60
    await asyncio.sleep(total_seconds)

    final_end_time_vn = datetime.now(VN_TZ)
    await ctx.send(f"{ctx.author.mention} ⏰ Thời gian kết thúc: **{final_end_time_vn.strftime('%H:%M:%S')}**! Đã hết giờ.")

@bot.command()
async def qr(ctx):
    if ctx.message.author.id == bot.user.id:
        return

    embed = Embed(description="Sau khi thanh toán xong thì gửi bill vào đây nhá. Không ghi NDCK giúp mình nha ୨୧")
    qr_path = "qr.png"

    if os.path.exists(qr_path):
        qr_file = File(qr_path, filename="qr.png")
        embed.set_image(url="attachment://qr.png")
        await ctx.send(embed=embed, file=qr_file)
    else:
        await ctx.send("Không tìm thấy ảnh QR. " + embed.description, embed=embed)

# -----------------------
# Error handling
# -----------------------
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        # do not spam
        try:
            await ctx.message.delete()
        except:
            pass
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Thiếu tham số cho lệnh.", delete_after=6)
    else:
        print("Command error:", error)

# -----------------------
# Run bot
# -----------------------
if __name__ == '__main__':
    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"Bot gặp lỗi khi chạy: {e}")
        if "Bad Gateway" in str(e) or "HTTP 401" in str(e):
            print("\nLỖI: Hãy kiểm tra lại TOKEN DISCORD_BOT_SECRET đã chính xác chưa.")
