# bot_full.py
# Full-featured Discord bot (single-file)
# - Python 3.11 recommended
# - Uses discord.py
# - SQLite storage (luong.db)
# - Pastel pink embeds (0xFFB7D5)
# - Features: salary (!luong), prf, !io/by, !dnt/by, voice auto-create, room controls,
#   post/rent (1:1), qr, time, text, clear, av, ban, mute, giveaway, rd, choose, monthly report

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

# Channel & IDs (from your requests)
WELCOME_CHANNEL_ID = 1432659040680284191
SUPPORT_CHANNEL_ID = 1432685282955755595
IMAGE_CHANNEL_FEMALE = 1432691499094769704
IMAGE_CHANNEL_MALE = 1432691597363122357

CHANNEL_IO_DNT = 1448047569421733981         # IO / DNT log channel
CHANNEL_MONTHLY_REPORT = 1448052039384043683 # monthly report channel

TRIGGER_VOICE_CREATE = 1432658695719751794   # join to auto-create public voice
TRIGGER_VOICE_PRIVATE = 1448063002518487092  # join to auto-create private locked voice

EXEMPT_ROLE_ID = 1432670531529867295        # role allowed to see hidden rooms
ADMIN_ID = 757555763559399424

ALLOWED_ROLE_NAME = "Staff"  # role name allowed to use io/dnt etc.

LUONG_GIO_RATE = 25000  # VNĐ per hour

PASTEL_PINK = 0xFFB7D5

VN_TZ = pytz.timezone("Asia/Ho_Chi_Minh")

DB_FILE = "luong.db"

# Flask keep-alive (optional)
app = Flask('')
@app.route('/')
def home():
    return "Bot is running"
def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
Thread(target=run_flask).start()

# -------------------------
# DISCORD BOT SETUP
# -------------------------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------------
# DATABASE (SQLite) SETUP
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

def db_add_log(uid: str, in_time: str, out_time: str, hours: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    now = datetime.now(VN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("INSERT INTO logs(user_id, in_time, out_time, hours, created_at) VALUES (?,?,?,?,?)",
                (uid, in_time, out_time, int(hours), now))
    conn.commit()
    conn.close()

def db_get_logs(uid: str, limit=20):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT in_time, out_time, hours, created_at FROM logs WHERE user_id=? ORDER BY id DESC LIMIT ?", (uid, limit))
    rows = cur.fetchall()
    conn.close()
    return rows

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

def db_get_all_users():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT user_id, book_hours, donate FROM users")
    rows = cur.fetchall()
    conn.close()
    return rows

def db_monthly_sent_exists(ym: str):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM monthly_sent WHERE ym=?", (ym,))
    exists = cur.fetchone() is not None
    conn.close()
    return exists

def db_monthly_mark_sent(ym: str):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO monthly_sent(ym) VALUES (?)", (ym,))
    conn.commit()
    conn.close()

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

# -------------------------
# VOICE AUTO-CREATE + CLEANUP
# -------------------------
@bot.event
async def on_voice_state_update(member, before, after):
    try:
        # joined create channel trigger (public)
        if (before.channel is None or (before.channel and before.channel.id != TRIGGER_VOICE_CREATE)) and after.channel and after.channel.id == TRIGGER_VOICE_CREATE:
            guild = member.guild
            name = f"⋆𐙚 ̊. - {member.name}"
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(connect=True, view_channel=True),
                member: discord.PermissionOverwrite(connect=True, view_channel=True, manage_channels=True)
            }
            new_channel = await guild.create_voice_channel(name, overwrites=overwrites, reason="Auto-created voice room")
            # move member
            try:
                await member.move_to(new_channel)
            except:
                pass
            db_add_room(str(new_channel.id), str(member.id), is_hidden=0, is_locked=0)
            # send room control embed to support channel or guild.system_channel
            ch = guild.get_channel(SUPPORT_CHANNEL_ID) or guild.system_channel
            if ch:
                embed = Embed(title="Room created", description=f"Voice room for {member.mention}", color=PASTEL_PINK)
                embed.add_field(name="Room", value=f"{new_channel.mention}", inline=False)
                view = RoomControlView(new_channel.id, member.id)
                await ch.send(embed=embed, view=view)
        # joined private trigger
        if (before.channel is None or (before.channel and before.channel.id != TRIGGER_VOICE_PRIVATE)) and after.channel and after.channel.id == TRIGGER_VOICE_PRIVATE:
            guild = member.guild
            name = f"⋆𐙚 ̊. - {member.name}"
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=False),
                member: discord.PermissionOverwrite(connect=True, view_channel=True, manage_channels=True),
            }
            # also give admins see
            admin_member = guild.get_member(ADMIN_ID)
            if admin_member:
                overwrites[admin_member] = discord.PermissionOverwrite(view_channel=True, connect=True)
            new_channel = await guild.create_voice_channel(name, overwrites=overwrites, reason="Auto-created private voice room")
            try:
                await member.move_to(new_channel)
            except:
                pass
            db_add_room(str(new_channel.id), str(member.id), is_hidden=1, is_locked=1)
            ch = guild.get_channel(SUPPORT_CHANNEL_ID) or guild.system_channel
            if ch:
                embed = Embed(title="Private Room created", description=f"Private voice room for {member.mention}", color=PASTEL_PINK)
                embed.add_field(name="Room", value=f"{new_channel.mention}", inline=False)
                view = RoomControlView(new_channel.id, member.id)
                await ch.send(embed=embed, view=view)

        # left a channel: if it's an auto-created room and now empty -> delete
        if before.channel and (after.channel is None or (after.channel and after.channel.id != before.channel.id)):
            left_channel = before.channel
            room = db_get_room(str(left_channel.id))
            if room:
                # if no members remain -> delete and remove from DB
                if len(left_channel.members) == 0:
                    try:
                        await left_channel.delete(reason="Auto-delete empty room")
                    except:
                        pass
                    db_delete_room(str(left_channel.id))
    except Exception as e:
        print("voice_state_update error:", e)

