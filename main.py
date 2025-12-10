import discord
from discord.ext import commands, tasks
from discord import Embed, ui, File
from flask import Flask
from threading import Thread
import asyncio
from datetime import datetime, timedelta
import re
import os
import requests
import pytz
import sqlite3
import random

# -----------------------
# Flask server ping 24/7
app = Flask('')
@app.route('/')
def home():
    return "Bot is running!"

def run():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

Thread(target=run).start()
# -----------------------

# Bot setup
TOKEN = os.getenv('DISCORD_BOT_SECRET')
if not TOKEN:
    print("Missing DISCORD_BOT_SECRET!")
    exit()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# -----------------------
# Constants
WELCOME_CHANNEL_ID = 1432658695719751793
SUPPORT_CHANNEL_ID = 1432685282955755595
IMAGE_CHANNEL_FEMALE = 1432691499094769704
IMAGE_CHANNEL_MALE = 1432691597363122357
ADMIN_ID = 757555763559399424
ROLE_IO = 1448047569421733981
LUONGALL_CHANNEL = 1448052039384043683
VOICE_CATEGORY = 1448062526599205037

DB_FILE = "botdata.db"
LUA_HOUR_PRICE = 25000  # VNĐ

# -----------------------
# SQLite setup
conn = sqlite3.connect(DB_FILE)
c = conn.cursor()
c.execute("""CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    gio_book INTEGER DEFAULT 0,
    donate INTEGER DEFAULT 0,
    gio_da_book INTEGER DEFAULT 0
)""")
c.execute("""CREATE TABLE IF NOT EXISTS codes (
    user_id INTEGER PRIMARY KEY,
    ping TEXT,
    content TEXT,
    image TEXT
)""")
conn.commit()

def get_user(user_id):
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    return c.fetchone()

def add_user(user_id):
    c.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (user_id,))
    conn.commit()

def update_luong(user_id, gio=0, donate=0, gio_da_book=0):
    add_user(user_id)
    c.execute("UPDATE users SET gio_book = gio_book + ?, donate = donate + ?, gio_da_book = gio_da_book + ? WHERE user_id=?",
              (gio, donate, gio_da_book, user_id))
    conn.commit()

def reset_luong_all():
    c.execute("UPDATE users SET gio_book=0, donate=0, gio_da_book=0")
    conn.commit()

# -----------------------
# Ping healthchecks
HC_PING_URL = os.getenv('HEALTHCHECKS_URL')
async def keep_alive_ping():
    if not HC_PING_URL:
        return
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            requests.get(HC_PING_URL, timeout=10)
        except:
            pass
        await asyncio.sleep(14*60)

# -----------------------
@bot.event
async def on_ready():
    print(f'Bot logged in as {bot.user}')
    bot.loop.create_task(keep_alive_ping())

# -----------------------
@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        embed = Embed(description=f"Chào mừng {member.mention} đến với ⋆. 𐙚˚࿔ 𝒜𝓈𝓉𝓇𝒶 𝜗𝜚˚⋆, mong bạn ở đây thật vui nhá ^^ Có cần hỗ trợ gì thì <#{SUPPORT_CHANNEL_ID}> nhá",
                      color=0xF4C2C2)
        embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
        await channel.send(embed=embed)

# -----------------------
# !luong cá nhân
@bot.command()
async def luong(ctx, member: discord.Member=None):
    target = member or ctx.author
    add_user(target.id)
    data = get_user(target.id)
    gio = data[1]
    luong_gio = gio * LUA_HOUR_PRICE
    donate = data[2]
    luong_total = luong_gio + donate
    embed = Embed(title=f"Lương tháng", color=0xF4C2C2)
    embed.add_field(name="𐙚 Giờ book:", value=f"{gio}", inline=False)
    embed.add_field(name="𐙚 Lương giờ:", value=f"{luong_gio:,} VNĐ", inline=False)
    embed.add_field(name="𐙚 Donate:", value=f"{donate:,} VNĐ", inline=False)
    embed.add_field(name="𐙚 Lương tổng:", value=f"{luong_total:,} VNĐ", inline=False)
    try:
        await ctx.author.send(embed=embed)
        await ctx.message.add_reaction("✅")
    except:
        await ctx.send("Không thể gửi DM.")

