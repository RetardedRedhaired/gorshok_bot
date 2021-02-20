from discord.ext import tasks, commands
import asyncio


class MyCog(commands.Cog):
    def __init__(self, bot):
        self.index = 0
        self.bot = bot
        self.checker.start()

    def cog_unload(self):
        self.checker.cancel()

    @tasks.loop(seconds=300.0)
    async def checker(self):
        vc = self.bot.voice_clients
        if len(vc) != 0:
            for client in vc:
                print(client.channel.members)
                if len(client.channel.members) == 1:
                    await client.disconnect()