# -------------------------
# ROOM CONTROL VIEW (Lock/Unlock/Hide/Invite)
# -------------------------
class InviteModal(ui.Modal):
    user_mention = ui.TextInput(label="Nhập mention user (ví dụ @user)", required=True, placeholder="@user")
    def __init__(self, channel_id: str):
        super().__init__(title="Invite to room")
        self.channel_id = channel_id
    async def on_submit(self, interaction: discord.Interaction):
        text = self.user_mention.value.strip()
        mentions = re.findall(r'<@!?(\d+)>', text)
        if not mentions:
            await interaction.response.send_message("Không tìm thấy mention.", ephemeral=True); return
        ch = interaction.guild.get_channel(int(self.channel_id))
        if not ch:
            await interaction.response.send_message("Channel không tồn tại.", ephemeral=True); return
        for uid in mentions:
            member = interaction.guild.get_member(int(uid))
            if member:
                try:
                    await ch.set_permissions(member, connect=True, view_channel=True)
                except:
                    pass
        await interaction.response.send_message("Đã invite (không gửi thông báo).", ephemeral=True)

class RoomControlView(ui.View):
    def __init__(self, voice_id: int, owner_id: int):
        super().__init__(timeout=None)
        self.voice_id = str(voice_id)
        self.owner_id = str(owner_id)

    def _is_allowed(self, user: discord.Member):
        # allowed if owner, admin, or has exempt role
        if user.id == int(self.owner_id): return True
        if is_admin(user): return True
        for r in user.roles:
            if r.id == EXEMPT_ROLE_ID:
                return True
        return False

    async def _get_channel(self, interaction: discord.Interaction):
        return interaction.guild.get_channel(int(self.voice_id))

    @ui.button(label="Lock room", style=discord.ButtonStyle.danger, custom_id="room_lock")
    async def lock(self, button: ui.Button, interaction: discord.Interaction):
        ch = await self._get_channel(interaction)
        if not ch:
            await interaction.response.send_message("Channel không tồn tại.", ephemeral=True); return
        if not self._is_allowed(interaction.user):
            await interaction.response.send_message("Bạn không có quyền.", ephemeral=True); return
        await ch.set_permissions(interaction.guild.default_role, connect=False)
        db_add_room(str(ch.id), str(self.owner_id), is_hidden=0, is_locked=1)
        await interaction.response.send_message("Đã khóa room.", ephemeral=True)

    @ui.button(label="Unlock room", style=discord.ButtonStyle.success, custom_id="room_unlock")
    async def unlock(self, button: ui.Button, interaction: discord.Interaction):
        ch = await self._get_channel(interaction)
        if not ch:
            await interaction.response.send_message("Channel không tồn tại.", ephemeral=True); return
        if not self._is_allowed(interaction.user):
            await interaction.response.send_message("Bạn không có quyền.", ephemeral=True); return
        await ch.set_permissions(interaction.guild.default_role, connect=True, view_channel=True)
        db_add_room(str(ch.id), str(self.owner_id), is_hidden=0, is_locked=0)
        await interaction.response.send_message("Đã mở khóa room.", ephemeral=True)

    @ui.button(label="Hide", style=discord.ButtonStyle.secondary, custom_id="room_hide")
    async def hide(self, button: ui.Button, interaction: discord.Interaction):
        ch = await self._get_channel(interaction)
        if not ch:
            await interaction.response.send_message("Channel không tồn tại.", ephemeral=True); return
        if not self._is_allowed(interaction.user):
            await interaction.response.send_message("Bạn không có quyền.", ephemeral=True); return
        # hide from everyone
        await ch.set_permissions(interaction.guild.default_role, view_channel=False, connect=False)
        # owner & admin & exempt role see it
        owner_m = interaction.guild.get_member(int(self.owner_id))
        if owner_m:
            await ch.set_permissions(owner_m, view_channel=True, connect=True)
        exempt_role = interaction.guild.get_role(EXEMPT_ROLE_ID)
        if exempt_role:
            await ch.set_permissions(exempt_role, view_channel=True, connect=True)
        db_add_room(str(ch.id), str(self.owner_id), is_hidden=1, is_locked=1)
        await interaction.response.send_message("Đã ẩn room.", ephemeral=True)

    @ui.button(label="Invite", style=discord.ButtonStyle.primary, custom_id="room_invite")
    async def invite(self, button: ui.Button, interaction: discord.Interaction):
        ch = await self._get_channel(interaction)
        if not ch:
            await interaction.response.send_message("Channel không tồn tại.", ephemeral=True); return
        if not self._is_allowed(interaction.user):
            await interaction.response.send_message("Bạn không có quyền.", ephemeral=True); return
        modal = InviteModal(self.voice_id)
        await interaction.response.send_modal(modal)

