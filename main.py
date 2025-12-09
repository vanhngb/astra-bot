# bot_luong_sqlite.py
import discord
from discord.ext import commands, tasks
from discord import Embed, ui, File
from flask import Flask
from threading import Thread
import asyncio
from datetime import datetime, timedelta
import re
import os
import sqlite3
import pytz

# -----------------------
# CONFIG - chỉnh ở đây nếu cần
# -----------------------
TOKEN = os.getenv('DISCORD_BOT_SECRET')
if not TOKEN:
    print("LỖI: Thiếu biến môi trường 'DISCORD_BOT_SECRET'.")
    exit()

INTENTS = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=INTENTS)

# Channel + admin + role settings
WELCOME_CHANNEL_ID = 1432659040680284191
SUPPORT_CHANNEL_ID = 1432685282955755595
IMAGE_CHANNEL_FEMALE = 1432691499094769704
IMAGE_CHANNEL_MALE = 1432691597363122357
ADMIN_ID = 757555763559399424

# Channel nơi gửi IO + Donate messages (theo bạn)
CHANNEL_IO_DNT = 1448047569421733981

# Channel gửi báo cáo hàng tháng
CHANNEL_MONTHLY_REPORT = 1448052039384043683

# Role name được phép dùng IO (bạn có thể đổi tên role nếu muốn)
ALLOWED_ROLE_NAME = "Staff"

# Lương giờ cố định (VNĐ)
LUONG_GIO_RATE = 25000

# DB file
DB_FILE = "luong.db"

# Timezone VN
VN_TZ = pytz.timezone("Asia/Ho_Chi_Minh")

# -----------------------
# FLASK KEEP-ALIVE (không bắt buộc)
# -----------------------
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

Thread(target=run_flask).start()

# -----------------------
# Database helpers (SQLite)
# -----------------------
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
    return {"user_id": row[0], "book_hours": row[1], "donate": row[2], "in_time": row[3]}

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

# -----------------------
# Utility helpers
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
# Initialize DB
# -----------------------
init_db()

# -----------------------
# UI: Donate modal
# -----------------------
class DonateModal(ui.Modal):
    amount = ui.TextInput(label="Số tiền (VNĐ) - không dấu", placeholder="Ví dụ: 50000", required=True)

    def __init__(self, target_member: discord.Member | None = None):
        super().__init__(title="Donate")
        self.target_member = target_member

    async def on_submit(self, interaction: discord.Interaction):
        raw = re.sub(r"[^\d]", "", self.amount.value)
        if not raw:
            await interaction.response.send_message("Số tiền không hợp lệ.", ephemeral=True)
            return
        amount = int(raw)
        user = self.target_member or interaction.user
        uid = str(user.id)

        u = db_get_user(uid)
        new_donate = int(u["donate"]) + amount
        db_update_user(uid, donate=new_donate)

        # gửi message vào channel IO
        ch = bot.get_channel(CHANNEL_IO_DNT)
        content = f"<@{user.id}> donate : {format_vnd(amount)}"
        if ch:
            try:
                await ch.send(content)
            except:
                pass

        await interaction.response.send_message(f"Đã cộng {format_vnd(amount)} cho {user.display_name}.", ephemeral=True)

