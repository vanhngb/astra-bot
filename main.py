# bot_full.py
# Full-featured Discord bot per user's spec (single file)
# Requirements: discord.py >= 2.0, pytz, flask
# Python 3.11 recommended
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

# IDs and settings (as requested)
WELCOME_CHANNEL_ID = 1432659040680284191
SUPPORT_CHANNEL_ID = 1432685282955755595
IMAGE_CHANNEL_FEMALE = 1432691499094769704  # !post fm
IMAGE_CHANNEL_MALE = 1432691597363122357    # !post m

RENT_CATEGORY_ID = 1448062526599205037

TRIGGER_VOICE_CREATE = 1432658695719751794
TRIGGER_VOICE_PRIVATE = 1448063002518487092
VOICE_CATEGORY_ID = 1432658695719751792

EXEMPT_ROLE_ID = 1432670531529867295
ADMIN_ID = 757555763559399424

ALLOWED_ROLE_NAME = "Staff"

CHANNEL_IO_DNT = 1448047569421733981
CHANNEL_MONTHLY_REPORT = 1448052039384043683

LUONG_GIO_RATE = 25000
PASTEL_PINK = 0xFFB7D5

VN_TZ = pytz.timezone("Asia/Ho_Chi_Minh")

DB_FILE = "luong.db"

# Keep-alive Flask
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
        is_locked INTEGER DEFAULT 0,
        text_channel_id TEXT
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
    cur.execute("""
    CREATE TABLE IF NOT EXISTS monthly_sent ( ym TEXT PRIMARY KEY )
    """)
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

def db_add_room(voice_id, owner_id, is_hidden=0, is_locked=0, text_channel_id=None):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO rooms(voice_channel_id, owner_id, is_hidden, is_locked, text_channel_id) VALUES (?,?,?,?,?)",
                (str(voice_id), str(owner_id), int(is_hidden), int(is_locked), str(text_channel_id) if text_channel_id else None))
    conn.commit()
    conn.close()

def db_get_room_by_voice(voice_id):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT voice_channel_id, owner_id, is_hidden, is_locked, text_channel_id FROM rooms WHERE voice_channel_id=?", (str(voice_id),))
    r = cur.fetchone()
    conn.close()
    if r:
        return {"voice_channel_id": r[0], "owner_id": r[1], "is_hidden": bool(r[2]), "is_locked": bool(r[3]), "text_channel_id": r[4]}
    return None

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
# Welcome banner with avatar
# -------------------------
@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if not channel:
        return
    try:
        av_url = member.avatar.url if member.avatar else member.default_avatar.url
    except:
        av_url = None
    # Big banner embed
    embed = Embed(title=f"Chào mừng {member.display_name}!", description=f"Chào mừng {member.mention} đến với ⋆. 𐙚˚࿔ 𝒜𝓈𝓉𝓇𝒶 𝜗𝜚˚⋆, mong bạn ở đây thật vui nhá ^^\nCó cần hỗ trợ gì thì <#{SUPPORT_CHANNEL_ID}> nhá", color=PASTEL_PINK)
    if av_url:
        # Use thumbnail + image placeholder to make banner-like
        embed.set_thumbnail(url=av_url)
        # Optionally put avatar as image (discord will show)
        embed.set_image(url=av_url)
    embed.set_footer(text=f"Joined at {datetime.now(VN_TZ).strftime('%Y-%m-%d %H:%M:%S')}")
    try:
        await channel.send(embed=embed)
    except:
        pass

# -------------------------
# Room Control View (buttons) and Invite modal
# -------------------------
class InviteModal(ui.Modal):
    user_mention = ui.TextInput(label="Nhập mention user (vd: @user)", required=True, placeholder="@user")
    def __init__(self, channel_id):
        super().__init__(title="Invite user")
        self.channel_id = channel_id
    async def on_submit(self, interaction: discord.Interaction):
        text = self.user_mention.value.strip()
        mentions = re.findall(r'<@!?(\d+)>', text)
        if not mentions:
            await interaction.response.send_message("Không tìm thấy mention.", ephemeral=True)
            return
        ch = interaction.guild.get_channel(int(self.channel_id))
        if not ch:
            await interaction.response.send_message("Channel không tồn tại.", ephemeral=True)
            return
        for uid in mentions:
            member = interaction.guild.get_member(int(uid))
            if member:
                try:
                    await ch.set_permissions(member, view_channel=True, connect=True, read_messages=True, send_messages=True)
                except:
                    pass
        await interaction.response.send_message("Đã invite (không gửi thông báo).", ephemeral=True)