# -------------------------
# SALARY / PRF / IO / DNT / PRF commands
# -------------------------

@bot.command()
async def luong(ctx, member: discord.Member = None):
    """
    !luong => DM to invoker with pastel-pink embed (Giờ book, Lương giờ, Donate, Lương tổng)
    !luong @user => admin only, admin receives DM for that user
    """
    if member and not is_admin(ctx.author):
        await ctx.reply("Bạn không có quyền xem lương người khác.", delete_after=8)
        return
    target = member or ctx.author
    u = db_get_user(str(target.id))
    hours = int(u["book_hours"])
    donate = int(u["donate"])
    pay_from_hours = hours * LUONG_GIO_RATE
    total = pay_from_hours + donate
    embed = Embed(title=f"Lương của {target.display_name}", color=PASTEL_PINK)
    embed.add_field(name="Giờ book:", value=f"{hours} giờ", inline=False)
    embed.add_field(name="Lương giờ:", value=f"{fmt_vnd(pay_from_hours)}", inline=False)
    embed.add_field(name="Donate:", value=f"{fmt_vnd(donate)}", inline=False)
    embed.add_field(name="Lương tổng:", value=f"{fmt_vnd(total)}", inline=False)
    try:
        await ctx.author.send(embed=embed)
    except:
        await ctx.reply("Không thể gửi DM — bật tin nhắn riêng để nhận lương.", delete_after=8)
    try:
        if ctx.channel.type != discord.ChannelType.private:
            await ctx.message.delete()
    except:
        pass