# -----------------------
# UI: IO modal (in/out)
# -----------------------
class IoModal(ui.Modal):
    in_time = ui.TextInput(label="In time (YYYY-MM-DD HH:MM hoặc HH:MM) - để trống nếu không IN", required=False)
    out_time = ui.TextInput(label="Out time (YYYY-MM-DD HH:MM hoặc HH:MM) - để trống nếu không OUT", required=False)
    hours = ui.TextInput(label="Số giờ (ví dụ: 2.5) - optional", required=False)

    def __init__(self, target_member: discord.Member | None = None):
        super().__init__(title="IN / OUT")
        self.target_member = target_member

    async def on_submit(self, interaction: discord.Interaction):
        user = self.target_member or interaction.user
        uid = str(user.id)
        u = db_get_user(uid)  # ensure exists
        now = datetime.now(VN_TZ)

        def parse_time_field(s):
            s = s.strip()
            if not s:
                return None
            # full date
            m_full = re.match(r"^(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2})$", s)
            m_short = re.match(r"^(\d{1,2}:\d{2})$", s)
            if m_full:
                try:
                    dt = datetime.strptime(f"{m_full.group(1)} {m_full.group(2)}", "%Y-%m-%d %H:%M")
                    return VN_TZ.localize(dt)
                except:
                    return None
            if m_short:
                try:
                    today = datetime.now(VN_TZ).strftime("%Y-%m-%d")
                    dt = datetime.strptime(f"{today} {m_short.group(1)}", "%Y-%m-%d %H:%M")
                    return VN_TZ.localize(dt)
                except:
                    return None
            return None

        parsed_in = parse_time_field(self.in_time.value) if self.in_time.value.strip() else None
        parsed_out = parse_time_field(self.out_time.value) if self.out_time.value.strip() else None
        parsed_hours = None
        if self.hours.value.strip():
            try:
                parsed_hours = float(re.sub(r"[^\d\.]", "", self.hours.value))
            except:
                parsed_hours = None

        # If only IN provided
        if parsed_in and not parsed_out and parsed_hours is None:
            db_update_user(uid, in_time=parsed_in.strftime("%Y-%m-%d %H:%M:%S"))
            ch = bot.get_channel(CHANNEL_IO_DNT)
            msg = f"<@{user.id}> : IN : {parsed_in.strftime('%Y-%m-%d %H:%M:%S')}"
            if ch:
                try:
                    await ch.send(msg)
                except:
                    pass
            await interaction.response.send_message(f"Đã lưu IN lúc {parsed_in.strftime('%Y-%m-%d %H:%M:%S')}", ephemeral=True)
            return

        # OUT handling
        computed_hours = None
        in_time_str = None
        out_time_str = None

        # if both parsed_in and parsed_out
        if parsed_in and parsed_out:
            delta = parsed_out - parsed_in
            computed_hours = round(delta.total_seconds() / 3600.0, 2)
            in_time_str = parsed_in.strftime("%Y-%m-%d %H:%M:%S")
            out_time_str = parsed_out.strftime("%Y-%m-%d %H:%M:%S")
        elif parsed_out and not parsed_in:
            # try stored in_time
            stored = u.get("in_time")
            if stored:
                try:
                    stored_dt = datetime.strptime(stored, "%Y-%m-%d %H:%M:%S")
                    stored_dt = VN_TZ.localize(stored_dt)
                    delta = parsed_out - stored_dt
                    computed_hours = round(delta.total_seconds() / 3600.0, 2)
                    in_time_str = stored_dt.strftime("%Y-%m-%d %H:%M:%S")
                    out_time_str = parsed_out.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    computed_hours = None
        elif parsed_hours is not None:
            computed_hours = round(parsed_hours, 2)
            out_time_str = now.strftime("%Y-%m-%d %H:%M:%S")
            in_time_str = u.get("in_time") or ""
        else:
            # fallback: if user has stored in_time and no parsed_out but hours not given -> cannot compute
            await interaction.response.send_message("Không đủ thông tin để OUT. Vui lòng cung cấp IN+OUT hoặc Số giờ.", ephemeral=True)
            return

        if computed_hours is None:
            await interaction.response.send_message("Không thể tính giờ từ dữ liệu cung cấp.", ephemeral=True)
            return

        # update book_hours and reset in_time
        new_hours = float(u.get("book_hours", 0.0)) + float(computed_hours)
        db_update_user(uid, book_hours=new_hours, in_time=None)
        db_add_log(uid, in_time_str or "", out_time_str or now.strftime("%Y-%m-%d %H:%M:%S"), computed_hours)

        # send message to IO channel
        ch = bot.get_channel(CHANNEL_IO_DNT)
        mention = f"<@{user.id}>"
        in_display = in_time_str or "N/A"
        out_display = out_time_str or now.strftime("%Y-%m-%d %H:%M:%S")
        msg = f"{mention} : {computed_hours} giờ. In : {in_display}, Out : {out_display}"
        if ch:
            try:
                await ch.send(msg)
            except:
                pass

        await interaction.response.send_message(f"OUT thành công. Đã cộng {computed_hours} giờ cho {user.display_name}.", ephemeral=True)