class RoomControlView(ui.View):
    def __init__(self, voice_id:int, owner_id:int, text_channel_id:int):
        super().__init__(timeout=None)
        self.voice_id = str(voice_id)
        self.owner_id = str(owner_id)
        self.text_channel_id = text_channel_id

    def _is_allowed(self, guild, user:discord.Member):
        # allowed if admin or exempt role or inside voice channel
        if is_admin(user):
            return True
        for r in user.roles:
            if r.id == EXEMPT_ROLE_ID:
                return True
        # if user is in voice channel
        ch = guild.get_channel(int(self.voice_id))
        if ch and any(m.id == user.id for m in ch.members):
            return True
        return False

    async def _get_voice(self, guild):
        return guild.get_channel(int(self.voice_id))

    async def _get_text(self, guild):
        if self.text_channel_id:
            return guild.get_channel(int(self.text_channel_id))
        return None

    @ui.button(label="Lock room", style=discord.ButtonStyle.danger)
    async def lock(self, button: ui.Button, interaction: discord.Interaction):
        guild = interaction.guild
        if not self._is_allowed(guild, interaction.user):
            return await interaction.response.send_message("Bạn không có quyền.", ephemeral=True)
        vch = await self._get_voice(guild)
        if not vch:
            return await interaction.response.send_message("Voice channel không tồn tại.", ephemeral=True)
        try:
            await vch.set_permissions(guild.default_role, connect=False)
            db_add_room(str(self.voice_id), self.owner_id, is_hidden=0, is_locked=1, text_channel_id=self.text_channel_id)
            await interaction.response.send_message("Đã khóa room.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Lỗi: {e}", ephemeral=True)

    @ui.button(label="Unlock room", style=discord.ButtonStyle.success)
    async def unlock(self, button: ui.Button, interaction: discord.Interaction):
        guild = interaction.guild
        if not self._is_allowed(guild, interaction.user):
            return await interaction.response.send_message("Bạn không có quyền.", ephemeral=True)
        vch = await self._get_voice(guild)
        if not vch:
            return await interaction.response.send_message("Voice channel không tồn tại.", ephemeral=True)
        try:
            await vch.set_permissions(guild.default_role, connect=True, view_channel=True)
            db_add_room(str(self.voice_id), self.owner_id, is_hidden=0, is_locked=0, text_channel_id=self.text_channel_id)
            await interaction.response.send_message("Đã mở khóa room.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Lỗi: {e}", ephemeral=True)

    @ui.button(label="Hide", style=discord.ButtonStyle.secondary)
    async def hide(self, button: ui.Button, interaction: discord.Interaction):
        guild = interaction.guild
        if not self._is_allowed(guild, interaction.user):
            return await interaction.response.send_message("Bạn không có quyền.", ephemeral=True)
        vch = await self._get_voice(guild)
        if not vch:
            return await interaction.response.send_message("Voice channel không tồn tại.", ephemeral=True)
        try:
            await vch.set_permissions(guild.default_role, view_channel=False, connect=False)
            # ensure owner and exempt role can still view/connect
            owner = guild.get_member(int(self.owner_id))
            if owner:
                await vch.set_permissions(owner, view_channel=True, connect=True)
            ex_role = guild.get_role(EXEMPT_ROLE_ID)
            if ex_role:
                await vch.set_permissions(ex_role, view_channel=True, connect=True)
            db_add_room(str(self.voice_id), self.owner_id, is_hidden=1, is_locked=1, text_channel_id=self.text_channel_id)
            await interaction.response.send_message("Đã ẩn room (chỉ admin/exempt/owner thấy).", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Lỗi: {e}", ephemeral=True)

    @ui.button(label="Invite", style=discord.ButtonStyle.primary)
    async def invite(self, button: ui.Button, interaction: discord.Interaction):
        if not self._is_allowed(interaction.guild, interaction.user):
            return await interaction.response.send_message("Bạn không có quyền.", ephemeral=True)
        modal = InviteModal(self.text_channel_id if self.text_channel_id else self.voice_id)
        await interaction.response.send_modal(modal)

# -------------------------
# Voice create: create voice + paired text channel and POST control message in paired text channel
# -------------------------
@bot.event
async def on_voice_state_update(member, before, after):
    try:
        # joined create trigger public
        if (before.channel is None or (before.channel and before.channel.id != TRIGGER_VOICE_CREATE)) and after.channel and after.channel.id == TRIGGER_VOICE_CREATE:
            guild = member.guild
            name = f"⋆𐙚 ̊. - {member.name}"
            category = discord.utils.get(guild.categories, id=VOICE_CATEGORY_ID)
            overwrites_voice = {
                guild.default_role: discord.PermissionOverwrite(connect=True, view_channel=True),
                member: discord.PermissionOverwrite(connect=True, view_channel=True)
            }
            # create voice channel under voice category if possible
            new_voice = await guild.create_voice_channel(name, overwrites=overwrites_voice, category=category, reason="Auto-created voice room")
            # create paired text channel (controls) under same category (text)
            try:
                text_overwrites = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                }
                # place text channel under same category (if category exists)
                if category:
                    text_ch = await guild.create_text_channel(name=f"{member.name}-room", overwrites=text_overwrites, category=category, reason="Paired control channel")
                else:
                    text_ch = await guild.create_text_channel(name=f"{member.name}-room", overwrites=text_overwrites, reason="Paired control channel")
            except Exception:
                text_ch = None
            # move member into voice
            try:
                await member.move_to(new_voice)
            except:
                pass
            # store in DB
            db_add_room(str(new_voice.id), str(member.id), is_hidden=0, is_locked=0, text_channel_id=(str(text_ch.id) if text_ch else None))
            # send control embed + buttons to the paired text channel (not support channel)
            if text_ch:
                embed = Embed(title="Voice room control", description=f"Voice room created for {member.mention}", color=PASTEL_PINK)
                embed.add_field(name="Room:", value=f"{new_voice.mention}", inline=False)
                view = RoomControlView(new_voice.id, member.id, text_ch.id if text_ch else None)
                try:
                    await text_ch.send(embed=embed, view=view)
                except:
                    pass
            else:
                # fallback: send to support channel but note buttons may not work properly there
                ch = guild.get_channel(SUPPORT_CHANNEL_ID) or guild.system_channel
                if ch:
                    embed = Embed(title="Voice room created", description=f"Voice {member.mention}", color=PASTEL_PINK)
                    view = RoomControlView(new_voice.id, member.id, None)
                    try:
                        await ch.send(embed=embed, view=view)
                    except:
                        pass

        # create private room
        if (before.channel is None or (before.channel and before.channel.id != TRIGGER_VOICE_PRIVATE)) and after.channel and after.channel.id == TRIGGER_VOICE_PRIVATE:
            guild = member.guild
            name = f"⋆𐙚 ̊. - {member.name}"
            category = discord.utils.get(guild.categories, id=VOICE_CATEGORY_ID)
            overwrites_voice = {
                guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=False),
                member: discord.PermissionOverwrite(connect=True, view_channel=True)
            }
            admin_member = guild.get_member(ADMIN_ID)
            if admin_member:
                overwrites_voice[admin_member] = discord.PermissionOverwrite(connect=True, view_channel=True)
            new_voice = await guild.create_voice_channel(name, overwrites=overwrites_voice, category=category, reason="Auto-created private voice")
            # paired text channel
            try:
                text_overwrites = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=False, send_messages=False)
                }
                if category:
                    text_ch = await guild.create_text_channel(name=f"{member.name}-room", overwrites=text_overwrites, category=category, reason="Paired private control channel")
                else:
                    text_ch = await guild.create_text_channel(name=f"{member.name}-room", overwrites=text_overwrites, reason="Paired private control channel")
            except Exception:
                text_ch = None
            try:
                await member.move_to(new_voice)
            except:
                pass
            db_add_room(str(new_voice.id), str(member.id), is_hidden=1, is_locked=1, text_channel_id=(str(text_ch.id) if text_ch else None))
            if text_ch:
                embed = Embed(title="Private voice room control", description=f"Private voice room for {member.mention}", color=PASTEL_PINK)
                embed.add_field(name="Room:", value=f"{new_voice.mention}", inline=False)
                view = RoomControlView(new_voice.id, member.id, text_ch.id if text_ch else None)
                try:
                    await text_ch.send(embed=embed, view=view)
                except:
                    pass
            else:
                ch = guild.get_channel(SUPPORT_CHANNEL_ID) or guild.system_channel
                if ch:
                    embed = Embed(title="Private voice room created", description=f"{member.mention}", color=PASTEL_PINK)
                    view = RoomControlView(new_voice.id, member.id, None)
                    try:
                        await ch.send(embed=embed, view=view)
                    except:
                        pass

        # cleanup: delete empty auto rooms and paired text channel
        if before.channel and (after.channel is None or (after.channel and after.channel.id != before.channel.id)):
            left_channel = before.channel
            row = db_get_room_by_voice(str(left_channel.id))
            if row:
                # if voice channel now empty -> delete voice + its paired text channel
                if len(left_channel.members) == 0:
                    try:
                        # delete paired text if exists
                        if row.get("text_channel_id"):
                            t = bot.get_channel(int(row["text_channel_id"]))
                            if t:
                                await t.delete()
                        await left_channel.delete(reason="Auto-delete empty room")
                    except:
                        pass
                    db_delete_room(str(left_channel.id))
    except Exception as e:
        print("on_voice_state_update error:", e)

