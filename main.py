import os, re, sqlite3, asyncio
from datetime import datetime, timedelta
from threading import Thread
import pytz

import discord
from discord.ext import commands
from discord import Embed, ui, app_commands

from flask import Flask

# ------------------------------------------------
# CẤU HÌNH CỐ ĐỊNH & INITIALIZATION
# ------------------------------------------------
# Lấy Token từ biến môi trường
TOKEN = os.getenv("DISCORD_BOT_SECRET")
if not TOKEN:
    print("ERROR: set DISCORD_BOT_SECRET env variable")
    exit(1)

# Config IDs (VUI LÒNG KIỂM TRA LẠI CÁC ID NÀY)
WELCOME_CHANNEL_ID = 1432658695719751793
SUPPORT_CHANNEL_ID = 1432685282955755595
ADMIN_ID = 757555763559399424 
ALLOWED_ROLE_NAME = "Staff"
CHANNEL_IO_DNT = 1448047569421733981
CHANNEL_LUONG_ALL = 1448052039384043683

# Channels/Category cho lệnh !post/Rent
RENT_CATEGORY_ID = 1448062526599205037
POST_FM_CHANNEL_ID = 1432691499094769704
POST_M_CHANNEL_ID = 1432691597363122357

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
def run_flask(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8080)), debug=False)
Thread(target=run_flask).start()

# -------------------------
# Bot init
# -------------------------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------------
# DATABASE SETUP & HELPERS (Giữ nguyên cấu trúc hàm cũ)
# -------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, book_hours INTEGER DEFAULT 0, donate INTEGER DEFAULT 0)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS prf (user_id TEXT PRIMARY KEY, prf_hours INTEGER DEFAULT 0, prf_donate INTEGER DEFAULT 0)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS codes (title TEXT PRIMARY KEY, target_user_id TEXT, content TEXT, image_url TEXT)""") 
    cur.execute("""CREATE TABLE IF NOT EXISTS rooms (voice_channel_id TEXT PRIMARY KEY, owner_id TEXT, is_hidden INTEGER DEFAULT 0, is_locked INTEGER DEFAULT 0)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS rent_rooms (channel_id TEXT PRIMARY KEY, user_id TEXT, created_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS giveaways (id INTEGER PRIMARY KEY AUTOINCREMENT, channel_id TEXT, message_id TEXT, title TEXT, winners INTEGER, host_id TEXT, end_at TEXT, ended INTEGER DEFAULT 0)""")
    conn.commit(); conn.close()
init_db()

# DB helpers (Giữ nguyên logic hàm cũ)
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
    else: conn.close(); return False 

    cur.execute(f"UPDATE codes SET {field_name}=? WHERE title=?", (value, title.lower()))
    conn.commit(); conn.close(); return True

def db_get_code_by_title(title):
    conn=sqlite3.connect(DB_FILE); cur=conn.cursor()
    cur.execute("SELECT title, target_user_id, content, image_url FROM codes WHERE title=?",(title.lower(),))
    row=cur.fetchone(); conn.close()
    if row: return {"title":row[0],"ping":row[1],"content":row[2],"image_url":row[3]}
    return None

# Rent Room Helpers
def db_save_rent_room(channel_id, user_id):
    conn=sqlite3.connect(DB_FILE); cur=conn.cursor()
    cur.execute("INSERT OR REPLACE INTO rent_rooms(channel_id, user_id, created_at) VALUES (?,?,?)", (str(channel_id), str(user_id), datetime.now(VN_TZ).isoformat()))
    conn.commit(); conn.close()

def db_get_rent_room(channel_id):
    conn=sqlite3.connect(DB_FILE); cur=conn.cursor()
    cur.execute("SELECT user_id FROM rent_rooms WHERE channel_id=?", (str(channel_id),))
    row=cur.fetchone(); conn.close()
    return row[0] if row else None