# -----------------------
# VIEW: Menu !luong
# -----------------------
class LuongView(ui.View):
    def __init__(self, target_member: discord.Member | None = None):
        super().__init__(timeout=None)
        self.target_member = target_member

    @ui.button(label="Xem lương", style=discord.ButtonStyle.primary, custom_id="view_salary")
    async def view_salary(self, button: ui.Button, interaction: discord.Interaction):
        member = self.target_member or interaction.user
        u = db_get_user(str(member.id))
        pay_from_hours = int(round(u["book_hours"] * LUONG_GIO_RATE))
        total = pay_from_hours + int(u["donate"])
        embed = Embed(title=f"Lương của {member.display_name}", color=discord.Color.green())
        embed.add_field(name="Giờ book:", value=f"{u['book_hours']} giờ", inline=False)
        embed.add_field(name="Lương giờ:", value=f"{format_vnd(pay_from_hours)}", inline=False)
        embed.add_field(name="Donate:", value=f"{format_vnd(u['donate'])}", inline=False)
        embed.add_field(name="Lương tổng:", value=f"{format_vnd(total)}", inline=False)
        embed.set_footer(text=f"Lương giờ cố định: {format_vnd(LUONG_GIO_RATE)}/giờ")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="IO (In/Out)", style=discord.ButtonStyle.secondary, custom_id="btn_io")
    async def btn_io(self, button: ui.Button, interaction: discord.Interaction):
        # permission check
        if not has_io_permission(interaction.user):
            await interaction.response.send_message("⚠️ Bạn không có quyền dùng IO.", ephemeral=True)
            return
        modal = IoModal(target_member=self.target_member or interaction.user)
        await interaction.response.send_modal(modal)

    @ui.button(label="Donate", style=discord.ButtonStyle.success, custom_id="btn_donate")
    async def btn_donate(self, button: ui.Button, interaction: discord.Interaction):
        modal = DonateModal(target_member=self.target_member or interaction.user)
        await interaction.response.send_modal(modal)

    @ui.button(label="Xem log", style=discord.ButtonStyle.gray, custom_id="btn_log")
    async def btn_log(self, button: ui.Button, interaction: discord.Interaction):
        member = self.target_member or interaction.user
        rows = db_get_logs(str(member.id), limit=12)
        if not rows:
            await interaction.response.send_message("Không có lịch sử IN/OUT.", ephemeral=True)
            return
        msg = f"📘 Lịch sử IN/OUT của {member.display_name} (12 gần nhất):\n"
        for in_t, out_t, hours, created_at in rows:
            msg += f"- IN: `{in_t}` OUT: `{out_t}` → {hours} giờ\n"
        await interaction.response.send_message(msg, ephemeral=True)

# -----------------------
# Command: !luong -> mở menu
# -----------------------
@bot.command()
async def luong(ctx, member: discord.Member = None):
    target = member or ctx.author
    # ensure user exists
    db_get_user(str(target.id))
    embed = Embed(title="📋 Menu Lương", description=f"Người dùng: {target.display_name}", color=discord.Color.blue())
    embed.add_field(name="Lưu ý", value="Lương giờ = 25.000đ/giờ. Lương tổng = (Giờ book * Lương giờ) + Donate", inline=False)
    embed.set_footer(text="Sử dụng các nút bên dưới để thao tác")
    view = LuongView(target_member=target)
    await ctx.send(embed=embed, view=view)

# -----------------------
# Command: !reset -> reset toàn bộ lương user
# Nếu có mention và người gọi có quyền manage_guild -> reset người đó
# Nếu không -> reset chính mình
# -----------------------
@bot.command()
async def reset(ctx, member: discord.Member = None):
    if member:
        # require manage_guild or admin
        if not (ctx.author.guild_permissions.manage_guild or ctx.author.id == ADMIN_ID):
            await ctx.send("Bạn không có quyền reset lương người khác.")
            return
        target = member
    else:
        target = ctx.author

    uid = str(target.id)
    db_update_user(uid, book_hours=0.0, donate=0, in_time=None)
    await ctx.send(f"✅ Đã reset toàn bộ lương của {target.display_name}.")

# -----------------------
# Command: !dnt (text-only fallback) -> nếu user muốn nhanh
# -----------------------
@bot.command()
async def dnt(ctx, amount: int):
    uid = str(ctx.author.id)
    u = db_get_user(uid)
    new_donate = int(u["donate"]) + int(amount)
    db_update_user(uid, donate=new_donate)
    ch = bot.get_channel(CHANNEL_IO_DNT)
    if ch:
        try:
            await ch.send(f"<@{ctx.author.id}> donate : {format_vnd(amount)}")
        except:
            pass
    await ctx.send(f"Đã ghi donate {format_vnd(amount)} cho bạn.")

# -----------------------
# Monthly report task - gửi báo cáo 1 lần / tháng
# Gửi vào channel CHANNEL_MONTHLY_REPORT lúc 00:01 ngày 1 (VN time)
# -----------------------
@tasks.loop(minutes=5)
async def monthly_report_task():
    now = datetime.now(VN_TZ)
    if now.day == 1 and now.hour == 0 and 1 <= now.minute < 6:
        ym = now.strftime("%Y-%m")
        if db_monthly_sent_exists(ym):
            return
        # compile report
        rows = db_get_all_users()
        if not rows:
            return
        channel = bot.get_channel(CHANNEL_MONTHLY_REPORT)
        if not channel:
            return
        header = f"📊 **Báo cáo lương tháng {now.strftime('%Y-%m')}**\nLương giờ = {format_vnd(LUONG_GIO_RATE)}/giờ\n\n"
        msg = header
        for user_id, hours, donate in rows:
            pay_from_hours = int(round(float(hours) * LUONG_GIO_RATE))
            total = pay_from_hours + int(donate)
            msg += f"<@{user_id}> — Giờ: {hours} giờ | Lương giờ: {format_vnd(pay_from_hours)} | Donate: {format_vnd(donate)} | Tổng: {format_vnd(total)}\n"
            if len(msg) > 1800:
                try:
                    await channel.send(msg)
                except:
                    pass
                msg = ""
        if msg:
            try:
                await channel.send(msg)
            except:
                pass
        # mark sent
        db_monthly_mark_sent(ym)

