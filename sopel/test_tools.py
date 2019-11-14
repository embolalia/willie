# coding=utf-8
"""This module has classes and functions that can help in writing tests.

test_tools.py - Sopel misc tools
Copyright 2013, Ari Koivula, <ari@koivu.la>
Licensed under the Eiffel Forum License 2.

https://sopel.chat
"""
from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals
)

import os
import re
import sys
import tempfile

import sopel.config
import sopel.config.core_section
import sopel.tools
import sopel.tools.target
import sopel.trigger
from sopel.bot import SopelWrapper
from sopel.irc.abstract_backends import AbstractIRCBackend

try:
    import ConfigParser
except ImportError:
    import configparser as ConfigParser


__all__ = [
    'MockConfig',
    'MockSopel',
    'MockSopelWrapper',
    'MockIRCBackend',
    'get_example_test',
    'get_disable_setup',
    'insert_into_module',
    'run_example_tests',
]

if sys.version_info.major >= 3:
    basestring = str


def rawlist(*args):
    """Build a list of raw IRC messages from the lines given as ``*args``.

    :return: a list of raw IRC messages as seen by the bot

    This is a helper function to build a list of messages without having to
    care about encoding or this pesky carriage return::

        >>> rawlist('PRIVMSG :Hello!')
        [b'PRIVMSG :Hello!\r\n']

    """
    return ['{0}\r\n'.format(arg).encode('utf-8') for arg in args]


class MockIRCBackend(AbstractIRCBackend):
    def __init__(self, *args, **kwargs):
        super(MockIRCBackend, self).__init__(*args, **kwargs)
        self.message_sent = []

    def send(self, data):
        self.message_sent.append(data)


class MockConfig(sopel.config.Config):
    def __init__(self):
        self.filename = tempfile.mkstemp()[1]
        self.parser = ConfigParser.RawConfigParser(allow_no_value=True)
        self.parser.add_section('core')
        self.parser.set('core', 'owner', 'Embolalia')
        self.define_section('core', sopel.config.core_section.CoreSection)
        self.get = self.parser.get

    def define_section(self, name, cls_):
        if not self.parser.has_section(name):
            self.parser.add_section(name)
        setattr(self, name, cls_(self, name))


class MockSopel(object):
    def __init__(self, nick, admin=False, owner=False):
        self.nick = nick
        self.user = "sopel"

        channel = sopel.tools.Identifier("#Sopel")
        self.channels = sopel.tools.SopelMemory()
        self.channels[channel] = sopel.tools.target.Channel(channel)

        self.users = sopel.tools.SopelMemory()
        self.privileges = sopel.tools.SopelMemory()

        self.memory = sopel.tools.SopelMemory()
        self.memory['url_callbacks'] = sopel.tools.SopelMemory()

        self.ops = {}
        self.halfplus = {}
        self.voices = {}

        self.config = MockConfig()
        self._init_config()

        self.output = []

        if admin:
            self.config.core.admins = [self.nick]
        if owner:
            self.config.core.owner = self.nick

    def _store(self, string, *args, **kwargs):
        self.output.append(string.strip())

    write = msg = say = notice = action = reply = _store

    def _init_config(self):
        cfg = self.config
        cfg.parser.set('core', 'admins', '')
        cfg.parser.set('core', 'owner', '')
        home_dir = os.path.join(os.path.expanduser('~'), '.sopel')
        if not os.path.exists(home_dir):
            os.mkdir(home_dir)
        cfg.parser.set('core', 'homedir', home_dir)

    def register_url_callback(self, pattern, callback):
        if isinstance(pattern, basestring):
            pattern = re.compile(pattern)

        self.memory['url_callbacks'][pattern] = callback

    def unregister_url_callback(self, pattern):
        if isinstance(pattern, basestring):
            pattern = re.compile(pattern)

        try:
            del self.memory['url_callbacks'][pattern]
        except KeyError:
            pass

    def search_url_callbacks(self, url):
        for regex, function in sopel.tools.iteritems(self.memory['url_callbacks']):
            match = regex.search(url)
            if match:
                yield function, match


