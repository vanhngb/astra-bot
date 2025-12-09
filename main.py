# bot_full.py
# Full-featured Discord bot per user's spec (single file)
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

# IDs and settings (final confirmed)
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
CHANNEL_LUONG_ALL = 1448052039384043683

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
    # format with dot as thousands sep
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
# Welcome banner (anime pastel-like)
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
    # Create a banner-like embed: big title + avatar as thumbnail and image (simple approach)
    embed = Embed(title=f"Chào mừng {member.display_name}!", description=f"Chào mừng {member.mention} đến với ⋆. 𐙚˚࿔ 𝒜𝓈𝓉𝓇𝒶 𝜗𝜚˚⋆, mong bạn ở đây thật vui nhá ^^\nCó cần hỗ trợ gì thì <#{SUPPORT_CHANNEL_ID}> nhá", color=PASTEL_PINK)
    if av_url:
        embed.set_thumbnail(url=av_url)
        # use avatar also as big image to create banner feel (client will display)
        embed.set_image(url=av_url)
    embed.set_footer(text=f"Joined at {datetime.now(VN_TZ).strftime('%Y-%m-%d %H:%M:%S')}")
    try:
        await channel.send(embed=embed)
    except Exception as e:
        print("welcome send error:", e)

# -------------------------
# Voice create: create voice only (no paired text). No buttons posted to voice channel.
# -------------------------
@bot.event
async def on_voice_state_update(member, before, after):
    try:
        # Public voice trigger
        if (before.channel is None or (before.channel and before.channel.id != TRIGGER_VOICE_CREATE)) and after.channel and after.channel.id == TRIGGER_VOICE_CREATE:
            guild = member.guild
            name = f"⋆𐙚 ̊. - {member.name}"
            category = discord.utils.get(guild.categories, id=VOICE_CATEGORY_ID)
            overwrites_voice = {
                guild.default_role: discord.PermissionOverwrite(connect=True, view_channel=True),
                member: discord.PermissionOverwrite(connect=True, view_channel=True)
            }
            new_voice = await guild.create_voice_channel(name, overwrites=overwrites_voice, category=category, reason="Auto-created voice room")
            # move member to voice
            try:
                await member.move_to(new_voice)
            except:
                pass
            db_add_room = None  # we do not store extra for voice here (table exists but optional)
            # do NOT send control with buttons into voice (impossible). Optionally notify support channel
            # per request: do NOT send message to 1432685282955755595
            return

        # Private voice trigger
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
            try:
                await member.move_to(new_voice)
            except:
                pass
            return

    except Exception as e:
        print("on_voice_state_update error:", e)

# -------------------------
# Modal classes for IO and DNT
# -------------------------
class IOCreateModal(ui.Modal):
    # per your choice B earlier: modal won't collect mentions; modal used for optional note
    note = ui.TextInput(label="Ghi chú (tuỳ chọn)", required=False, style=discord.TextStyle.long)
    def __init__(self, ctx_info: dict):
        """
        ctx_info: {'target_id': str, 'hours': int, 'actor_id': str or None}
        """
        super().__init__(title="Xác nhận IO")
        self.ctx_info = ctx_info

    async def on_submit(self, interaction: discord.Interaction):
        tgt = self.ctx_info.get("target_id")
        hours = self.ctx_info.get("hours", 0)
        actor_id = self.ctx_info.get("actor_id")
        # update DB
        t = db_get_user(str(tgt))
        db_update_user(str(tgt), book_hours=int(t["book_hours"]) + int(hours))
        if actor_id:
            db_prf_add_hours(str(actor_id), int(hours))
        ch = bot.get_channel(CHANNEL_IO_DNT)
        if ch:
            try:
                await ch.send(f"<@{tgt}> : {hours} giờ")
            except:
                pass
        await interaction.response.send_message("Đã lưu IO.", ephemeral=True)

class DNTCreateModal(ui.Modal):
    note = ui.TextInput(label="Ghi chú (tuỳ chọn)", required=False, style=discord.TextStyle.long)
    def __init__(self, ctx_info: dict):
        """
        ctx_info: {'target_id': str, 'amount': int, 'actor_id': str or None}
        """
        super().__init__(title="Xác nhận Donate")
        self.ctx_info = ctx_info

    async def on_submit(self, interaction: discord.Interaction):
        tgt = self.ctx_info.get("target_id")
        amount = self.ctx_info.get("amount", 0)
        actor_id = self.ctx_info.get("actor_id")
        u = db_get_user(str(tgt))
        db_update_user(str(tgt), donate=int(u["donate"]) + int(amount))
        if actor_id:
            db_prf_add_donate(str(actor_id), int(amount))
        ch = bot.get_channel(CHANNEL_IO_DNT)
        if ch:
            try:
                await ch.send(f"<@{tgt}> : {fmt_vnd(amount)}")
            except:
                pass
        await interaction.response.send_message("Đã lưu Donate.", ephemeral=True)

