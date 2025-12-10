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

# Kênh Log & Tổng hợp
CHANNEL_IO_DNT = 1448047569421733981 # Kênh log IO/DNT
CHANNEL_LUONG_ALL = 1448052039384043683 # Kênh gửi tổng hợp lương

# Config mới cho !post và !luong
RENT_ROLE_ID = 1432670531529867295 # ID role được thêm vào kênh riêng (Role có quyền xem/rep kênh Rent)
RENT_CATEGORY_ID = 1432658695719751792 # ID Category để tạo kênh riêng (Category của Voice Channel)
FM_CHANNEL_ID = 1432691499094769704 # ID Kênh FM
M_CHANNEL_ID = 1432691597363122357 # ID Kênh M

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
    cur.execute("""CREATE TABLE IF NOT EXISTS codes (title TEXT PRIMARY KEY, target_user_id TEXT, content TEXT, image_url TEXT)""")
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
    
def db_room_save(vc_id, owner_id):
    conn=sqlite3.connect(DB_FILE); cur=conn.cursor()
    cur.execute("INSERT OR IGNORE INTO rooms(voice_channel_id, owner_id) VALUES (?,?)", (vc_id, owner_id))
    conn.commit(); conn.close()
    
def db_room_delete(vc_id):
    conn=sqlite3.connect(DB_FILE); cur=conn.cursor()
    cur.execute("DELETE FROM rooms WHERE voice_channel_id=?", (vc_id,))
    conn.commit(); conn.close()
    
def db_room_get(vc_id):
    conn=sqlite3.connect(DB_FILE); cur=conn.cursor()
    cur.execute("SELECT owner_id, is_hidden, is_locked FROM rooms WHERE voice_channel_id=?", (vc_id,))
    row = cur.fetchone()
    conn.close()
    if row: return {"owner_id": row[0], "is_hidden": bool(row[1]), "is_locked": bool(row[2])}
    return None

def db_room_update(vc_id, is_hidden=None, is_locked=None):
    conn=sqlite3.connect(DB_FILE); cur=conn.cursor()
    
    updates = []
    params = []
    if is_hidden is not None:
        updates.append("is_hidden=?")
        params.append(int(is_hidden))
    if is_locked is not None:
        updates.append("is_locked=?")
        params.append(int(is_locked))
        
    if updates:
        query = f"UPDATE rooms SET {', '.join(updates)} WHERE voice_channel_id=?"
        params.append(vc_id)
        cur.execute(query, tuple(params))
        conn.commit()
    conn.close()
    
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
    
def has_rent_permission(member:discord.Member):
    if is_admin(member): return True
    rent_role = member.guild.get_role(RENT_ROLE_ID)
    return rent_role in member.roles if rent_role else False

# -------------------------
# LỚP NÚT BẤM (VIEWS)
# -------------------------

# --- 1. Lớp tương tác Rent (Cho lệnh !post m) ---
class DoneButtonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Nhấn Done khi xong nha yêu ơiiii", 
                       style=discord.ButtonStyle.red, 
                       custom_id="done_exchange_button")
    async def done_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        
        # Chỉ Admin hoặc người có Rent Role mới được đóng kênh Rent
        if not (is_admin(interaction.user) or has_rent_permission(interaction.user)):
             return await interaction.response.send_message(" Bạn không có quyền đóng kênh này.", ephemeral=True)
             
        if channel.name.startswith('rent-'):
            # Xác nhận trước khi xóa kênh
            confirm_view = ConfirmDeleteView(channel)
            await interaction.response.send_message(
                "Bạn có chắc chắn muốn đóng kênh này không? Kênh sẽ bị xóa vĩnh viễn.", 
                view=confirm_view, 
                ephemeral=True
            )
        else:
            await interaction.response.send_message(" Lệnh này chỉ dùng trong kênh thuê riêng.", ephemeral=True)

