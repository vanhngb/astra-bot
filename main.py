# -------------------------
# FULL BOT READY FOR WEB (Render/Heroku/Replit)
# Includes all commands: !av, !text, !post, !ban, !mute, !io, !dnt, !prf, !luong, !rs, !luongall, !clear, !code, !code_edit, !<code>
# -------------------------

import os, re, sqlite3, random, asyncio
from datetime import datetime, timedelta
from threading import Thread
import pytz

import discord
from discord.ext import commands
from discord import Embed, File, ui

from flask import Flask

# ------------------------------------------------
# CONFIG & INITIALIZATION
# ------------------------------------------------
TOKEN = os.getenv("DISCORD_BOT_SECRET")
if not TOKEN:
    print("ERROR: set DISCORD_BOT_SECRET env variable")
    exit(1)

# Config IDs (VUI LÒNG KIỂM TRA LẠI CÁC ID NÀY)
WELCOME_CHANNEL_ID = 1432658695719751793
SUPPORT_CHANNEL_ID = 1432685282955755595
ADMIN_ID = 757555763559399424 # ID người quản trị
ALLOWED_ROLE_NAME = "Staff" # Tên vai trò được phép dùng lệnh IO/DNT
CHANNEL_IO_DNT = 1448047569421733981 # Kênh log IO/DNT
CHANNEL_LUONG_ALL = 1448052039384043683 # Kênh gửi tổng hợp lương

# Voice Channels/Category
TRIGGER_VOICE_CREATE = 1432658695719751794
TRIGGER_VOICE_PRIVATE = 1448063002518487092
VOICE_CATEGORY_ID = 1432658695719751792

# Constants
LUONG_GIO_RATE = 25000
PASTEL_PINK = 0xFFB7D5
VN_TZ = pytz.timezone("Asia/Ho_Chi_Minh")
DB_FILE = "luong.db"

# -------------------------
# Flask keep-alive
# -------------------------
app = Flask("")
@app.route("/")
def home(): return "Bot is running"
def run_flask(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8080)))
Thread(target=run_flask).start()

# -------------------------
# Bot init
# -------------------------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------------
# Database
# -------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, book_hours INTEGER DEFAULT 0, donate INTEGER DEFAULT 0)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS prf (user_id TEXT PRIMARY KEY, prf_hours INTEGER DEFAULT 0, prf_donate INTEGER DEFAULT 0)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS codes (title TEXT PRIMARY KEY, target_user_id TEXT, content TEXT, image_url TEXT)""") # Đã chỉnh sửa: title là PRIMARY KEY
    cur.execute("""CREATE TABLE IF NOT EXISTS rooms (voice_channel_id TEXT PRIMARY KEY, owner_id TEXT, is_hidden INTEGER DEFAULT 0, is_locked INTEGER DEFAULT 0)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS giveaways (id INTEGER PRIMARY KEY AUTOINCREMENT, channel_id TEXT, message_id TEXT, title TEXT, winners INTEGER, host_id TEXT, end_at TEXT, ended INTEGER DEFAULT 0)""")
    conn.commit(); conn.close()
init_db()

# DB helpers
def db_get_user(uid):
    conn=sqlite3.connect(DB_FILE); cur=conn.cursor()
    cur.execute("SELECT user_id, book_hours, donate FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT INTO users(user_id, book_hours, donate) VALUES (?,?,?)",(uid,0,0))
        conn.commit(); cur.execute("SELECT user_id, book_hours, donate FROM users WHERE user_id=?", (uid,))
        row = cur.fetchone()
    conn.close()
    return {"user_id": row[0], "book_hours": int(row[1]), "donate": int(row[2])}

def db_update_user_add(uid, hours=0, donate=0):
    conn=sqlite3.connect(DB_FILE); cur=conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users(user_id, book_hours, donate) VALUES (?,?,?)",(uid,0,0))
    cur.execute("UPDATE users SET book_hours=book_hours+?, donate=donate+? WHERE user_id=?", (int(hours), int(donate), uid))
    conn.commit(); conn.close()

