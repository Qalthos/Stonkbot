import logging
import os

from stonkbot.discord_bot import bot


if __name__ == "__main__":
    logger = logging.getLogger("stonkbot")
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(filename="disco_bot.log", mode="w")
    logger.addHandler(handler)
    bot.run(os.environ.get("DISCORD_TOKEN"))