# -------------------------
# Salary / PRF / IO / DNT commands + modal support
# -------------------------

# Modal classes for IO and DNT
class IOCreateModal(ui.Modal):
    time_field = ui.TextInput(label="Số giờ (ví dụ 2h)", required=True, placeholder="2h")
    target_field = ui.TextInput(label="Tag người nhận (vd: @user)", required=True, placeholder="@user")
    actor_field = ui.TextInput(label="Tag người thực hiện (by) - optional", required=False, placeholder="@actor (optional)")
    def __init__(self, ctx_author_id):
        super().__init__(title="Nhập IO")
        self.ctx_author_id = ctx_author_id
    async def on_submit(self, interaction: discord.Interaction):
        time_token = self.time_field.value.strip()
        m = re.match(r"^(\d+)(?:\.\d+)?h$", time_token.lower())
        if not m:
            await interaction.response.send_message("Sai định dạng thời gian. VD: 2h", ephemeral=True)
            return
        hours = int(m.group(1))
        targets = re.findall(r'<@!?(\d+)>', self.target_field.value)
        if not targets:
            await interaction.response.send_message("Không tìm thấy target mention.", ephemeral=True)
            return
        target_id = targets[0]
        actors = re.findall(r'<@!?(\d+)>', self.actor_field.value) if self.actor_field.value else []
        actor_id = actors[0] if actors else None
        t = db_get_user(str(target_id))
        db_update_user(str(target_id), book_hours=int(t["book_hours"]) + hours)
        if actor_id:
            db_prf_add_hours(str(actor_id), hours)
        ch = bot.get_channel(CHANNEL_IO_DNT)
        if ch:
            try:
                await ch.send(f"<@{target_id}> : {hours} giờ")
            except:
                pass
        await interaction.response.send_message("Đã lưu IO.", ephemeral=True)