def db_prf_get(uid):
    conn=sqlite3.connect(DB_FILE); cur=conn.cursor()
    cur.execute("SELECT prf_hours, prf_donate FROM prf WHERE user_id=?", (uid,))
    row = cur.fetchone()
    if not row: cur.execute("INSERT INTO prf(user_id, prf_hours, prf_donate) VALUES (?,?,?)",(uid,0,0)); conn.commit(); cur.execute("SELECT prf_hours, prf_donate FROM prf WHERE user_id=?", (uid,)); row=cur.fetchone()
    conn.close()
    return {"prf_hours": int(row[0]), "prf_donate": int(row[1])}

def db_prf_add(uid,hours=0,amount=0):
    conn=sqlite3.connect(DB_FILE); cur=conn.cursor()
    cur.execute("INSERT OR IGNORE INTO prf(user_id, prf_hours, prf_donate) VALUES (?,?,?)",(uid,0,0))
    cur.execute("UPDATE prf SET prf_hours=prf_hours+?, prf_donate=prf_donate+? WHERE user_id=?",(int(hours),int(amount),uid))
    conn.commit(); conn.close()

def db_get_all_users():
    conn=sqlite3.connect(DB_FILE); cur=conn.cursor()
    cur.execute("SELECT user_id, book_hours, donate FROM users"); rows=cur.fetchall(); conn.close(); return rows

# Code/Notification Helpers
def db_save_code(title, target_user_id, content, image_url=None):
    conn=sqlite3.connect(DB_FILE); cur=conn.cursor()
    cur.execute("INSERT OR REPLACE INTO codes(title, target_user_id, content, image_url) VALUES (?,?,?,?)",(title.lower(), str(target_user_id), content, image_url))
    conn.commit(); conn.close()

def db_update_code(title, field, value):
    conn=sqlite3.connect(DB_FILE); cur=conn.cursor()
    if field == 'delete':
        cur.execute("DELETE FROM codes WHERE title=?", (title.lower(),))
        conn.commit(); conn.close(); return True
    
    if field == 'ping': field_name = 'target_user_id'
    elif field == 'content': field_name = 'content'
    elif field == 'image': field_name = 'image_url'
    else: conn.close(); return False # Trường không hợp lệ

    # Cập nhật giá trị
    cur.execute(f"UPDATE codes SET {field_name}=? WHERE title=?", (value, title.lower()))
    conn.commit(); conn.close(); return True

def db_get_code_by_title(title):
    conn=sqlite3.connect(DB_FILE); cur=conn.cursor()
    cur.execute("SELECT title, target_user_id, content, image_url FROM codes WHERE title=?",(title.lower(),))
    row=cur.fetchone(); conn.close()
    if row: return {"title":row[0],"ping":row[1],"content":row[2],"image_url":row[3]}
    return None

def fmt_vnd(amount):
    try: a=int(round(float(amount)))
    except: a=0
    return f"{a:,} đ".replace(",",".")

def is_admin(member:discord.Member): return member.guild_permissions.administrator or member.id==ADMIN_ID

def has_io_permission(member:discord.Member):
    if is_admin(member): return True
    for r in member.roles:
        if r.name==ALLOWED_ROLE_NAME: return True
    return False

# -------------------------
# WELCOME
# -------------------------
@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if not channel: return
    try: av_url=member.avatar.url if member.avatar else member.default_avatar.url
    except: av_url=None
    embed=Embed(title=f"Chào mừng {member.display_name} đến với ⋆. 𐙚˚࿔ 𝒜𝓈𝓉𝓇𝒶 𝜗𝜚˚⋆",
                description=f"Mong bạn ở đây thật vui nhá ^^\nCó cần hỗ trợ gì thì <#{SUPPORT_CHANNEL_ID}> nhá", color=PASTEL_PINK)
    if av_url: embed.set_thumbnail(url=av_url)
    await channel.send(embed=embed)

