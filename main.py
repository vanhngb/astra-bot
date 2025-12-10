import discord
from discord.ext import commands
from discord import Embed, File
from flask import Flask
from threading import Thread
import asyncio
from datetime import datetime, timedelta
import re
import os
import requests
import pytz
import sqlite3

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
    print("LỖI: Thiếu biến môi trường 'DISCORD_BOT_SECRET'. Không thể chạy bot.")
    exit()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# -----------------------
# Config
WELCOME_CHANNEL_ID = 1432658695719751793
ROLE_IO = 1448047569421733981
ADMIN_ID = 1432670531529867295
REPORT_CHANNEL_ID = 1448052039384043683
IMAGE_CHANNEL_FEMALE = 1432691499094769704
IMAGE_CHANNEL_MALE = 1432691597363122357

# -----------------------
# Database setup
conn = sqlite3.connect('bot_data.db')
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS luong (user_id INTEGER PRIMARY KEY, gio_book INTEGER, donate INTEGER)''')
c.execute('''CREATE TABLE IF NOT EXISTS prf (user_id INTEGER PRIMARY KEY, gio_book INTEGER, donate INTEGER)''')
c.execute('''CREATE TABLE IF NOT EXISTS code_data (keyword TEXT PRIMARY KEY, ping TEXT, content TEXT, image TEXT)''')
conn.commit()

# -----------------------
@bot.event
async def on_ready():
    print(f'Bot logged in as {bot.user}')

@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        embed = Embed(
            description=f"Chào mừng {member.mention} đến với ⋆. 𐙚˚࿔ 𝒜𝓈𝓉𝓇𝒶 𝜗𝜚˚⋆, mong bạn ở đây thật vui nhá ^^ Có cần hỗ trợ gì thì <#{ROLE_IO}> nhá",
            color=0xFFC0CB
        )
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
        await channel.send(embed=embed)

# -----------------------
# !luong
@bot.command()
async def luong(ctx, member: discord.Member=None):
    target = member or ctx.author
    c.execute('SELECT gio_book, donate FROM luong WHERE user_id=?', (target.id,))
    row = c.fetchone()
    gio = row[0] if row else 0
    donate = row[1] if row else 0
    luong_gio = gio * 25000
    tong = luong_gio + donate
    embed = Embed(title=f"Lương tháng {datetime.now(pytz.timezone('Asia/Ho_Chi_Minh')).month}", color=0xFFC0CB)
    embed.add_field(name='𐙚 Giờ book:', value=str(gio))
    embed.add_field(name='𐙚 Lương giờ:', value=f'{luong_gio}đ')
    embed.add_field(name='𐙚 Donate:', value=f'{donate}đ')
    embed.add_field(name='𐙚 Lương tổng:', value=f'{tong}đ')
    try:
        await target.send(embed=embed)
        if target != ctx.author:
            await ctx.send(f'✅ Đã gửi lương của {target.display_name} vào DM.')
    except:
        await ctx.send('❌ Không thể gửi DM cho user này.')

# -----------------------
# !prf
@bot.command()
async def prf(ctx, member: discord.Member=None):
    target = member or ctx.author
    c.execute('SELECT gio_book, donate FROM prf WHERE user_id=?', (target.id,))
    row = c.fetchone()
    gio = row[0] if row else 0
    donate = row[1] if row else 0
    embed = Embed(title=f"Thống kê {target.display_name}", color=0xFFC0CB)
    embed.add_field(name='𐙚 Giờ đã book:', value=str(gio))
    embed.add_field(name='𐙚 Đã Donate:', value=f'{donate}đ')
    await ctx.send(embed=embed)

# -----------------------
# !io
@bot.command()
async def io(ctx, time: str, member: discord.Member, by: discord.Member):
    match = re.match(r'(\d+)h', time)
    if not match:
        await ctx.send('❌ Format: !io <time>h @user by @user')
        return
    gio = int(match.group(1))
    # Update luong
    c.execute('SELECT gio_book FROM luong WHERE user_id=?', (member.id,))
    row = c.fetchone()
    if row:
        c.execute('UPDATE luong SET gio_book = gio_book + ? WHERE user_id=?', (gio, member.id))
    else:
        c.execute('INSERT INTO luong (user_id, gio_book, donate) VALUES (?, ?, 0)', (member.id, gio))
    # Update prf
    c.execute('SELECT gio_book FROM prf WHERE user_id=?', (by.id,))
    row2 = c.fetchone()
    if row2:
        c.execute('UPDATE prf SET gio_book = gio_book + ? WHERE user_id=?', (gio, by.id))
    else:
        c.execute('INSERT INTO prf (user_id, gio_book, donate) VALUES (?, ?, 0)', (by.id, gio))
    conn.commit()
    # Send notification
    channel = bot.get_channel(ROLE_IO)
    await channel.send(f'{member.mention} : {gio}')

# -----------------------
# !dnt
@bot.command()
async def dnt(ctx, amount: int, member: discord.Member, by: discord.Member):
    # Update luong
    c.execute('SELECT donate FROM luong WHERE user_id=?', (member.id,))
    row = c.fetchone()
    if row:
        c.execute('UPDATE luong SET donate = donate + ? WHERE user_id=?', (amount, member.id))
    else:
        c.execute('INSERT INTO luong (user_id, gio_book, donate) VALUES (?, 0, ?)', (member.id, amount))
    # Update prf
    c.execute('SELECT donate FROM prf WHERE user_id=?', (by.id,))
    row2 = c.fetchone()
    if row2:
        c.execute('UPDATE prf SET donate = donate + ? WHERE user_id=?', (amount, by.id))
    else:
        c.execute('INSERT INTO prf (user_id, gio_book, donate) VALUES (?, 0, ?)', (by.id, amount))
    conn.commit()
    # Send notification
    channel = bot.get_channel(ROLE_IO)
    await channel.send(f'{member.mention} : {amount}')

# -----------------------
# !rs
@bot.command()
async def rs(ctx):
    c.execute('UPDATE luong SET gio_book=0, donate=0')
    c.execute('UPDATE prf SET gio_book=0, donate=0')
    conn.commit()
    await ctx.send('✅ Đã reset toàn bộ dữ liệu lương và prf.')

# -----------------------
# !code
@bot.command()
async def code(ctx, ping: str, *, content):
    img_url = None
    if ctx.message.attachments:
        img_url = ctx.message.attachments[0].url
    c.execute('REPLACE INTO code_data (keyword, ping, content, image) VALUES (?, ?, ?, ?)', (ping, ping, content, img_url))
    conn.commit()
    await ctx.send(f'✅ Đã lưu code với từ khóa: {ping}')

# Trigger code
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    c.execute('SELECT ping, content, image FROM code_data WHERE keyword=?', (message.content,))
    row = c.fetchone()
    if row:
        embed = Embed(description=f'{row[0]} {row[1]}', color=0xFFC0CB)
        if row[2]:
            embed.set_image(url=row[2])
        await message.channel.send(embed=embed)
    await bot.process_commands(message)

# -----------------------
# Run bot
if __name__ == '__main__':
    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f'Bot gặp lỗi: {e}')