def db_delete_rent_room(channel_id):
    conn=sqlite3.connect(DB_FILE); cur=conn.cursor()
    cur.execute("DELETE FROM rent_rooms WHERE channel_id=?", (str(channel_id),))
    conn.commit(); conn.close()

# Giveaway Helpers
def db_save_giveaway(channel_id, message_id, title, winners, host_id, end_at):
    conn=sqlite3.connect(DB_FILE); cur=conn.cursor()
    cur.execute("INSERT INTO giveaways(channel_id, message_id, title, winners, host_id, end_at) VALUES (?,?,?,?,?,?)", 
                (str(channel_id), str(message_id), title, winners, str(host_id), end_at.isoformat()))
    conn.commit(); conn.close()

# -------------------------
# UTILS
# -------------------------
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
# CUSTOM VIEWS / COMPONENTS
# -------------------------

# View cho lệnh !post/Rent
class RentView(ui.View):
    def __init__(self, original_embed: Embed, user_request: discord.Member, guild: discord.Guild, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_embed = original_embed
        self.user_request = user_request
        self.guild = guild
        self.staff_role = discord.utils.get(guild.roles, name=ALLOWED_ROLE_NAME)
        self.timeout = None

    @ui.button(label="Nhấn Rent nha khách iu ơi", style=discord.ButtonStyle.green)
    async def rent_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        
        button.disabled = True
        await interaction.message.edit(view=self)
        
        # Cấu hình quyền cho kênh riêng tư
        overwrites = {
            self.guild.default_role: discord.PermissionOverwrite(read_messages=False, view_channel=False),
            self.user_request: discord.PermissionOverwrite(read_messages=True, view_channel=True, send_messages=True),
            self.guild.me: discord.PermissionOverwrite(read_messages=True, view_channel=True, send_messages=True),
        }
        # Thêm Admin và Staff
        admin_member = self.guild.get_member(ADMIN_ID)
        if admin_member: overwrites[admin_member] = discord.PermissionOverwrite(read_messages=True, view_channel=True, send_messages=True)
        if self.staff_role: overwrites[self.staff_role] = discord.PermissionOverwrite(read_messages=True, view_channel=True, send_messages=True)
        
        try:
            category = discord.utils.get(self.guild.categories, id=RENT_CATEGORY_ID)
            
            # Tạo kênh chat riêng tư
            rent_channel = await self.guild.create_text_channel(
                f" - {self.user_request.name}", 
                category=category, 
                overwrites=overwrites
            )
            
            # Lưu thông tin phòng vào DB
            db_save_rent_room(rent_channel.id, self.user_request.id)
            
            # Gửi embed ban đầu và nút quản lý
            await rent_channel.send(f"{self.user_request.mention}, Khách ơi đợi tí, bọn mình rep liền nhaaa", embed=self.original_embed)
            
            # Gửi nút Done/Unlock
            management_view = RentManagementView(self.user_request, self.staff_role, self.guild)
            await rent_channel.send("Bấm Done để xóa kênh nha bạn ơii", view=management_view)
            
            await interaction.followup.send("Đã tạo kênh: {}".format(rent_channel.mention), ephemeral=True)

        except Exception as e:
            await interaction.followup.send("Lỗi khi tạo kênh: {}".format(e), ephemeral=True)


class RentManagementView(ui.View):
    def __init__(self, user_owner: discord.Member, staff_role: discord.Role, guild: discord.Guild, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_owner = user_owner
        self.staff_role = staff_role
        self.guild = guild
        self.is_locked = True
        self.timeout = None

    async def check_permissions(self, interaction: discord.Interaction):
        # Chỉ admin, staff hoặc người tạo mới được dùng nút này
        if interaction.user.id == self.user_owner.id or is_admin(interaction.user) or (self.staff_role and self.staff_role in interaction.user.roles):
            return True
        await interaction.response.send_message("Bạn không có quyền sử dụng nút này.", ephemeral=True)
        return False

    @ui.button(label="Done", style=discord.ButtonStyle.red)
    async def done_button(self, interaction: discord.Interaction, button: ui.Button):
        if not await self.check_permissions(interaction): return

        # Xác nhận xóa
        await interaction.response.send_message("Bạn có chắc chắn muốn xóa kênh này?", view=ConfirmDeleteView(interaction.channel.id), ephemeral=True)
        self.stop()
    
    @ui.button(label="Unlock", style=discord.ButtonStyle.secondary)
    async def unlock_button(self, interaction: discord.Interaction, button: ui.Button):
        if not await self.check_permissions(interaction): return
        
        channel = interaction.channel
        
        # Cập nhật quyền cho @everyone (default_role)
        overwrites = channel.overwrites
        overwrites[self.guild.default_role] = discord.PermissionOverwrite(read_messages=True, view_channel=True, send_messages=True)
        
        try:
            await channel.edit(overwrites=overwrites)
            self.is_locked = False
            button.label = "Lock"
            button.style = discord.ButtonStyle.primary
            await interaction.response.edit_message(view=self)
            await channel.send("Kênh đã được Mở Khóa (Mọi người đều có thể thấy và tham gia).")
        except Exception as e:
            await interaction.response.send_message("Lỗi khi mở khóa: {}".format(e), ephemeral=True)

class ConfirmDeleteView(ui.View):
    def __init__(self, channel_id: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.channel_id = channel_id
        self.timeout = 60 # Tự động xóa sau 60s

    @ui.button(label="Xóa Ngay", style=discord.ButtonStyle.red)
    async def confirm_delete(self, interaction: discord.Interaction, button: ui.Button):
        channel = bot.get_channel(self.channel_id)
        if channel:
            await interaction.response.send_message("Kênh sẽ bị xóa trong vài giây...", ephemeral=True)
            try:
                # Xóa khỏi DB và xóa kênh
                db_delete_rent_room(self.channel_id)
                await channel.delete()
            except Exception as e:
                await interaction.followup.send("Lỗi khi xóa kênh: {}".format(e), ephemeral=True)
        self.stop()

    @ui.button(label="Hủy Bỏ", style=discord.ButtonStyle.secondary)
    async def cancel_delete(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(content="Hủy xóa kênh.", view=None)
        self.stop()

# -------------------------
# EVENTS
# -------------------------
@bot.event
async def on_ready():
    print("Bot running as {} (id:{})".format(bot.user, bot.user.id))

@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if not channel: return
    try: av_url=member.avatar.url if member.avatar else member.default_avatar.url
    except: av_url=None
    embed=Embed(title="Chào mừng {} đến với . Astra".format(member.display_name),
                description="Mong bạn ở đây thật vui nhá ^^\\nCó cần hỗ trợ gì thì <#{}> nhá".format(SUPPORT_CHANNEL_ID), color=PASTEL_PINK)
    if av_url: embed.set_thumbnail(url=av_url)
    await channel.send(embed=embed)

# VOICE CREATE (Đã thêm logic xóa kênh rỗng)
@bot.event
async def on_voice_state_update(member, before, after):
    # Logic tạo kênh
    try:
        if (before.channel is None or (before.channel and before.channel.id != TRIGGER_VOICE_CREATE)) and after.channel and after.channel.id == TRIGGER_VOICE_CREATE:
            guild = member.guild; category = discord.utils.get(guild.categories, id=VOICE_CATEGORY_ID)
            overwrites = {guild.default_role: discord.PermissionOverwrite(connect=True, view_channel=True), member: discord.PermissionOverwrite(connect=True, view_channel=True)}
            new_voice = await guild.create_voice_channel(" - {}".format(member.name), overwrites=overwrites, category=category)
            try: await member.move_to(new_voice)
            except: pass
        
        elif (before.channel is None or (before.channel and before.channel.id != TRIGGER_VOICE_PRIVATE)) and after.channel and after.channel.id == TRIGGER_VOICE_PRIVATE:
            guild = member.guild; category = discord.utils.get(guild.categories, id=VOICE_CATEGORY_ID)
            # Khóa mặc định (chỉ người tạo và admin thấy)
            overwrites = {guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=False), member: discord.PermissionOverwrite(connect=True, view_channel=True)}
            admin_member = guild.get_member(ADMIN_ID);
            if admin_member: overwrites[admin_member] = discord.PermissionOverwrite(connect=True, view_channel=True)
            new_voice = await guild.create_voice_channel(" - {}".format(member.name), overwrites=overwrites, category=category)
            try: await member.move_to(new_voice)
            except: pass

    except Exception as e: 
        print("on_voice_state_update error (Create):", e)
        
    # Logic xóa kênh rỗng (chỉ xóa kênh trong VOICE_CATEGORY_ID và không phải kênh trigger)
    if before.channel and before.channel.category_id == VOICE_CATEGORY_ID:
        if before.channel.id != TRIGGER_VOICE_CREATE and before.channel.id != TRIGGER_VOICE_PRIVATE:
            if len(before.channel.members) == 0:
                try:
                    await before.channel.delete()
                except Exception as e:
                    print("on_voice_state_update error (Delete):", e)

# Dynamic command handler (Code, !gw)
@bot.event
async def on_message(message):
    if message.author.bot: return
    ctx = await bot.get_context(message)
    
    # Xử lý lệnh code động: !<title>
    if ctx.prefix and message.content.startswith(ctx.prefix):
        command_name = message.content[len(ctx.prefix):].split()[0].lower()
        if command_name not in bot.all_commands:
            code_data = db_get_code_by_title(command_name)
            if code_data:
                embed = Embed(description=code_data['content'], color=PASTEL_PINK)
                if code_data['image_url']:
                    embed.set_image(url=code_data['image_url'])
                
                ping_msg = code_data['ping'] if code_data['ping'].lower() != 'none' else ''
                
                await message.channel.send(ping_msg, embed=embed)
                return 
            
    await bot.process_commands(message) 

# -------------------------
# COMMANDS CƠ BẢN
# -------------------------

# !av
@bot.command()
async def av(ctx, member:discord.Member=None):
    member=member or ctx.author
    avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
    embed=Embed(title="Avatar {}".format(member.display_name), color=PASTEL_PINK)
    embed.set_image(url=avatar_url)
    await ctx.send(embed=embed)
    try: await ctx.message.delete()
    except: pass

# !text
@bot.command()
async def text(ctx, *, content:str):
    embed=Embed(description=content,color=PASTEL_PINK)
    try: await ctx.message.delete()
    except: pass
    await ctx.send(embed=embed)

# !clear
@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount_str: str):
    if not ctx.channel.permissions_for(ctx.guild.me).manage_messages:
        return await ctx.send("Bot cần có quyền Quản lý Tin nhắn.", delete_after=6)
    
    try: await ctx.message.delete()
    except: pass
        
    limit = None
    if amount_str.lower() == 'all':
        limit = 100
    else:
        try: amount = int(amount_str)
        except ValueError:
            return await ctx.send("Cú pháp sai. Vui lòng dùng: 'clear <số lượng>' (VD: 'clear 5') hoặc 'clear all'.", delete_after=8)
        if amount <= 0: return await ctx.reply("Số lượng phải lớn hơn 0.", delete_after=6)
        limit = amount 

    try: 
        deleted = await ctx.channel.purge(limit=limit)
        await ctx.send("Đã xóa thành công {} tin nhắn.".format(len(deleted)), delete_after=5)
    except Exception as e: 
        await ctx.send("Lỗi khi xóa: {}".format(e), delete_after=6)

# !ban
@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member:discord.Member=None, *, reason:str="Không có lý do"):
    if not member: return await ctx.send("Chọn người để ban.")
    if member.top_role >= ctx.author.top_role and not is_admin(ctx.author):
        return await ctx.send("Bạn không thể ban người có vai trò cao hơn hoặc bằng bạn.")
    try: 
        await member.ban(reason="Banned by {} for: {}".format(ctx.author, reason))
        await ctx.send("Đã ban {} (Lý do: {})".format(member.mention, reason))
    except Exception as e: 
        await ctx.send("Lỗi khi ban: {}".format(e), delete_after=6)

# !mute (Đã sửa cú pháp: member trước time)
@bot.command()
@commands.has_permissions(manage_roles=True)
async def mute(ctx, member:discord.Member=None, time:str=None):
    if not member: return await ctx.reply("Cần @user",delete_after=8)
    if not time: return await ctx.reply("Thiếu thời gian VD: 'mute @user 1m'",delete_after=8)

    m=re.match(r"^(\d+)([smhd])$",time.lower())
    if not m: return await ctx.reply("Sai định dạng thời gian (s/m/h/d).",delete_after=8)
    
    qty=int(m.group(1)); unit=m.group(2)
    seconds = qty*(1 if unit=='s' else 60 if unit=='m' else 3600 if unit=='h' else 86400)
    
    if seconds > 28 * 86400:
        return await ctx.reply("Thời gian mute quá dài (tối đa 28 ngày).", delete_after=8)

    if seconds > 0:
        duration = timedelta(seconds=seconds)
        try:
            await member.timeout(duration, reason="Muted by {} for {}".format(ctx.author, time))
            await ctx.send("Đã mute {} trong **{}**.".format(member.mention, time))
        except Exception as e:
            await ctx.send("Lỗi khi mute: {}".format(e), delete_after=8)
    
    try: await ctx.message.delete()
    except: pass

# -------------------------
# COMMANDS LƯƠNG & PRF
# -------------------------

# !io (Giữ hours:int và thêm logic PRF)
@bot.command()
async def io(ctx, hours:int, member:discord.Member, by:discord.Member=None):
    if not has_io_permission(ctx.author): return await ctx.reply("Không có quyền.",delete_after=8)
    if hours <= 0: return await ctx.reply("Giờ book phải lớn hơn 0.", delete_after=8)

    db_update_user_add(str(member.id), hours=hours)
    
    prf_target = by or ctx.author
    db_prf_add(str(prf_target.id), hours=hours)

    ch=bot.get_channel(CHANNEL_IO_DNT)
    log_msg = “{} (+{} giờ lương)".format(member.mention, hours, prf_target.mention, hours)
    
    if ch: await ch.send(log_msg)
    else: await ctx.send(log_msg)
    
    try: await ctx.message.delete()
    except: pass

# !dnt (Thêm logic PRF)
@bot.command()
async def dnt(ctx, amount:int, member:discord.Member, by:discord.Member=None):
    if not has_io_permission(ctx.author): return await ctx.reply("Không có quyền.",delete_after=8)
    if amount <= 0: return await ctx.reply("Số tiền donate phải lớn hơn 0.", delete_after=8)

    db_update_user_add(str(member.id), donate=amount)
    
    prf_target = by or ctx.author
    db_prf_add(str(prf_target.id), amount=amount)
    
    ch=bot.get_channel(CHANNEL_IO_DNT)
    log_msg = "Donate: {} (+{} lương)".format(member.mention, fmt_vnd(amount), prf_target.mention, fmt_vnd(amount))
    
    if ch: await ch.send(log_msg)
    else: await ctx.send(log_msg)
    
    try: await ctx.message.delete()
    except: pass

# !prf (Cập nhật định dạng: dùng ♡ và sửa 'Donate' thành 'Đã Donate')
@bot.command()
async def prf(ctx, member:discord.Member=None):
    target=member or ctx.author; p=db_prf_get(str(target.id))
    embed=Embed(title="PRF {}".format(target.display_name),color=PASTEL_PINK)
    embed.add_field(name="♡ Giờ đã book:",value="{} giờ".format(p['prf_hours']),inline=False)
    embed.add_field(name="♡ Đã Donate:",value="{}".format(fmt_vnd(p['prf_donate'])),inline=False)
    await ctx.send(embed=embed)
    try: await ctx.message.delete()
    except: pass

# !luong (Cập nhật định dạng: dùng ♡)
@bot.command()
async def luong(ctx, member:discord.Member=None):
    target=member or ctx.author
    u=db_get_user(str(target.id))
    hours=int(u["book_hours"]); donate=int(u["donate"])
    pay=hours*LUONG_GIO_RATE; total=pay+donate
    embed=Embed(title="Lương của {}".format(target.display_name),color=PASTEL_PINK)
    embed.add_field(name="♡ Giờ book:", value="{} giờ".format(hours),inline=False)
    embed.add_field(name="♡ Lương giờ:", value="{}".format(fmt_vnd(pay)),inline=False)
    embed.add_field(name="♡ Donate:", value="{}".format(fmt_vnd(donate)),inline=False)
    embed.add_field(name="♡ Lương tổng:", value="{}".format(fmt_vnd(total)),inline=False)
    
    if member is None: # !luong (Gửi DM)
        try: 
            await ctx.author.send(embed=embed)
            await ctx.reply("Check DM nha tình iuuu.", delete_after=8)
        except discord.Forbidden: 
            await ctx.reply("Không thể gửi DM, vui lòng bật DM.",delete_after=8)
    else: # !luong @user (Gửi trực tiếp)
        await ctx.send(embed=embed)
    
    try: await ctx.message.delete()
    except: pass

# !rs (Reset Lương và PRF)
@bot.command()
@commands.has_permissions(administrator=True)
async def rs(ctx):
    conn=sqlite3.connect(DB_FILE); cur=conn.cursor()
    cur.execute("UPDATE users SET book_hours=0, donate=0")
    cur.execute("DELETE FROM prf"); conn.commit(); conn.close()
    await ctx.send("Đã reset toàn bộ Lương và PRF.")
    try: await ctx.message.delete()
    except: pass

# !luongall (Gửi tổng hợp lương)
@bot.command()
@commands.has_permissions(administrator=True)
async def luongall(ctx):
    rows=db_get_all_users()
    ch=bot.get_channel(CHANNEL_LUONG_ALL)
    if not ch: return await ctx.reply("Không tìm thấy channel ID: {}.".format(CHANNEL_LUONG_ALL),delete_after=8)
    
    embed=Embed(title="Tổng hợp Lương tháng {}".format(datetime.now(VN_TZ).strftime('%m/%Y')),color=PASTEL_PINK)
    msg_text_parts = []
    
    for uid,hours,donate in rows:
        member = ctx.guild.get_member(int(uid))
        name = member.display_name if member else "ID:{}".format(uid)
        pay=hours*LUONG_GIO_RATE; total=pay+donate
        
        line = "**{}** — Giờ book: {} | Lương giờ: {} | Donate: {} | **Tổng: {}**\\n".format(name, hours, fmt_vnd(pay), fmt_vnd(donate), fmt_vnd(total))
        
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
# COMMANDS CODE & POST
# -------------------------

# !code (Tạo/Lưu code)
@bot.command()
@commands.has_permissions(administrator=True)
async def code(ctx, title: str, ping: str, *, content_with_image: str):
    """Tạo hoặc cập nhật một code (thông báo) mới. Cú pháp: !code <title> <ping/@ID/none> <content> [image_url/none]"""
    # Logic tách content và image_url (giữ nguyên logic cũ)
    parts = content_with_image.rsplit(' ', 1)
    if len(parts) == 2 and (parts[1].startswith('http') or parts[1].lower() == 'none'):
        content, image_url = parts
    else:
        content, image_url = content_with_image, None

    if len(title) > 30: return await ctx.send("Title quá dài (max 30 ký tự).", delete_after=8)
    
    if not (ping.lower() == 'none' or re.match(r'^<@!?\d+>$', ping) or ping.isdigit()):
        return await ctx.send("Ping phải là '@user', ID, hoặc 'none'.", delete_after=8)
    
    final_image = image_url if image_url and image_url.lower() != 'none' else None
    
    db_save_code(title, ping, content, final_image)
    await ctx.send("Code **{}** đã được tạo/cập nhật.".format(title.lower()), delete_after=5)
    try: await ctx.message.delete()
    except: pass

# !code_edit (Sửa code)
@bot.command()
@commands.has_permissions(administrator=True)
async def code_edit(ctx, title: str, field: str, *, value: str = None):
    """Chỉnh sửa hoặc xóa code đã lưu: !code_edit <title> [ping|content|image|delete] <giá trị>"""
    field = field.lower()
    title = title.lower()

    if field == 'delete':
        if db_update_code(title, 'delete', None):
            await ctx.send("Code **{}** đã được xóa.".format(title), delete_after=5)
        else:
            await ctx.send("Code **{}** không tồn tại.".format(title), delete_after=8)
        return

    if field not in ['ping', 'content', 'image'] or not value:
        return await ctx.send("Cú pháp: 'code_edit <title> [ping|content|image|delete] <giá trị>'", delete_after=10)

    final_value = value if value and value.lower() != 'none' else None
    
    if db_update_code(title, field, final_value):
        await ctx.send("Đã cập nhật trường **{}** của code **{}**.".format(field, title), delete_after=5)
    else:
        await ctx.send("Code **{}** không tồn tại hoặc lỗi trường dữ liệu.".format(title), delete_after=8)
            
    try: await ctx.message.delete()
    except: pass

# !post (Đã thêm 3 dạng và nút Rent)
@bot.command()
@commands.has_permissions(administrator=True)
async def post(ctx, channel_or_prefix, title: str = None, *, content: str = None):
    
    target_channel = None
    original_title = title if title else "Thông Báo"
    
    # Xử lý các prefix đặc biệt
    if channel_or_prefix.lower() == 'fm':
        target_channel = bot.get_channel(POST_FM_CHANNEL_ID)
    elif channel_or_prefix.lower() == 'm':
        target_channel = bot.get_channel(POST_M_CHANNEL_ID)
    else:
        # Nếu là ID/Mention kênh thông thường
        try:
            channel_id = int(re.sub(r'[<#>]', '', channel_or_prefix))
            target_channel = bot.get_channel(channel_id)
        except ValueError:
            await ctx.send("Kênh không hợp lệ. Vui lòng dùng: ID kênh, mention kênh, 'fm' hoặc 'm'.", delete_after=8)
            return

    if not target_channel:
        return await ctx.send("Không tìm thấy kênh: {}".format(channel_or_prefix), delete_after=8)

    if not content:
        # Xử lý nội dung từ tin nhắn gốc (kèm ảnh 1:1)
        if ctx.message.attachments and len(ctx.message.attachments) > 0:
            content_desc = original_title if original_title else " "
            embed = Embed(description=content_desc, color=PASTEL_PINK)
            embed.set_image(url=ctx.message.attachments[0].url)
        else:
            return await ctx.send("Thiếu nội dung bài đăng.", delete_after=8)
    else:
        # Tách tiêu đề in đậm và nội dung thường
        full_content = "**{}**\\n{}".format(original_title, content)
        embed = Embed(description=full_content, color=PASTEL_PINK)
        
        # Kèm ảnh nếu có (từ upload trực tiếp)
        if ctx.message.attachments and len(ctx.message.attachments) > 0:
            embed.set_image(url=ctx.message.attachments[0].url)

    # Thêm nút Rent
    rent_view = RentView(embed, ctx.author, ctx.guild)
    
    try:
        await target_channel.send(embed=embed, view=rent_view)
        await ctx.send("Đã gửi bài đăng kèm nút **Rent** đến {}.".format(target_channel.mention), delete_after=5)
    except Exception as e:
        await ctx.send("Lỗi khi gửi bài: {}".format(e), delete_after=8)

    try: await ctx.message.delete()
    except: pass

# -------------------------
# COMMANDS GIVEAWAY
# -------------------------
class GiveawayModal(ui.Modal, title='Tạo Giveaway'):
    # Text Input cho Tiêu đề
    title_input = ui.TextInput(label='Tiêu đề Giveaway', placeholder='Nhập tên phần thưởng...', max_length=100)
    
    # Text Input cho Số lượng
    winners_input = ui.TextInput(label='Số lượng người trúng giải', placeholder='VD: 1, 3, 5...', max_length=5)
    
    # Text Input cho Thời gian
    time_input = ui.TextInput(label='Thời gian kết thúc (s/m/h/d)', placeholder='VD: 1h, 30m, 7d...', max_length=10)
    
    def __init__(self, host: discord.Member, channel: discord.TextChannel):
        super().__init__()
        self.host = host
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Xử lý số lượng người trúng giải
            winners = int(self.winners_input.value)
            if winners <= 0:
                return await interaction.response.send_message("Số lượng người trúng giải phải lớn hơn 0.", ephemeral=True)
            
            # Xử lý thời gian
            time_str = self.time_input.value.lower().strip()
            m = re.match(r"^(\d+)([smhd])$", time_str)
            if not m: 
                return await interaction.response.send_message("Sai định dạng thời gian. Dùng: s (giây), m (phút), h (giờ), d (ngày).", ephemeral=True)

            qty = int(m.group(1)); unit = m.group(2)
            seconds = qty * (1 if unit == 's' else 60 if unit == 'm' else 3600 if unit == 'h' else 86400)
            
            if seconds < 60 or seconds > 30 * 86400:
                return await interaction.response.send_message("Thời gian phải từ 1 phút đến 30 ngày.", ephemeral=True)

            end_at = datetime.now(VN_TZ) + timedelta(seconds=seconds)
            
            # --- CẬP NHẬT ĐỊNH DẠNG GIVEAWAY ---
            embed_title = self.title_input.value
            embed = Embed(
                # Tiêu đề được in đậm và chuyển xuống description
                title="**{}**".format(embed_title), 
                description="Nhấn để tham gia!", 
                color=PASTEL_PINK
            )
            
            # Thêm các trường dùng ♡
            embed.add_field(name="♡ Winners :", value="{} người".format(winners), inline=True)
            embed.add_field(name="♡ Hosted by :", value=self.host.mention, inline=True)
            embed.add_field(name="♡ Time :", value="<t:{}:R>".format(int(end_at.timestamp())), inline=False) 
            # -----------------------------------

            # Gửi tin nhắn Giveaway
            msg = await self.channel.send(embed=embed)
            
            # Lưu vào DB
            db_save_giveaway(self.channel.id, msg.id, self.title_input.value, winners, self.host.id, end_at)
            
            # Thêm reaction
            await msg.add_reaction("🎉")

            await interaction.response.send_message("Đã tạo Giveaway thành công: {}".format(msg.jump_url), ephemeral=True)
            
        except ValueError:
            await interaction.response.send_message("Lỗi dữ liệu: Số lượng người trúng giải phải là số.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message("Lỗi: {}".format(e), ephemeral=True)


@bot.command()
@commands.has_permissions(manage_guild=True)
async def gw(ctx):
    """Tạo Giveaway mới với Modal Input."""
    
    modal = GiveawayModal(ctx.author, ctx.channel)
    await ctx.send_modal(modal)
    
    try: await ctx.message.delete()
    except: pass

# -------------------------
# RUN BOT
# -------------------------
if __name__ == '__main__':
    bot.run(TOKEN)


