import discord
from discord.ext import commands
from discord import Embed, FFmpegPCMAudio, ui, File
from flask import Flask
from threading import Thread
import asyncio
from datetime import datetime, timedelta
import re
import os
import yt_dlp
import requests
import pytz # Thư viện để quản lý múi giờ

# -----------------------
# Flask server để ping 24/7 (Không cần thay đổi)
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    # Sử dụng port từ biến môi trường nếu có, nếu không mặc định 8080
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# Bắt đầu server Flask trong một luồng riêng
Thread(target=run).start()
# -----------------------

# Bot setup
# Lấy TOKEN từ biến môi trường (BẮT BUỘC KHI TRIỂN KHAI)
TOKEN = os.getenv('DISCORD_BOT_SECRET')
if not TOKEN:
    print("LỖI: Thiếu biến môi trường 'DISCORD_BOT_SECRET'. Không thể chạy bot.")
    exit()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# -----------------------
# Cấu hình channel ID và admin
WELCOME_CHANNEL_ID = 1432659040680284191
SUPPORT_CHANNEL_ID = 1432685282955755595
IMAGE_CHANNEL_FEMALE = 1432691499094769704
IMAGE_CHANNEL_MALE = 1432691597363122357
ADMIN_ID = 757555763559399424

# -----------------------
# CODE PING 24/7
HC_PING_URL = os.getenv('HEALTHCHECKS_URL') # Lấy URL Ping từ biến môi trường

async def keep_alive_ping():
    if not HC_PING_URL:
        return
    
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            requests.get(HC_PING_URL, timeout=10)
        except Exception as e:
            print(f"Lỗi khi ping Healthchecks.io: {e}")
        
        await asyncio.sleep(14 * 60) # Chờ 14 phút

@bot.event
async def on_ready():
    print(f'Bot đã đăng nhập như {bot.user}')
    if HC_PING_URL:
        bot.loop.create_task(keep_alive_ping())

# -----------------------
@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        await channel.send(
            f"Chào mừng {member.mention} đến với ⋆. 𐙚˚࿔ 𝒜𝓈𝓉𝓇𝒶 𝜗𝜚˚⋆, mong bạn ở đây thật vui nhá ^^ "
            f"Có cần hỗ trợ gì thì <#{SUPPORT_CHANNEL_ID}> nhá"
        )

# -----------------------
# Music player
ytdl_format_options = {
    'format': 'bestaudio/best',
    'noplaylist': False,
    'quiet': True,
}
# Đảm bảo ffmpeg_options được thiết lập
ffmpeg_options = {'options': '-vn'} 
ytdl = yt_dlp.YoutubeDL(ytdl_format_options)
music_queue = {}

def ensure_queue(guild_id):
    if guild_id not in music_queue:
        music_queue[guild_id] = []

async def play_next(ctx, voice_client):
    guild_id = ctx.guild.id
    ensure_queue(guild_id)
    if len(music_queue[guild_id]) == 0:
        await asyncio.sleep(60) 
        if len(music_queue[guild_id]) == 0:
             await voice_client.disconnect()
        return
    
    url = music_queue[guild_id].pop(0)
    loop = asyncio.get_event_loop()
    try:
        # Lấy thông tin và URL audio
        info = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
        # Sử dụng URL trực tiếp từ info
        audio_url = info.get('url') or info['formats'][0]['url'] 
        source = FFmpegPCMAudio(audio_url, **ffmpeg_options)
        voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx, voice_client), bot.loop))
    except Exception as e:
        print(f"Lỗi phát nhạc: {e}")
        await ctx.send(f"❌ Lỗi khi phát bài hát: {e}")
        asyncio.run_coroutine_threadsafe(play_next(ctx, voice_client), bot.loop) # Thử phát bài tiếp theo

@bot.command()
async def play(ctx, *, url):
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("Bạn cần vào voice channel trước!")
        return
    
    # Thêm check chặn lặp lại lệnh
    if ctx.message.author.id == bot.user.id:
        return

    channel = ctx.author.voice.channel
    voice_client = ctx.voice_client
    if not voice_client:
        voice_client = await channel.connect()
    
    guild_id = ctx.guild.id
    ensure_queue(guild_id)
    
    # Logic phát/thêm vào queue
    if voice_client.is_playing() or voice_client.is_paused() or len(music_queue[guild_id]) > 0:
        music_queue[guild_id].append(url)
        await ctx.send(f"Đã thêm vào queue: {url}")
    else:
        music_queue[guild_id].append(url)
        await ctx.send(f"Bắt đầu phát nhạc: {url}")
        await play_next(ctx, voice_client)

@bot.command()
async def next(ctx):
    if ctx.message.author.id == bot.user.id:
        return
    voice_client = ctx.voice_client
    if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
        voice_client.stop()
        await ctx.send("Bài tiếp theo...")
    else:
        await ctx.send("Bot không phát nhạc.")

@bot.command()
async def stop(ctx):
    if ctx.message.author.id == bot.user.id:
        return
    voice_client = ctx.voice_client
    if voice_client:
        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()
        music_queue[ctx.guild.id] = [] 
        await ctx.send("Ngừng nhạc và xóa hàng đợi.")

@bot.command()
async def out(ctx):
    if ctx.message.author.id == bot.user.id:
        return
    voice_client = ctx.voice_client
    if voice_client:
        music_queue[ctx.guild.id] = [] 
        await voice_client.disconnect()
        await ctx.send("Bot đã out voice channel")