# -------------------------
# Commands: io / dnt with modal fallback
# -------------------------
@bot.command(name="io")
async def cmd_io(ctx, *, raw: str = None):
    """
    Usage:
    - Preferred: !io 2h @target [by @actor]
      then bot opens modal to confirm (note optional).
    - If client doesn't support modal, parse directly from raw.
    """
    if not has_io_permission(ctx.author):
        return await ctx.reply("Bạn không có quyền dùng lệnh này.", delete_after=8)
    if not raw:
        return await ctx.reply("VD: !io 2h @user [by @actor]", delete_after=8)
    # parse
    parts = raw.split()
    time_token = parts[0]
    m = re.match(r"^(\d+)(?:\.\d+)?h$", time_token.lower())
    if not m:
        return await ctx.reply("Sai format time. VD: 2h", delete_after=8)
    hours = int(m.group(1))
    mentions = re.findall(r'<@!?(\d+)>', raw)
    if len(mentions) < 1:
        return await ctx.reply("Cần tag target.", delete_after=8)
    target_id = mentions[0]
    actor_id = mentions[1] if len(mentions) >= 2 else None
    # try open modal via interaction
    try:
        modal = IOCreateModal({'target_id': target_id, 'hours': hours, 'actor_id': actor_id})
        if hasattr(ctx, "interaction") and ctx.interaction:
            await ctx.interaction.response.send_modal(modal)
            try:
                await ctx.message.delete()
            except:
                pass
            return
        # fallback: try to use send_modal on ctx (some clients)
        await ctx.send("Mở form xác nhận IO (nếu client hỗ trợ modal)...", delete_after=6)
    except Exception:
        # fallback: directly save
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

@bot.command(name="dnt")
async def cmd_dnt(ctx, *, raw: str = None):
    """
    Usage:
    !dnt 20000 @target [by @actor]
    """
    if not has_io_permission(ctx.author):
        return await ctx.reply("Bạn không có quyền dùng lệnh này.", delete_after=8)
    if not raw:
        return await ctx.reply("VD: !dnt 20000 @user [by @actor]", delete_after=8)
    m = re.match(r"^(\d+)\s+", raw)
    if not m:
        return await ctx.reply("Sai cú pháp. VD: !dnt 20000 @user [by @actor]", delete_after=8)
    amount = int(m.group(1))
    mentions = re.findall(r'<@!?(\d+)>', raw)
    if len(mentions) < 1:
        return await ctx.reply("Cần tag target.", delete_after=8)
    target_id = mentions[0]
    actor_id = mentions[1] if len(mentions) >= 2 else None
    try:
        modal = DNTCreateModal({'target_id': target_id, 'amount': amount, 'actor_id': actor_id})
        if hasattr(ctx, "interaction") and ctx.interaction:
            await ctx.interaction.response.send_modal(modal)
            try:
                await ctx.message.delete()
            except:
                pass
            return
        await ctx.send("Mở form xác nhận Donate (nếu client hỗ trợ modal)...", delete_after=6)
    except Exception:
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

# -------------------------
# luong, prf, luongall, rs (reset)
# -------------------------
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

@bot.command()
@commands.has_permissions(administrator=True)
async def rs(ctx):
    # reset all luong and prf to 0 silently
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("UPDATE users SET book_hours=0, donate=0")
    cur.execute("DELETE FROM prf")
    conn.commit()
    conn.close()
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command()
async def luongall(ctx):
    # compile all users and post to CHANNEL_LUONG_ALL as embed
    rows = db_get_all_users()
    ch = bot.get_channel(CHANNEL_LUONG_ALL)
    if not ch:
        return await ctx.reply("Không tìm thấy channel báo cáo.", delete_after=8)
    embed = Embed(title="Tổng hợp lương", description="Ai thắc mắc về lương phản hồi trước 12h ngày mai nhaa", color=PASTEL_PINK)
    msg_text = ""
    for uid, hours, donate in rows:
        pay = int(hours) * LUONG_GIO_RATE
        total = pay + int(donate)
        msg_text += f"<@{uid}> — Giờ book: {hours} giờ | Lương giờ: {fmt_vnd(pay)} | Donate: {fmt_vnd(donate)} | Tổng: {fmt_vnd(total)}\n"
    if not msg_text:
        msg_text = "Chưa có dữ liệu."
    # Due to embed size limits, send one embed then plain text if needed
    embed.add_field(name="Chi tiết:", value=msg_text[:1024] if len(msg_text) <= 1024 else msg_text[:1024], inline=False)
    await ch.send(embed=embed)
    # if more content left, send as subsequent messages
    rest = msg_text[1024:]
    while rest:
        await ch.send(rest[:1900])
        rest = rest[1900:]

    try:
        await ctx.message.delete()
    except:
        pass

