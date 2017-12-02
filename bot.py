import arrow
import discord
import requests
import logging
import asyncio
import pymongo
import random

class Bot:

    SESS_KEY = "53616c7465645f5f698119e83582912bf3a97a7dcb22f7589d69223e54d765825bbd106e2e337a3993bd6484f5314a6b"

    REQ_URL = "http://adventofcode.com/2017/leaderboard/private/view/{}.json"

    SECRET = "Mzg1ODg5Mzk1NDU2MjEyOTk1.DQRznQ.2FVLPZF6YhhP6AL8bti6BGFLgHc"

    CHAN_ID = "292494245825347584"

    LEADERBOARD_ID = "55305"

    debug = True

    def __init__(self):
        self.store = {}
        self.client = discord.Client()

        self.client.event(self.on_ready)
        self.client.event(self.on_message)

        self.db = pymongo.MongoClient('mongodb').aoc

    async def on_ready(self):
        logging.info('Logged in as {}'.format(self.client.user.name))
        self.client.loop.create_task(self.fetch_leaderboard())

    async def fetch_leaderboard(self):
        r = requests.get(Bot.REQ_URL.format(Bot.LEADERBOARD_ID),
                         cookies={'session': Bot.SESS_KEY})

        logging.info("Fetched from API: {}".format(r.text))
        await self.update_store(r.json())
        await asyncio.sleep(600)

    async def update_store(self, json):
        try:
            logging.info("attempting to update store")
            logging.info("old store: {}".format(self.db.memberlist.find()))
            lines = []
            for m in json["members"]:
                new = json["members"][m]
                old = self.db.memberlist.find_one({'id': new["id"]})

                if not old:
                    greet = "{} just joined. Welcome!".format(new["name"])
                    lines.append(greet)
                    self.db.memberlist.insert_one(new)
                    logging.info("adding ({}, {}) to store".format(
                                 new["id"], new["name"]))
                else:
                    db_ts = arrow.get(old["last_star_ts"])
                    cur_ts = arrow.get(new["last_star_ts"])

                    if cur_ts > db_ts:
                        finished, started = [], []
                        logging.info("updating store for ({}, {})",format(new["id"], new["name"]))
                        self.db.memberlist_replace_one({"_id": old["_id"]}, new)
                        for day in new["completion_day_level"]:
                            if not old or day not in old["completion_day_level"]:
                                t = new["completion_day_level"][day]
                                if "1" in t and "2" in t:
                                    finished.append(day)
                                else:
                                    started.append(day)

                        started.sort()
                        finished.sort()

                        s = "{} just completed **Day {}**"
                        s = s.format(new["name"], Bot.pretty_join(finished))

                        if started:
                            s += " and started on **Day {}**".format(Bot.pretty_join(started))

                        if len(finished) + len(started) >= 2:
                            s += ". {}!".format(random.choice(["Nice", "Wew", "Whoa", "( ͡° ͜ʖ ͡°)"]))
                        else:
                            s += "."
                       
                        lines.append(s)
            
            if lines:
                await self.client.send_message(self.client.get_channel(Bot.CHAN_ID),
                                               "\n".join(lines))

            logging.info("Done updating store")
        except KeyError as e:
            logging.warn("Malformed update_store attempt")
            logging.debug("Malformed JSON: {}".format(new))

    def generate_leaderboard(self):
        ret = []
        for m in self.db.memberlist.find():
            ret.append((m["name"], m["local_score"]))
        ret.sort(key=lambda x: x[1], reverse=True)
        lines = []
        for i, j in enumerate(ret):
            lines.append("{}. {} ({} points)".format(i + 1, j[0], j[1]))
        return "\n".join(lines)

    def pretty_join(list):
        if len(list) <= 1:
            return "".join(list)
        return "{} and {}".format(", ".join(list[:-1]), list[-1])

    async def on_message(self, message):
        if message.content.startswith('%leaderboard'):
            await self.client.send_message(message.channel,
                                           self.generate_leaderboard())
        elif message.content.startswith('%ping'):
            await self.client.send_message(message.channel, "Pong!")
        elif message.content.startswith('%store'):
            await self.client.send_message(message.channel,
                                           self.db.memberlist.find())

    def run(self):
        self.client.run(Bot.SECRET)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    b = Bot()
    b.run()