# -----------------------
# !prf
@bot.command()
async def prf(ctx, member: discord.Member=None):
    target = member or ctx.author
    add_user(target.id)
    data = get_user(target.id)
    embed = Embed(title="Profile", color=0xF4C2C2)
    embed.add_field(name="𐙚 Giờ đã book:", value=f"{data[3]}", inline=False)
    embed.add_field(name="𐙚 Đã Donate:", value=f"{data[2]:,} VNĐ", inline=False)
    await ctx.send(embed=embed)

# -----------------------
# !io
@bot.command()
async def io(ctx, time: str, member: discord.Member, by: discord.Member=None):
    if not any(role.id == ROLE_IO for role in ctx.author.roles):
        await ctx.send("Bạn không có quyền sử dụng lệnh này.")
        return
    gio = 0
    match = re.match(r'(\d+)h', time.lower())
    if match:
        gio = int(match.group(1))
    else:
        await ctx.send("Sai định dạng giờ, VD: 2h")
        return
    update_luong(member.id, gio=gio)
    if by:
        update_luong(by.id, gio_da_book=gio)
    channel = bot.get_channel(ROLE_IO)
    await channel.send(f"{member.mention} : {gio}")

# -----------------------
# !dnt
@bot.command()
async def dnt(ctx, amount: int, member: discord.Member, by: discord.Member=None):
    if not any(role.id == ROLE_IO for role in ctx.author.roles):
        await ctx.send("Bạn không có quyền sử dụng lệnh này.")
        return
    update_luong(member.id, donate=amount)
    if by:
        update_luong(by.id, gio_da_book=0)
    channel = bot.get_channel(ROLE_IO)
    await channel.send(f"{member.mention} : {amount}")

# -----------------------
# !rs
@bot.command()
async def rs(ctx):
    reset_luong_all()
    await ctx.message.add_reaction("✅")

# -----------------------
# !luongall
@bot.command()
async def luongall(ctx):
    c.execute("SELECT * FROM users")
    all_data = c.fetchall()
    embed = Embed(title="Tổng hợp lương", description="Ai thắc mắc về lương phản hồi trước 12h ngày mai nhaa", color=0xF4C2C2)
    for data in all_data:
        user = bot.get_user(data[0])
        if user:
            gio = data[1]
            luong_gio = gio * LUA_HOUR_PRICE
            donate = data[2]
            luong_total = luong_gio + donate
            embed.add_field(name=user.display_name, value=f"Giờ book: {gio}\nLương giờ: {luong_gio:,} VNĐ\nDonate: {donate:,} VNĐ\nLương tổng: {luong_total:,} VNĐ", inline=False)
    channel = bot.get_channel(LUONGALL_CHANNEL)
    await channel.send(embed=embed)

# -----------------------
# !qr
@bot.command()
async def qr(ctx):
    if not os.path.exists("qr.png"):
        await ctx.send("Không tìm thấy qr.png")
        return
    file = File("qr.png", filename="qr.png")
    embed = Embed(title="QR Code", color=0xF4C2C2)
    embed.set_image(url="attachment://qr.png")
    embed.add_field(name="Hướng dẫn", value="Sau khi thanh toán xong gửi bill vào đây nhá. Không ghi NDCK giúp mình nha ୨୧", inline=False)
    await ctx.send(embed=embed, file=file)

# -----------------------
# !text
@bot.command()
async def text(ctx, *, content: str):
    await ctx.message.delete()
    embed = Embed(description=content, color=0xF4C2C2)
    await ctx.send(embed=embed)