@bot.command()
async def prf(ctx):
    """Show PRF for caller (Giờ đã book, Donate)"""
    p = db_prf_get(str(ctx.author.id))
    ph = int(p["prf_hours"])
    pd = int(p["prf_donate"])
    embed = Embed(title="Profile (PRF)", color=PASTEL_PINK)
    embed.add_field(name="Giờ đã book:", value=f"{ph} giờ", inline=False)
    embed.add_field(name="Donate:", value=f"{fmt_vnd(pd)}", inline=False)
    try:
        await ctx.author.send(embed=embed)
    except:
        await ctx.reply("Không thể gửi DM.", delete_after=8)
    try:
        if ctx.channel.type != discord.ChannelType.private:
            await ctx.message.delete()
    except:
        pass

@bot.command(name="io")
async def cmd_io(ctx, *, raw: str):
    """
    Formats accepted:
    - !io 2h @target
    - !io 2h @target by @actor
    Behavior:
    - first mentioned user (target) -> add to luong.book_hours
    - second mentioned user (actor) -> add to prf.prf_hours
    - send log message only: "<@target> : <hours> giờ"
    """
    if not has_io_permission(ctx.author):
        return await ctx.reply("Bạn không có quyền dùng lệnh này.", delete_after=8)
    # parse time token at start
    parts = raw.split()
    if not parts:
        return await ctx.reply("Sai cú pháp. VD: !io 2h @target [by @actor]", delete_after=8)
    time_token = parts[0]
    m = re.match(r"^(\d+)(?:\.\d+)?h$", time_token.lower())
    if not m:
        return await ctx.reply("Sai format thời gian. Ví dụ: 2h", delete_after=8)
    hours = int(m.group(1))
    mentions = re.findall(r'<@!?(\d+)>', raw)
    if len(mentions) < 1:
        return await ctx.reply("Cần tag target.", delete_after=8)
    target_id = mentions[0]
    actor_id = mentions[1] if len(mentions) >= 2 else None
    # update target book_hours
    t = db_get_user(str(target_id))
    new_hours = int(t["book_hours"]) + hours
    db_update_user(str(target_id), book_hours=new_hours)
    # update PRF for actor if provided (silent)
    if actor_id:
        db_prf_add_hours(str(actor_id), hours)
    # log only target
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

@bot.command(name="dnt")
async def cmd_dnt(ctx, *, raw: str):
    """
    Formats:
    - !dnt 20000 @target
    - !dnt 20000 @target by @actor
    Behavior:
    - target gets donate added to luong
    - actor gets donate added to prf (silent)
    - log only: "<@target> : <amount>"
    """
    if not has_io_permission(ctx.author):
        return await ctx.reply("Bạn không có quyền dùng lệnh này.", delete_after=8)
    m = re.match(r"^(\d+)\s+", raw)
    if not m:
        return await ctx.reply("Sai cú pháp. VD: !dnt 20000 @target [by @actor]", delete_after=8)
    amount = int(m.group(1))
    mentions = re.findall(r'<@!?(\d+)>', raw)
    if len(mentions) < 1:
        return await ctx.reply("Cần tag target.", delete_after=8)
    target_id = mentions[0]
    actor_id = mentions[1] if len(mentions) >= 2 else None
    # update target donate
    u = db_get_user(str(target_id))
    new_d = int(u["donate"]) + amount
    db_update_user(str(target_id), donate=new_d)
    # update PRF donate for actor (silent)
    if actor_id:
        db_prf_add_donate(str(actor_id), amount)
    # log only target
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

@bot.command()
@commands.has_permissions(administrator=True)
async def reset_all(ctx):
    """
    Reset all users' book_hours and donate (and PRF table)
    No notification should be sent.
    """
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("UPDATE users SET book_hours=0, donate=0, in_time=NULL")
    cur.execute("DELETE FROM prf")
    conn.commit()
    conn.close()
    try:
        await ctx.message.delete()
    except:
        pass

# -------------------------
# MISC Utilities
# -------------------------
@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: str):
    """!clear <n> or !clear all"""
    if amount == "all":
        try:
            await ctx.channel.purge()
        except Exception:
            await ctx.send("Không xóa được tất cả.", delete_after=5)
        try: await ctx.message.delete()
        except: pass
        return
    if not amount.isdigit():
        return await ctx.reply("Sai cú pháp. VD: !clear 3", delete_after=6)
    n = int(amount)
    if n <= 0:
        return await ctx.reply("Số phải lớn hơn 0.", delete_after=6)
    try:
        # include command message -> delete n+1
        await ctx.channel.purge(limit=n+1)
    except Exception:
        await ctx.send("Không thể xóa.", delete_after=5)

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
    except Exception:
        await ctx.send("Lỗi khi ban.")