class DNTCreateModal(ui.Modal):
    amount_field = ui.TextInput(label="Số tiền (vd: 20000)", required=True, placeholder="20000")
    target_field = ui.TextInput(label="Tag người nhận (vd: @user)", required=True, placeholder="@user")
    actor_field = ui.TextInput(label="Tag người thực hiện (by) - optional", required=False, placeholder="@actor (optional)")
    def __init__(self, ctx_author_id):
        super().__init__(title="Nhập Donate")
        self.ctx_author_id = ctx_author_id
    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount_field.value.strip())
        except:
            await interaction.response.send_message("Số tiền không hợp lệ.", ephemeral=True)
            return
        targets = re.findall(r'<@!?(\d+)>', self.target_field.value)
        if not targets:
            await interaction.response.send_message("Không tìm thấy target mention.", ephemeral=True)
            return
        target_id = targets[0]
        actors = re.findall(r'<@!?(\d+)>', self.actor_field.value) if self.actor_field.value else []
        actor_id = actors[0] if actors else None
        t = db_get_user(str(target_id))
        db_update_user(str(target_id), donate=int(t["donate"]) + amount)
        if actor_id:
            db_prf_add_donate(str(actor_id), amount)
        ch = bot.get_channel(CHANNEL_IO_DNT)
        if ch:
            try:
                await ch.send(f"<@{target_id}> : {fmt_vnd(amount)}")
            except:
                pass
        await interaction.response.send_message("Đã lưu Donate.", ephemeral=True)

# IO command: open modal if possible, else fallback to parse text
@bot.command(name="io")
async def cmd_io(ctx, *, raw: str = None):
    if not has_io_permission(ctx.author):
        return await ctx.reply("Bạn không có quyền dùng lệnh này.", delete_after=8)
    # If context has interaction and supports modal -> open modal
    modal = IOCreateModal(ctx.author.id)
    try:
        # Try to open modal via interaction if available
        if hasattr(ctx, "interaction") and ctx.interaction:
            await ctx.interaction.response.send_modal(modal)
            try:
                await ctx.message.delete()
            except:
                pass
            return
        # fallback: try bot to send modal using newer API
        await ctx.send("Mở form nhập IO... nếu client của bạn hỗ trợ modal, nó sẽ xuất hiện.", delete_after=5)
        # if raw provided (user used text format), parse it
        if raw:
            # parse same as earlier: !io 2h @target by @actor
            parts = raw.split()
            if not parts:
                return await ctx.reply("Sai cú pháp. VD: !io 2h @target [by @actor]", delete_after=8)
            time_token = parts[0]
            m = re.match(r"^(\d+)(?:\.\d+)?h$", time_token.lower())
            if not m:
                return await ctx.reply("Sai định dạng thời gian. VD: 2h", delete_after=8)
            hours = int(m.group(1))
            mentions = re.findall(r'<@!?(\d+)>', raw)
            if len(mentions) < 1:
                return await ctx.reply("Cần tag target.", delete_after=8)
            target_id = mentions[0]
            actor_id = mentions[1] if len(mentions) >= 2 else None
            t = db_get_user(str(target_id))
            db_update_user(str(target_id), book_hours=int(t["book_hours"]) + hours)
            if actor_id:
                db_prf_add_hours(str(actor_id), hours)
            ch = bot.get_channel(CHANNEL_IO_DNT)
            if ch:
                try:
                    await ch.send(f"<@{target_id}> : {hours} giờ")
                except:
                    pass
            try:
                await ctx.message.delete()
            except:
                pass
    except Exception:
        # If modal not possible, instruct user for text format
        await ctx.reply("Không thể mở modal trên client này. Vui lòng dùng: `!io 2h @target by @actor`", delete_after=10)