# -----------------------
# Lệnh !text để gửi tin nhắn dưới dạng Embed
@bot.command()
async def text(ctx, *, content: str):
    if ctx.message.author.id == bot.user.id:
        return
    await ctx.message.delete()
    
    embed = discord.Embed(
        description=content, 
        color=discord.Color.from_rgb(46, 204, 113) 
    )
    embed.set_footer(text=f"Sent by {ctx.author.display_name}", icon_url=ctx.author.avatar.url)
    
    await ctx.send(embed=embed)
# -----------------------

# -----------------------
# !post kèm attachment + nút Rent + Done
@bot.command()
async def post(ctx, gender: str, *, caption: str = ""):
    if ctx.message.author.id == bot.user.id:
        return
    if len(ctx.message.attachments) == 0:
        await ctx.send("❌ Bạn chưa gửi ảnh kèm message!")
        return

    attachment = ctx.message.attachments[0]
    image_file = await attachment.to_file()

    if gender.lower() == "female":
        channel = bot.get_channel(IMAGE_CHANNEL_FEMALE)
    else:
        channel = bot.get_channel(IMAGE_CHANNEL_MALE)

    if not channel:
        await ctx.send("Lỗi: Không tìm thấy channel ảnh.")
        return

    embed = Embed(description=caption)
    embed.set_image(url=f"attachment://{attachment.filename}")
    
    class RentButton(ui.View):
        # ... (Phần code RentButton giữ nguyên) ...
        def __init__(self):
            super().__init__(timeout=None)

        @ui.button(label="Rent", style=discord.ButtonStyle.primary)
        async def rent(self, interaction: discord.Interaction, button: discord.ui.Button):
            guild = interaction.guild
            member = interaction.user
            
            if member.bot:
                await interaction.response.send_message("Bot không thể tương tác với nút này.", ephemeral=True)
                return

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                member: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.get_member(ADMIN_ID): discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            }

            temp_channel = await guild.create_text_channel(
                name="temp-rent-" + datetime.now().strftime("%H%M%S"),
                overwrites=overwrites
            )

            await temp_channel.send(f"Channel đã tạo cho {member.mention} . Bạn thuê Player nào ạ? Bạn đợi xíu bên mình phản hồi lại nhaaa.")

            class DoneButton(ui.View):
                def __init__(self):
                    super().__init__(timeout=None)

                @ui.button(label="Done", style=discord.ButtonStyle.danger)
                async def done(self, interaction2: discord.Interaction, button2: discord.ui.Button):
                    await temp_channel.delete()
                    await interaction2.response.send_message("✅ Channel đã xóa.", ephemeral=True)

            await temp_channel.send("Nhấn Done khi hoàn tất.", view=DoneButton())
            await interaction.response.send_message(f"✅ Đã tạo channel : {temp_channel.mention}", ephemeral=True)

    await channel.send(embed=embed, file=image_file) # Gửi Embed và File trước
    await channel.send("Nhấn Rent để trao đổi nha khác iu ơi ⋆𐙚 ̊.", view=RentButton())
    await ctx.send("✅ Đã post bài thành công.")

# -----------------------
# Timer !time 
@bot.command()
async def time(ctx, *, t: str):
    if ctx.message.author.id == bot.user.id:
        return

    t = t.lower().replace(" ", "")
    hours, minutes = 0, 0

    h_match = re.search(r'(\d+)h', t)
    m_match = re.search(r'(\d+)m', t)

    if h_match:
        hours = int(h_match.group(1))
    if m_match:
        minutes = int(m_match.group(1))

    if hours == 0 and minutes == 0:
        await ctx.send("Không nhận diện được thời gian! VD: !time 1h30m, !time 45m")
        return
    
    vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')
    
    start_time_vn = datetime.now(vn_tz)
    end_time_vn = start_time_vn + timedelta(hours=hours, minutes=minutes)
    
    await ctx.send(
        f"⏳ Oki vậy là mình bắt đầu từ **{start_time_vn.strftime('%H:%M:%S')}** (VN time) đến **{end_time_vn.strftime('%H:%M:%S')}** nha khách iu ơi ⋆𐙚 ̊."
    )

    total_seconds = hours * 3600 + minutes * 60
    
    await asyncio.sleep(total_seconds)
    
    final_end_time_vn = datetime.now(vn_tz)

    await ctx.send(f"{ctx.author.mention} ⏰ Thời gian kết thúc: **{final_end_time_vn.strftime('%H:%M:%S')}**! Đã hết giờ.")

# -----------------------
# QR command
@bot.command()
async def qr(ctx):
    if ctx.message.author.id == bot.user.id:
        return
        
    embed = Embed(description="Sau khi thanh toán xong thì gửi bill vào đây nhá. Không ghi NDCK giúp mình nha ୨୧")
    
    qr_path = "qr.png" 
    
    if os.path.exists(qr_path):
        qr_file = File(qr_path, filename="qr.png")
        embed.set_image(url="attachment://qr.png")
        await ctx.send(embed=embed, file=qr_file)
    else:
        await ctx.send("Không tìm thấy ảnh QR. " + embed.description, embed=embed)

# -----------------------
# Khởi chạy bot
if __name__ == '__main__':
    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"Bot gặp lỗi khi chạy: {e}")
        if "Bad Gateway" in str(e) or "HTTP 401" in str(e):
             print("\nLỖI: Hãy kiểm tra lại TOKEN DISCORD_BOT_SECRET đã chính xác chưa.")