@bot.command()
async def mute(ctx, time: str = None, member: discord.Member = None):
    # only admin or exempt role allowed
    allowed = is_admin(ctx.author) or any(r.id == EXEMPT_ROLE_ID for r in ctx.author.roles)
    if not allowed:
        return await ctx.reply("Bạn không có quyền mute.", delete_after=8)
    if not member:
        embed = Embed(title="Chọn người bạn muốn mute?", color=PASTEL_PINK)
        await ctx.send(embed=embed)
        return
    if not time:
        return await ctx.reply("Thiếu thời gian. VD: !mute 1m @user", delete_after=8)
    m = re.match(r"^(\d+)([smhd])$", time.lower())
    if not m:
        return await ctx.reply("Sai định dạng thời gian. VD: 1m, 1h", delete_after=8)
    qty = int(m.group(1)); unit = m.group(2)
    seconds = qty * (1 if unit == 's' else 60 if unit == 'm' else 3600 if unit == 'h' else 86400)
    guild = ctx.guild
    muted_role = discord.utils.get(guild.roles, name="Muted")
    if not muted_role:
        muted_role = await guild.create_role(name="Muted")
        for ch in guild.channels:
            try:
                await ch.set_permissions(muted_role, send_messages=False, speak=False, add_reactions=False)
            except:
                pass
    try:
        await member.add_roles(muted_role, reason=f"Muted by {ctx.author} for {time}")
    except:
        pass
    try:
        await ctx.message.delete()
    except:
        pass
    async def unmute_later():
        await asyncio.sleep(seconds)
        try:
            await member.remove_roles(muted_role, reason="Auto unmute")
        except:
            pass
    bot.loop.create_task(unmute_later())

@bot.command()
async def rd(ctx):
    num = random.randint(1, 999)
    await ctx.send(f"Random: {num}")

@bot.command()
async def choose(ctx, *, options: str):
    parts = options.split()
    if not parts:
        return await ctx.reply("Cần ít nhất 1 lựa chọn.")
    choice = random.choice(parts)
    await ctx.send(f"Chọn: **{choice}**")

# -------------------------
# GIVEAWAY (simple)
# -------------------------
class GiveawayModal(ui.Modal):
    title = ui.TextInput(label="Tiêu đề giveaway", required=True)
    winners = ui.TextInput(label="Số người thắng", required=True, placeholder="1")
    end = ui.TextInput(label="Thời lượng (vd: 1h30m)", required=True, placeholder="1h30m")
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
        # parse time string (supports h/m/s/d)
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
        end_at = datetime.now(VN_TZ) + timedelta(seconds=total_seconds)
        embed = Embed(title=f"🎉 Giveaway: {title}", description=f"Hosted by: {interaction.user.mention}\nWinners: {winners}\nEnds at: {end_at.strftime('%Y-%m-%d %H:%M:%S')}", color=PASTEL_PINK)
        msg = await self.channel.send(embed=embed)
        await msg.add_reaction("🎉")
        # store giveaway
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("INSERT INTO giveaways(channel_id, message_id, title, winners, host_id, end_at, ended) VALUES (?,?,?,?,?,?,0)",
                    (str(self.channel.id), str(msg.id), title, winners, str(interaction.user.id), end_at.strftime("%Y-%m-%d %H:%M:%S")))
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
                users = list(users)
                winners_list = []
                if users:
                    winners_list = random.sample(users, min(len(users), winners))
                announce = f"🎊 Giveaway ended! Winners: {', '.join(f'<@{w}>' for w in winners_list) if winners_list else 'No participants.'}"
                await self.channel.send(announce)
            except Exception as e:
                print("giveaway draw error", e)
        bot.loop.create_task(wait_and_draw())

