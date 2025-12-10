import discord
from discord.ext import commands, tasks
from discord import Embed, File, ui
from flask import Flask
from threading import Thread
import asyncio
from datetime import datetime, timedelta
import os
import sqlite3
import requests
import pytz

# ---------------------------
# Flask ping 24/7
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

Thread(target=run).start()

# ---------------------------
# Bot setup
TOKEN = os.getenv('DISCORD_BOT_SECRET')
if not TOKEN:
    print("Missing token!")
    exit()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# ---------------------------
# Database
DB_PATH = "data.db"
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS luong (
    user_id INTEGER PRIMARY KEY,
    gio_book INTEGER DEFAULT 0,
    donate INTEGER DEFAULT 0
)''')
c.execute('''CREATE TABLE IF NOT EXISTS prf (
    user_id INTEGER PRIMARY KEY,
    gio_da_book INTEGER DEFAULT 0,
    donate INTEGER DEFAULT 0
)''')
c.execute('''CREATE TABLE IF NOT EXISTS codes (
    user_id INTEGER PRIMARY KEY,
    title TEXT,
    content TEXT,
    image TEXT
)''')
conn.commit()

# ---------------------------
# Config
WELCOME_CHANNEL = 1432658695719751793
SUPPORT_CHANNEL = 1432685282955755595
IMAGE_CHANNEL_FEMALE = 1432691499094769704
IMAGE_CHANNEL_MALE = 1432691597363122357
ADMIN_ROLE = 1432670531529867295
PING_CHANNEL = 1448047569421733981
LUONGALL_CHANNEL = 1448052039384043683
VOICE_CATEGORY = 1448062526599205037
FIXED_RATE = 25000

# ---------------------------
# Ping Healthchecks
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

@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user}")
    if HC_PING_URL:
        bot.loop.create_task(keep_alive_ping())

# ---------------------------
# Welcome
@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL)
    if channel:
        embed = Embed(
            description=f"Chào mừng {member.mention} đến với ⋆. 𐙚˚࿔ 𝒜𝓈𝓉𝓇𝒶 𝜗𝜚˚⋆, mong bạn ở đây thật vui nhá ^^\nCó cần hỗ trợ gì thì <#{SUPPORT_CHANNEL}> nhá",
            color=0xFFC0CB
        )
        embed.set_thumbnail(url=member.avatar.url)
        await channel.send(embed=embed)

# ---------------------------
# !luong
@bot.command()
async def luong(ctx, member: discord.Member=None):
    target = member or ctx.author
    c.execute("SELECT gio_book, donate FROM luong WHERE user_id=?", (target.id,))
    row = c.fetchone()
    gio = row[0] if row else 0
    donate = row[1] if row else 0
    tong = gio*FIXED_RATE + donate

    embed = Embed(
        title=f"Lương tháng {datetime.now(pytz.timezone('Asia/Ho_Chi_Minh')).strftime('%m/%Y')}",
        color=0xFFC0CB
    )
    embed.add_field(name="𐙚 Giờ book:", value=str(gio))
    embed.add_field(name="𐙚 Lương giờ:", value=f"{gio*FIXED_RATE}đ")
    embed.add_field(name="𐙚 Donate:", value=f"{donate}đ")
    embed.add_field(name="𐙚 Lương tổng:", value=f"{tong}đ")

    try:
        await ctx.author.send(embed=embed)
        if ctx.author != target:
            await ctx.send(f"✅ Lương của {target.display_name} đã gửi vào DM.")
    except:
        await ctx.send(embed=embed)

# ---------------------------
# !prf
@bot.command()
async def prf(ctx, member: discord.Member=None):
    target = member or ctx.author
    c.execute("SELECT gio_da_book, donate FROM prf WHERE user_id=?", (target.id,))
    row = c.fetchone()
    gio = row[0] if row else 0
    donate = row[1] if row else 0
    embed = Embed(
        title="Thông tin PRF",
        color=0xFFC0CB
    )
    embed.add_field(name="𐙚 Giờ đã book:", value=str(gio))
    embed.add_field(name="𐙚 Đã Donate:", value=f"{donate}đ")
    await ctx.send(embed=embed)

# ---------------------------
# !io <time> @user by @user
@bot.command()
async def io(ctx, time: str, target: discord.Member, by: discord.Member=None):
    by = by or ctx.author
    # Convert time
    match = re.match(r'(\d+)h', time.lower())
    hours = int(match.group(1)) if match else 0
    match = re.match(r'(\d+)m', time.lower())
    minutes = int(match.group(1)) if match else 0
    total_hours = hours + minutes/60
    total_hours_int = int(total_hours)

    # Add to luong for first user
    c.execute("INSERT OR IGNORE INTO luong (user_id) VALUES (?)", (target.id,))
    c.execute("UPDATE luong SET gio_book=gio_book+? WHERE user_id=?", (total_hours_int, target.id))

    # Add to prf for second user
    c.execute("INSERT OR IGNORE INTO prf (user_id) VALUES (?)", (by.id,))
    c.execute("UPDATE prf SET gio_da_book=gio_da_book+? WHERE user_id=?", (total_hours_int, by.id))
    conn.commit()

    await ctx.send(f"{target.mention} : {total_hours_int}", delete_after=10)
    ch = bot.get_channel(PING_CHANNEL)
    await ch.send(f"{target.mention} : {total_hours_int}")

# ---------------------------
# !dnt <amount> @user by @user
@bot.command()
async def dnt(ctx, amount: int, target: discord.Member, by: discord.Member=None):
    by = by or ctx.author
    c.execute("INSERT OR IGNORE INTO luong (user_id) VALUES (?)", (target.id,))
    c.execute("UPDATE luong SET donate=donate+? WHERE user_id=?", (amount, target.id))

    c.execute("INSERT OR IGNORE INTO prf (user_id) VALUES (?)", (by.id,))
    c.execute("UPDATE prf SET donate=donate+? WHERE user_id=?", (amount, by.id))
    conn.commit()

    await ctx.send(f"{target.mention} : {amount}đ", delete_after=10)
    ch = bot.get_channel(PING_CHANNEL)
    await ch.send(f"{target.mention} : {amount}đ")

# ---------------------------
# !rs reset toàn bộ
@bot.command()
async def rs(ctx):
    c.execute("UPDATE luong SET gio_book=0, donate=0")
    c.execute("UPDATE prf SET gio_da_book=0, donate=0")
    conn.commit()
    await ctx.send("✅ Đã reset lương tất cả.", delete_after=5)

# ---------------------------
# !voice <name> tạo voice
@bot.command()
async def voice(ctx, *, name=None):
    name = name or f"{ctx.author.display_name}"
    category = bot.get_channel(VOICE_CATEGORY)
    channel = await ctx.guild.create_voice_channel(name, category=category)
    await ctx.send(f"✅ Voice channel `{channel.name}` đã được tạo!", delete_after=10)

# ---------------------------
# !qr
@bot.command()
async def qr(ctx):
    qr_path = "qr.png"
    embed = Embed(
        title="QR",
        color=0xFFC0CB
    )
    if os.path.exists(qr_path):
        embed.set_image(url="attachment://qr.png")
        await ctx.send(embed=embed, file=File(qr_path))
    else:
        await ctx.send(embed=embed)

# ---------------------------
# Keep bot running
if __name__ == "__main__":
    bot.run(TOKEN)
