import discord
from discord.ext import commands
import asyncio
import os
from yt_dlp import YoutubeDL
from typing import Optional
import json

# ==========================================
# CẤU HÌNH MUSIC PLAYER
# ==========================================
YTDL_FORMAT_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'default_search': 'ytsearch',
    'quiet': True,
    'no_warnings': True,
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

# ==========================================
# MUSIC QUEUE & PLAYER STATE
# ==========================================
class MusicQueue:
    def __init__(self):
        self.queue = []
        self.current_song = None
        self.is_playing = False
        self.loop_mode = 0  # 0: No loop, 1: Loop queue, 2: Loop one
        self.volume = 0.5

    def add_song(self, song_data):
        self.queue.append(song_data)

    def next_song(self):
        if self.loop_mode == 2 and self.current_song:
            return self.current_song
        
        if self.queue:
            self.current_song = self.queue.pop(0)
            return self.current_song
        return None

    def skip(self):
        self.current_song = None
        return self.next_song()

    def clear_queue(self):
        self.queue = []
        self.current_song = None

    def get_queue_info(self):
        return {
            "current": self.current_song,
            "queue": self.queue,
            "queue_length": len(self.queue),
            "loop_mode": self.loop_mode,
            "volume": self.volume,
            "is_playing": self.is_playing
        }

# ==========================================
# YTDL SOURCE (HỖ TRỢ YOUTUBE & SOUNDCLOUD)
# ==========================================
class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title', 'Unknown')
        self.url = data.get('webpage_url', '')
        self.duration = data.get('duration', 0)
        self.uploader = data.get('uploader', 'Unknown')
        self.thumbnail = data.get('thumbnail', '')

    @classmethod
    async def from_url(cls, url, *, loop=None, volume=0.5):
        loop = loop or asyncio.get_event_loop()
        ytdl = YoutubeDL(YTDL_FORMAT_OPTIONS)
        
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
        except Exception as e:
            return None

        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url']
        return cls(
            discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS),
            data=data,
            volume=volume
        )

    def __str__(self):
        return f"**{self.title}** - {self.uploader}"

