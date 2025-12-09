import discord
from discord.ext import commands
from discord import Embed, ui, File
from flask import Flask
from threading import Thread
import asyncio
from datetime import datetime, timedelta
import re
import os
import json
import requests
import pytz

# -----------------------
# Flask server để ping 24/7 (Replit)
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
    print("LỖI: Thiếu DISCORD_BOT_SECRET.")
    exit()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# -----------------------
# Channel ID + Admin
WELCOME_CHANNEL_ID = 1432659040680284191
SUPPORT_CHANNEL_ID = 1432685282955755595
IMAGE_CHANNEL_FEMALE = 1432691499094769704
IMAGE_CHANNEL_MALE = 1432691597363122357
ADMIN_ID = 757555763559399424

# -----------------------
# KEEP ALIVE (Healthcheck)
HC_PING_URL = os.getenv('HEALTHCHECKS_URL')

async def keep_alive_ping():
    if not HC_PING_URL:
        return
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            requests.get(HC_PING_URL, timeout=10)
        except Exception as e:
            print("Ping error:", e)
        await asyncio.sleep(14 * 60)

@bot.event
async def on_ready():
    print(f'Bot đang chạy: {bot.user}')
    if HC_PING_URL:
        bot.loop.create_task(keep_alive_ping())

# -----------------------
# Welcome event
@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        await channel.send(
            f"Chào mừng {member.mention} đến với ⋆. 𐙚˚࿔ 𝒜𝓈𝓉𝓇𝒶 𝜗𝜚˚⋆ "
            f"Nếu cần hỗ trợ vào <#{SUPPORT_CHANNEL_ID}> nha!"
        )

# =====================================================
# 📌 PHẦN QUẢN LÝ LƯƠNG – JSON
# =====================================================

DATA_FILE = "luong.json"

def load_data():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=4)
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def ensure_user(uid):
    data = load_data()
    if uid not in data:
        data[uid] = {
            "book_hours": 0,
            "donate": 0,
            "luong_gio": 0,
        }
        save_data(data)

# =====================================================
# 📌 LỆNH !luong — XEM LƯƠNG
# =====================================================

@bot.command()
async def luong(ctx, member: discord.Member = None):
    member = member or ctx.author
    uid = str(member.id)

    ensure_user(uid)
    data = load_data()[uid]

    luong_tong = (data["book_hours"] * data["luong_gio"]) + data["donate"]

    embed = Embed(
        title=f"💰 Bảng lương của {member.display_name}",
        color=discord.Color.green()
    )
    embed.add_field(name="Giờ book:", value=f"{data['book_hours']} giờ", inline=False)
    embed.add_field(name="Donate:", value=f"{data['donate']} đ", inline=False)
    embed.add_field(name="Lương giờ:", value=f"{data['luong_gio']} đ/giờ", inline=False)
    embed.add_field(name="Lương tổng:", value=f"{luong_tong} đ", inline=False)

    await ctx.send(embed=embed)

# =====================================================
# 📌 LỆNH !inout — THÊM GIỜ BOOK
# =====================================================

@bot.command()
async def inout(ctx, hours: float, luong_gio: int = None):
    uid = str(ctx.author.id)
    ensure_user(uid)

    data = load_data()

    data[uid]["book_hours"] += hours
    if luong_gio is not None:
        data[uid]["luong_gio"] = luong_gio

    save_data(data)

    await ctx.send(
        f"⏳ Đã ghi nhận **{hours} giờ** cho {ctx.author.mention}.\n"
        f"💵 Lương giờ hiện tại: **{data[uid]['luong_gio']} đ/giờ**"
    )

# =====================================================
# 📌 LỆNH !dnt — THÊM DONATE
# =====================================================

@bot.command()
async def dnt(ctx, amount: int):
    uid = str(ctx.author.id)
    ensure_user(uid)

    data = load_data()
    data[uid]["donate"] += amount
    save_data(data)

    await ctx.send(f"💗 Đã cộng donate **{amount} đ** cho {ctx.author.mention}")

