import discord
import youtube_dl
import asyncio
from discord.ext import commands, tasks
import logging
from random import choice

bot = commands.Bot(command_prefix='#')
sem = asyncio.Semaphore(1)
music_emotes = [':saxophone:', ':trumpet:', ':microphone:', ':headphones:', ':musical_score:', ':drum:', ':musical_keyboard:', ':long_drum:', ':guitar:', ':banjo:', ':violin:', ':accordion:']

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
    'noplaylist': False,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'  # bind to ipv4 since ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
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
        tracks = []

        if 'entries' in data:
            for entry in data['entries']:
                data = entry
                filename = data['url'] if stream else ytdl.prepare_filename(data)
                tracks.append(cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data))
        else:
            filename = data['url'] if stream else ytdl.prepare_filename(data)
            tracks.append(cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data))
        return tracks


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queue = asyncio.Queue()
        self.ctx = None
        self.url = None
        self.repeat = False
        self.gachi_list = None

    def clear_queue(self):
        """Метод для очистки очереди воспроизведения"""

        while not self.queue.empty():
            try:
                tmp = self.queue.get_nowait()
            except asyncio.QueueEmpty:
                pass

    def next_song(self, error):
        """Метод-корутина, который можно засунуть в after при создании плеера"""
        coro = self.skip()
        loop = self.bot.loop
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        try:
            fut.result()
        except Exception:
            print(error)

    @commands.command()
    async def gachi(self, ctx):
        """Врубает рандомный гачи микс"""

        if self.gachi_list is None:
            with open("gachi.txt", "r") as gachi_list:
                self.gachi_list = gachi_list.read().rstrip("\n").split("\n")
        await self.play(ctx, url=choice(self.gachi_list))


    @commands.command()
    async def repeat(self, ctx):
        """Включает и выключает повтор текущего трека"""

        if self.repeat is True:
            self.repeat = False
            await ctx.send(":repeat_one: **Выключен повтор**")
        else:
            self.repeat = True
            await ctx.send(":repeat_one: **Включен повтор**")

    @commands.command()
    async def skip(self, *args):
        """"Отключает текущий трек и включает следующий."""

        if self.ctx.voice_client.is_playing():
            await self.ctx.voice_client.stop()
        if self.repeat is True:
            player = await YTDLSource.from_url(self.url, loop=self.bot.loop, stream=True)
            self.ctx.voice_client.play(player, after=self.next_song)
        else:
            await self.stream(self.ctx)

    @commands.command()
    async def join(self, ctx, *, channel: discord.VoiceChannel):
        """Joins a voice channel"""

        if ctx.voice_client is not None:
            return await ctx.voice_client.move_to(channel)

        await channel.connect()

    async def stream(self, ctx):
        """Streams from a url"""

        player = await self.queue.get()
        ctx.voice_client.play(player, after=self.next_song)
        await ctx.channel.send(f'{choice(music_emotes)} **Cейчас играет** `{player.title}`')

    @commands.command()
    async def play(self, ctx, *, url):
        """Кладет трек в очередь и запускает воспроизведение, если это первый трек"""

        self.ctx = ctx
        if ctx.voice_client is None:
            async with sem:
                await self.ensure_voice(ctx)
        self.url = url
        tracks = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True)
        for player in tracks:
            if len(tracks) == 1:
                if not self.queue.empty() or ctx.voice_client.is_playing():
                    await ctx.channel.send(f':fast_forward: **Трек** `{player.title}` **добавлен в очередь '
                                           f'воспроизведения**')
            await self.queue.put(player)
        if not ctx.voice_client.is_playing():
            await self.stream(ctx)
        if len(tracks) > 1:
            await ctx.channel.send(f':fast_forward: **В очередь добавлено** `{len(tracks) - 1}` **трека(-ов)**')

    @commands.command()
    async def p(self, ctx, *, url):
        """То же самое, что и play"""

        await self.play(ctx, url=url)

    @commands.command()
    async def shadow(self, ctx, *, inp):
        """Позволяет воспроизводить аудио в канал, если автор не подключен к исходному каналу"""

        if ctx.voice_client.is_playing():
            ctx.channel.send("Бот сейчас занят")
        else:
            flag = True
            inp = inp.split('_')
            try:
                channel_name, url = inp[0], inp[1]
                if len(url) == 0:
                    raise IndexError
            except IndexError:
                await ctx.channel.send("Неправильный формат, надо: #shadow имяголосовогоканала_url")
                return
            for v_channel in ctx.guild.voice_channels:
                if v_channel.name == channel_name:
                    flag = False
                    break
            if flag is False:
                await self.join(ctx, channel=v_channel)
                await self.play(ctx, url=url)
            else:
                await ctx.channel.send(f"Канал с именем {channel_name} не найден")

    @commands.command()
    async def volume(self, ctx, volume: int):
        """Changes the player's volume"""

        if ctx.voice_client is None:
            return await ctx.channel.send("**Вы не присоеденены к голосовому каналу**")

        ctx.voice_client.source.volume = volume / 100
        await ctx.channel.send(f"**Громкость изменена на** `{volume}`")

    @commands.command()
    async def pause(self, ctx):
        """Pause translating"""

        ctx.voice_client.pause()
        await ctx.channel.send("**Воспроизведение приостановлено**")

    @commands.command()
    async def resume(self, ctx):
        """Resume translating"""

        ctx.voice_client.resume()
        await ctx.channel.send("**Продолжаю воспроизведение**")

    @commands.command()
    async def stop(self, ctx):
        """Stops translating"""

        self.clear_queue()
        ctx.voice_client.stop()
        await ctx.channel.send(":stop_button: **Воспроизведение остановлено**")

    @commands.command()
    async def leave(self, ctx):
        """Stops and disconnects the bot from voice"""

        self.clear_queue()
        await ctx.voice_client.disconnect()

    async def ensure_voice(self, ctx):
        if ctx.voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.channel.send("You are not connected to a voice channel.")
                raise commands.CommandError("Author not connected to a voice channel.")
        elif ctx.voice_client.is_playing():
            ctx.voice_client.stop()


@bot.event
async def on_ready():
    print('Logged in as {0} ({0.id})'.format(bot.user))
    print('------')