# -------------------------
# Code create / edit / delete (modal) with prefill for edit
# -------------------------
class CodeModal(ui.Modal):
    title_field = ui.TextInput(label="Tiêu đề", required=True)
    user_field = ui.TextInput(label="@user (mention)", required=True, placeholder="@user")
    content_field = ui.TextInput(label="Nội dung", style=discord.TextStyle.long, required=True)
    image_url_field = ui.TextInput(label="Image URL (optional)", required=False, placeholder="https://...")
    def __init__(self, existing=None):
        """
        existing: dict with keys title, target_user_id, content, image_url
        """
        super().__init__(title="Tạo / Sửa Code")
        self.existing = existing
        if existing:
            try:
                self.title_field.default = existing.get("title", "")
                self.user_field.default = f"<@{existing.get('target_user_id')}>" if existing.get("target_user_id") else ""
                self.content_field.default = existing.get("content", "")
                self.image_url_field.default = existing.get("image_url") or ""
            except Exception:
                pass

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
    modal = CodeModal(existing=None)
    try:
        if hasattr(ctx, "interaction") and ctx.interaction:
            await ctx.interaction.response.send_modal(modal)
            try:
                await ctx.message.delete()
            except:
                pass
            return
        await ctx.reply("Mở form tạo code... (nếu client hỗ trợ modal).", delete_after=6)
    except:
        await ctx.reply("Không thể mở modal trong ngữ cảnh này.", delete_after=8)

@bot.command()
async def code_edit(ctx, *, args: str = None):
    allowed = is_admin(ctx.author) or any(r.id == EXEMPT_ROLE_ID for r in ctx.author.roles)
    if not allowed:
        return await ctx.reply("Bạn không có quyền sửa code.", delete_after=8)
    if not args:
        return await ctx.reply("VD: !code_edit <title>", delete_after=8)
    title = args.strip().split()[0]
    data = db_get_code_by_title(title)
    if not data:
        return await ctx.reply("Không tìm thấy template với tiêu đề đó.", delete_after=8)
    modal = CodeModal(existing=data)
    try:
        if hasattr(ctx, "interaction") and ctx.interaction:
            await ctx.interaction.response.send_modal(modal)
            try:
                await ctx.message.delete()
            except:
                pass
            return
        # fallback: DM instruction
        await ctx.author.send("Không thể mở modal từ client này. Hãy dùng Discord PC/Web để edit template.")
    except:
        await ctx.reply("Không thể mở modal.", delete_after=8)

@bot.command()
async def code_delete(ctx, member: discord.Member = None):
    allowed = is_admin(ctx.author) or any(r.id == EXEMPT_ROLE_ID for r in ctx.author.roles)
    if not allowed:
        return await ctx.reply("Bạn không có quyền xóa code.", delete_after=8)
    if not member:
        return await ctx.reply("Cần @user để xóa code liên kết.", delete_after=8)
    db_delete_code_by_user_id(str(member.id))
    await ctx.reply(f"Đã xóa code cho {member.display_name}", delete_after=6)

# message listener for code titles (sending content when title typed)
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
# Giveaway modal
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
        try:
            await ctx.message.delete()
        except:
            pass
        if hasattr(ctx, "interaction") and ctx.interaction:
            await ctx.interaction.response.send_modal(modal)
        else:
            await ctx.send("Mở form tạo giveaway (nếu client hỗ trợ modal)...", delete_after=5)
    except:
        await ctx.send("Không thể mở modal trong client này.")

