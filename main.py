import discord
from discord.ext import commands, tasks
from discord import Embed, FFmpegPCMAudio, ui, File
from flask import Flask
from threading import Thread
import asyncio
from datetime import datetime, timedelta
import re
import os
import yt_dlp
import requests
import pytz

# -----------------------
# Flask server để ping 24/7
app = Flask('')

@app.route('/')
def home():
    return "Bot is running"

def run():
    # Sử dụng port từ biến môi trường nếu có
    port = int(os.environ.get("PORT", 8080))
    # Sử dụng debug=False cho môi trường production
    app.run(host="0.0.0.0", port=port, debug=False) 

def keep_alive():
    t = Thread(target=run)
    t.start()

# -----------------------
# Khai báo Intents
intents = discord.Intents.default()
intents.message_content = True  # Cho phép bot đọc nội dung tin nhắn cho các lệnh prefix
intents.members = True          # Cần thiết cho các lệnh quản lý thành viên (ban, mute, luongall)
intents.presences = True        # Cần thiết cho một số tính năng phức tạp hơn

bot = commands.Bot(command_prefix='!', intents=intents)

# -----------------------
# CẤU HÌNH CỦA BOT - HÃY THAY THẾ CÁC ID NÀY
# -----------------------
GUILD_ID = 123456789012345678          # Thay bằng guild/server ID của bạn
RENT_CATEGORY_ID = 1448062526599205037  # Category cho kênh rent
LUONG_ROLES = [1432661435397181520, 1432662058322624523] # Role được dùng lệnh !luong
RENT_STAFF_ROLE_ID = 1432670531529867295 # ID role Staff/Mod có quyền xem kênh Rent

# -----------------------
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    # Bắt đầu vòng lặp task nếu có
    # Example: check_reminders.start()
    