# DNT command: modal or fallback
@bot.command(name="dnt")
async def cmd_dnt(ctx, *, raw: str = None):
    if not has_io_permission(ctx.author):
        return await ctx.reply("Bạn không có quyền dùng lệnh này.", delete_after=8)
    modal = DNTCreateModal(ctx.author.id)
    try:
        if hasattr(ctx, "interaction") and ctx.interaction:
            await ctx.interaction.response.send_modal(modal)
            try:
                await ctx.message.delete()
            except:
                pass
            return
        await ctx.send("Mở form nhập Donate... nếu client hỗ trợ modal, nó sẽ xuất hiện.", delete_after=5)
        # fallback parse
        if raw:
            m = re.match(r"^(\d+)\s+", raw)
            if not m:
                return await ctx.reply("Sai cú pháp. VD: !dnt 20000 @target [by @actor]", delete_after=8)
            amount = int(m.group(1))
            mentions = re.findall(r'<@!?(\d+)>', raw)
            if len(mentions) < 1:
                return await ctx.reply("Cần tag target.", delete_after=8)
            target_id = mentions[0]
            actor_id = mentions[1] if len(mentions) >= 2 else None
            u = db_get_user(str(target_id))
            db_update_user(str(target_id), donate=int(u["donate"]) + amount)
            if actor_id:
                db_prf_add_donate(str(actor_id), amount)
            ch = bot.get_channel(CHANNEL_IO_DNT)
            if ch:
                try:
                    await ch.send(f"<@{target_id}> : {fmt_vnd(amount)}")
                except:
                    pass
            try:
                await ctx.message.delete()
            except:
                pass
    except Exception:
        await ctx.reply("Không thể mở modal trên client này. Dùng: `!dnt 20000 @target by @actor`", delete_after=10)

# luong command
@bot.command()
async def luong(ctx, member: discord.Member = None):
    if member and not (is_admin(ctx.author) or any(r.id == EXEMPT_ROLE_ID for r in ctx.author.roles)):
        return await ctx.reply("Bạn không có quyền xem lương người khác.", delete_after=8)
    target = member or ctx.author
    u = db_get_user(str(target.id))
    hours = int(u["book_hours"])
    donate = int(u["donate"])
    pay = hours * LUONG_GIO_RATE
    total = pay + donate
    embed = Embed(title=f"Lương của {target.display_name}", color=PASTEL_PINK)
    embed.add_field(name="Giờ book:", value=f"{hours} giờ", inline=False)
    embed.add_field(name="Lương giờ:", value=f"{fmt_vnd(pay)}", inline=False)
    embed.add_field(name="Donate:", value=f"{fmt_vnd(donate)}", inline=False)
    embed.add_field(name="Lương tổng:", value=f"{fmt_vnd(total)}", inline=False)
    try:
        await ctx.author.send(embed=embed)
    except:
        await ctx.reply("Không thể gửi DM — bật tin nhắn riêng.", delete_after=8)
    try:
        if ctx.channel.type != discord.ChannelType.private:
            await ctx.message.delete()
    except:
        pass

# prf command (anyone can view)
@bot.command()
async def prf(ctx, member: discord.Member = None):
    target = member or ctx.author
    p = db_prf_get(str(target.id))
    embed = Embed(title=f"PRF của {target.display_name}", color=PASTEL_PINK)
    embed.add_field(name="Giờ đã book:", value=f"{int(p['prf_hours'])} giờ", inline=False)
    embed.add_field(name="Donate:", value=f"{fmt_vnd(p['prf_donate'])}", inline=False)
    await ctx.send(embed=embed)
    try:
        await ctx.message.delete()
    except:
        pass

# -------------------------
# Code create/edit/delete via modal (only admin or exempt role)
# -------------------------
class CodeModal(ui.Modal):
    title_field = ui.TextInput(label="Tiêu đề", required=True)
    user_field = ui.TextInput(label="@user (mention)", required=True, placeholder="@user")
    content_field = ui.TextInput(label="Nội dung", style=discord.TextStyle.long, required=True)
    image_url_field = ui.TextInput(label="Image URL (optional)", required=False, placeholder="https://...")
    def __init__(self, existing_title=None):
        super().__init__(title="Tạo/Sửa Code")
        self.existing_title = existing_title
    async def on_submit(self, interaction: discord.Interaction):
        title = self.title_field.value.strip()
        user_text = self.user_field.value.strip()
        mentions = re.findall(r'<@!?(\d+)>', user_text)
        if not mentions:
            await interaction.response.send_message("Không tìm thấy mention trong @user.", ephemeral=True); return
        target_id = mentions[0]
        content = self.content_field.value.strip()
        image_url = self.image_url_field.value.strip() if self.image_url_field.value.strip() else None
        db_save_code(title, str(target_id), content, image_url)
        await interaction.response.send_message("Đã lưu template code.", ephemeral=True)

@bot.command()
async def code(ctx):
    allowed = is_admin(ctx.author) or any(r.id == EXEMPT_ROLE_ID for r in ctx.author.roles)
    if not allowed:
        return await ctx.reply("Bạn không có quyền tạo code.", delete_after=8)
    modal = CodeModal()
    try:
        if hasattr(ctx, "interaction") and ctx.interaction:
            await ctx.interaction.response.send_modal(modal)
            try:
                await ctx.message.delete()
            except:
                pass
            return
        await ctx.send("Mở form tạo code (nếu client hỗ trợ modal)...", delete_after=6)
    except Exception:
        await ctx.send("Không thể mở modal. Dùng command text: !code <title> - @user <content>")