# -------------------------
# VOICE CREATE
# -------------------------
@bot.event
async def on_voice_state_update(member,before,after):
    try:
        if (before.channel is None or (before.channel and before.channel.id!=TRIGGER_VOICE_CREATE)) and after.channel and after.channel.id==TRIGGER_VOICE_CREATE:
            guild=member.guild; category=discord.utils.get(guild.categories,id=VOICE_CATEGORY_ID)
            overwrites={guild.default_role:discord.PermissionOverwrite(connect=True,view_channel=True), member:discord.PermissionOverwrite(connect=True,view_channel=True)}
            new_voice = await guild.create_voice_channel(f"⋆𐙚 - {member.name}", overwrites=overwrites, category=category)
            try: await member.move_to(new_voice)
            except: pass
            return
        if (before.channel is None or (before.channel and before.channel.id!=TRIGGER_VOICE_PRIVATE)) and after.channel and after.channel.id==TRIGGER_VOICE_PRIVATE:
            guild=member.guild; category=discord.utils.get(guild.categories,id=VOICE_CATEGORY_ID)
            overwrites={guild.default_role:discord.PermissionOverwrite(connect=False,view_channel=False), member:discord.PermissionOverwrite(connect=True,view_channel=True)}
            admin_member=guild.get_member(ADMIN_ID); 
            if admin_member: overwrites[admin_member]=discord.PermissionOverwrite(connect=True,view_channel=True)
            new_voice = await guild.create_voice_channel(f"⋆𐙚 - {member.name}", overwrites=overwrites, category=category)
            try: await member.move_to(new_voice)
            except: pass
            return
    except Exception as e: print("on_voice_state_update error:", e)


# -------------------------
# COMMANDS
# -------------------------

# Lệnh bị thiếu: !post (Chỉ Admin)
@bot.command()
@commands.has_permissions(administrator=True)
async def post(ctx, channel: discord.TextChannel, *, content: str):
    embed = Embed(description=content, color=PASTEL_PINK)
    try:
        await channel.send(embed=embed)
        await ctx.send(f"✅ Đã gửi bài đăng đến {channel.mention}", delete_after=5)
    except Exception as e:
        await ctx.send(f"❌ Lỗi khi gửi bài: {e}", delete_after=8)
    try: await ctx.message.delete()
    except: pass

# Lệnh bị thiếu: !code (Tạo/Lưu code)
@bot.command()
@commands.has_permissions(administrator=True)
async def code(ctx, title: str, ping: str, content: str, image: str = None):
    """Tạo hoặc cập nhật một code (thông báo) mới."""
    if len(title) > 30: return await ctx.send("❌ Title quá dài (max 30 ký tự).", delete_after=8)
    
    # Kiểm tra xem ping có hợp lệ là mention hoặc ID không
    if not (ping.lower() == 'none' or re.match(r'^<@!?\d+>$', ping) or ping.isdigit()):
        return await ctx.send("❌ Ping phải là `@user`, ID, hoặc `none`.", delete_after=8)
    
    db_save_code(title, ping, content, image if image and image.lower() != 'none' else None)
    await ctx.send(f"✅ Code **{title.lower()}** đã được tạo/cập nhật.", delete_after=5)
    try: await ctx.message.delete()
    except: pass

