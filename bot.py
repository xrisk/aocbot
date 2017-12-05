import arrow
import discord
import requests
import logging
import asyncio
import pymongo
import random
import config
import bs4


class Bot:

    SESS_KEY = config.SESS_KEY
    SECRET = config.SECRET
    CHAN_ID = config.CHAN_ID
    LEADERBOARD_ID = config.LEADERBOARD_ID
    REQ_URL = "http://adventofcode.com/2017/leaderboard/private/view/{}.json"

    def __init__(self):
        self.client = discord.Client()
        self.client.event(self.on_ready)
        self.client.event(self.on_message)
        self.db = pymongo.MongoClient('mongodb').aoc
        self.last_date = None

    async def on_ready(self):
        logging.info('Logged in as {}'.format(self.client.user.name))
        self.channel = self.client.get_channel(Bot.CHAN_ID)
        self.client.loop.create_task(self.fetch_leaderboard())

    async def watch_for_start(self):
        logging.info("now watching for day start events")
        while True:
            last_date = self.last_date
            if not last_date:
                today = arrow.utcnow()
                last_date = today.day
                if today.hour < 5:
                    last_date = today - 1
            logging.info("found last watched date as {}".format(last_date))
            if last_date == 25:
                return # AOC is over ^_^

            next_start = arrow.Arrow(last_date.year, last_date.month, last_date + 1, hour=5)
            logging.info("next start time computed as {}".format(next_start))

            while True:
                cur_date = arrow.utcnow()
                time_del = (next_start - cur_date).seconds
                logging.info("time till next day start is {}".format(time_del))
                if time_del < 0:
                    self.client.send_message(self.channel, "Day {} has started!".format(next_start.day))
                    logging.info("day {} has started!".format(next_start.day))
                    self.last_date = next_start.day
                    await self.watch_leaderboard(self.last_date)
                else:
                    logging.info("sleeping till next day start")
                    if time_del <= 10:
                        asyncio.sleep(1)
                    else:
                        asyncio.sleep(time_del - 10)



    async def watch_leaderboard(self, day):
        while True:
            r = requests.get('http://adventofcode.com/2017/leaderboard/day/{}'.format(day))
            soup = bs4.BeautifulSoup(r.text)
            p = soup.find_all('p')
            cnt = 0
            for tag in p[2].next_siblings:
                if tag.name == "p":
                    break
                elif tag.name == "div":
                    cnt += 1

            if cnt >= 100:
                await self.client.send_message("Top 100 for Day {} filled. Stopping live updates.".format(day))
                break
            else:
                await self.client.send_message("Day {}: {} users finished.".format(day, cnt))
                asyncio.sleep(30)




    async def fetch_leaderboard(self, onetime=False):
        while not self.client.is_closed:
            r = requests.get(Bot.REQ_URL.format(Bot.LEADERBOARD_ID),
                             cookies={'session': Bot.SESS_KEY})

            if r.status_code != requests.codes.ok:
                err = "API fetch failed - bad status code in HTTP response {}"
                err = err.format(r.status_code)
                logging.critical(err)
                self.client.send_message(self.channel, err)
            else:
                try:
                    resp_as_json = r.json()
                    logging.info("API fetch as JSON successful")
                except ValueError:
                    err = "API fetch failed - Invalid JSON response"
                    logging.critical(err)
                    self.client.send_message(self.channel, err)

                await self.update_store(resp_as_json)

            if onetime:
                break
            else:
                await asyncio.sleep(600)

    async def update_store(self, json):
        try:
            logging.info("attempting to update store")
            joins = []
            lines = []
            for m in json["members"]:
                new = json["members"][m]
                old = self.db.memberlist.find_one({'id': new["id"]})

                if not old:
                    greet = "{} just joined. Welcome!".format(new["name"])
                    joins.append(greet)
                    self.db.memberlist.insert_one(new)
                    logging.info("adding ({}, {}) to store".format(
                                 new["id"], new["name"]))
                else:
                    db_ts = arrow.get(old["last_star_ts"])
                    cur_ts = arrow.get(new["last_star_ts"])

                    if cur_ts > db_ts:
                        finished, started = [], []
                        logging.info("updating store for ({}, {})".format(
                                     new["id"], new["name"]))
                        self.db.memberlist.replace_one({"_id": old["_id"]}, new)
                        for day in new["completion_day_level"]:
                            old_cnt = len(old["completion_day_level"].get(day, {}))
                            new_cnt = len(new["completion_day_level"][day])

                            if new_cnt > old_cnt:
                                if new_cnt == 2 and old_cnt != 2:
                                    finished.append(day)
                                elif new_cnt == 1 and old_cnt == 0:
                                    started.append(day)

                        started.sort()
                        finished.sort()

                        s = "{} just completed **Day {}**"
                        s = s.format(new["name"], Bot.pretty_join(finished))

                        if started:
                            if len(finished) == 0:
                                s = "{} just started on **Day {}**".format(
                                    new["name"], Bot.pretty_join(started))
                            else:
                                s += " and started on **Day {}**".format(
                                     Bot.pretty_join(started))

                        if len(finished) + len(started) >= 2:
                            s += ". {}!".format(random.choice(
                                 ["Nice", "Wew", "Whoa", "( ͡° ͜ʖ ͡°)"]))
                        else:
                            s += "."

                        lines.append(s)

            if joins:
                await self.client.send_message(self.channel, "\n".join(joins))
            if lines:
                await self.client.send_message(self.channel, "\n".join(lines))

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
        elif message.content.startswith('%refresh'):
            logging.info("attempting to manually refresh")
            await self.fetch_leaderboard(onetime=True)

    def run(self):
        self.client.run(Bot.SECRET)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    b = Bot()
    b.run()
