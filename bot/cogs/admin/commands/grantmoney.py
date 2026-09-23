import discord
import utils.services.dbutils as dbutils
import db
import utils.services.discord.discordutils as discordutils
from languages import l

async def grantmoney(self, ctx, user: discord.Member|None = None, amount: int|None = None):
    if not isinstance(user, discord.Member):
        await ctx.send(l.text("give", "no_target"))
        return
    
    quantity = await discordutils.sanitize_quantity(ctx, amount, allow_negative=True)
    if (quantity is None): return
    async with db.transaction() as cur:
        info = await dbutils.get_user_info(ctx.author.id, cur=cur, for_update=True) 
        target_info = await dbutils.get_user_info(user.id, cur=cur, for_update=True)
        target_info["coins"] += quantity
        await cur.execute("""
        UPDATE users AS u
        SET u.coins = u.coins + %s
        WHERE u.id = %s;
        """, (quantity, user.id))
        await ctx.send(l.text("give", "success", mention=user.mention, coins=target_info["coins"]), allowed_mentions=discord.AllowedMentions.none())