# Lệnh bị thiếu: !code_edit (Sửa code)
@bot.command()
@commands.has_permissions(administrator=True)
async def code_edit(ctx, title: str, field: str, *, value: str = None):
    """Chỉnh sửa hoặc xóa code đã lưu: !code_edit <title> [ping|content|image|delete] <giá trị>"""
    field = field.lower()
    title = title.lower()

    if field == 'delete':
        if db_update_code(title, 'delete', None):
            await ctx.send(f"✅ Code **{title}** đã được xóa.", delete_after=5)
        else:
            await ctx.send(f"❌ Code **{title}** không tồn tại.", delete_after=8)
        return

    if field not in ['ping', 'content', 'image'] or not value:
        return await ctx.send("❌ Cú pháp: `!code_edit <title> [ping|content|image|delete] <giá trị>`", delete_after=10)

    if db_update_code(title, field, value if value.lower() != 'none' else None):
        await ctx.send(f"✅ Đã cập nhật trường **{field}** của code **{title}**.", delete_after=5)
    else:
        await ctx.send(f"❌ Code **{title}** không tồn tại hoặc lỗi trường dữ liệu.", delete_after=8)
        
    try: await ctx.message.delete()
    except: pass
    
# Lệnh gọi code (Dynamic command handler)
@bot.event
async def on_message(message):
    if message.author.bot: return
    ctx = await bot.get_context(message)
    
    # Kiểm tra nếu lệnh bắt đầu bằng '!' và không phải là lệnh có sẵn
    if ctx.prefix and message.content.startswith(ctx.prefix):
        command_name = message.content[len(ctx.prefix):].split()[0].lower()
        if command_name not in bot.all_commands:
            # Đây có thể là lệnh gọi code
            code_data = db_get_code_by_title(command_name)
            if code_data:
                embed = Embed(description=code_data['content'], color=PASTEL_PINK)
                if code_data['image_url']:
                    embed.set_image(url=code_data['image_url'])
                
                ping_msg = code_data['ping'] if code_data['ping'].lower() != 'none' else ''
                
                await message.channel.send(ping_msg, embed=embed)
                return # Đã xử lý lệnh code, không tiếp tục xử lý lệnh khác
            
    await bot.process_commands(message) # Xử lý các lệnh Discord đã định nghĩa

# !av
@bot.command()
async def av(ctx, member:discord.Member=None):
    member=member or ctx.author
    avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
    embed=Embed(title=f"Avatar {member.display_name}", color=PASTEL_PINK)
    embed.set_image(url=avatar_url)
    await ctx.send(embed=embed)

# !text
@bot.command()
async def text(ctx, *, content:str):
    embed=Embed(description=content,color=PASTEL_PINK)
    try: await ctx.message.delete()
    except: pass
    await ctx.send(embed=embed)

# !clear (Hỗ trợ cả <số lượng> và "all")
@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount_str: str):
    # Kiểm tra quyền bot
    if not ctx.channel.permissions_for(ctx.guild.me).manage_messages:
        return await ctx.send("❌ Bot cần có quyền Quản lý Tin nhắn.", delete_after=6)

    try: await ctx.message.delete()
    except: pass
        
    if amount_str.lower() == 'all':
        try: 
            deleted = await ctx.channel.purge(limit=100)
            await ctx.send(f"✅ Đã xóa **{len(deleted)}** tin nhắn gần nhất.", delete_after=5)
        except Exception as e: 
            await ctx.send(f"❌ Lỗi khi xóa tất cả: {e}", delete_after=6)
        return

    try:
        amount = int(amount_str)
        if amount <= 0: 
            return await ctx.reply("❌ Số lượng phải lớn hơn 0.", delete_after=6)
        
        deleted = await ctx.channel.purge(limit=amount) 
        await ctx.send(f"✅ Đã xóa thành công **{len(deleted)}** tin nhắn.", delete_after=5)
        
    except ValueError:
        await ctx.send("❌ Cú pháp sai. Vui lòng dùng: `!clear <số lượng>` (VD: `!clear 5`) hoặc `!clear all`.", delete_after=8)
    except Exception as e:
        await ctx.send(f"❌ Lỗi khi xóa: {e}", delete_after=6)


@clear.error
async def clear_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Bạn không có quyền Quản lý Tin nhắn.", delete_after=6)
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Cú pháp: `!clear <số lượng>` (VD: `!clear 5`) hoặc `!clear all`.", delete_after=6)