class MockSopelWrapper(SopelWrapper):
    pass


def get_example_test(tested_func, msg, results, privmsg, admin,
                     owner, repeat, use_regexp, ignore=[]):
    """Get a function that calls tested_func with fake wrapper and trigger.

    Args:
        tested_func - A sopel callable that accepts SopelWrapper and Trigger.
        msg - Message that is supposed to trigger the command.
        results - Expected output from the callable.
        privmsg - If true, make the message appear to have sent in a private
            message to the bot. If false, make it appear to have come from a
            channel.
        admin - If true, make the message appear to have come from an admin.
        owner - If true, make the message appear to have come from an owner.
        repeat - How many times to repeat the test. Useful for tests that
            return random stuff.
        use_regexp = Bool. If true, results is in regexp format.
        ignore - List of strings to ignore.

    """
    def test():
        bot = MockSopel("NickName", admin=admin, owner=owner)

        match = None
        if hasattr(tested_func, "commands"):
            for command in tested_func.commands:
                regexp = sopel.tools.get_command_regexp(".", command)
                match = regexp.match(msg)
                if match:
                    break
        assert match, "Example did not match any command."

        sender = bot.nick if privmsg else "#channel"
        hostmask = "%s!%s@%s" % (bot.nick, "UserName", "example.com")
        # TODO enable message tags
        full_message = ':{} PRIVMSG {} :{}'.format(hostmask, sender, msg)

        pretrigger = sopel.trigger.PreTrigger(bot.nick, full_message)
        trigger = sopel.trigger.Trigger(bot.config, pretrigger, match)

        module = sys.modules[tested_func.__module__]
        if hasattr(module, 'setup'):
            module.setup(bot)

        def isnt_ignored(value):
            """Return True if value doesn't match any re in ignore list."""
            for ignored_line in ignore:
                if re.match(ignored_line, value):
                    return False
            return True

        expected_output_count = 0
        for _i in range(repeat):
            expected_output_count += len(results)
            wrapper = MockSopelWrapper(bot, trigger)
            tested_func(wrapper, trigger)
            wrapper.output = list(filter(isnt_ignored, wrapper.output))
            assert len(wrapper.output) == expected_output_count
            for result, output in zip(results, wrapper.output):
                if type(output) is bytes:
                    output = output.decode('utf-8')
                if use_regexp:
                    if not re.match(result, output):
                        assert result == output
                else:
                    assert result == output

    return test


def get_disable_setup():
    import pytest
    import py

    @pytest.fixture(autouse=True)
    def disable_setup(request, monkeypatch):
        setup = getattr(request.module, "setup", None)
        isfixture = hasattr(setup, "_pytestfixturefunction")
        if setup is not None and not isfixture and py.builtin.callable(setup):
            monkeypatch.setattr(setup, "_pytestfixturefunction", pytest.fixture(), raising=False)
    return disable_setup


def insert_into_module(func, module_name, base_name, prefix):
    """Add a function into a module."""
    func.__module__ = module_name
    module = sys.modules[module_name]
    # Make sure the func method does not overwrite anything.
    for i in range(1000):
        func.__name__ = str("%s_%s_%s" % (prefix, base_name, i))
        if not hasattr(module, func.__name__):
            break
    setattr(module, func.__name__, func)


def run_example_tests(filename, tb='native', multithread=False, verbose=False):
    # These are only required when running tests, so import them here rather
    # than at the module level.
    import pytest
    from multiprocessing import cpu_count

    args = [filename, "-s"]
    args.extend(['--tb', tb])
    if verbose:
        args.extend(['-v'])
    if multithread and cpu_count() > 1:
        args.extend(["-n", str(cpu_count())])

    pytest.main(args)