# -------------------------
# POST (fm / m) and Rent with private text channel creation
# Rent includes text "Nhấn Rent nha khách iu ơi ⋆𐙚 ̊." shown WITH the Rent button in image post channel
# Done button deletes the created private channel
# -------------------------
class RentDoneView(ui.View):
    @ui.button(label="Done", style=discord.ButtonStyle.danger)
    async def done(self, interaction: discord.Interaction, button: ui.Button):
        # delete the channel if user presses Done and if they have permission (owner or admin or role)
        try:
            channel = interaction.channel
            # allow admin or owner (owner is stored in channel topic if we set) or user messages
            # We'll allow admin or the member who created channel by checking channel.name against their name
            if interaction.user.guild_permissions.administrator or channel.name == interaction.user.name:
                await channel.delete()
                await interaction.response.send_message("Kênh đã xóa.", ephemeral=True)
            else:
                # try check topic for owner mention
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
        name = f"⋆𐙚 ̊ - {member.name}"
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
        # set channel topic to owner id for possible checks
        try:
            await temp_channel.edit(topic=f"owner:{member.id}")
        except:
            pass
        # send embed + image + greeting message in that channel
        try:
            await temp_channel.send(embed=self.embed, file=self.image_file)
        except:
            await temp_channel.send(embed=self.embed)
        # greeting inside private channel
        await temp_channel.send("Khách ơi đợi tí, bọn mình rep liền nhaaa ₊˚⊹ ᰔ")
        # Done button in channel to allow deletion
        await temp_channel.send("Nhấn Done khi xong nha yêu ơiiii", view=RentDoneView())
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
    # set image as 1:1 -> we can't force ratio but client respects square if image is square
    embed.set_image(url=f"attachment://{attachment.filename}")
    channel = bot.get_channel(IMAGE_CHANNEL_FEMALE if kind.lower()=="fm" else IMAGE_CHANNEL_MALE)
    if not channel:
        return await ctx.reply("Không tìm thấy channel ảnh.", delete_after=6)
    view = RentView(embed, image_file, ctx.author)
    # send message with Rent button and the specified text together (so text and button are together)
    await channel.send(content="Nhấn Rent nha khách iu ơi ⋆𐙚 ̊.", embed=embed, file=image_file, view=view)
    try:
        await ctx.message.delete()
    except:
        pass

# -------------------------
# !text: send embed without showing original sender info
# -------------------------
@bot.command()
async def text(ctx, *, content: str):
    embed = Embed(description=content, color=PASTEL_PINK)
    try:
        await ctx.message.delete()
    except:
        pass
    await ctx.send(embed=embed)

# -------------------------
# QR embed: combine text + qr.png into one embed
# -------------------------
@bot.command()
async def qr(ctx):
    path = "qr.png"
    embed = Embed(title="QR Payment", description="Sau khi thanh toán xong thì gửi bill vào đây nhá. Không ghi NDCK giúp mình nha ୨୧", color=PASTEL_PINK)
    if os.path.exists(path):
        embed.set_image(url="attachment://qr.png")
        await ctx.send(embed=embed, file=File(path, filename="qr.png"))
    else:
        await ctx.send(embed=embed)

# -------------------------
# !invv command: add permission for a user to join a voice (even if locked)
# Usage:
#   !invv @user             -> adds to voice that the command author is in
#   !invv @user <voice_id>  -> adds to specified voice id
# -------------------------
@bot.command()
async def invv(ctx, member: discord.Member = None, voice_id: str = None):
    if not member:
        return await ctx.reply("VD: !invv @user [voice_id]", delete_after=8)
    guild = ctx.guild
    target_voice = None
    # if voice_id provided try parse mention or id
    if voice_id:
        # allow mention or id
        m = re.match(r'<#?(\d+)>', voice_id)
        vid = m.group(1) if m else voice_id
        try:
            vid = int(vid)
            target_voice = guild.get_channel(vid)
        except:
            target_voice = None
    else:
        # try to use invoker's current voice channel
        if ctx.author.voice and ctx.author.voice.channel:
            target_voice = ctx.author.voice.channel
    if not target_voice or not isinstance(target_voice, discord.VoiceChannel):
        return await ctx.reply("Không tìm thấy voice channel để invite.", delete_after=8)
    try:
        await target_voice.set_permissions(member, connect=True, view_channel=True)
        await ctx.reply(f"Đã cấp quyền cho {member.mention} vào {target_voice.mention}", delete_after=8)
    except Exception as e:
        await ctx.reply(f"Lỗi khi cấp quyền: {e}", delete_after=8)

# -------------------------
# Utilities: clear, av, ban, mute, rd, pick
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
    pick_choice = random.choice(parts)
    await ctx.send(f"Chọn: **{pick_choice}**")

# -------------------------
# time command (timer)
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

# -------------------------
# on_ready and error handler
# -------------------------
@bot.event
async def on_ready():
    print(f"Bot running as {bot.user} (id: {bot.user.id})")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        try: await ctx.message.delete()
        except: pass
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Thiếu tham số.", delete_after=6)
    else:
        print("Command error:", error)

# -------------------------
# Run
# -------------------------
if __name__ == "__main__":
    bot.run(TOKEN)