# !ban
@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member:discord.Member=None, *, reason:str="Không có lý do"):
    if not member: return await ctx.send("❌ Chọn người để ban.")
    if member.top_role >= ctx.author.top_role and not is_admin(ctx.author):
        return await ctx.send("❌ Bạn không thể ban người có vai trò cao hơn hoặc bằng bạn.")
    try: 
        await member.ban(reason=f"Banned by {ctx.author} for: {reason}")
        await ctx.send(f"✅ Đã ban {member.mention} (Lý do: {reason})")
    except Exception as e: 
        await ctx.send(f"❌ Lỗi khi ban: {e}", delete_after=6)

# !mute
@bot.command()
@commands.has_permissions(manage_roles=True)
async def mute(ctx, time:str=None, member:discord.Member=None):
    if not member: return await ctx.reply("❌ Cần @user",delete_after=8)
    if not time: return await ctx.reply("❌ Thiếu thời gian VD: `!mute 1m @user`",delete_after=8)

    m=re.match(r"^(\d+)([smhd])$",time.lower())
    if not m: return await ctx.reply("❌ Sai định dạng thời gian (s/m/h/d).",delete_after=8)
    
    qty=int(m.group(1)); unit=m.group(2)
    seconds = qty*(1 if unit=='s' else 60 if unit=='m' else 3600 if unit=='h' else 86400)
    
    if seconds > 28 * 86400:
        return await ctx.reply("❌ Thời gian mute quá dài (tối đa 28 ngày).", delete_after=8)

    if seconds > 0:
        duration = timedelta(seconds=seconds)
        try:
            await member.timeout(duration, reason=f"Muted by {ctx.author} for {time}")
            await ctx.send(f"✅ Đã mute {member.mention} trong **{time}**.")
        except Exception as e:
            await ctx.send(f"❌ Lỗi khi mute: {e}", delete_after=8)
    
    try: await ctx.message.delete()
    except: pass

# !io (Giữ hours:int và thêm logic PRF)
@bot.command()
async def io(ctx, hours:int, member:discord.Member, by:discord.Member=None):
    if not has_io_permission(ctx.author): return await ctx.reply("❌ Không có quyền.",delete_after=8)
    if hours <= 0: return await ctx.reply("❌ Giờ book phải lớn hơn 0.", delete_after=8)

    db_update_user_add(str(member.id), hours=hours)
    
    prf_target = by or ctx.author
    db_prf_add(str(prf_target.id), hours=hours)

    ch=bot.get_channel(CHANNEL_IO_DNT)
    log_msg = f"✅ IO: {member.mention} (+{hours} giờ lương) | Booked bởi: {prf_target.mention} (PRF +{hours} giờ)"
    
    if ch: await ch.send(log_msg)
    else: await ctx.send(log_msg)

# !dnt (Thêm logic PRF)
@bot.command()
async def dnt(ctx, amount:int, member:discord.Member, by:discord.Member=None):
    if not has_io_permission(ctx.author): return await ctx.reply("❌ Không có quyền.",delete_after=8)
    if amount <= 0: return await ctx.reply("❌ Số tiền donate phải lớn hơn 0.", delete_after=8)

    db_update_user_add(str(member.id), donate=amount)
    
    prf_target = by or ctx.author
    db_prf_add(str(prf_target.id), amount=amount)
    
    ch=bot.get_channel(CHANNEL_IO_DNT)
    log_msg = f"✅ DNT: {member.mention} (+{fmt_vnd(amount)} lương) | Donate bởi: {prf_target.mention} (PRF +{fmt_vnd(amount)})"
    
    if ch: await ch.send(log_msg)
    else: await ctx.send(log_msg)

# !prf
@bot.command()
async def prf(ctx, member:discord.Member=None):
    target=member or ctx.author; p=db_prf_get(str(target.id))
    embed=Embed(title=f"PRF {target.display_name}",color=PASTEL_PINK)
    embed.add_field(name="𐙚 Giờ đã book:",value=f"{p['prf_hours']} giờ",inline=False)
    embed.add_field(name="𐙚 Donate:",value=f"{fmt_vnd(p['prf_donate'])}",inline=False)
    await ctx.send(embed=embed)
    try: await ctx.message.delete()
    except: pass