class ConfirmDeleteView(discord.ui.View):
    def __init__(self, channel):
        super().__init__(timeout=300)
        self.channel = channel

    @discord.ui.button(label="Xác nhận Đóng", style=discord.ButtonStyle.danger)
    async def confirm_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"🗑️ Đang xóa kênh {self.channel.name}...", ephemeral=True)
        try:
            await self.channel.delete()
        except Exception as e:
            await interaction.followup.send(f"Lỗi khi xóa kênh: {e}", ephemeral=True)
        self.stop()

    @discord.ui.button(label="Hủy", style=discord.ButtonStyle.secondary)
    async def cancel_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(" Đã hủy thao tác đóng kênh.", ephemeral=True)
        self.stop()

class RentButtonView(discord.ui.View):
    def __init__(self, bot_instance):
        super().__init__(timeout=None)
        self.bot = bot_instance

    @discord.ui.button(label="Nhấn Rent nha khách iu ơi ⋆𐙚 ̊", 
                       style=discord.ButtonStyle.green, 
                       custom_id="rent_exchange_button")
    async def rent_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        guild = interaction.guild
        
        # 1. Kiểm tra xem người dùng đã có kênh riêng đang mở chưa
        for channel in guild.channels:
            if channel.name == f"rent-{user.name.lower().replace(' ', '-')}" and isinstance(channel, discord.TextChannel):
                return await interaction.response.send_message(
                    f"Bạn đã có một kênh thuê riêng đang hoạt động: {channel.mention}", 
                    ephemeral=True
                )

        # 2. Định nghĩa quyền
        rent_role = guild.get_role(RENT_ROLE_ID)
        admin_member = guild.get_member(ADMIN_ID)
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            # Chỉ Admin/Role Rent mới thấy
            admin_member: discord.PermissionOverwrite(read_messages=True, send_messages=True) if admin_member else None,
            rent_role: discord.PermissionOverwrite(read_messages=True, send_messages=True) if rent_role else None
        }
        
        # Lọc bỏ quyền None (nếu không tìm thấy Admin/Role)
        overwrites = {k: v for k, v in overwrites.items() if v is not None}
        
        # 3. Tạo kênh riêng
        try:
            new_channel = await guild.create_text_channel(
                f"rent-{user.name}", 
                category=discord.utils.get(guild.categories, id=RENT_CATEGORY_ID),
                overwrites=overwrites
            )

            # 4. Gửi tin nhắn đầu tiên và nút Done
            done_view = DoneButtonView()
            await new_channel.send(
                f"Chào {user.mention}, <@&{RENT_ROLE_ID}>! Khách ơi đợi tí, bọn mình rep liền nhaaa ₊˚⊹ ᰔ ",
                view=done_view
            )

            await interaction.response.send_message(f" Kênh của bạn đã được tạo: {new_channel.mention}", ephemeral=True)

        except Exception as e:
            print(f"Lỗi khi tạo kênh riêng: {e}")
            await interaction.response.send_message(" Lỗi xảy ra khi tạo kênh riêng.", ephemeral=True)


