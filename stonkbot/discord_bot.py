import logging
import random
from typing import Optional

import discord
from discord.ext import commands
from turnips.ttime import TimePeriod

from stonkbot import db


logger = logging.getLogger("stonkbot")


bot = commands.Bot(command_prefix="!turnip ")


@bot.command()
async def log(ctx: commands.Context, price: int, time: str) -> None:
    logger.info("%s logged %s for %s", ctx.author.name, price, time)
    try:
        time = TimePeriod.normalize(time)
    except KeyError:
        await ctx.send(f"{time} is not a valid time period. Try 'Monday_PM' or 'Friday_AM'.")
        return

    db.log(str(ctx.author.id), price, time)

    if price == random.randint(10, 660):
        await ctx.send("That's Numberwang!")

    reaction_map = {
        69: "👌",
        100: "💯",
        420: "🌿",
    }

    if price in reaction_map:
        await react(ctx.message, reaction_map[price])
    elif price <= 10:
        for reaction in ("😭", "📉", "😰"):
            await react(ctx.message, reaction)
    elif price < 45:
        await react(ctx.message, "😓")
    elif price >= 400:
        for reaction in ("📈", "🥳", "💰"):
            await react(ctx.message, reaction)
    else:
        await react(ctx.message)


@bot.command()
async def source(ctx: commands.Context) -> None:
    await ctx.send("I live at https://github.com/Qalthos/Stonkbot")


@bot.command()
async def stats(ctx: commands.Context, target: Optional[str] = None):
    logger.info("%s asked for stats", ctx.author.name)
    if target is None:
        msg = db.user_stats(str(ctx.author.id))
    elif target == "stonkbot":
        msg = db.meta_stats()
    elif target == "all":
        msg = db.all_stats()
    else:
        logger.warning("Invalid target %s", target)
        return

    await ctx.send(msg)


@bot.command()
async def rename(ctx: commands.Context, *new_name: str) -> None:
    name = " ".join(new_name)
    logger.info("%s said their island was named %s", ctx.author.name, name)

    if db.rename(str(ctx.author.id), name):
        await react(ctx.message)
    else:
        await ctx.send("I don't know about any island of yours.")


async def react(message: discord.Message, reaction: str = "👀") -> None:
    try:
        await message.add_reaction(reaction)
    except discord.Forbidden:
        logger.error("Couldn't react to that message. Darn")