# !luong
@bot.command()
async def luong(ctx, member:discord.Member=None):
    target=member or ctx.author
    u=db_get_user(str(target.id))
    hours=int(u["book_hours"]); donate=int(u["donate"])
    pay=hours*LUONG_GIO_RATE; total=pay+donate
    embed=Embed(title=f"Lương của {target.display_name}",color=PASTEL_PINK)
    embed.add_field(name="𐙚 Giờ book:", value=f"{hours} giờ",inline=False)
    embed.add_field(name="𐙚 Lương giờ:", value=f"{fmt_vnd(pay)}",inline=False)
    embed.add_field(name="𐙚 Donate:", value=f"{fmt_vnd(donate)}",inline=False)
    embed.add_field(name="𐙚 Lương tổng:", value=f"{fmt_vnd(total)}",inline=False)
    
    try: 
        await target.send(embed=embed)
        if target != ctx.author:
            await ctx.reply(f"✅ Đã gửi lương của {target.display_name} vào DM.", delete_after=8)
    except discord.Forbidden: 
        await ctx.reply("❌ Không thể gửi DM, vui lòng bật DM.",delete_after=8)
    
    try: await ctx.message.delete()
    except: pass

# !rs (Reset Lương và PRF)
@bot.command()
@commands.has_permissions(administrator=True)
async def rs(ctx):
    conn=sqlite3.connect(DB_FILE); cur=conn.cursor()
    cur.execute("UPDATE users SET book_hours=0, donate=0")
    cur.execute("DELETE FROM prf"); conn.commit(); conn.close()
    await ctx.send("✅ Đã reset toàn bộ Lương và PRF.")
    try: await ctx.message.delete()
    except: pass

# !luongall (Gửi tổng hợp lương)
@bot.command()
@commands.has_permissions(administrator=True)
async def luongall(ctx):
    rows=db_get_all_users()
    ch=bot.get_channel(CHANNEL_LUONG_ALL)
    if not ch: return await ctx.reply(f"❌ Không tìm thấy channel ID: {CHANNEL_LUONG_ALL}.",delete_after=8)
    
    embed=Embed(title=f"Tổng hợp Lương tháng {datetime.now(VN_TZ).strftime('%m/%Y')}",color=PASTEL_PINK)
    msg_text_parts = []
    
    for uid,hours,donate in rows:
        member = ctx.guild.get_member(int(uid))
        name = member.display_name if member else f"ID:{uid}"
        pay=hours*LUONG_GIO_RATE; total=pay+donate
        
        line = f"**{name}** — Giờ: {hours} | Lương giờ: {fmt_vnd(pay)} | Donate: {fmt_vnd(donate)} | **Tổng: {fmt_vnd(total)}**\n"
        
        if not msg_text_parts or len(msg_text_parts[-1]) + len(line) > 1900:
            msg_text_parts.append(line)
        else:
            msg_text_parts[-1] += line
            
    if not msg_text_parts:
        embed.add_field(name="Chi tiết:", value="Không có dữ liệu lương trong tháng này.", inline=False)
        await ch.send(embed=embed)
        return

    embed.add_field(name="Chi tiết:", value=msg_text_parts[0][:1024], inline=False)
    await ch.send(embed=embed)
    
    for part in msg_text_parts[1:]:
        await ch.send(part)
        
    try: await ctx.message.delete()
    except: pass

# -------------------------
# ON READY
# -------------------------
@bot.event
async def on_ready():
    print(f"Bot running as {bot.user} (id:{bot.user.id})")

# -------------------------
# RUN BOT
# -------------------------
if __name__ == '__main__':
    bot.run(TOKEN)

