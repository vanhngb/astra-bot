import discord
from discord.ext import commands, tasks
from discord import Embed, File, ui
from flask import Flask
from threading import Thread
import asyncio
import os
import sqlite3
from datetime import datetime, timedelta
import pytz
import random
import re

# -----------------------
# Flask server để ping 24/7
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
    print("LỖI: Thiếu biến môi trường 'DISCORD_BOT_SECRET'. Không thể chạy bot.")
    exit()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# -----------------------
# Channel & role config
WELCOME_CHANNEL_ID = 1432658695719751793
SUPPORT_CHANNEL_ID = 1432685282955755595
IMAGE_CHANNEL_FEMALE = 1432691499094769704
IMAGE_CHANNEL_MALE = 1432691597363122357
ADMIN_ID = 757555763559399424
ROLE_IO = 1448047569421733981
CHANNEL_LUONGALL = 1448052039384043683

# -----------------------
# Database setup
conn = sqlite3.connect('botdata.db')
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS luong (
    user_id INTEGER PRIMARY KEY,
    gio_book INTEGER DEFAULT 0,
    donate INTEGER DEFAULT 0
)''')
c.execute('''CREATE TABLE IF NOT EXISTS prf (
    user_id INTEGER PRIMARY KEY,
    gio_book INTEGER DEFAULT 0,
    donate INTEGER DEFAULT 0
)''')
c.execute('''CREATE TABLE IF NOT EXISTS code_data (
    user_id INTEGER PRIMARY KEY,
    ping TEXT,
    content TEXT,
    image TEXT
)''')
conn.commit()

# -----------------------
# Helper functions
def pastel_pink():
    return discord.Color.from_rgb(255, 192, 203)

def format_money(amount):
    return f"{amount:,} VNĐ"

def get_user_luong(user_id):
    c.execute('SELECT gio_book, donate FROM luong WHERE user_id=?', (user_id,))
    row = c.fetchone()
    if row:
        gio, donate = row
    else:
        gio, donate = 0, 0
    luong_gio = gio * 25000
    return gio, donate, luong_gio, luong_gio + donate

def get_user_prf(user_id):
    c.execute('SELECT gio_book, donate FROM prf WHERE user_id=?', (user_id,))
    row = c.fetchone()
    if row:
        gio, donate = row
    else:
        gio, donate = 0, 0
    return gio, donate

def update_luong(user_id, gio=0, donate=0):
    c.execute('INSERT OR IGNORE INTO luong(user_id, gio_book, donate) VALUES(?,?,?)', (user_id, 0,0))
    c.execute('UPDATE luong SET gio_book = gio_book + ?, donate = donate + ? WHERE user_id=?', (gio, donate, user_id))
    conn.commit()

def update_prf(user_id, gio=0, donate=0):
    c.execute('INSERT OR IGNORE INTO prf(user_id, gio_book, donate) VALUES(?,?,?)', (user_id,0,0))
    c.execute('UPDATE prf SET gio_book = gio_book + ?, donate = donate + ? WHERE user_id=?', (gio, donate, user_id))
    conn.commit()

# -----------------------
# Events
@bot.event
async def on_ready():
    print(f'Bot đã đăng nhập như {bot.user}')

@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        embed = Embed(
            title=f"Chào mừng {member.display_name} đến với ⋆. 𐙚˚࿔ 𝒜𝓈𝓉𝓇𝒶 𝜗𝜚˚⋆",
            description=f"Mong bạn ở đây thật vui nhá ^^\nCó cần hỗ trợ gì thì <#{SUPPORT_CHANNEL_ID}> nhá",
            color=pastel_pink()
        )
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
        await channel.send(embed=embed)

# -----------------------
# Commands

## Luong / PRF
@bot.command()
async def luong(ctx, target: discord.Member=None):
    if target and ctx.author.id != ADMIN_ID and 1432670531529867295 not in [r.id for r in ctx.author.roles]:
        await ctx.send("❌ Bạn không có quyền xem lương người khác")
        return
    user = target or ctx.author
    gio, donate, luong_gio, luong_total = get_user_luong(user.id)
    embed = Embed(title=f"Lương tháng", color=pastel_pink())
    embed.add_field(name="𐙚 Giờ book:", value=f"{gio}", inline=False)
    embed.add_field(name="𐙚 Lương giờ:", value=format_money(luong_gio), inline=False)
    embed.add_field(name="𐙚 Donate:", value=format_money(donate), inline=False)
    embed.add_field(name="𐙚 Lương tổng:", value=format_money(luong_total), inline=False)
    try:
        await user.send(embed=embed)
        if user != ctx.author:
            await ctx.send(f"✅ Đã gửi lương của {user.display_name} vào DM.")
    except:
        await ctx.send(embed=embed)

@bot.command()
async def prf(ctx, target: discord.Member=None):
    user = target or ctx.author
    gio, donate = get_user_prf(user.id)
    embed = Embed(title=f"PRF", color=pastel_pink())
    embed.add_field(name="𐙚 Giờ đã book:", value=f"{gio}", inline=False)
    embed.add_field(name="𐙚 Đã Donate:", value=format_money(donate), inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def rs(ctx):
    c.execute('UPDATE luong SET gio_book=0, donate=0')
    c.execute('UPDATE prf SET gio_book=0, donate=0')
    conn.commit()
    await ctx.send("✅ Đã reset toàn bộ lương.")

@bot.command()
async def luongall(ctx):
    embed = Embed(title="Tổng hợp lương", description="Ai thắc mắc về lương phản hồi trước 12h ngày mai nhaa", color=pastel_pink())
    c.execute('SELECT user_id, gio_book, donate FROM luong')
    rows = c.fetchall()
    for uid, gio, donate in rows:
        luong_gio = gio * 25000
        embed.add_field(name=str(uid), value=f"Giờ book: {gio}\nLương giờ: {format_money(luong_gio)}\nDonate: {format_money(donate)}\nTổng: {format_money(luong_gio+donate)}", inline=False)
    await bot.get_channel(CHANNEL_LUONGALL).send(embed=embed)

## IO / DNT
@bot.command()
async def io(ctx, time: str, user1: discord.Member, by: discord.Member=None):
    gio = 0
    h_match = re.search(r'(\d+)h', time)
    m_match = re.search(r'(\d+)m', time)
    if h_match: gio += int(h_match.group(1))
    if m_match: gio += int(m_match.group(1))/60
    gio = int(gio)
    update_luong(user1.id, gio=gio)
    if by: update_prf(by.id, gio=gio)
    channel = bot.get_channel(ROLE_IO)
    await channel.send(f"{user1.mention} : {gio}")

@bot.command()
async def dnt(ctx, amount: int, user1: discord.Member, by: discord.Member=None):
    update_luong(user1.id, donate=amount)
    if by: update_prf(by.id, donate=amount)
    channel = bot.get_channel(ROLE_IO)
    await channel.send(f"{user1.mention} : {amount}")

## QR
@bot.command()
async def qr(ctx):
    embed = Embed(title="QR Payment", color=pastel_pink())
    qr_path = "qr.png"
    if os.path.exists(qr_path):
        embed.set_image(url="attachment://qr.png")
        await ctx.send(embed=embed, file=File(qr_path, filename="qr.png"))
    else:
        await ctx.send("Không tìm thấy ảnh QR.", embed=embed)

## Text
@bot.command()
async def text(ctx, *, content: str):
    await ctx.message.delete()
    embed = Embed(description=content, color=pastel_pink())
    await ctx.send(embed=embed)

## Random / Pick
@bot.command()
async def rd(ctx):
    await ctx.send(str(random.randint(1,999)))

@bot.command()
async def pick(ctx, *, options):
    lst = options.split()
    await ctx.send(random.choice(lst))

# -----------------------
# Run bot
if __name__ == '__main__':
    bot.run(TOKEN)