# -----------------------
# Lệnh !post (Với nút Rent - tạo kênh riêng và gửi Embed)
class PostView(ui.View):
    def __init__(self, author: discord.Member, post_embed: Embed):
        super().__init__(timeout=None)
        self.author = author
        self.post_embed = post_embed 

    @ui.button(label="Rent", style=discord.ButtonStyle.green)
    async def rent(self, interaction: discord.Interaction, button: ui.Button):
        user = interaction.user
        guild = interaction.guild
        
        # 1. Kiểm tra xem user đã có kênh riêng chưa
        # Lấy Category Rent
        category = guild.get_channel(RENT_CATEGORY_ID)
        if not category:
            return await interaction.response.send_message("Lỗi: Không tìm thấy Category Rent. Vui lòng kiểm tra lại ID.", ephemeral=True)
            
        for channel in category.channels:
            if channel.name.startswith(f"private-{user.name.lower().replace(' ', '-')}"):
                return await interaction.response.send_message(f"Bạn đã có kênh riêng đang hoạt động: {channel.mention}", ephemeral=True)
        
        # 2. Định nghĩa quyền
        rent_staff_role = guild.get_role(RENT_STAFF_ROLE_ID)
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        
        # Thêm quyền cho Role Staff
        if rent_staff_role:
             overwrites[rent_staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
             
        # 3. Tạo kênh chat riêng
        try:
            channel_name = f"private-{user.name.lower().replace(' ', '-')}"
            channel = await guild.create_text_channel(
                name=channel_name, 
                category=category, 
                overwrites=overwrites
            )
            
            # 4. Gửi Embed gốc vào kênh vừa tạo
            private_embed = self.post_embed.copy()
            private_embed.title = f"Bài Đăng Rent (Chuyển tiếp từ {self.post_embed.title})"
            
            staff_mention = f"<@&{RENT_STAFF_ROLE_ID}>" if rent_staff_role else "Staff"
            
            await channel.send(
                f"Chào {user.mention} và {staff_mention}! Đã có khách hàng liên hệ qua bài đăng này. Vui lòng phản hồi sớm.", 
                embed=private_embed
            )
            
            await interaction.response.send_message(f"Đã tạo kênh {channel.mention} và chuyển tiếp bài đăng.", ephemeral=True)
            
        except Exception as e:
            print(f"Lỗi khi tạo kênh riêng: {e}")
            await interaction.response.send_message(f"Lỗi khi tạo kênh riêng: {e}", ephemeral=True)

    @ui.button(label="Done", style=discord.ButtonStyle.red)
    async def done(self, interaction: discord.Interaction, button: ui.Button):
        # Admin hoặc người tạo post mới được xóa
        if not interaction.user.guild_permissions.administrator and interaction.user != self.author:
            await interaction.response.send_message("Bạn không có quyền sử dụng nút này.", ephemeral=True)
            return
            
        await interaction.message.delete()
        await interaction.response.send_message("Post đã hoàn tất/đã xóa.", ephemeral=True)

@bot.command()
async def post(ctx, *, content=None):
    # Xóa lệnh gọi post gốc để tránh clutter
    try: await ctx.message.delete()
    except: pass
    
    if not content:
        await ctx.send("Vui lòng nhập nội dung sau lệnh `!post`", delete_after=10)
        return
    
    lines = content.split("\n")
    title = lines[0].strip()
    description = "\n".join(lines[1:]).strip()
    
    if not description:
        description = "Không có mô tả chi tiết."
        
    embed = Embed(title=title, description=description, color=discord.Color.green())
    
    if ctx.message.attachments and ctx.message.attachments[0].content_type.startswith('image'):
        embed.set_image(url=ctx.message.attachments[0].url)
    
    # Tạo View, truyền Embed vừa tạo vào
    view = PostView(ctx.author, embed) 
    
    # Gửi tin nhắn
    await ctx.send(embed=embed, view=view)


# -----------------------
# Lệnh !io và !dnt (Thông báo nhanh)
@bot.command()
async def io(ctx, *, content):
    try: await ctx.message.delete()
    except: pass
    await ctx.send(f"**Thông báo IO:** {content}")

@bot.command()
async def dnt(ctx, *, content):
    try: await ctx.message.delete()
    except: pass
    await ctx.send(f"**Thông báo DNT:** {content}")

# -----------------------
# Lệnh !luong và !luongall (Quản lý Lương)
@bot.command()
async def luong(ctx, member: discord.Member, amount: int):
    # Kiểm tra quyền
    if not any(role.id in LUONG_ROLES for role in ctx.author.roles):
        return await ctx.send("Bạn không có quyền sử dụng lệnh này.")
        
    await ctx.send(f"{member.mention} đã được nhận lương: **{amount} coins**.")

@bot.command()
async def luongall(ctx, amount: int):
    # Kiểm tra quyền
    if not any(role.id in LUONG_ROLES for role in ctx.author.roles):
        return await ctx.send("Bạn không có quyền sử dụng lệnh này.")
        
    count = 0
    # Gửi thông báo chung, không cần mention từng người
    await ctx.send(f"Đang tiến hành phát lương **{amount} coins** cho tất cả thành viên không phải bot...")
    
    for member in ctx.guild.members:
        if not member.bot:
            # Bạn có thể thêm logic gửi tin nhắn DM cho từng người ở đây nếu cần
            # await member.send(f"Bạn đã nhận được lương: {amount} coins")
            count += 1
            
    await ctx.send(f"✅ Đã thông báo phát lương **{amount} coins** cho **{count}** thành viên.")
    
@bot.command()
async def reset_luong(ctx):
    # Lệnh này chỉ mang tính chất thông báo/ghi nhận, nếu bạn dùng DB thì cần thêm logic DB
    if not any(role.id in LUONG_ROLES for role in ctx.author.roles):
        return await ctx.send("Bạn không có quyền sử dụng lệnh này.")
        
    # Đã sửa lỗi SyntaxError: invalid character '“' ở đây (từ lần báo lỗi trước)
    await ctx.send("✅ Đã reset toàn bộ Lương và PRF (Chỉ mang tính chất ghi nhận).")


# -----------------------
# Lệnh !mute / !ban (Quản trị cơ bản)
@bot.command()
@commands.has_permissions(administrator=True)
async def mute(ctx, member: discord.Member, duration: str = "0s", *, reason: str = "Không rõ lý do"):
    try:
        # Xử lý thời gian (ví dụ: 5m, 1h, 30s)
        duration = duration.lower().replace(" ", "")
        time_regex = re.compile(r"(\d+)([smhd])")
        matches = time_regex.findall(duration)
        
        seconds = 0
        if matches:
            for (time, unit) in matches:
                time = int(time)
                if unit == 's':
                    seconds += time
                elif unit == 'm':
                    seconds += time * 60
                elif unit == 'h':
                    seconds += time * 3600
                elif unit == 'd':
                    seconds += time * 86400
        
        if seconds == 0:
            # Mute vĩnh viễn (max 28 ngày)
            timeout = timedelta(days=28)
            await member.timeout(timeout, reason=f"Mute vĩnh viễn (28d) by {ctx.author.name}: {reason}")
            await ctx.send(f"{member.mention} đã bị mute (28 ngày) với lý do: **{reason}**")
        else:
            timeout = timedelta(seconds=seconds)
            if timeout.days > 28:
                timeout = timedelta(days=28)
            
            await member.timeout(timeout, reason=f"Mute by {ctx.author.name}: {reason}")
            await ctx.send(f"{member.mention} đã bị mute trong {timeout} với lý do: **{reason}**")
            
    except discord.Forbidden:
        await ctx.send("Bot không có đủ quyền để thực hiện lệnh này (có thể role của bot thấp hơn role của người bị mute).")
    except Exception as e:
        await ctx.send(f"Lỗi: {e}")

@bot.command()
@commands.has_permissions(administrator=True)
async def ban(ctx, member: discord.Member, *, reason: str = "Không rõ lý do"):
    try:
        await member.ban(reason=f"{ctx.author.name}: {reason}")
        await ctx.send(f"{member.mention} đã bị ban với lý do: **{reason}**")
    except discord.Forbidden:
        await ctx.send("Bot không có đủ quyền để ban thành viên này.")
    except Exception as e:
        await ctx.send(f"Lỗi: {e}")
        
@bot.command()
@commands.has_permissions(administrator=True)
async def voice(ctx, member: discord.Member):
    # Lệnh voice (ngắt kết nối khỏi kênh thoại)
    if member.voice and member.voice.channel:
        try:
            await member.move_to(None) # Ngắt kết nối
            await ctx.send(f"Đã ngắt kết nối voice của {member.mention}.")
        except discord.Forbidden:
            await ctx.send("Bot không có đủ quyền để ngắt kết nối voice.")
        except Exception as e:
            await ctx.send(f"Lỗi khi ngắt kết nối voice: {e}")
    else:
        await ctx.send(f"{member.mention} hiện không ở trong kênh thoại nào.")


# -----------------------
# Lệnh !code / !codeedit (Post code có thể chỉnh sửa)
class CodeView(ui.View):
    def __init__(self, author, embed_message):
        super().__init__(timeout=None)
        self.author = author
        self.embed_message = embed_message

    @ui.select(
        placeholder="Chọn phần muốn sửa",
        options=[
            discord.SelectOption(label="Nội dung"),
            discord.SelectOption(label="Ảnh")
        ]
    )
    async def select_callback(self, select: ui.Select, interaction: discord.Interaction):
        # Chỉ Admin hoặc người tạo post mới được sửa
        if not interaction.user.guild_permissions.administrator and interaction.user != self.author:
            await interaction.response.send_message("Bạn không có quyền sử dụng menu này.", ephemeral=True)
            return
            
        selected_option = select.values[0]
        
        # Yêu cầu nhập nội dung/ảnh mới
        await interaction.response.send_message(f"Vui lòng nhập **{selected_option}** mới trong chat.", ephemeral=True)

        def check(m: discord.Message):
            return m.author == self.author and m.channel == interaction.channel

        try:
            # Chờ tin nhắn mới trong 60 giây
            msg = await bot.wait_for('message', check=check, timeout=60.0)
            
            embed = self.embed_message.embeds[0]
            if selected_option == "Nội dung":
                embed.description = msg.content
                feedback = "✅ Đã cập nhật nội dung."
            else: # selected_option == "Ảnh"
                if msg.attachments and msg.attachments[0].content_type.startswith('image'):
                    embed.set_image(url=msg.attachments[0].url)
                    feedback = "✅ Đã cập nhật ảnh."
                else:
                    feedback = "❌ Vui lòng đính kèm ảnh hợp lệ để cập nhật."
                    
            await self.embed_message.edit(embed=embed)
            await interaction.followup.send(feedback, ephemeral=True)
            
            # Xóa tin nhắn chứa nội dung sửa
            try: await msg.delete()
            except: pass
            
        except asyncio.TimeoutError:
            await interaction.followup.send("Hết thời gian chỉnh sửa.", ephemeral=True)
        except Exception as e:
             await interaction.followup.send(f"Lỗi khi sửa: {e}", ephemeral=True)

@bot.command()
async def code(ctx, *, content=None):
    # Xóa lệnh gọi code gốc
    try: await ctx.message.delete()
    except: pass
    
    if not content:
        await ctx.send("Vui lòng nhập nội dung sau lệnh `!code`", delete_after=10)
        return
        
    lines = content.split("\n")
    title = lines[0].strip()
    description = "\n".join(lines[1:]).strip()
    
    embed = Embed(title=title, description=description, color=discord.Color.blue())
    
    if ctx.message.attachments and ctx.message.attachments[0].content_type.startswith('image'):
        embed.set_image(url=ctx.message.attachments[0].url)
        
    # Gửi tin nhắn
    msg = await ctx.send(embed=embed)
    
    # Tạo View và gán message_id
    view = CodeView(ctx.author, msg)
    await msg.edit(view=view)

# -----------------------
# Chạy Flask + Bot
if __name__ == '__main__':
    keep_alive()
    # THAY 'YOUR_BOT_TOKEN' BẰNG TOKEN CỦA BẠN
    bot.run('YOUR_BOT_TOKEN')