@bot.command()
async def code_edit(ctx, *, args: str):
    allowed = is_admin(ctx.author) or any(r.id == EXEMPT_ROLE_ID for r in ctx.author.roles)
    if not allowed:
        return await ctx.reply("Bạn không có quyền.", delete_after=8)
    title = args.strip().split()[0]
    data = db_get_code_by_title(title)
    modal = CodeModal(existing_title=title)
    if data:
        modal.title_field.default = data["title"]
        modal.user_field.default = f"<@{data['target_user_id']}>"
        modal.content_field.default = data["content"]
        modal.image_url_field.default = data["image_url"] or ""
    try:
        if hasattr(ctx, "interaction") and ctx.interaction:
            await ctx.interaction.response.send_modal(modal)
            try:
                await ctx.message.delete()
            except:
                pass
            return
        await ctx.send("Mở form edit code (nếu client hỗ trợ modal)...", delete_after=6)
    except:
        await ctx.send("Không thể mở modal.")

@bot.command()
async def code_delete(ctx, member: discord.Member = None):
    allowed = is_admin(ctx.author) or any(r.id == EXEMPT_ROLE_ID for r in ctx.author.roles)
    if not allowed:
        return await ctx.reply("Bạn không có quyền xóa code.", delete_after=8)
    if not member:
        return await ctx.reply("Cần @user để xóa code liên kết.", delete_after=8)
    db_delete_code_by_user_id(str(member.id))
    await ctx.reply(f"Đã xóa code cho {member.display_name}", delete_after=6)

# message listener for code titles
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    await bot.process_commands(message)
    title = message.content.strip()
    if not title:
        return
    data = db_get_code_by_title(title)
    if data:
        try:
            mention = f"<@{data['target_user_id']}>"
            content = data["content"]
            image_url = data["image_url"]
            if image_url:
                embed = Embed(description=f"{mention} {content}", color=PASTEL_PINK)
                embed.set_image(url=image_url)
                await message.channel.send(embed=embed)
            else:
                await message.channel.send(f"{mention} {content}")
        except Exception as e:
            print("code send error:", e)

