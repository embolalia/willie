# coding=utf-8
"""
uptime.py - Uptime module
Copyright 2014, Fabian Neundorf
Licensed under the Eiffel Forum License 2.

https://sopel.chat
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from sopel.module import commands
import datetime


def setup(bot):
    if "uptime" not in bot.memory:
        bot.memory["uptime"] = datetime.datetime.utcnow()


@commands('uptime')
def uptime(bot, trigger):
    """.uptime - Returns the uptime of Sopel."""
    delta = datetime.timedelta(seconds=round((datetime.datetime.utcnow() -
                                              bot.memory["uptime"])
                                             .total_seconds()))
    bot.say("I've been sitting here for {} and I keep "
            "going!".format(delta))