# --- 2. Lớp tương tác Voice (Cho lệnh !voice) ---
class VoiceControlView(discord.ui.View):
    def __init__(self, bot_instance):
        super().__init__(timeout=None)
        self.bot = bot_instance

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        room_data = db_room_get(str(interaction.channel_id))
        
        if not room_data or str(interaction.user.id) != room_data['owner_id']:
            await interaction.response.send_message(" Bạn không phải chủ phòng này.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Lock (Khóa)", style=discord.ButtonStyle.blurple, custom_id="vc_lock")
    async def lock_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        owner = interaction.user
        
        # Cập nhật quyền: Tắt CONNECT cho @everyone
        overwrites = channel.overwrites_for(interaction.guild.default_role)
        overwrites.connect = False
        
        try:
            await channel.set_permissions(interaction.guild.default_role, overwrite=overwrites)
            db_room_update(str(channel.id), is_locked=True)
            await interaction.response.send_message(" Kênh Voice đã được **khóa**.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f" Lỗi: {e}", ephemeral=True)

    @discord.ui.button(label="Unlock (Mở khóa)", style=discord.ButtonStyle.green, custom_id="vc_unlock")
    async def unlock_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        
        # Cập nhật quyền: Bật CONNECT cho @everyone
        overwrites = channel.overwrites_for(interaction.guild.default_role)
        overwrites.connect = True
        
        try:
            await channel.set_permissions(interaction.guild.default_role, overwrite=overwrites)
            db_room_update(str(channel.id), is_locked=False)
            await interaction.response.send_message(" Kênh Voice đã được **mở khóa**.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f" Lỗi: {e}", ephemeral=True)
            
    @discord.ui.button(label="Hide (Ẩn)", style=discord.ButtonStyle.red, custom_id="vc_hide")
    async def hide_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        owner = interaction.user
        
        # Cập nhật quyền: Tắt VIEW_CHANNEL cho @everyone, Bật VIEW_CHANNEL cho owner
        overwrites_default = channel.overwrites_for(interaction.guild.default_role)
        overwrites_default.view_channel = False
        
        overwrites_owner = channel.overwrites_for(owner)
        overwrites_owner.view_channel = True
        
        try:
            await channel.set_permissions(interaction.guild.default_role, overwrite=overwrites_default)
            await channel.set_permissions(owner, overwrite=overwrites_owner)
            db_room_update(str(channel.id), is_hidden=True)
            await interaction.response.send_message(" Kênh Voice đã được **ẩn** (chỉ bạn và người được mời thấy).", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f" Lỗi: {e}", ephemeral=True)
            
    @discord.ui.button(label="Invite (@user)", style=discord.ButtonStyle.gray, custom_id="vc_invite")
    async def invite_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Mở Modal (Hộp thoại nhập) để người dùng nhập tên người muốn mời
        await interaction.response.send_modal(InviteUserModal(self.bot, interaction.channel))


class InviteUserModal(discord.ui.Modal, title="Mời người vào phòng riêng"):
    def __init__(self, bot_instance, voice_channel):
        super().__init__()
        self.bot = bot_instance
        self.voice_channel = voice_channel

    user_input = discord.ui.TextInput(
        label="Nhập tên người bạn muốn mời:",
        placeholder="@user hoặc ID",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        user_str = self.user_input.value.strip()
        
        # Tìm Member dựa trên mention hoặc ID
        invited_member = None
        try:
            # Check for mention: <@ID> or <@!ID>
            match = re.search(r'<@!?(\d+)>', user_str)
            if match:
                user_id = int(match.group(1))
                invited_member = interaction.guild.get_member(user_id)
            elif user_str.isdigit():
                 user_id = int(user_str)
                 invited_member = interaction.guild.get_member(user_id)
        except:
            pass
        
        if not invited_member:
            return await interaction.response.send_message(f" Không tìm thấy người dùng `{user_str}`.", ephemeral=True)

        # Cấp quyền vào Voice Channel
        try:
            overwrites = self.voice_channel.overwrites_for(invited_member)
            overwrites.connect = True
            overwrites.view_channel = True
            await self.voice_channel.set_permissions(invited_member, overwrite=overwrites)
            
            await interaction.response.send_message(f" Đã mời {invited_member.mention} vào phòng.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Lỗi khi mời: {e}", ephemeral=True)


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
# VOICE CREATE & DELETE LOGIC
# -------------------------
@bot.event
async def on_voice_state_update(member,before,after):
    guild = member.guild
    
    # Logic TẠO kênh riêng (Create)
    try:
        if (before.channel is None or (before.channel and before.channel.id not in [TRIGGER_VOICE_CREATE, TRIGGER_VOICE_PRIVATE])) and after.channel and after.channel.id in [TRIGGER_VOICE_CREATE, TRIGGER_VOICE_PRIVATE]:
            category = discord.utils.get(guild.categories, id=VOICE_CATEGORY_ID)
            
            # Kênh công cộng (CREATE)
            if after.channel.id == TRIGGER_VOICE_CREATE:
                overwrites = {guild.default_role:discord.PermissionOverwrite(connect=True,view_channel=True), member:discord.PermissionOverwrite(connect=True,view_channel=True)}
                new_voice = await guild.create_voice_channel(f"⋆𐙚 - {member.name}", overwrites=overwrites, category=category)
            
            # Kênh riêng (PRIVATE)
            else: 
                overwrites = {guild.default_role:discord.PermissionOverwrite(connect=False,view_channel=False), member:discord.PermissionOverwrite(connect=True,view_channel=True)}
                admin_member = guild.get_member(ADMIN_ID); 
                if admin_member: overwrites[admin_member]=discord.PermissionOverwrite(connect=True,view_channel=True)
                new_voice = await guild.create_voice_channel(f"⋆𐙚 - {member.name}", overwrites=overwrites, category=category)
                
            # Lưu thông tin phòng vào DB và gửi control panel
            db_room_save(str(new_voice.id), str(member.id))
            
            # Gửi control panel (chỉ có owner mới thấy)
            control_view = VoiceControlView(bot)
            await new_voice.send(
                f"**Panel điều khiển phòng riêng của {member.mention}**",
                view=control_view,
                delete_after=1800 # Xóa sau 30 phút
            )
            
            try: await member.move_to(new_voice)
            except: pass
            return
    except Exception as e: print("on_voice_state_update create error:", e)

    # Logic XÓA kênh khi không còn ai (Delete)
    try:
        if before.channel and db_room_get(str(before.channel.id)) and len(before.channel.members) == 0:
            # Kiểm tra xem có phải là kênh được tạo bởi bot không
            if before.channel.name.startswith(('⋆𐙚 -', '⋆𐙚 -')):
                db_room_delete(str(before.channel.id))
                await before.channel.delete()
    except Exception as e: print("on_voice_state_update delete error:", e)


# -------------------------
# COMMANDS
# -------------------------

# !post (Đã cập nhật theo yêu cầu)
@bot.command()
@commands.has_permissions(administrator=True)
async def post(ctx, target: str, *, content: str = None):
    # Kiểm tra xem có file đính kèm không
    if not ctx.message.attachments:
        return await ctx.send(" Vui lòng đính kèm ảnh size 1:1 cho bài đăng.", delete_after=10)

    attachment = ctx.message.attachments[0]
    image_url = attachment.url

    target = target.lower()
    
    if target == 'fm':
        channel_id = FM_CHANNEL_ID
        view_to_send = None # Không có nút bấm
    elif target == 'm':
        channel_id = M_CHANNEL_ID
        view_to_send = RentButtonView(ctx.bot) # Gửi nút Rent
    else:
        return await ctx.send(" Lệnh sai: `!post fm` hoặc `!post m`.", delete_after=8)

    channel = ctx.guild.get_channel(channel_id)
    if not channel:
        return await ctx.send(f" Không tìm thấy kênh với ID: {channel_id}.", delete_after=8)
        
    # Tạo Embed
    embed = Embed(description=content or "Không có nội dung", color=PASTEL_PINK)
    embed.set_image(url=image_url)

    try:
        # Gửi tin nhắn
        await channel.send(embed=embed, view=view_to_send)
        await ctx.send(f"Đã gửi bài đăng (Target: {target.upper()}) đến {channel.mention}", delete_after=5)
    except Exception as e:
        await ctx.send(f" Lỗi khi gửi bài: {e}", delete_after=8)
        
    try: await ctx.message.delete()
    except: pass

# !time (Lệnh đếm ngược mới)
@bot.command()
async def time(ctx, time_str: str):
    m = re.match(r"^(\d+)([smhd])$", time_str.lower())
    if not m: return await ctx.reply("Sai định dạng thời gian (s/m/h/d). Ví dụ: `!time 2h`", delete_after=8)
    
    qty = int(m.group(1)); unit = m.group(2)
    seconds = qty * (1 if unit == 's' else 60 if unit == 'm' else 3600 if unit == 'h' else 86400)
    
    if seconds <= 0 or seconds > 7 * 86400: # Max 7 ngày
        return await ctx.reply(" Thời gian không hợp lệ (tối đa 7 ngày).", delete_after=8)

    start_time = datetime.now(VN_TZ)
    end_time = start_time + timedelta(seconds=seconds)
    
    # Định dạng giờ cho Embed
    start_fmt = start_time.strftime("%H:%M:%S (%d/%m/%Y)")
    end_fmt = end_time.strftime("%H:%M:%S (%d/%m/%Y)")
    
    # Tạo Unix Timestamp cho Discord (để hiển thị đếm ngược)
    end_timestamp_unix = int(end_time.timestamp())
    
    embed = Embed(
        title="⏰ Bắt đầu đếm ngược Bill",
        description=f"Bill bắt đầu lúc **{start_fmt}** và kết thúc lúc **{end_fmt}** nha khách iu ơiiii.",
        color=PASTEL_PINK
    )
    embed.add_field(
        name="Đếm ngược:", 
        value=f"Kết thúc: <t:{end_timestamp_unix}:R> (tức là <t:{end_timestamp_unix}:T>)", 
        inline=False
    )
    embed.set_footer(text=f"Yêu cầu bởi {ctx.author.display_name}")
    
    await ctx.send(embed=embed)
    try: await ctx.message.delete()
    except: pass

# !av
@bot.command()
async def av(ctx, member:discord.Member=None):
    member=member or ctx.author
    avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
    embed=Embed(title=f"Avatar {member.display_name}", color=PASTEL_PINK)
    embed.set_image(url=avatar_url)
    await ctx.send(embed=embed)

# !text (Đã cập nhật theo yêu cầu)
@bot.command()
async def text(ctx, title: str, *, content:str):
    # Tiêu đề to trước, in đậm, chữ màu hồng (PASTEL_PINK)
    title_display = f"**{title.upper()}**"
    
    embed = Embed(
        title=title_display,
        description=content,
        color=PASTEL_PINK
    )
    
    # Discord không cho Embed Title đổi màu, nên tôi dùng BOLD và màu Embed
    await ctx.send(embed=embed)
    try: await ctx.message.delete()
    except: pass

# !io (Đã cập nhật theo yêu cầu)
@bot.command()
async def io(ctx, time_str: str, member: discord.Member, prf_member: discord.Member):
    if not has_io_permission(ctx.author): return await ctx.reply("❌ Không có quyền.",delete_after=8)

    # Phân tích thời gian (chỉ lấy giờ, nếu có phút thì làm tròn)
    m = re.match(r"^(\d+)([smhd])$", time_str.lower())
    if not m: return await ctx.reply(" Sai định dạng thời gian (s/m/h/d). Ví dụ: `!io 2h @user1 @user2`", delete_after=8)
    
    qty = int(m.group(1)); unit = m.group(2)
    
    if unit in ('s', 'm'):
        return await ctx.reply(" Chỉ chấp nhận giờ (h) hoặc ngày (d).", delete_after=8)
    
    hours = qty * (1 if unit == 'h' else 24 if unit == 'd' else 0)
    
    if hours <= 0: return await ctx.reply(" Giờ book phải lớn hơn 0.", delete_after=8)

    # 1. Cập nhật lương của member (user1)
    db_update_user_add(str(member.id), hours=hours)
    
    # 2. Cập nhật PRF của prf_member (user2)
    db_prf_add(str(prf_member.id), hours=hours)

    # 3. Gửi log vào CHANNEL_IO_DNT (1448047569421733981)
    ch = bot.get_channel(CHANNEL_IO_DNT)
    log_msg = f"{member.mention} : {hours} giờ" # @user1 : <time>
    
    if ch: await ch.send(log_msg)
    
    # 4. Gửi thông báo PRF cho prf_member (user2)
    try:
        await prf_member.send(f"Đã book {member.mention} {hours} giờ.")
    except discord.Forbidden:
        await ctx.reply(f"Không thể gửi DM cho {prf_member.display_name} (PRF).", delete_after=8)

    await ctx.send(f" IO: Đã cập nhật {member.mention} (+{hours} giờ) và PRF {prf_member.mention} (+{hours} giờ).", delete_after=8)
    try: await ctx.message.delete()
    except: pass

# !dnt (Đã cập nhật theo yêu cầu)
@bot.command()
async def dnt(ctx, amount: int, member: discord.Member, prf_member: discord.Member):
    if not has_io_permission(ctx.author): return await ctx.reply("Không có quyền.",delete_after=8)
    if amount <= 0: return await ctx.reply(" Số tiền donate phải lớn hơn 0.", delete_after=8)

    # 1. Cập nhật lương của member (user1)
    db_update_user_add(str(member.id), donate=amount)
    
    # 2. Cập nhật PRF của prf_member (user2)
    db_prf_add(str(prf_member.id), amount=amount)
    
    amount_vnd = fmt_vnd(amount)

    # 3. Gửi log vào CHANNEL_IO_DNT (1448047569421733981)
    ch = bot.get_channel(CHANNEL_IO_DNT)
    log_msg = f"donate {member.mention} : {amount_vnd}" # donate @user1 : <amount>
    
    if ch: await ch.send(log_msg)
    
    # 4. Gửi thông báo PRF cho prf_member (user2)
    try:
        await prf_member.send(f"Đã donate {member.mention} {amount_vnd}.")
    except discord.Forbidden:
        await ctx.reply(f"Không thể gửi DM cho {prf_member.display_name} (PRF).", delete_after=8)
    
    await ctx.send(f"DNT: Đã cập nhật {member.mention} (+{amount_vnd}) và PRF {prf_member.mention} (+{amount_vnd}).", delete_after=8)
    try: await ctx.message.delete()
    except: pass

# !prf (Đã cập nhật theo yêu cầu)
@bot.command()
async def prf(ctx, member:discord.Member=None):
    target=member or ctx.author; p=db_prf_get(str(target.id))
    
    embed=Embed(title=f"PRF {target.display_name}",color=PASTEL_PINK)
    embed.add_field(name="♡ Giờ đã book:",value=f"{p['prf_hours']} giờ",inline=False)
    embed.add_field(name="♡ Đã Donate:",value=f"{fmt_vnd(p['prf_donate'])}",inline=False)
    
    await ctx.send(embed=embed)
    try: await ctx.message.delete()
    except: pass

# !luong (Đã cập nhật theo yêu cầu)
@bot.command()
async def luong(ctx, member:discord.Member=None):
    target=member or ctx.author
    
    # Kiểm tra quyền: Chỉ ADMIN hoặc ROLE_RENT mới được xem lương người khác trong kênh
    can_view_other = (target != ctx.author and (is_admin(ctx.author) or has_rent_permission(ctx.author)))
    
    u=db_get_user(str(target.id))
    hours=int(u["book_hours"]); donate=int(u["donate"])
    pay=hours*LUONG_GIO_RATE; total=pay+donate
    
    embed=Embed(title=f"Lương của {target.display_name}",color=PASTEL_PINK)
    embed.add_field(name="♡ Giờ book:", value=f"{hours} giờ",inline=False)
    embed.add_field(name="♡ Lương giờ:", value=f"{fmt_vnd(pay)}",inline=False)
    embed.add_field(name="♡ Donate:", value=f"{fmt_vnd(donate)}",inline=False)
    embed.add_field(name="♡ Lương tổng:", value=f"{fmt_vnd(total)}",inline=False)
    
    if can_view_other or target == ctx.author and ctx.guild is None: # Admin/Role xem người khác hoặc xem trong DM
        await ctx.send(embed=embed)
    
    elif target == ctx.author and ctx.guild is not None: # User tự xem trong Server
        try:
            await target.send(embed=embed)
            await ctx.reply("Check DM nha tình yêuuuu.", delete_after=8)
        except discord.Forbidden:
            await ctx.reply(" Không thể gửi DM, vui lòng bật DM.", delete_after=8)
            
    try: await ctx.message.delete()
    except: pass


# !voice (Lệnh mới quản lý kênh thoại)
@bot.command()
async def voice(ctx):
    # Lệnh này chỉ hoạt động trong kênh text của guild
    if ctx.guild is None:
        return await ctx.send(" Lệnh này chỉ hoạt động trong Server Discord.", delete_after=8)

    # 1. Kiểm tra xem người dùng có đang ở trong kênh thoại nào không
    voice_state = ctx.author.voice
    if not voice_state or not voice_state.channel:
        return await ctx.send(" Bạn cần ở trong một kênh Voice do bot tạo để sử dụng lệnh này.", delete_after=8)

    voice_channel = voice_state.channel
    
    # 2. Kiểm tra xem kênh thoại này có phải là kênh bot tạo và đang được quản lý không
    room_data = db_room_get(str(voice_channel.id))
    if not room_data or str(ctx.author.id) != room_data['owner_id']:
        return await ctx.send("Bạn không phải là chủ của kênh Voice này hoặc đây không phải kênh bot quản lý.", delete_after=8)

    # 3. Gửi lại Panel điều khiển
    control_view = VoiceControlView(bot)
    
    embed = Embed(
        title=f"🎤 Panel Điều Khiển - {voice_channel.name}",
        description="Sử dụng các nút bên dưới để điều chỉnh quyền riêng tư của phòng.",
        color=PASTEL_PINK
    )
    embed.add_field(name="Trạng thái hiện tại:", value=f"Lock: **{'Có' if room_data['is_locked'] else 'Không'}**\nHide: **{'Có' if room_data['is_hidden'] else 'Không'}**", inline=False)
    
    await ctx.send(embed=embed, view=control_view, delete_after=300) # Panel tồn tại 5 phút
    try: await ctx.message.delete()
    except: pass


# Lệnh !rs, !luongall, !ban, !mute, !clear, !code, !code_edit và Dynamic command handler (giữ nguyên)
# ... (Giữ nguyên các lệnh còn lại)

# !clear (Hỗ trợ cả <số lượng> và "all")
@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount_str: str):
    # Kiểm tra quyền bot
    if not ctx.channel.permissions_for(ctx.guild.me).manage_messages:
        return await ctx.send("Bot cần có quyền Quản lý Tin nhắn.", delete_after=6)

    try: await ctx.message.delete()
    except: pass
        
    if amount_str.lower() == 'all':
        try: 
            deleted = await ctx.channel.purge(limit=100)
            await ctx.send(f"Đã xóa **{len(deleted)}** tin nhắn gần nhất.", delete_after=5)
        except Exception as e: 
            await ctx.send(f"Lỗi khi xóa tất cả: {e}", delete_after=6)
        return

    try:
        amount = int(amount_str)
        if amount <= 0: 
            return await ctx.reply("Số lượng phải lớn hơn 0.", delete_after=6)
        
        deleted = await ctx.channel.purge(limit=amount) 
        await ctx.send(f"Đã xóa thành công **{len(deleted)}** tin nhắn.", delete_after=5)
        
    except ValueError:
        await ctx.send("Cú pháp sai. Vui lòng dùng: `!clear <số lượng>` (VD: `!clear 5`) hoặc `!clear all`.", delete_after=8)
    except Exception as e:
        await ctx.send(f"Lỗi khi xóa: {e}", delete_after=6)


@clear.error
async def clear_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("Bạn không có quyền Quản lý Tin nhắn.", delete_after=6)
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Cú pháp: `!clear <số lượng>` (VD: `!clear 5`) hoặc `!clear all`.", delete_after=6)


# !ban
@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member:discord.Member=None, *, reason:str="Không có lý do"):
    if not member: return await ctx.send("Chọn người để ban.")
    if member.top_role >= ctx.author.top_role and not is_admin(ctx.author):
        return await ctx.send(" Bạn không thể ban người có vai trò cao hơn hoặc bằng bạn.")
    try: 
        await member.ban(reason=f"Banned by {ctx.author} for: {reason}")
        await ctx.send(f"Đã ban {member.mention} (Lý do: {reason})")
    except Exception as e: 
        await ctx.send(f" Lỗi khi ban: {e}", delete_after=6)

# !mute
@bot.command()
@commands.has_permissions(manage_roles=True)
async def mute(ctx, time:str=None, member:discord.Member=None):
    if not member: return await ctx.reply("Cần @user",delete_after=8)
    if not time: return await ctx.reply(" Thiếu thời gian VD: `!mute 1m @user`",delete_after=8)

    m=re.match(r"^(\d+)([smhd])$",time.lower())
    if not m: return await ctx.reply("Sai định dạng thời gian (s/m/h/d).",delete_after=8)
    
    qty=int(m.group(1)); unit=m.group(2)
    seconds = qty*(1 if unit=='s' else 60 if unit=='m' else 3600 if unit=='h' else 86400)
    
    if seconds > 28 * 86400:
        return await ctx.reply(" Thời gian mute quá dài (tối đa 28 ngày).", delete_after=8)

    if seconds > 0:
        duration = timedelta(seconds=seconds)
        try:
            await member.timeout(duration, reason=f"Muted by {ctx.author} for {time}")
            await ctx.send(f"Đã mute {member.mention} trong **{time}**.")
        except Exception as e:
            await ctx.send(f" Lỗi khi mute: {e}", delete_after=8)
    
    try: await ctx.message.delete()
    except: pass

# !code (Tạo/Lưu code)
@bot.command()
@commands.has_permissions(administrator=True)
async def code(ctx, title: str, ping: str, content: str, image: str = None):
    """Tạo hoặc cập nhật một code (thông báo) mới."""
    if len(title) > 30: return await ctx.send("❌ Title quá dài (max 30 ký tự).", delete_after=8)
    
    # Kiểm tra xem ping có hợp lệ là mention hoặc ID không
    if not (ping.lower() == 'none' or re.match(r'^<@!?\d+>$', ping) or ping.isdigit()):
        return await ctx.send("Ping phải là `@user`, ID, hoặc `none`.", delete_after=8)
    
    db_save_code(title, ping, content, image if image and image.lower() != 'none' else None)
    await ctx.send(f"Code **{title.lower()}** đã được tạo/cập nhật.", delete_after=5)
    try: await ctx.message.delete()
    except: pass

# Lệnh bị thiếu: !codeedit (Sửa code)
@bot.command()
@commands.has_permissions(administrator=True)
async def codeedit(ctx, title: str, field: str, *, value: str = None):
    """Chỉnh sửa hoặc xóa code đã lưu: !codeedit <title> [ping|content|image|delete] <giá trị>"""
    field = field.lower()
    title = title.lower()

    if field == 'delete':
        if db_update_code(title, 'delete', None):
            await ctx.send(f"Code **{title}** đã được xóa.", delete_after=5)
        else:
            await ctx.send(f"Code **{title}** không tồn tại.", delete_after=8)
        return

    if field not in ['ping', 'content', 'image'] or not value:
        return await ctx.send("Cú pháp: `!code_edit <title> [ping|content|image|delete] <giá trị>`", delete_after=10)

    if db_update_code(title, field, value if value.lower() != 'none' else None):
        await ctx.send(f" Đã cập nhật trường **{field}** của code **{title}**.", delete_after=5)
    else:
        await ctx.send(f"Code **{title}** không tồn tại hoặc lỗi trường dữ liệu.", delete_after=8)
        
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

# !rs (Reset Lương và PRF)
@bot.command()
@commands.has_permissions(administrator=True)
async def rs(ctx):
    conn=sqlite3.connect(DB_FILE); cur=conn.cursor()
    cur.execute("UPDATE users SET book_hours=0, donate=0")
    cur.execute("DELETE FROM prf"); conn.commit(); conn.close()
    await ctx.send(“ Đã reset toàn bộ Lương và PRF.")
    try: await ctx.message.delete()
    except: pass

# !luongall (Gửi tổng hợp lương)
@bot.command()
@commands.has_permissions(administrator=True)
async def luongall(ctx):
    rows=db_get_all_users()
    ch=bot.get_channel(CHANNEL_LUONG_ALL)
    if not ch: return await ctx.reply(f"Không tìm thấy channel ID: {CHANNEL_LUONG_ALL}.",delete_after=8)
    
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
# ON READY & VIEW RELOAD
# -------------------------
@bot.event
async def on_ready():
    print(f"Bot running as {bot.user} (id:{bot.user.id})")
    
    # Tải lại Views cho nút bấm Rent
    try:
        # Tải lại RentButtonView, DoneButtonView và VoiceControlView
        bot.add_view(RentButtonView(bot))
        bot.add_view(DoneButtonView())
        bot.add_view(VoiceControlView(bot))
    except Exception as e:
        # Nếu đã được thêm, sẽ có lỗi và bỏ qua
        pass

# -------------------------
# RUN BOT
# -------------------------
if __name__ == '__main__':
    bot.run(TOKEN)