# -------------------------
# Giveaway modal (creates embed, deletes invoking command)
# -------------------------
class GiveawayModal(ui.Modal):
    title = ui.TextInput(label="Tiêu đề", required=True)
    winners = ui.TextInput(label="Số winners", required=True, placeholder="1")
    end = ui.TextInput(label="Thời lượng (vd: 1h30m)", required=True, placeholder="1h30m")
    host_user = ui.TextInput(label="Hosted by (mention) - optional", required=False, placeholder="@user")
    def __init__(self, channel):
        super().__init__(title="Tạo Giveaway")
        self.channel = channel
    async def on_submit(self, interaction: discord.Interaction):
        title = self.title.value.strip()
        try:
            winners = int(self.winners.value.strip())
        except:
            await interaction.response.send_message("Winners phải là số.", ephemeral=True); return
        end_str = self.end.value.strip()
        host_text = self.host_user.value.strip()
        matches = re.findall(r'(\d+)([smhd])', end_str)
        total_seconds = 0
        for qty, unit in matches:
            q = int(qty)
            if unit == 's': total_seconds += q
            elif unit == 'm': total_seconds += q*60
            elif unit == 'h': total_seconds += q*3600
            elif unit == 'd': total_seconds += q*86400
        if total_seconds <= 0:
            await interaction.response.send_message("Thời gian không hợp lệ.", ephemeral=True); return
        host_id = None
        if host_text:
            h = re.findall(r'<@!?(\d+)>', host_text)
            if h:
                host_id = h[0]
        if not host_id:
            host_id = "1432668389943410780"
        end_at = datetime.now(VN_TZ) + timedelta(seconds=total_seconds)
        embed = Embed(title=f"🎉 Giveaway: {title}", description=f"Hosted by: <@{host_id}>\nWinners: {winners}\nEnds at: {end_at.strftime('%Y-%m-%d %H:%M:%S')}", color=PASTEL_PINK)
        msg = await self.channel.send(embed=embed)
        await msg.add_reaction("🎉")
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("INSERT INTO giveaways(channel_id, message_id, title, winners, host_id, end_at, ended) VALUES (?,?,?,?,?,?,0)",
                    (str(self.channel.id), str(msg.id), title, winners, str(host_id), end_at.strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()
        await interaction.response.send_message("Đã tạo giveaway!", ephemeral=True)
        async def wait_and_draw():
            await asyncio.sleep(total_seconds)
            try:
                gmsg = await self.channel.fetch_message(msg.id)
                users = set()
                for react in gmsg.reactions:
                    if react.emoji == "🎉":
                        async for u in react.users():
                            if not u.bot:
                                users.add(u.id)
                winners_list = []
                if users:
                    winners_list = random.sample(list(users), min(len(users), winners))
                announce = f"🎊 Giveaway ended! Winners: {', '.join(f'<@{w}>' for w in winners_list) if winners_list else 'No participants.'}"
                await self.channel.send(announce)
            except Exception as e:
                print("giveaway draw error:", e)
        bot.loop.create_task(wait_and_draw())

@bot.command()
async def gw(ctx):
    modal = GiveawayModal(ctx.channel)
    try:
        # delete invoking message for cleanliness
        try:
            await ctx.message.delete()
        except:
            pass
        if hasattr(ctx, "interaction") and ctx.interaction:
            await ctx.interaction.response.send_modal(modal)
        else:
            # try to open modal via interaction-less context (may not work)
            await ctx.send("Mở form tạo giveaway (nếu client hỗ trợ modal)...", delete_after=5)
    except Exception:
        await ctx.send("Không thể mở modal trong client này.")

# -------------------------
# POST / RENT (fm / m) behavior
# -------------------------
class RentDoneView(ui.View):
    @ui.button(label="Done", style=discord.ButtonStyle.danger)
    async def done(self, interaction: discord.Interaction, button: ui.Button):
        # allow owner or admin to delete the rent channel
        try:
            # check if channel name equals user who pressed (basic guard)
            if interaction.user.guild_permissions.administrator or interaction.channel.name == interaction.user.name:
                await interaction.channel.delete()
                await interaction.response.send_message("Kênh đã xóa.", ephemeral=True)
            else:
                await interaction.response.send_message("Bạn không có quyền xóa kênh này.", ephemeral=True)
        except Exception:
            await interaction.response.send_message("Không thể xóa kênh.", ephemeral=True)

class RentView(ui.View):
    def __init__(self, embed:Embed, image_file, owner:discord.Member):
        super().__init__(timeout=None)
        self.embed = embed
        self.image_file = image_file
        self.owner = owner

    @ui.button(label="Rent", style=discord.ButtonStyle.primary)
    async def rent(self, interaction: discord.Interaction, button: ui.Button):
        member = interaction.user
        guild = interaction.guild
        category = discord.utils.get(guild.categories, id=RENT_CATEGORY_ID)
        name = f"{member.name}"
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.get_member(ADMIN_ID): discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        try:
            temp_channel = await guild.create_text_channel(name=name, overwrites=overwrites, category=category, reason="Rent created")
        except:
            temp_channel = await guild.create_text_channel(name=name, overwrites=overwrites, reason="Rent created")
        # send embed + image + greeting
        try:
            await temp_channel.send(embed=self.embed, file=self.image_file)
        except:
            await temp_channel.send(embed=self.embed)
        await temp_channel.send("Khách ơi đợi tí, bọn mình rep liền nhaaa ₊˚⊹ ᰔ")
        await temp_channel.send("Nhấn Done khi xong.", view=RentDoneView())
        await interaction.response.send_message(f"Đã tạo channel {temp_channel.mention}", ephemeral=True)

@bot.command()
async def post(ctx, kind: str, *, caption: str = ""):
    if kind.lower() not in ("fm", "m"):
        return await ctx.reply("Sai cú pháp. Dùng `!post fm` hoặc `!post m`", delete_after=6)
    if len(ctx.message.attachments) == 0:
        return await ctx.reply("Bạn chưa gửi ảnh kèm message!", delete_after=6)
    attachment = ctx.message.attachments[0]
    image_file = await attachment.to_file()
    embed = Embed(description=caption, color=PASTEL_PINK)
    embed.set_image(url=f"attachment://{attachment.filename}")
    channel = bot.get_channel(IMAGE_CHANNEL_FEMALE if kind.lower()=="fm" else IMAGE_CHANNEL_MALE)
    if not channel:
        return await ctx.reply("Không tìm thấy channel ảnh.", delete_after=6)
    view = RentView(embed, image_file, ctx.author)
    await channel.send(embed=embed, file=image_file, view=view)
    try:
        await ctx.message.delete()
    except:
        pass

# -------------------------
# Utilities: clear, av, ban, mute, rd, pick (was choose)
# -------------------------
@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: str):
    if amount == "all":
        try:
            await ctx.channel.purge()
        except:
            await ctx.send("Không thể xóa tất cả.", delete_after=6)
        try:
            await ctx.message.delete()
        except:
            pass
        return
    if not amount.isdigit():
        return await ctx.reply("Sai cú pháp. VD: !clear 3", delete_after=6)
    n = int(amount)
    if n <= 0:
        return await ctx.reply("Số phải >0", delete_after=6)
    try:
        await ctx.channel.purge(limit=n+1)
    except:
        await ctx.send("Không thể xóa.", delete_after=6)

@bot.command()
async def av(ctx, member: discord.Member = None):
    member = member or ctx.author
    avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
    embed = Embed(title=f"Avatar — {member.display_name}", color=PASTEL_PINK)
    embed.set_image(url=avatar_url)
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def ban(ctx, member: discord.Member = None):
    if not member:
        embed = Embed(title="Chọn người bạn muốn ban?", color=PASTEL_PINK)
        await ctx.send(embed=embed)
        return
    try:
        await member.ban(reason=f"Banned by {ctx.author}")
        await ctx.send(f"Đã ban {member.mention}")
    except:
        await ctx.send("Lỗi khi ban.", delete_after=6)

@bot.command()
async def mute(ctx, time: str = None, member: discord.Member = None):
    allowed = is_admin(ctx.author) or any(r.id == EXEMPT_ROLE_ID for r in ctx.author.roles)
    if not allowed:
        return await ctx.reply("Bạn không có quyền mute.", delete_after=8)
    if not member:
        embed = Embed(title="Chọn người bạn muốn mute?", color=PASTEL_PINK)
        await ctx.send(embed=embed)
        return
    if not time:
        return await ctx.reply("Thiếu thời gian VD: !mute 1m @user", delete_after=8)
    m = re.match(r"^(\d+)([smhd])$", time.lower())
    if not m:
        return await ctx.reply("Sai định dạng thời gian.", delete_after=8)
    qty = int(m.group(1)); unit = m.group(2)
    seconds = qty * (1 if unit == 's' else 60 if unit == 'm' else 3600 if unit == 'h' else 86400)
    guild = ctx.guild
    muted = discord.utils.get(guild.roles, name="Muted")
    if not muted:
        muted = await guild.create_role(name="Muted")
        for ch in guild.channels:
            try:
                await ch.set_permissions(muted, send_messages=False, speak=False, add_reactions=False)
            except:
                pass
    try:
        await member.add_roles(muted, reason=f"Muted by {ctx.author} for {time}")
    except:
        pass
    try:
        await ctx.message.delete()
    except:
        pass
    async def unmute_later():
        await asyncio.sleep(seconds)
        try:
            await member.remove_roles(muted, reason="Auto unmute")
        except:
            pass
    bot.loop.create_task(unmute_later())

@bot.command()
async def rd(ctx):
    n = random.randint(1, 999)
    await ctx.send(f"Random: {n}")

@bot.command(name="pick")
async def pick(ctx, *, options: str):
    parts = options.split()
    if not parts:
        return await ctx.reply("Cần ít nhất 1 lựa chọn.", delete_after=6)
    pick = random.choice(parts)
    await ctx.send(f"Chọn: **{pick}**")

# -------------------------
# time/qr/text (pastel)
# -------------------------
@bot.command()
async def time(ctx, *, t: str):
    t = t.lower().replace(" ", "")
    hours = 0; minutes = 0
    h = re.search(r'(\d+)h', t); m = re.search(r'(\d+)m', t)
    if h: hours = int(h.group(1))
    if m: minutes = int(m.group(1))
    if hours == 0 and minutes == 0:
        return await ctx.reply("Không nhận diện thời gian!", delete_after=6)
    start = datetime.now(VN_TZ); end = start + timedelta(hours=hours, minutes=minutes)
    embed = Embed(description=f"⏳ Bắt đầu: {start.strftime('%H:%M:%S')} → Kết thúc: {end.strftime('%H:%M:%S')}", color=PASTEL_PINK)
    await ctx.send(embed=embed)
    await asyncio.sleep(hours*3600 + minutes*60)
    await ctx.send(f"{ctx.author.mention} ⏰ Đã hết giờ")

@bot.command()
async def qr(ctx):
    embed = Embed(description="Sau khi thanh toán xong thì gửi bill vào đây nhá. Không ghi NDCK giúp mình nha ୨୧", color=PASTEL_PINK)
    path = "qr.png"
    if os.path.exists(path):
        await ctx.send(embed=embed, file=File(path, filename="qr.png"))
    else:
        await ctx.send(embed=embed)

@bot.command()
async def text(ctx, *, content: str):
    embed = Embed(description=content, color=PASTEL_PINK)
    try:
        avatar = ctx.author.avatar.url
        embed.set_footer(text=f"Sent by {ctx.author.display_name}", icon_url=avatar)
    except:
        embed.set_footer(text=f"Sent by {ctx.author.display_name}")
    try:
        await ctx.message.delete()
    except:
        pass
    await ctx.send(embed=embed)

# -------------------------
# Monthly report task
# -------------------------
@tasks.loop(minutes=10)
async def monthly_report_task():
    now = datetime.now(VN_TZ)
    if now.day == 1 and now.hour == 0 and 1 <= now.minute < 11:
        ym = now.strftime("%Y-%m")
        if db_monthly_sent_exists(ym):
            return
        rows = db_get_all_users()
        ch = bot.get_channel(CHANNEL_MONTHLY_REPORT)
        if not ch:
            db_monthly_mark_sent(ym)
            return
        header = f"📊 Báo cáo lương tháng {now.strftime('%Y-%m')}\nLương giờ = {fmt_vnd(LUONG_GIO_RATE)}/giờ\n\n"
        msg = header
        for uid, hours, donate in rows:
            pay = int(hours) * LUONG_GIO_RATE
            total = pay + int(donate)
            msg += f"<@{uid}> — Giờ: {hours} giờ | Lương giờ: {fmt_vnd(pay)} | Donate: {fmt_vnd(donate)} | Tổng: {fmt_vnd(total)}\n"
            if len(msg) > 1800:
                await ch.send(msg); msg = ""
        if msg: await ch.send(msg)
        db_monthly_mark_sent(ym)

# -------------------------
# on_ready
# -------------------------
@bot.event
async def on_ready():
    print(f"Bot running as {bot.user} (id: {bot.user.id})")
    if not monthly_report_task.is_running():
        monthly_report_task.start()

# -------------------------
# Error handler
# -------------------------
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        try:
            await ctx.message.delete()
        except:
            pass
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Thiếu tham số.", delete_after=6)
    else:
        print("Command error:", error)

# -------------------------
# Run
# -------------------------
if __name__ == "__main__":
    bot.run(TOKEN)