@bot.command()
async def gw(ctx):
    modal = GiveawayModal(ctx.channel)
    # In message context modals may not open; we attempt to respond
    try:
        await ctx.send("Mở form tạo giveaway (check DM/modal)...", delete_after=3)
        await ctx.interaction.response.send_modal(modal) if hasattr(ctx, "interaction") else await ctx.send("Vui lòng dùng slash hoặc hỗ trợ modal.")
    except:
        try:
            await ctx.send("Mở form tạo giveaway...") 
        except:
            pass

# -------------------------
# POST / RENT (1:1 image embed) adjustments
# -------------------------
class RentDoneView(ui.View):
    @ui.button(label="Done", style=discord.ButtonStyle.danger)
    async def done(self, interaction: discord.Interaction, button: ui.Button):
        # delete the channel where called if allowed
        try:
            await interaction.channel.delete()
        except:
            await interaction.response.send_message("Không thể xóa channel.", ephemeral=True)

@bot.command()
async def post(ctx, gender: str, *, caption: str = ""):
    if len(ctx.message.attachments) == 0:
        return await ctx.reply("Bạn chưa gửi ảnh kèm message!", delete_after=6)
    attachment = ctx.message.attachments[0]
    image_file = await attachment.to_file()
    if gender.lower() == "female":
        channel = bot.get_channel(IMAGE_CHANNEL_FEMALE)
    elif gender.lower() == "male":
        channel = bot.get_channel(IMAGE_CHANNEL_MALE)
    else:
        return await ctx.reply("Giới tính không hợp lệ! dùng `female` hoặc `male`", delete_after=6)
    if not channel:
        return await ctx.reply("Không tìm thấy channel ảnh.", delete_after=6)
    embed = Embed(description=caption, color=PASTEL_PINK)
    embed.set_image(url=f"attachment://{attachment.filename}")  # can't force 1:1, user should upload square
    class RentView(ui.View):
        def __init__(self):
            super().__init__(timeout=None)
        @ui.button(label="Rent", style=discord.ButtonStyle.primary)
        async def rent(self, interaction: discord.Interaction, button: ui.Button):
            member = interaction.user
            guild = interaction.guild
            name = f"{member.name}"
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                member: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.get_member(ADMIN_ID): discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            temp_channel = await guild.create_text_channel(name=name, overwrites=overwrites)
            await temp_channel.send(embed=embed, file=image_file, view=RentDoneView())
            await interaction.response.send_message(f"Đã tạo channel {temp_channel.mention}", ephemeral=True)
    await channel.send(embed=embed, file=image_file, view=RentView())
    try: await ctx.message.delete()
    except: pass

# -------------------------
# time / qr / text (pastel)
# -------------------------
@bot.command()
async def time(ctx, *, t: str):
    t = t.lower().replace(" ", "")
    hours = 0; minutes = 0
    h_match = re.search(r'(\d+)h', t)
    m_match = re.search(r'(\d+)m', t)
    if h_match: hours = int(h_match.group(1))
    if m_match: minutes = int(m_match.group(1))
    if hours == 0 and minutes == 0:
        return await ctx.reply("Không nhận diện được thời gian! VD: !time 1h30m, !time 45m", delete_after=6)
    start = datetime.now(VN_TZ); end = start + timedelta(hours=hours, minutes=minutes)
    embed = Embed(description=f"⏳ Bắt đầu: **{start.strftime('%H:%M:%S')}** → Kết thúc: **{end.strftime('%H:%M:%S')}**", color=PASTEL_PINK)
    await ctx.send(embed=embed)
    await asyncio.sleep(hours*3600 + minutes*60)
    await ctx.send(f"{ctx.author.mention} ⏰ Thời gian kết thúc: **{datetime.now(VN_TZ).strftime('%H:%M:%S')}**")

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
# MONTHLY REPORT
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
        header = f"📊 **Báo cáo lương tháng {now.strftime('%Y-%m')}**\nLương giờ = {fmt_vnd(LUONG_GIO_RATE)}/giờ\n\n"
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
# ON_READY
# -------------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id: {bot.user.id})")
    if not monthly_report_task.is_running():
        monthly_report_task.start()

# -------------------------
# ERROR HANDLING
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
# RUN
# -------------------------
if __name__ == "__main__":
    bot.run(TOKEN)
