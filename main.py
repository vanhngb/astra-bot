# bot_full_v2.py
# Full-featured Discord bot per user's spec (single file, no modal)
# Requirements: discord.py >= 2.0, pytz, flask
# Python 3.11+ recommended
# Set DISCORD_BOT_SECRET environment variable

import os
import re
import sqlite3
import random
import asyncio
from datetime import datetime, timedelta
from threading import Thread

import pytz
import discord
from discord.ext import commands, tasks
from discord import Embed, File, ui
from flask import Flask

# -------------------------
# CONFIG
# -------------------------
TOKEN = os.getenv("DISCORD_BOT_SECRET")
if not TOKEN:
    print("ERROR: Please set DISCORD_BOT_SECRET environment variable.")
    exit(1)

WELCOME_CHANNEL_ID = 1432658695719751793  # Welcome nhỏ
SUPPORT_CHANNEL_ID = 1432685282955755595
IMAGE_CHANNEL_FEMALE = 1432691499094769704
IMAGE_CHANNEL_MALE = 1432691597363122357

RENT_CATEGORY_ID = 1448062526599205037
VOICE_CATEGORY_ID = 1432658695719751792

TRIGGER_VOICE_CREATE = 1432658695719751794
TRIGGER_VOICE_PRIVATE = 1448063002518487092

EXEMPT_ROLE_ID = 1432670531529867295
ADMIN_ID = 757555763559399424
ALLOWED_ROLE_NAME = "Staff"

CHANNEL_IO_DNT = 1448047569421733981
CHANNEL_LUONG_ALL = 1448052039384043683

LUONG_GIO_RATE = 25000
PASTEL_PINK = 0xFFB7D5
VN_TZ = pytz.timezone("Asia/Ho_Chi_Minh")
DB_FILE = "luong.db"

# -------------------------
# Flask keep-alive
# -------------------------
app = Flask("")
@app.route("/")
def home():
    return "Bot is running"
def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
Thread(target=run_flask).start()

