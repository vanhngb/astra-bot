import discord
from discord.ext import commands
from discord import Embed
import sqlite3
import os
from datetime import datetime

# =======================
# CONFIG
# =======================
TOKEN = os.getenv("DISCORD_BOT_SECRET")

LOG_CHANNEL_ID = 1448047569421733981  # Channel log IO + Donate
REPORT_CHANNEL_ID = 1448052039384043683  # Channel báo cáo lương tháng
HOURLY_WAGE = 25000  # 25.000đ mỗi giờ
ADMIN_ID = 757555763559399424

PASTEL_PINK = 0xFFB7D5  # MÀU HỒNG PASTEL

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# =======================
# SQLITE SETUP
# =======================
conn = sqlite3.connect("salary.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS salary (
    user_id INTEGER PRIMARY KEY,
    hours INTEGER DEFAULT 0,
    donate INTEGER DEFAULT 0
)
""")
conn.commit()

def get_salary(user_id):
    cursor.execute("SELECT hours, donate FROM salary WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row:
        return row[0], row[1]
    return 0, 0

def add_hours(user_id, h):
    h = int(h)  # đảm bảo là số nguyên
    hours, donate = get_salary(user_id)
    cursor.execute("REPLACE INTO salary(user_id, hours, donate) VALUES (?, ?, ?)",
                   (user_id, hours + h, donate))
    conn.commit()

def add_donate(user_id, amount):
    hours, donate = get_salary(user_id)
    cursor.execute("REPLACE INTO salary(user_id, hours, donate) VALUES (?, ?, ?)",
                   (user_id, hours, donate + amount))
    conn.commit()

def reset_all():
    cursor.execute("DELETE FROM salary")
    conn.commit()

# =======================
# COMMAND: !luong
# =======================
@bot.command()
async def luong(ctx, member: discord.Member = None):
    # user tự xem lương mình
    if member is None:
        member = ctx.author
    else:
        # admin mới xem được lương người khác
        if ctx.author.id != ADMIN_ID:
            return await ctx.send("❌ Bạn không có quyền xem lương của người khác.")

    hours, donate = get_salary(member.id)
    total_salary = hours * HOURLY_WAGE + donate

    embed = Embed(
        title=f"Lương của {member.display_name}",
        color=PASTEL_PINK
    )
    embed.add_field(name="Giờ book:", value=f"{hours} giờ", inline=False)
    embed.add_field(name="Lương giờ:", value=f"{hours * HOURLY_WAGE:,} đ", inline=False)
    embed.add_field(name="Donate:", value=f"{donate:,} đ", inline=False)
    embed.add_field(name="Lương tổng:", value=f"{total_salary:,} đ", inline=False)

    await ctx.author.send(embed=embed)
    await ctx.message.delete()  # không để lại tin nhắn lệnh

# =======================
# COMMAND: !io <hours> @user
# =======================
@bot.command()
@commands.has_permissions(administrator=True)
async def io(ctx, hours: str, member: discord.Member):
    # parse giờ: 2h → 2
    if hours.lower().endswith("h"):
        number = hours[:-1]
    else:
        number = hours

    if not number.isdigit():
        return await ctx.send("❌ Sai cú pháp. Ví dụ: `!io 2h @user`")

    hours_int = int(number)
    add_hours(member.id, hours_int)

    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    await log_channel.send(f"**{member.mention} : +{hours_int} giờ**")

    await ctx.message.delete()

# =======================
# COMMAND: !dnt <amount> @user
# =======================
@bot.command()
@commands.has_permissions(administrator=True)
async def dnt(ctx, amount: int, member: discord.Member):
    add_donate(member.id, amount)

    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    await log_channel.send(f"**{member.mention} donate : {amount:,} đ**")

    await ctx.message.delete()

# =======================
# COMMAND: !reset (admin only)
# =======================
@bot.command()
@commands.has_permissions(administrator=True)
async def reset(ctx):
    reset_all()
    await ctx.message.delete()  # không báo gì cả

# =======================
# AUTO BÁO CÁO LƯƠNG THÁNG
# =======================
@bot.event
async def on_ready():
    print(f"Bot đã đăng nhập như {bot.user}")
    bot.loop.create_task(monthly_report_task())

async def monthly_report_task():
    await bot.wait_until_ready()
    sent_month = None

    while not bot.is_closed():
        now = datetime.now()

        if now.day == 1 and (sent_month != now.month):
            sent_month = now.month

            channel = bot.get_channel(REPORT_CHANNEL_ID)

            cursor.execute("SELECT user_id, hours, donate FROM salary")
            rows = cursor.fetchall()

            if len(rows) == 0:
                await channel.send("📄 Không có dữ liệu lương tháng này.")
            else:
                report_text = "📊 **BÁO CÁO LƯƠNG THÁNG**\n\n"
                for uid, hours, donate in rows:
                    total = hours * HOURLY_WAGE + donate
                    report_text += (
                        f"<@{uid}> — Giờ: **{hours}**, Lương giờ: **{hours * HOURLY_WAGE:,} đ**, "
                        f"Donate: **{donate:,} đ**, Tổng: **{total:,} đ**\n"
                    )

                await channel.send(report_text)

        await asyncio.sleep(3600)

# =======================
# RUN BOT
# =======================
bot.run(TOKEN)