# -----------------------
# Keep-alive ping (healthchecks) optional - use env HEALTHCHECKS_URL
# -----------------------
HC_PING_URL = os.getenv('HEALTHCHECKS_URL')
async def keep_alive_ping():
    if not HC_PING_URL:
        return
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            import requests
            requests.get(HC_PING_URL, timeout=10)
        except Exception:
            pass
        await asyncio.sleep(14 * 60)

# -----------------------
# Existing commands you wanted to keep (post, time, qr, text) - adapted
# -----------------------
@bot.command()
async def text(ctx, *, content: str):
    if ctx.message.author.id == bot.user.id:
        return
    await ctx.message.delete()
    embed = Embed(description=content, color=discord.Color.from_rgb(255, 209, 220))
    embed.set_footer(text=f"Sent by {ctx.author.display_name}", icon_url=ctx.author.avatar.url)
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
    vn_tz = VN_TZ
    start_time_vn = datetime.now(vn_tz)
    end_time_vn = start_time_vn + timedelta(hours=hours, minutes=minutes)
    await ctx.send(
        f"⏳ Oki vậy là mình bắt đầu từ **{start_time_vn.strftime('%H:%M:%S')}** (VN time) đến **{end_time_vn.strftime('%H:%M:%S')}** nha khách iu ơi ⋆𐙚 ̊."
    )
    total_seconds = hours * 3600 + minutes * 60
    await asyncio.sleep(total_seconds)
    final_end_time_vn = datetime.now(vn_tz)
    await ctx.send(f"{ctx.author.mention} ⏰ Thời gian kết thúc: **{final_end_time_vn.strftime('%H:%M:%S')}**! Đã hết giờ.")

@bot.command()
async def qr(ctx):
    if ctx.message.author.id == bot.user.id:
        return
    embed = Embed(description="Sau khi thanh toán xong thì gửi bill vào đây nhá. Không ghi NDCK giúp mình nha ୨୧")
    qr_path = "qr.png"
    if os.path.exists(qr_path):
        await ctx.send(embed=embed, file=File(qr_path, filename="qr.png"))
    else:
        await ctx.send("Không tìm thấy ảnh QR.", embed=embed)

# -----------------------
# on_ready: start background tasks
# -----------------------
@bot.event
async def on_ready():
    print(f"Bot đã đăng nhập như {bot.user} (id: {bot.user.id})")
    # Start monthly report task if not running
    if not monthly_report_task.is_running():
        monthly_report_task.start()
    # start keep alive ping if env provided
    if HC_PING_URL := os.getenv('HEALTHCHECKS_URL'):
        bot.loop.create_task(keep_alive_ping())

# -----------------------
# monthly report loop
# -----------------------
@tasks.loop(minutes=5)
async def monthly_report_task():
    now = datetime.now(VN_TZ)
    # send at 00:01 on day 1
    if now.day == 1 and now.hour == 0 and 1 <= now.minute < 6:
        ym = now.strftime("%Y-%m")
        if db_monthly_sent_exists(ym):
            return
        rows = db_get_all_users()
        if not rows:
            return
        ch = bot.get_channel(CHANNEL_MONTHLY_REPORT)
        if not ch:
            return
        header = f"📊 **Báo cáo lương tháng {now.strftime('%Y-%m')}**\nLương giờ = {format_vnd(LUONG_GIO_RATE)}/giờ\n\n"
        msg = header
        for user_id, hours, donate in rows:
            pay = int(round(float(hours) * LUONG_GIO_RATE))
            total = pay + int(donate)
            msg += f"<@{user_id}> — Giờ: {hours} giờ | Lương giờ: {format_vnd(pay)} | Donate: {format_vnd(donate)} | Tổng: {format_vnd(total)}\n"
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
# basic error handler
# -----------------------
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("Bạn không có quyền thực hiện lệnh này.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Thiếu tham số.")
    else:
        print("Command error:", error)
        await ctx.send("Đã xảy ra lỗi khi thực thi lệnh.")

# -----------------------
# run bot
# -----------------------
if __name__ == "__main__":
    bot.run(TOKEN)