# =====================================================
# 📌 LỆNH !ban — BAN USER
# =====================================================

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member = None):
    if not member:
        await ctx.send("❌ Bạn cần tag 1 người để ban. VD: `!ban @user`")
        return

    try:
        await member.ban(reason=f"Banned by {ctx.author}")
        await ctx.send(f"🔨 Đã ban {member.mention}.")
    except Exception as e:
        await ctx.send(f"❌ Lỗi khi ban: {e}")

# =====================================================
# 📌 LỆNH !banrole — BAN TẤT CẢ USER TRONG ROLE
# =====================================================

@bot.command()
@commands.has_permissions(ban_members=True)
async def banrole(ctx, role: discord.Role = None):
    if not role:
        await ctx.send("❌ Cần nhập role. VD `!banrole Player`")
        return

    count = 0
    for member in role.members:
        try:
            await member.ban(reason=f"Banned by {ctx.author} (role ban)")
            count += 1
        except:
            pass

    await ctx.send(f"🔨 Đã ban **{count} thành viên** trong role **{role.name}**.")

# =====================================================
# LỆNH EMBED !text
# =====================================================

@bot.command()
async def text(ctx, *, content: str):
    await ctx.message.delete()

    embed = discord.Embed(description=content, color=discord.Color.from_rgb(255, 209, 220))
    embed.set_footer(text=f"Sent by {ctx.author.display_name}", icon_url=ctx.author.avatar.url)

    await ctx.send(embed=embed)

# =====================================================
# LỆNH !post (Rent System)
# =====================================================

@bot.command()
async def post(ctx, gender: str, *, caption: str = ""):
    if len(ctx.message.attachments) == 0:
        await ctx.send("❌ Bạn chưa gửi ảnh!")
        return

    attachment = ctx.message.attachments[0]
    image_file = await attachment.to_file()

    if gender.lower() == "female":
        channel = bot.get_channel(IMAGE_CHANNEL_FEMALE)
    else:
        channel = bot.get_channel(IMAGE_CHANNEL_MALE)

    embed = Embed(description=caption)
    embed.set_image(url=f"attachment://{attachment.filename}")

    class RentButton(ui.View):
        def __init__(self):
            super().__init__(timeout=None)

        @ui.button(label="Rent", style=discord.ButtonStyle.primary)
        async def rent(self, interaction, button):
            guild = interaction.guild
            member = interaction.user

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                member: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.get_member(ADMIN_ID): discord.PermissionOverwrite(read_messages=True),
                guild.me: discord.PermissionOverwrite(read_messages=True),
            }

            temp_channel = await guild.create_text_channel(
                name=f"temp-rent-{datetime.now().strftime('%H%M%S')}",
                overwrites=overwrites
            )

            await temp_channel.send(f"Channel đã tạo cho {member.mention}.")

            class DoneButton(ui.View):
                @ui.button(label="Done", style=discord.ButtonStyle.danger)
                async def done(self, interaction2, button2):
                    await temp_channel.delete()
                    await interaction2.response.send_message("Đã xóa channel!", ephemeral=True)

            await temp_channel.send("Nhấn Done khi hoàn tất.", view=DoneButton())
            await interaction.response.send_message(f"Đã tạo: {temp_channel.mention}", ephemeral=True)

    await channel.send(embed=embed, file=image_file)
    await channel.send("Nhấn Rent để trao đổi nha!", view=RentButton())
    await ctx.send("✅ Đã đăng bài thành công.")

# =====================================================
# LỆNH !qr
# =====================================================

@bot.command()
async def qr(ctx):
    embed = Embed(description="Gửi bill thanh toán vào đây, không ghi NDCK nha ୨୧")
    qr_path = "qr.png"

    if os.path.exists(qr_path):
        qr_file = File(qr_path, filename="qr.png")
        embed.set_image(url="attachment://qr.png")
        await ctx.send(embed=embed, file=qr_file)
    else:
        await ctx.send("Không tìm thấy ảnh QR.")

# =====================================================
# RUN BOT
# =====================================================

if __name__ == '__main__':
    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"Lỗi chạy bot: {e}")
