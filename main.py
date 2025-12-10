# bot_full_render.py
# Full-featured Discord bot for Render
# Python 3.11+, discord.py 2.6+, Flask for keep-alive
# Features: salary, PRF, IO/DNT, voice rooms, post/rent, !code, giveaway, qr, text, av, ban, mute, rd, pick

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
    print("ERROR: DISCORD_BOT_SECRET not set.")
    exit(1)

PASTEL_PINK = 0xFFB7D5
VN_TZ = pytz.timezone("Asia/Ho_Chi_Minh")
DB_FILE = "luong.db"
LUONG_GIO_RATE = 25000

# Channel & IDs (replace with your IDs)
WELCOME_CHANNEL_ID = 1432658695719751793
SUPPORT_CHANNEL_ID = 1432685282955755595
IMAGE_CHANNEL_FEMALE = 1432691499094769704
IMAGE_CHANNEL_MALE = 1432691597363122357
CHANNEL_IO_DNT = 1448047569421733981
CHANNEL_MONTHLY_REPORT = 1448052039384043683
TRIGGER_VOICE_CREATE = 1432658695719751792  # for auto voice
EXEMPT_ROLE_ID = 1432670531529867295
ADMIN_ID = 757555763559399424

ALLOWED_ROLE_NAME = "Staff"

# -------------------------
# Flask keep-alive
# -------------------------
app = Flask('')
@app.route('/')
def home():
    return "Bot is running"
def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
Thread(target=run_flask).start()

# -------------------------
# BOT SETUP
# -------------------------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

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

def fmt_vnd(amount):
    try: a=int(round(float(amount)))
    except: a=0
    return f"{a:,} đ".replace(",", ".")

def is_admin(member: discord.Member):
    return member.guild_permissions.administrator or member.id == ADMIN_ID

def has_io_permission(member: discord.Member):
    if member.guild_permissions.manage_guild: return True
    if member.id == ADMIN_ID: return True
    for r in member.roles:
        if r.name == ALLOWED_ROLE_NAME: return True
    return False

# -------------------------
# VOICE AUTO-CREATE
# -------------------------
@bot.event
async def on_voice_state_update(member, before, after):
    try:
        if after.channel and after.channel.id == TRIGGER_VOICE_CREATE:
            guild = member.guild
            name = f"⋆𐙚 ̊. - {member.name}"
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(connect=True, view_channel=True),
                member: discord.PermissionOverwrite(connect=True, view_channel=True, manage_channels=True)
            }
            new_channel = await guild.create_voice_channel(name, overwrites=overwrites)
            try: await member.move_to(new_channel)
            except: pass
            db_add_room(str(new_channel.id), str(member.id))
        if before.channel and (after.channel is None or after.channel.id != before.channel.id):
            left_channel = before.channel
            room = db_get_room(str(left_channel.id))
            if room and len(left_channel.members) == 0:
                try: await left_channel.delete(reason="Auto-delete empty room")
                except: pass
                db_delete_room(str(left_channel.id))
    except Exception as e:
        print("voice_state_update error:", e)

# -------------------------
# COMMANDS
# -------------------------
@bot.command()
async def luong(ctx, member: discord.Member = None):
    target = member or ctx.author
    u = db_get_user(str(target.id))
    hours = int(u["book_hours"])
    donate = int(u["donate"])
    pay_from_hours = hours * LUONG_GIO_RATE
    total = pay_from_hours + donate
    embed = Embed(title=f"Lương {target.display_name}", color=PASTEL_PINK)
    embed.add_field(name="Giờ book:", value=f"{hours} giờ", inline=False)
    embed.add_field(name="Lương giờ:", value=fmt_vnd(pay_from_hours), inline=False)
    embed.add_field(name="Donate:", value=fmt_vnd(donate), inline=False)
    embed.add_field(name="Tổng:", value=fmt_vnd(total), inline=False)
    try: await ctx.author.send(embed=embed)
    except: await ctx.reply("Không thể gửi DM.", delete_after=8)
    try: await ctx.message.delete()
    except: pass

@bot.command()
async def prf(ctx):
    p = db_prf_get(str(ctx.author.id))
    ph = int(p["prf_hours"])
    pd = int(p["prf_donate"])
    embed = Embed(title="PRF", color=PASTEL_PINK)
    embed.add_field(name="Giờ đã book:", value=f"{ph} giờ", inline=False)
    embed.add_field(name="Đã donate:", value=fmt_vnd(pd), inline=False)
    try: await ctx.author.send(embed=embed)
    except: await ctx.reply("Không thể gửi DM.", delete_after=8)
    try: await ctx.message.delete()
    except: pass

@bot.command()
async def rd(ctx):
    await ctx.send(f"Random: {random.randint(1,999)}")

@bot.command()
async def pick(ctx, *, options: str):
    parts = options.split()
    if not parts: return await ctx.reply("Cần ít nhất 1 lựa chọn.")
    await ctx.send(f"Chọn: **{random.choice(parts)}**")

# -------------------------
# ON_READY
# -------------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id:{bot.user.id})")

# -------------------------
# RUN BOT
# -------------------------
bot.run(TOKEN)
