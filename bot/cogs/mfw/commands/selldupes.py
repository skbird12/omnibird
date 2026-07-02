import db
import utils.services.dbutils as dbutils
import utils.services.discord.discordutils as discordutils
from languages import l

async def selldupes(self, ctx, *values: str):
        # Having mfws of rarity -2 increases their price by 20% (proportional)
        PRICE_BUFF = 1.0
        async with db.transaction() as cur:
            before_coins = (await dbutils.get_user_info(ctx.author.id, cur=cur, for_update=True))["coins"]
            mfws_to_exclude = []
            if values:
                try:
                    mfws_to_exclude, _, _, _ = await discordutils.parse_and_validate_mfws(self.bot, ctx.author, *values)
                    mfws_to_exclude = [int(mfw[0]) for mfw in mfws_to_exclude]
                except ValueError as e:
                    await ctx.send(e)
                    return
            if mfws_to_exclude:
                placeholders = ", ".join(["%s"] * len(mfws_to_exclude))
                inner_in = f"AND i.mfw_id NOT IN ({placeholders})"
            else:
                inner_in = ""
                placeholders = ""

            await cur.execute("""SELECT
            COUNT(DISTINCT i.mfw_id) AS owned_count,
            (
                SELECT COUNT(m.id) FROM mfws m
                WHERE m.rarity_id = -1
            ) AS total_count
            FROM inventory i
            INNER JOIN mfws m ON i.mfw_id = m.id
            WHERE i.user_id = %s AND m.rarity_id = -1""", (ctx.author.id,))
            row = await cur.fetchone()
            owned_count, total_count = row
            if total_count > 0:
                owned_ratio = owned_count/total_count
                PRICE_BUFF += (0.2 * owned_ratio)

            update_sql = f"""
            UPDATE users u
            JOIN (
                SELECT i.user_id, COALESCE(SUM((i.quantity - 1) * ROUND((r.price * %s) / 2)), 0) AS earned
                FROM inventory i
                JOIN mfws m ON i.mfw_id = m.id
                JOIN rarities r ON r.id = m.rarity_id
                WHERE i.quantity > 1 AND i.user_id = %s
                {inner_in}
                GROUP BY i.user_id
            ) sub ON u.id = sub.user_id
            SET u.coins = u.coins + sub.earned
            WHERE u.id = %s
            """
            # Parameter order: inner i.user_id, then excluded ids (if any), then outer u.id
            params = [PRICE_BUFF] + [ctx.author.id] + mfws_to_exclude + [ctx.author.id]

            await cur.execute(update_sql, tuple(params))

            if mfws_to_exclude:
                delete_in = f"AND mfw_id NOT IN ({placeholders})"
                params2 = [ctx.author.id] + mfws_to_exclude
            else:
                delete_in = ""
                params2 = [ctx.author.id]

            delete_sql = f"""
            UPDATE inventory
            SET quantity = 1
            WHERE user_id = %s
            {delete_in}
            """
            await cur.execute(delete_sql, tuple(params2))

            new = await dbutils.get_user_info(ctx.author.id, cur=cur)
            new_coins = new["coins"] if new and new.get("coins") is not None else 0
            earned = int(new_coins) - int(before_coins)

            if earned != 0:
                await ctx.send(l.text("selldupes", "success", new_coins=new_coins, earned=earned))
            else:
                await ctx.send(l.text("selldupes", "no_dupes"))