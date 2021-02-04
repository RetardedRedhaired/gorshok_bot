from discord.ext import commands
import gorshok_bot_music as mus
import configparser
import argparse


class Config:
    def __init__(self, config):
        self.token = config['Bot']['Token']


def config_parsing():
    parser = argparse.ArgumentParser(description='Server script')
    parser.add_argument('config_path', action="store", help="Absolute or local path to config file")
    args = parser.parse_args()
    config = configparser.ConfigParser()
    config.read(args.config_path)
    return config


config = Config(config_parsing())
bot = commands.Bot(command_prefix='#')
bot.add_cog(mus.Music(bot))
bot.run(config.token)
