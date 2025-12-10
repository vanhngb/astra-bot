# bot_full_render.py
# Discord bot full-featured cho Render Web Service
# Python 3.11+, discord.py, SQLite

import os
import re
import sqlite3
import random
import asyncio
from datetime import datetime, timedelta

import pytz
import discord
from discord.ext import commands, tasks
from discord import Embed, File, ui
from quart import Quart

# -------------------------
# CONFIG
# -------------------------
TOKEN = os.getenv("DISCORD_BOT_SECRET")
if not TOKEN:
    print("ERROR: Please set DISCORD_BOT_SECRET environment variable.")
    exit(1)

# Channel & IDs
WELCOME_CHANNEL_ID = 1432658695719751793
SUPPORT_CHANNEL_ID = 1432685282955755595
IMAGE_CHANNEL_FEMALE = 1432691499094769704
IMAGE_CHANNEL_MALE = 1432691597363122357
CHANNEL_IO_DNT = 1448047569421733981
CHANNEL_MONTHLY_REPORT = 1448052039384043683

TRIGGER_VOICE_CREATE = 1432658695719751792  # auto create voice
EXEMPT_ROLE_ID = 1432670531529867295
ADMIN_ID = 757555763559399424

ALLOWED_ROLE_NAME = "Staff"
LUONG_GIO_RATE = 25000  # VNĐ/giờ
PASTEL_PINK = 0xFFB7D5
VN_TZ = pytz.timezone("Asia/Ho_Chi_Minh")

DB_FILE = "luong.db"

# -------------------------
# DATABASE
# -------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        book_hours INTEGER DEFAULT 0,
        donate INTEGER DEFAULT 0,
        in_time TEXT
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS prf (
        user_id TEXT PRIMARY KEY,
        prf_hours INTEGER DEFAULT 0,
        prf_donate INTEGER DEFAULT 0
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        in_time TEXT,
        out_time TEXT,
        hours INTEGER,
        created_at TEXT
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS rooms (
        voice_channel_id TEXT PRIMARY KEY,
        owner_id TEXT,
        is_hidden INTEGER DEFAULT 0,
        is_locked INTEGER DEFAULT 0
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS monthly_sent ( ym TEXT PRIMARY KEY )
    """)
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
# HELPERS
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

# DB helpers
def db_get_user(uid: str):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT user_id, book_hours, donate, in_time FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT INTO users(user_id, book_hours, donate, in_time) VALUES (?,?,?,NULL)", (uid,0,0))
        conn.commit()
        cur.execute("SELECT user_id, book_hours, donate, in_time FROM users WHERE user_id=?", (uid,))
        row = cur.fetchone()
    conn.close()
    return {"user_id": row[0], "book_hours": int(row[1]), "donate": int(row[2]), "in_time": row[3]}

def db_update_user(uid: str, book_hours=None, donate=None, in_time=None):
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

def db_prf_get(uid: str):
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

def db_prf_add_hours(uid: str, hours: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO prf(user_id, prf_hours, prf_donate) VALUES (?,?,?)", (uid,0,0))
    cur.execute("UPDATE prf SET prf_hours = prf_hours + ? WHERE user_id=?", (int(hours), uid))
    conn.commit()
    conn.close()

def db_prf_add_donate(uid: str, amount: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO prf(user_id, prf_hours, prf_donate) VALUES (?,?,?)", (uid,0,0))
    cur.execute("UPDATE prf SET prf_donate = prf_donate + ? WHERE user_id=?", (int(amount), uid))
    conn.commit()
    conn.close()

def db_add_room(voice_id: str, owner_id: str, is_hidden=0, is_locked=0):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO rooms(voice_channel_id, owner_id, is_hidden, is_locked) VALUES (?,?,?,?)",
                (voice_id, owner_id, is_hidden, is_locked))
    conn.commit()
    conn.close()

def db_get_room(voice_id: str):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT voice_channel_id, owner_id, is_hidden, is_locked FROM rooms WHERE voice_channel_id=?", (voice_id,))
    r = cur.fetchone()
    conn.close()
    if r:
        return {"voice_channel_id": r[0], "owner_id": r[1], "is_hidden": bool(r[2]), "is_locked": bool(r[3])}
    return None

def db_delete_room(voice_id: str):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM rooms WHERE voice_channel_id=?", (voice_id,))
    conn.commit()
    conn.close()

# -------------------------
# DISCORD BOT
# -------------------------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------------
# ON_READY
# -------------------------
@bot.event
async def on_ready():
    print(f"Bot online as {bot.user} (id: {bot.user.id})")

# -------------------------
# WELCOME MESSAGE
# -------------------------
@bot.event
async def on_member_join(member):
    ch = member.guild.get_channel(WELCOME_CHANNEL_ID)
    if ch:
        embed = Embed(
            description=f"Chào mừng {member.mention} đến với ⋆. 𐙚˚࿔ 𝒜𝓈𝓉𝓇𝒶 𝜗𝜚˚⋆, mong bạn ở đây thật vui nhá ^^ Có cần hỗ trợ gì thì ⁠<#{SUPPORT_CHANNEL_ID}> nhá",
            color=PASTEL_PINK
        )
        try:
            embed.set_thumbnail(url=member.avatar.url)
        except:
            pass
        await ch.send(embed=embed)

# -------------------------
# SIMPLE !luong / !prf
# -------------------------
@bot.command()
async def luong(ctx, member: discord.Member = None):
    target = member or ctx.author
    u = db_get_user(str(target.id))
    hours = u["book_hours"]
    donate = u["donate"]
    pay = hours*LUONG_GIO_RATE
    total = pay + donate
    embed = Embed(title=f"Lương {target.display_name}", color=PASTEL_PINK)
    embed.add_field(name="Giờ book:", value=f"{hours} giờ", inline=False)
    embed.add_field(name="Lương giờ:", value=f"{fmt_vnd(pay)}", inline=False)
    embed.add_field(name="Donate:", value=f"{fmt_vnd(donate)}", inline=False)
    embed.add_field(name="Tổng lương:", value=f"{fmt_vnd(total)}", inline=False)
    try:
        await ctx.author.send(embed=embed)
    except:
        await ctx.reply("Không thể gửi DM.", delete_after=6)
    try: await ctx.message.delete()
    except: pass

@bot.command()
async def prf(ctx):
    p = db_prf_get(str(ctx.author.id))
    embed = Embed(title="PRF", color=PASTEL_PINK)
    embed.add_field(name="Giờ đã book:", value=f"{p['prf_hours']} giờ", inline=False)
    embed.add_field(name="Đã donate:", value=f"{fmt_vnd(p['prf_donate'])}", inline=False)
    try:
        await ctx.author.send(embed=embed)
    except:
        await ctx.reply("Không thể gửi DM.", delete_after=6)
    try: await ctx.message.delete()
    except: pass

# -------------------------
# RUN WITH QUART (async web server)
# -------------------------
app = Quart(__name__)

@app.route("/")
async def home():
    return "Bot is running"

async def main():
    # Start bot
    asyncio.create_task(bot.start(TOKEN))
    # Start web server
    await app.run_task(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    asyncio.run(main())