# -----------------------
# !post
@bot.command()
async def post(ctx, gender: str, *, caption: str=""):
    if len(ctx.message.attachments) == 0:
        await ctx.send("Chưa gửi ảnh!")
        return
    att = ctx.message.attachments[0]
    file = await att.to_file()
    if gender.lower() == "fm":
        channel = bot.get_channel(IMAGE_CHANNEL_FEMALE)
    else:
        channel = bot.get_channel(IMAGE_CHANNEL_MALE)
    embed = Embed(description=caption, color=0xF4C2C2)
    embed.set_image(url=f"attachment://{att.filename}")
    class RentButton(ui.View):
        def __init__(self):
            super().__init__(timeout=None)
        @ui.button(label="Rent", style=discord.ButtonStyle.primary)
        async def rent(self, interaction: discord.Interaction, button: discord.ui.Button):
            temp_channel = await interaction.guild.create_text_channel(name=f"{interaction.user.name}")
            await temp_channel.send(f"{caption}\nNhấn Rent nha khách iu ơi ⋆𐙚 ̊.", embed=embed, file=file)
            await interaction.response.send_message(f"✅ Chat riêng đã tạo: {temp_channel.mention}", ephemeral=True)
    await channel.send(embed=embed, file=file)
    await channel.send("Nhấn Rent nha khách iu ơi ⋆𐙚 ̊.", view=RentButton())
    await ctx.message.add_reaction("✅")

# -----------------------
# !pick (choose)
@bot.command()
async def pick(ctx, *, options):
    choices = options.split()
    if choices:
        await ctx.send(random.choice(choices))

# -----------------------
# !rd
@bot.command()
async def rd(ctx):
    await ctx.send(str(random.randint(1,999)))

# -----------------------
# !clear
@bot.command()
async def clear(ctx, amount: str):
    if amount.lower() == "all":
        await ctx.channel.purge()
    else:
        try:
            n = int(amount)
            await ctx.channel.purge(limit=n+1)
        except:
            await ctx.send("Sai định dạng!")

# -----------------------
# !av
@bot.command()
async def av(ctx, member: discord.Member):
    embed = Embed(title=f"{member.name}'s Avatar", color=0xF4C2C2)
    embed.set_image(url=member.avatar.url if member.avatar else None)
    await ctx.send(embed=embed)

# -----------------------
# !ban
@bot.command()
async def ban(ctx, member: discord.Member=None):
    if ctx.author.id != ADMIN_ID:
        await ctx.send("Không có quyền.")
        return
    if not member:
        await ctx.send(embed=Embed(description="Chọn người bạn muốn ban?", color=0xF4C2C2))
        return
    try:
        await member.ban(reason=f"Banned by {ctx.author}")
        await ctx.send(f"{member} đã bị ban!")
    except:
        await ctx.send("Lỗi khi ban.")

# -----------------------
# !mute
@bot.command()
async def mute(ctx, member: discord.Member=None, time: str="1m"):
    if ctx.author.id not in [ADMIN_ID, 1432670531529867295]:
        await ctx.send("Không có quyền.")
        return
    if not member:
        await ctx.send(embed=Embed(description="Chọn người bạn muốn mute?", color=0xF4C2C2))
        return
    seconds = 60
    m = re.match(r'(\d+)m', time.lower())
    if m:
        seconds = int(m.group(1))*60
    role = discord.utils.get(ctx.guild.roles, name="Muted")
    if not role:
        role = await ctx.guild.create_role(name="Muted")
    await member.add_roles(role)
    await ctx.send(f"{member} đã bị mute {time}.")
    await asyncio.sleep(seconds)
    await member.remove_roles(role)

# -----------------------
# !voice
@bot.command()
async def voice(ctx):
    embed = Embed(title="Voice menu", description="Lock, Unlock, Hide, Invite", color=0xF4C2C2)
    await ctx.send(embed=embed)

# -----------------------
# Timer
@bot.command()
async def time(ctx, *, t: str):
    t = t.lower().replace(" ", "")
    h, m = 0,0
    h_match = re.search(r'(\d+)h', t)
    m_match = re.search(r'(\d+)m', t)
    if h_match: h=int(h_match.group(1))
    if m_match: m=int(m_match.group(1))
    total_sec = h*3600+m*60
    if total_sec==0:
        await ctx.send("Không nhận diện được thời gian!")
        return
    vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')
    end_time = datetime.now(vn_tz)+timedelta(seconds=total_sec)
    await ctx.send(f"⏳ Bắt đầu {h}h{m}m, kết thúc lúc {end_time.strftime('%H:%M:%S')} VN time")
    await asyncio.sleep(total_sec)
    await ctx.send(f"⏰ Hết giờ: {end_time.strftime('%H:%M:%S')}")

# -----------------------
if __name__ == '__main__':
    bot.run(TOKEN)
