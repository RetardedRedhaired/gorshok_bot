import discord
import youtube_dl
import asyncio
from discord.ext import commands
import logging

bot = commands.Bot(command_prefix='#')
sem = asyncio.Semaphore(1)

logger = logging.getLogger('discord')
logger.setLevel(logging.INFO)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

# Suppress noise about console usage from errors
youtube_dl.utils.bug_reports_message = lambda: ''

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'  # bind to ipv4 since ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)

        self.data = data

        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queue = asyncio.Queue()

    @commands.command()
    async def join(self, ctx, *, channel: discord.VoiceChannel):
        """Joins a voice channel"""

        if ctx.voice_client is not None:
            return await ctx.voice_client.move_to(channel)

        await channel.connect()

    async def stream(self, ctx):
        """Streams from a url"""

        print("STREAM STARTED at ", ctx.voice_client)
        while True:
            url = await self.queue.get()
            player = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True)
            await ctx.send('Now playing: {}'.format(player.title))
            ctx.voice_client.play(player, after=lambda e: print('Player error: %s' % e) if e else None)
            await asyncio.sleep(player.data["duration"])

    @commands.command()
    async def play(self, ctx, *, url):
        """Places song in the queue and activates player if it not activated yet."""

        print("IN QUEUE RIGHT NOW: ", self.queue.qsize())
        print("VOICE CLIENT: ", ctx.voice_client)
        print("GUILD: ", type(ctx.guild.channels[1].name))
        if ctx.voice_client is not None:
            self.queue.put_nowait(url)
            print("QUEUED")
            if not ctx.voice_client.is_playing():
                async with sem:
                    await self.stream(ctx)
        else:
            await self.ensure_voice(ctx)
            self.queue.put_nowait(url)
            print("BOT IS NOT CONNECTED TO VOICE CHANNEL")
            async with sem:
                await self.stream(ctx)

    @commands.command()
    async def p(self, ctx, *, url):
        """Same as play"""

        await self.play(ctx, url=url)

    @commands.command()
    async def shadow(self, ctx, *, inp):
        """Позволяет воспроизводить аудио в канал, если автор не подключен к исходному каналу"""

        flag = True
        inp = inp.split('_')
        try:
            channel_name, url = inp[0], inp[1]
            if len(url) == 0:
                raise IndexError
        except IndexError:
            await ctx.send("Неправильный формат, надо: #shadow имяголосовогоканала_url")
            return
        print(url, len(url))
        for v_channel in ctx.guild.voice_channels:
            if v_channel.name == channel_name:
                flag = False
                break
        if flag is False:
            await self.join(ctx, channel=v_channel)
            await self.play(ctx, url=url)
        else:
            await ctx.send(f"There is no voice channel with name {channel_name}")

    @commands.command()
    async def volume(self, ctx, volume: int):
        """Changes the player's volume"""

        if ctx.voice_client is None:
            return await ctx.send("Not connected to a voice channel.")

        ctx.voice_client.source.volume = volume / 100
        await ctx.send("Changed volume to {}%".format(volume))

    @commands.command()
    async def pause(self, ctx):
        """Pause translating"""

        await ctx.voice_client.pause()

    @commands.command()
    async def resume(self, ctx):
        """Resume translating"""

        await ctx.voice_client.resume()

    @commands.command()
    async def stop(self, ctx):
        """Stops translating"""

        await ctx.voice_client.stop()

    @commands.command()
    async def leave(self, ctx):
        """Stops and disconnects the bot from voice"""

        await ctx.voice_client.disconnect()

    async def ensure_voice(self, ctx):
        if ctx.voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("You are not connected to a voice channel.")
                raise commands.CommandError("Author not connected to a voice channel.")
        elif ctx.voice_client.is_playing():
            ctx.voice_client.stop()


@bot.event
async def on_ready():
    print('Logged in as {0} ({0.id})'.format(bot.user))
    print('------')