# ==========================================
# MUSIC PLAYER COG
# ==========================================
class MusicPlayer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.music_queues = {}  # guild_id -> MusicQueue

    def get_queue(self, guild_id):
        if guild_id not in self.music_queues:
            self.music_queues[guild_id] = MusicQueue()
        return self.music_queues[guild_id]

    async def play_next(self, ctx):
        queue = self.get_queue(ctx.guild.id)
        voice_client = ctx.guild.voice_client

        if not voice_client or not voice_client.is_connected():
            queue.is_playing = False
            return

        song = queue.next_song()
        if not song:
            queue.is_playing = False
            embed = discord.Embed(
                title="🎵 Hàng chờ Trống",
                description="Tất cả bài hát đã phát xong!",
                color=discord.Color.from_rgb(120, 198, 122)
            )
            await ctx.send(embed=embed)
            return

        try:
            source = await YTDLSource.from_url(song['url'], volume=queue.volume)
            if not source:
                await ctx.send(f"❌ Không thể phát: {song['title']}")
                await self.play_next(ctx)
                return

            queue.is_playing = True

            def after_playing(error):
                if error:
                    print(f"Lỗi phát nhạc: {error}")
                asyncio.run_coroutine_threadsafe(self.play_next(ctx), self.bot.loop)

            voice_client.play(source, after=after_playing)

            embed = discord.Embed(
                title="🎵 Đang Phát",
                description=f"**{source.title}**\nUploader: {source.uploader}",
                color=discord.Color.from_rgb(120, 198, 122)
            )
            embed.set_thumbnail(url=source.thumbnail)
            embed.add_field(name="Thời lượng", value=f"{source.duration // 60}:{source.duration % 60:02d}", inline=True)
            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(f"❌ Lỗi phát nhạc: {str(e)[:100]}")
            await self.play_next(ctx)

    @commands.command(name="join", aliases=["j"])
    async def join(self, ctx):
        """Lệnh tham gia kênh voice"""
        if not ctx.author.voice:
            await ctx.send("❌ Cậu phải vào kênh voice trước!")
            return

        voice_channel = ctx.author.voice.channel
        
        if ctx.guild.voice_client:
            await ctx.guild.voice_client.move_to(voice_channel)
        else:
            await voice_channel.connect()

        embed = discord.Embed(
            title="💚 Monika Vào Kênh",
            description=f"Tôi đã vào kênh **{voice_channel.name}** rồi!",
            color=discord.Color.from_rgb(120, 198, 122)
        )
        await ctx.send(embed=embed)

    @commands.command(name="play", aliases=["p"])
    async def play(self, ctx, *, query: str):
        """Lệnh phát nhạc từ YouTube hoặc SoundCloud"""
        if not ctx.author.voice:
            await ctx.send("❌ Cậu phải vào kênh voice trước!")
            return

        voice_channel = ctx.author.voice.channel

        if not ctx.guild.voice_client:
            await voice_channel.connect()
        elif ctx.guild.voice_client.channel != voice_channel:
            await ctx.guild.voice_client.move_to(voice_channel)

        status_msg = await ctx.send(f"🔍 *Monika đang tìm kiếm '{query}'...*")

        queue = self.get_queue(ctx.guild.id)
        ytdl = YoutubeDL(YTDL_FORMAT_OPTIONS)

        try:
            data = await asyncio.get_event_loop().run_in_executor(
                None, lambda: ytdl.extract_info(query, download=False)
            )

            if 'entries' in data:
                song_data = data['entries'][0]
            else:
                song_data = data

            song_info = {
                'url': song_data['webpage_url'],
                'title': song_data['title'],
                'uploader': song_data.get('uploader', 'Unknown'),
                'duration': song_data.get('duration', 0),
                'thumbnail': song_data.get('thumbnail', ''),
            }

            queue.add_song(song_info)
            await status_msg.delete()

            if not ctx.guild.voice_client.is_playing() and not queue.is_playing:
                await self.play_next(ctx)
            else:
                embed = discord.Embed(
                    title="✅ Thêm Vào Hàng Chờ",
                    description=f"**{song_info['title']}**",
                    color=discord.Color.from_rgb(120, 198, 122)
                )
                embed.set_thumbnail(url=song_info['thumbnail'])
                embed.add_field(name="Vị trí trong hàng", value=f"{len(queue.queue)}", inline=True)
                await ctx.send(embed=embed)

        except Exception as e:
            await status_msg.delete()
            await ctx.send(f"❌ Lỗi tìm kiếm: {str(e)[:100]}")

    @commands.command(name="skip", aliases=["s", "next"])
    async def skip(self, ctx):
        """Bỏ qua bài hát hiện tại"""
        voice_client = ctx.guild.voice_client
        if not voice_client or not voice_client.is_playing():
            await ctx.send("❌ Hiện tại không có bài hát nào đang phát!")
            return

        voice_client.stop()
        await ctx.send("⏭️ **Đã bỏ qua bài hát!**")

    @commands.command(name="stop", aliases=["leave", "disconnect", "dc"])
    async def stop(self, ctx):
        """Dừng phát nhạc và thoát kênh voice"""
        voice_client = ctx.guild.voice_client
        if not voice_client:
            await ctx.send("❌ Tôi không ở trong kênh voice!")
            return

        queue = self.get_queue(ctx.guild.id)
        queue.clear_queue()
        
        await voice_client.disconnect()
        await ctx.send("🛑 **Đã dừng phát nhạc và rời kênh!**")

    @commands.command(name="pause", aliases=["pa"])
    async def pause(self, ctx):
        """Tạm dừng bài hát"""
        voice_client = ctx.guild.voice_client
        if not voice_client or not voice_client.is_playing():
            await ctx.send("❌ Hiện tại không có bài hát nào đang phát!")
            return

        voice_client.pause()
        await ctx.send("⏸️ **Đã tạm dừng!**")

    @commands.command(name="resume", aliases=["re"])
    async def resume(self, ctx):
        """Tiếp tục phát nhạc"""
        voice_client = ctx.guild.voice_client
        if not voice_client:
            await ctx.send("❌ Tôi không ở trong kênh voice!")
            return

        if voice_client.is_paused():
            voice_client.resume()
            await ctx.send("▶️ **Đã tiếp tục phát!**")
        else:
            await ctx.send("❌ Bài hát không bị tạm dừng!")

    @commands.command(name="volume", aliases=["vol", "v"])
    async def volume(self, ctx, volume: int = None):
        """Điều chỉnh âm lượng (0-100)"""
        voice_client = ctx.guild.voice_client
        if not voice_client:
            await ctx.send("❌ Tôi không ở trong kênh voice!")
            return

        if volume is None:
            queue = self.get_queue(ctx.guild.id)
            await ctx.send(f"🔊 Âm lượng hiện tại: **{int(queue.volume * 100)}%**")
            return

        if not 0 <= volume <= 100:
            await ctx.send("❌ Âm lượng phải từ 0 đến 100!")
            return

        if voice_client.source:
            voice_client.source.volume = volume / 100
        
        queue = self.get_queue(ctx.guild.id)
        queue.volume = volume / 100
        await ctx.send(f"🔊 **Âm lượng được đặt thành {volume}%**")

    @commands.command(name="queue", aliases=["q"])
    async def queue(self, ctx):
        """Hiển thị hàng chờ phát nhạc"""
        queue = self.get_queue(ctx.guild.id)
        voice_client = ctx.guild.voice_client

        embed = discord.Embed(
            title="🎵 Hàng Chờ Phát Nhạc",
            color=discord.Color.from_rgb(120, 198, 122)
        )

        if voice_client and voice_client.is_playing():
            embed.add_field(
                name="Đang Phát",
                value=f"🎧 **{queue.current_song['title'] if queue.current_song else 'Không có'}**",
                inline=False
            )

        if queue.queue:
            queue_text = ""
            for i, song in enumerate(queue.queue[:10], 1):
                queue_text += f"{i}. **{song['title']}** - {song['uploader']}\n"
            
            if len(queue.queue) > 10:
                queue_text += f"\n*...và {len(queue.queue) - 10} bài hát khác*"
            
            embed.add_field(
                name=f"Hàng Chờ ({len(queue.queue)} bài)",
                value=queue_text,
                inline=False
            )
        else:
            embed.add_field(name="Hàng Chờ", value="Trống", inline=False)

        embed.set_footer(text=f"Âm lượng: {int(queue.volume * 100)}% | Loop: {['Tắt', 'Tất cả', 'Một'][queue.loop_mode]}")
        await ctx.send(embed=embed)

    @commands.command(name="loop", aliases=["repeat"])
    async def loop(self, ctx, mode: int = None):
        """Chế độ lặp (0: Tắt, 1: Lặp hàng chờ, 2: Lặp một bài)"""
        queue = self.get_queue(ctx.guild.id)

        if mode is None:
            queue.loop_mode = (queue.loop_mode + 1) % 3
        elif 0 <= mode <= 2:
            queue.loop_mode = mode
        else:
            await ctx.send("❌ Chế độ lặp phải là 0, 1, hoặc 2!")
            return

        loop_names = ["🔓 Tắt lặp", "🔄 Lặp hàng chờ", "🔁 Lặp một bài"]
        await ctx.send(f"**{loop_names[queue.loop_mode]}**")

    @commands.command(name="nowplaying", aliases=["np"])
    async def nowplaying(self, ctx):
        """Hiển thị bài hát đang phát"""
        voice_client = ctx.guild.voice_client
        queue = self.get_queue(ctx.guild.id)

        if not voice_client or not voice_client.is_playing() or not queue.current_song:
            await ctx.send("❌ Hiện tại không có bài hát nào đang phát!")
            return

        song = queue.current_song
        embed = discord.Embed(
            title="🎵 Đang Phát",
            description=f"**{song['title']}**",
            color=discord.Color.from_rgb(120, 198, 122)
        )
        embed.add_field(name="Uploader", value=song['uploader'], inline=False)
        embed.add_field(name="Thời lượng", value=f"{song['duration'] // 60}:{song['duration'] % 60:02d}", inline=True)
        embed.set_thumbnail(url=song['thumbnail'])
        await ctx.send(embed=embed)

    @commands.command(name="clearqueue", aliases=["cq"])
    async def clearqueue(self, ctx):
        """Xóa toàn bộ hàng chờ"""
        queue = self.get_queue(ctx.guild.id)
        count = len(queue.queue)
        queue.queue = []
        await ctx.send(f"🗑️ **Đã xóa {count} bài hát khỏi hàng chờ!**")

# ==========================================
# SETUP COG
# ==========================================
async def setup(bot):
    await bot.add_cog(MusicPlayer(bot))
