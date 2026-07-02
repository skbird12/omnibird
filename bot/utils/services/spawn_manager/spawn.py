from abc import abstractmethod, ABC
import discord
from discord.ext import commands
from collections import Counter
import math
import re
import db
from utils.services.MemoryCache import db_cache
from collections import defaultdict, deque
from utils.services.packs import get_mfws_from_pack
from datetime import datetime, timedelta


def ngram_entropy(text, n=2):
    grams = [
        text[i:i+n]
        for i in range(len(text)-n+1)
    ]

    if not grams:
        return 0.0

    counts = Counter(grams)
    total = len(grams)

    entropy = -sum(
        (c / total) * math.log2(c / total)
        for c in counts.values()
    )

    max_entropy = math.log2(len(counts))

    if max_entropy == 0:
        return 0.0

    return entropy / max_entropy


def human_score(text):
    text = text.lower()

    # 1. N-gram structure
    IDEAL = 0.92
    TOLERANCE = 0.05     # full score within +-0.05
    FALLOFF = 0.05  # distance after tolerance to reach 0

    entropy = ngram_entropy(text)
    delta = abs(entropy - IDEAL)

    if delta <= TOLERANCE:
        ngram_score = 1.0
    else:
        ngram_score = max(
            0,
            1 - (delta - TOLERANCE) / FALLOFF
        )
    # 2. Alphabetic ratio
    letters = sum(c.isalpha() or c == " " for c in text)
    char_score = letters / len(text)
    # 3. Repetition penalty
    chars = Counter(text)
    most_common_ratio = (
        chars.most_common(1)[0][1] / len(text)
    )
    repetition_score = 1 - most_common_ratio
    # 4. Word shape score
    words = re.findall(r"[a-z]+", text)
    if words:
        avg_word_length = sum(map(len, words)) / len(words)
        word_length_score = 1 - abs(avg_word_length - 5) / 5
        word_length_score = max(0, word_length_score)
    else:
        word_length_score = 0

    score = (
        0.25 * ngram_score +
        0.05 * char_score +
        0.2 * repetition_score +
        0.5 * word_length_score
    )

    return max(0, min(1, score))

class MfwSpawnManager():
    def __init__(self, bot):
        self.bot: commands.Bot = bot
        self.guild_accumulated_scores = defaultdict(float)
        self.user_messages = defaultdict(lambda: defaultdict(deque))
    
    async def handle_message(self, message: discord.Message):
        if message.author.bot or message.guild is None: return
        text_len = len(message.content)
        if text_len <= 3: return

        score = 1.0
        if text_len <= 5:
            score *= 0.5
        score *= human_score(message.content)
        print(f"Score: {score}")
        score *= self.spam_multiplier(message.guild.id, message.author.id)
        threshold = db_cache.get(f"threshold:{message.guild.id}")
        print(f"Threshold: {threshold}")

        if threshold is None:
            threshold = await self.calculate_threshold(message.guild.id)
            await db_cache.set(f"threshold:{message.guild.id}", threshold, ttl=60*60)
        self.guild_accumulated_scores[message.guild.id] += score
        print(f"Accumulated score: {self.guild_accumulated_scores[message.guild.id]}")
        if self.guild_accumulated_scores[message.guild.id] > threshold:
            self.guild_accumulated_scores[message.guild.id] = 0
            await self.generate_spawn(1529570316437684444)
        
    def spam_multiplier(self, guild_id: int, user_id: int) -> float:
        now = datetime.now()
        messages = self.user_messages[guild_id][user_id]
        while messages and messages[0] < now - timedelta(minutes=1):
            messages.popleft()
        messages.append(now)
        count = len(messages)
        if count >= 30:
            return 0.0
        if count >= 15:
            return 0.25
        if count >= 8:
            return 0.5
        return 1.0

    async def get_server_activity(self, guild_id: int):
        row = await db.fetch_one(
            """
                SELECT
                    COUNT(*),
                    COUNT(DISTINCT user_id)
                FROM spawn_messages
                WHERE guild_id = %s
                AND created_at >= NOW() - INTERVAL 1 HOUR
                """,
                (guild_id,), cache=True, ttl=60*60)
        if row is None: return 0, 0
        messages_per_hour, active_users = row
        return messages_per_hour, active_users
        
    async def calculate_threshold(self, guild_id: int) -> float:
        threshold = 50
        guild = self.bot.get_guild(guild_id)
        if guild is None: return threshold
        num_of_members = guild.approximate_member_count or 1
        threshold += math.log10(num_of_members) * 25

        messages_per_hour, active_users = await self.get_server_activity(guild_id)

        activity_bonus = min(messages_per_hour / 20, 30)
        threshold -= activity_bonus

        user_bonus = min(active_users / 10, 20)
        threshold -= user_bonus
        threshold = max(40.0, min(threshold, 200.0))
        return threshold
    
    async def generate_spawn(self, guild_id: int):
        # Rare pack
        mfw = await get_mfws_from_pack(2)
        print(mfw)
        