# -------------------------
# Bot init
# -------------------------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------------
# Database init
# -------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        book_hours INTEGER DEFAULT 0,
        donate INTEGER DEFAULT 0
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS prf (
        user_id TEXT PRIMARY KEY,
        prf_hours INTEGER DEFAULT 0,
        prf_donate INTEGER DEFAULT 0
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT UNIQUE,
        target_user_id TEXT,
        content TEXT,
        image_url TEXT
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS rooms (
        voice_channel_id TEXT PRIMARY KEY,
        owner_id TEXT,
        is_hidden INTEGER DEFAULT 0,
        is_locked INTEGER DEFAULT 0
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS giveaways (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id TEXT,
        message_id TEXT,
        title TEXT,
        winners INTEGER,
        host_id TEXT,
        end_at TEXT,
        ended INTEGER DEFAULT 0
    )""")
    conn.commit()
    conn.close()
init_db()

# -------------------------
# DB helpers
# -------------------------
def db_get_user(uid):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT user_id, book_hours, donate FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT INTO users(user_id, book_hours, donate) VALUES (?,?,?)", (uid,0,0))
        conn.commit()
        cur.execute("SELECT user_id, book_hours, donate FROM users WHERE user_id=?", (uid,))
        row = cur.fetchone()
    conn.close()
    return {"user_id": row[0], "book_hours": int(row[1]), "donate": int(row[2])}

def db_update_user(uid, book_hours=None, donate=None):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    if book_hours is not None:
        cur.execute("UPDATE users SET book_hours=? WHERE user_id=?", (int(book_hours), uid))
    if donate is not None:
        cur.execute("UPDATE users SET donate=? WHERE user_id=?", (int(donate), uid))
    conn.commit()
    conn.close()

def db_prf_get(uid):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT prf_hours, prf_donate FROM prf WHERE user_id=?", (uid,))
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT INTO prf(user_id, prf_hours, prf_donate) VALUES (?,?,?)", (uid,0,0))
        conn.commit()
        cur.execute("SELECT prf_hours, prf_donate FROM prf WHERE user_id=?", (uid,))
        row = cur.fetchone()
    conn.close()
    return {"prf_hours": int(row[0]), "prf_donate": int(row[1])}

def db_prf_add_hours(uid, hours):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO prf(user_id, prf_hours, prf_donate) VALUES (?,?,?)", (uid,0,0))
    cur.execute("UPDATE prf SET prf_hours = prf_hours + ? WHERE user_id=?", (int(hours), uid))
    conn.commit()
    conn.close()

def db_prf_add_donate(uid, amount):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO prf(user_id, prf_hours, prf_donate) VALUES (?,?,?)", (uid,0,0))
    cur.execute("UPDATE prf SET prf_donate = prf_donate + ? WHERE user_id=?", (int(amount), uid))
    conn.commit()
    conn.close()

def db_save_code(title, target_user_id, content, image_url=None):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO codes(title, target_user_id, content, image_url) VALUES (?,?,?,?)",
                (title, str(target_user_id), content, image_url))
    conn.commit()
    conn.close()

def db_get_code_by_title(title):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT title, target_user_id, content, image_url FROM codes WHERE title=?", (title,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {"title": row[0], "target_user_id": row[1], "content": row[2], "image_url": row[3]}
    return None

def db_delete_code_by_user_id(target_user_id):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM codes WHERE target_user_id=?", (str(target_user_id),))
    conn.commit()
    conn.close()

def db_get_all_users():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT user_id, book_hours, donate FROM users")
    rows = cur.fetchall()
    conn.close()
    return rows

# -------------------------
# Helpers
# -------------------------
def fmt_vnd(amount):
    try:
        a = int(round(float(amount)))
    except:
        a = 0
    return f"{a:,} đ".replace(",", ".")

def is_admin(member: discord.Member):
    return member.guild_permissions.administrator or member.id == ADMIN_ID

def has_io_permission(member: discord.Member):
    if member.guild_permissions.manage_guild:
        return True
    if member.id == ADMIN_ID:
        return True
    for r in member.roles:
        if r.name == ALLOWED_ROLE_NAME:
            return True
    return False

# -------------------------
# Welcome small
# -------------------------
@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if not channel:
        return
    av_url = member.avatar.url if member.avatar else member.default_avatar.url
    embed = Embed(description=f"Chào mừng {member.mention} đến với ⋆. 𐙚˚࿔ 𝒜𝓈𝓉𝓇𝒶 𝜗𝜚˚⋆", color=PASTEL_PINK)
    embed.set_thumbnail(url=av_url)
    try:
        await channel.send(embed=embed)
    except:
        pass

# -------------------------
# Giveaway (text-based, countdown)
# -------------------------
class Giveaway:
    def __init__(self, channel, title, winners, host_id, duration_seconds):
        self.channel = channel
        self.title = title
        self.winners = winners
        self.host_id = host_id
        self.duration_seconds = duration_seconds
        self.end_time = datetime.now(VN_TZ) + timedelta(seconds=duration_seconds)
        self.message = None

async def run_giveaway(g: Giveaway):
    embed = Embed(title=f"🎉 {g.title}", description=f"Hosted by: <@{g.host_id}>\nWinners: {g.winners}\nEnds at: {g.end_time.strftime('%H:%M:%S')}", color=PASTEL_PINK)
    msg = await g.channel.send(embed=embed)
    await msg.add_reaction("🎉")
    g.message = msg
    await asyncio.sleep(g.duration_seconds)
    # fetch reactions
    try:
        gmsg = await g.channel.fetch_message(msg.id)
        users = set()
        for react in gmsg.reactions:
            if react.emoji == "🎉":
                async for u in react.users():
                    if not u.bot:
                        users.add(u.id)
        winners_list = random.sample(list(users), min(len(users), g.winners)) if users else []
        announce = f"🎊 Giveaway ended! Winners: {', '.join(f'<@{w}>' for w in winners_list) if winners_list else 'No participants.'}"
        await g.channel.send(announce)
    except:
        pass

@bot.command()
async def gw(ctx):
    await ctx.send("Hãy nhập thông tin Giveaway theo format:\n`Tiêu đề | Winners | Số lượng | Hosted by (optional) | Time (vd: 15m)`")
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    try:
        msg = await bot.wait_for("message", check=check, timeout=300)
        parts = [p.strip() for p in msg.content.split("|")]
        if len(parts) < 4:
            await ctx.send("Sai format, hãy thử lại.")
            return
        title = parts[0]
        winners = int(parts[1])
        host_text = parts[3] if len(parts) > 3 else ""
        time_text = parts[4] if len(parts) > 4 else "1m"
        host_id = None
        h = re.findall(r'<@!?(\d+)>', host_text)
        if h:
            host_id = h[0]
        else:
            host_id = str(ctx.author.id)
        # parse duration
        matches = re.findall(r'(\d+)([smhd])', time_text)
        total_seconds = 0
        for qty, unit in matches:
            q = int(qty)
            if unit=='s': total_seconds+=q
            elif unit=='m': total_seconds+=q*60
            elif unit=='h': total_seconds+=q*3600
            elif unit=='d': total_seconds+=q*86400
        g = Giveaway(ctx.channel, title, winners, host_id, total_seconds)
        await run_giveaway(g)
        await ctx.send(f"🎉 Giveaway `{title}` đã được tạo! Tham gia bằng reaction 🎉")
    except asyncio.TimeoutError:
        await ctx.send("Timeout, không nhận input giveaway.")

# -------------------------
# Code create / edit / rm
# -------------------------
@bot.command()
async def code(ctx):
    await ctx.send("Nhập format:\n`Ping | Nội dung | Image URL (optional)`")
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    try:
        msg = await bot.wait_for("message", check=check, timeout=300)
        parts = [p.strip() for p in msg.content.split("|")]
        if len(parts)<2:
            await ctx.send("Sai format")
            return
        title = parts[0]
        content = parts[1]
        image_url = parts[2] if len(parts)>2 else None
        db_save_code(title, str(ctx.author.id), content, image_url)
        await ctx.send(f"Đã lưu code `{title}`")
    except asyncio.TimeoutError:
        await ctx.send("Timeout, hủy tạo code.")

@bot.command()
async def code_edit(ctx, *, title=None):
    if not title:
        await ctx.send("VD: !code_edit <Ping>")
        return
    data = db_get_code_by_title(title)
    if not data:
        await ctx.send("Không tìm thấy code")
        return
    await ctx.send(f"Code hiện tại: Nội dung: {data['content']}, Image: {data['image_url']}\nNhập nội dung mới (format: Nội dung | Image URL)")
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    try:
        msg = await bot.wait_for("message", check=check, timeout=300)
        parts = [p.strip() for p in msg.content.split("|")]
        content = parts[0]
        image_url = parts[1] if len(parts)>1 else None
        db_save_code(title, str(data['target_user_id']), content, image_url)
        await ctx.send(f"Đã cập nhật code `{title}`")
    except asyncio.TimeoutError:
        await ctx.send("Timeout, hủy edit code.")

@bot.command()
async def code_rm(ctx, member: discord.Member = None):
    if not member:
        await ctx.send("Cần tag user để xóa code")
        return
    db_delete_code_by_user_id(str(member.id))
    await ctx.send(f"Đã xóa code của {member.display_name}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    await bot.process_commands(message)
    title = message.content.strip()
    data = db_get_code_by_title(title)
    if data:
        mention = f"<@{data['target_user_id']}>"
        content = data["content"]
        image_url = data["image_url"]
        embed = Embed(description=f"{mention} {content}", color=PASTEL_PINK)
        if image_url:
            embed.set_image(url=image_url)
        await message.channel.send(embed=embed)

# -------------------------
# Voice menu
# -------------------------
class VoiceMenu(ui.View):
    def __init__(self, channel):
        super().__init__(timeout=None)
        self.channel = channel

    @ui.button(label="Lock", style=discord.ButtonStyle.danger)
    async def lock(self, interaction: discord.Interaction, button: ui.Button):
        await self.channel.set_permissions(interaction.guild.default_role, connect=False)
        await interaction.response.send_message("Voice đã khóa", ephemeral=True)

    @ui.button(label="Unlock", style=discord.ButtonStyle.success)
    async def unlock(self, interaction: discord.Interaction, button: ui.Button):
        await self.channel.set_permissions(interaction.guild.default_role, connect=True)
        await interaction.response.send_message("Voice đã mở", ephemeral=True)

    @ui.button(label="Hide", style=discord.ButtonStyle.secondary)
    async def hide(self, interaction: discord.Interaction, button: ui.Button):
        await self.channel.set_permissions(interaction.guild.default_role, view_channel=False)
        await interaction.response.send_message("Voice đã ẩn", ephemeral=True)

    @ui.button(label="Invite", style=discord.ButtonStyle.primary)
    async def invite(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("Tag @user để invite:", ephemeral=True)
        def check(m):
            return m.author == interaction.user and m.channel == interaction.channel
        try:
            msg = await bot.wait_for("message", check=check, timeout=60)
            mentions = msg.mentions
            if mentions:
                for u in mentions:
                    await self.channel.set_permissions(u, connect=True, view_channel=True)
                await interaction.followup.send(f"Đã invite {', '.join([u.name for u in mentions])}", ephemeral=True)
            else:
                await interaction.followup.send("Không tìm thấy user nào", ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send("Timeout invite", ephemeral=True)

# -------------------------
# Voice create / delete on leave
# -------------------------
@bot.event
async def on_voice_state_update(member, before, after):
    try:
        # Public trigger
        if (before.channel != after.channel) and after.channel and after.channel.id == TRIGGER_VOICE_CREATE:
            guild = member.guild
            category = discord.utils.get(guild.categories, id=VOICE_CATEGORY_ID)
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(connect=True, view_channel=True),
                member: discord.PermissionOverwrite(connect=True, view_channel=True)
            }
            new_voice = await guild.create_voice_channel(f"⋆𐙚 ̊. - {member.name}", overwrites=overwrites, category=category)
            await member.move_to(new_voice)
            await new_voice.send("Voice menu:", view=VoiceMenu(new_voice))
            return
        # Private trigger
        if (before.channel != after.channel) and after.channel and after.channel.id == TRIGGER_VOICE_PRIVATE:
            guild = member.guild
            category = discord.utils.get(guild.categories, id=VOICE_CATEGORY_ID)
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=True),
                member: discord.PermissionOverwrite(connect=True, view_channel=True),
                guild.get_member(ADMIN_ID): discord.PermissionOverwrite(connect=True, view_channel=True)
            }
            new_voice = await guild.create_voice_channel(f"⋆𐙚 ̊. - {member.name}", overwrites=overwrites, category=category)
            await member.move_to(new_voice)
            await new_voice.send("Voice menu:", view=VoiceMenu(new_voice))
            return
        # Delete empty voice channels in our category
        if before.channel and before.channel.category_id == VOICE_CATEGORY_ID:
            if len(before.channel.members) == 0:
                await before.channel.delete()
    except:
        pass

# -------------------------
# Lương / PRF
# -------------------------
@bot.command()
async def luong(ctx, member: discord.Member = None):
    member = member or ctx.author
    u = db_get_user(str(member.id))
    p = db_prf_get(str(member.id))
    total_hours = u["book_hours"] + p["prf_hours"]
    total_donate = u["donate"] + p["prf_donate"]
    total_vnd = total_hours * LUONG_GIO_RATE + total_donate
    embed = Embed(title=f"Lương {member.display_name}", color=PASTEL_PINK)
    embed.add_field(name="Book hours", value=f"{u['book_hours']}h", inline=True)
    embed.add_field(name="PRF hours", value=f"{p['prf_hours']}h", inline=True)
    embed.add_field(name="Donate", value=fmt_vnd(u['donate'] + p['prf_donate']), inline=False)
    embed.add_field(name="Tổng VND", value=fmt_vnd(total_vnd), inline=False)
    await ctx.send(embed=embed)

# -------------------------
# Bot run
# -------------------------
bot.run(TOKEN)
