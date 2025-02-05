"""Tests for core ``sopel.bot`` module"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
import typing

import pytest

from sopel import bot, loader, plugin, plugins, trigger
from sopel.plugins import rules
from sopel.tests import rawlist
from sopel.tools import Identifier, SopelMemory, target


if typing.TYPE_CHECKING:
    from sopel.config import Config
    from sopel.tests.factories import (
        BotFactory, ConfigFactory, IRCFactory, TriggerFactory, UserFactory,
    )
    from sopel.tests.mocks import MockIRCServer


TMP_CONFIG = """
[core]
owner = testnick
nick = TestBot
enable = coretasks
"""

MOCK_MODULE_CONTENT = """from __future__ import annotations
from sopel import plugin


@plugin.commands("do")
def command_do(bot, trigger):
    pass


@plugin.nickname_commands("info")
def nick_command_info(bot, trigger):
    pass


@plugin.action_commands("tell")
def action_command_tell(bot, trigger):
    pass


@plugin.interval(5)
def interval5s(bot):
    pass


@plugin.interval(10)
def interval10s(bot):
    pass


@plugin.url(r'(.+\\.)?example\\.com')
def example_url(bot):
    pass


@plugin.rule(r'Hello \\w+')
def rule_hello(bot):
    pass


@plugin.event('TOPIC')
def rule_on_topic(bot):
    pass


def shutdown():
    pass


def ignored():
    pass

"""


@pytest.fixture
def tmpconfig(configfactory: ConfigFactory) -> Config:
    return configfactory('test.cfg', TMP_CONFIG)


@pytest.fixture
def mockbot(tmpconfig: Config, botfactory: BotFactory) -> bot.Sopel:
    return botfactory(tmpconfig)


@pytest.fixture
def mockplugin(tmpdir) -> plugins.handlers.PyFilePlugin:
    root = tmpdir.mkdir('loader_mods')
    mod_file = root.join('mockplugin.py')
    mod_file.write(MOCK_MODULE_CONTENT)

    return plugins.handlers.PyFilePlugin(mod_file.strpath)


# -----------------------------------------------------------------------------
# sopel.bot.SopelWrapper

def test_wrapper_default_destination(mockbot, triggerfactory):
    wrapper = triggerfactory.wrapper(
        mockbot, ':Test!test@example.com PRIVMSG #channel :test message')

    assert wrapper.default_destination == '#channel'


def test_wrapper_default_destination_none(mockbot, triggerfactory):
    wrapper = triggerfactory.wrapper(
        mockbot, ':irc.example.com 301 Sopel :I am away.')

    assert wrapper.default_destination is None


def test_wrapper_default_destination_statusmsg(mockbot, triggerfactory):
    mockbot._isupport = mockbot.isupport.apply(
        STATUSMSG=tuple('+'),
    )

    wrapper = triggerfactory.wrapper(
        mockbot, ':Test!test@example.com PRIVMSG +#channel :test message')

    assert wrapper._trigger.sender == '#channel'
    assert wrapper.default_destination == '+#channel'


def test_wrapper_say(mockbot, triggerfactory):
    wrapper = triggerfactory.wrapper(
        mockbot, ':Test!test@example.com PRIVMSG #channel :test message')
    wrapper.say('Hi!')

    assert mockbot.backend.message_sent == rawlist(
        'PRIVMSG #channel :Hi!'
    )


def test_wrapper_say_statusmsg(mockbot, triggerfactory):
    mockbot._isupport = mockbot.isupport.apply(
        STATUSMSG=tuple('+'),
    )

    wrapper: bot.SopelWrapper = triggerfactory.wrapper(
        mockbot, ':Test!test@example.com PRIVMSG +#channel :test message')
    wrapper.say('Hi!')

    assert mockbot.backend.message_sent == rawlist(
        'PRIVMSG +#channel :Hi!'
    )


def test_wrapper_say_override_destination(mockbot, triggerfactory):
    wrapper = triggerfactory.wrapper(
        mockbot, ':Test!test@example.com PRIVMSG #channel :test message')
    wrapper.say('Hi!', destination='#different')

    assert mockbot.backend.message_sent == rawlist(
        'PRIVMSG #different :Hi!'
    )


def test_wrapper_notice(mockbot, triggerfactory):
    wrapper = triggerfactory.wrapper(
        mockbot, ':Test!test@example.com PRIVMSG #channel :test message')
    wrapper.notice('Hi!')

    assert mockbot.backend.message_sent == rawlist(
        'NOTICE #channel :Hi!'
    )


def test_wrapper_notice_statusmsg(mockbot, triggerfactory):
    mockbot._isupport = mockbot.isupport.apply(
        STATUSMSG=tuple('+'),
    )

    wrapper: bot.SopelWrapper = triggerfactory.wrapper(
        mockbot, ':Test!test@example.com PRIVMSG +#channel :test message')
    wrapper.notice('Hi!')

    assert mockbot.backend.message_sent == rawlist(
        'NOTICE +#channel :Hi!'
    )


def test_wrapper_notice_override_destination(mockbot, triggerfactory):
    wrapper = triggerfactory.wrapper(
        mockbot, ':Test!test@example.com PRIVMSG #channel :test message')
    wrapper.notice('Hi!', destination='#different')

    assert mockbot.backend.message_sent == rawlist(
        'NOTICE #different :Hi!'
    )


def test_wrapper_action(mockbot, triggerfactory):
    wrapper = triggerfactory.wrapper(
        mockbot, ':Test!test@example.com PRIVMSG #channel :test message')
    wrapper.action('Hi!')

    assert mockbot.backend.message_sent == rawlist(
        'PRIVMSG #channel :\x01ACTION Hi!\x01'
    )


def test_wrapper_action_statusmsg(mockbot, triggerfactory):
    mockbot._isupport = mockbot.isupport.apply(
        STATUSMSG=tuple('+'),
    )

    wrapper: bot.SopelWrapper = triggerfactory.wrapper(
        mockbot, ':Test!test@example.com PRIVMSG +#channel :test message')
    wrapper.action('Hi!')

    assert mockbot.backend.message_sent == rawlist(
        'PRIVMSG +#channel :\x01ACTION Hi!\x01'
    )


def test_wrapper_action_override_destination(mockbot, triggerfactory):
    wrapper = triggerfactory.wrapper(
        mockbot, ':Test!test@example.com PRIVMSG #channel :test message')
    wrapper.action('Hi!', destination='#different')

    assert mockbot.backend.message_sent == rawlist(
        'PRIVMSG #different :\x01ACTION Hi!\x01'
    )


def test_wrapper_reply(mockbot, triggerfactory):
    wrapper = triggerfactory.wrapper(
        mockbot, ':Test!test@example.com PRIVMSG #channel :test message')
    wrapper.reply('Hi!')

    assert mockbot.backend.message_sent == rawlist(
        'PRIVMSG #channel :Test: Hi!'
    )


def test_wrapper_reply_statusmsg(mockbot, triggerfactory):
    mockbot._isupport = mockbot.isupport.apply(
        STATUSMSG=tuple('+'),
    )

    wrapper: bot.SopelWrapper = triggerfactory.wrapper(
        mockbot, ':Test!test@example.com PRIVMSG +#channel :test message')
    wrapper.reply('Hi!')

    assert mockbot.backend.message_sent == rawlist(
        'PRIVMSG +#channel :Test: Hi!'
    )


def test_wrapper_reply_override_destination(mockbot, triggerfactory):
    wrapper = triggerfactory.wrapper(
        mockbot, ':Test!test@example.com PRIVMSG #channel :test message')
    wrapper.reply('Hi!', destination='#another')

    assert mockbot.backend.message_sent == rawlist(
        'PRIVMSG #another :Test: Hi!'
    )


def test_wrapper_reply_override_reply_to(mockbot, triggerfactory):
    wrapper = triggerfactory.wrapper(
        mockbot, ':Test!test@example.com PRIVMSG #channel :test message')
    wrapper.reply('Hi!', reply_to='Admin')

    assert mockbot.backend.message_sent == rawlist(
        'PRIVMSG #channel :Admin: Hi!'
    )


def test_wrapper_reply_override_destination_reply_to(mockbot, triggerfactory):
    wrapper = triggerfactory.wrapper(
        mockbot, ':Test!test@example.com PRIVMSG #channel :test message')
    wrapper.reply('Hi!', destination='#another', reply_to='Admin')

    assert mockbot.backend.message_sent == rawlist(
        'PRIVMSG #another :Admin: Hi!'
    )


def test_wrapper_kick(mockbot, triggerfactory):
    wrapper = triggerfactory.wrapper(
        mockbot, ':Test!test@example.com PRIVMSG #channel :test message')
    wrapper.kick('SpamUser')

    assert mockbot.backend.message_sent == rawlist(
        'KICK #channel SpamUser'
    )


def test_wrapper_kick_message(mockbot, triggerfactory):
    wrapper = triggerfactory.wrapper(
        mockbot, ':Test!test@example.com PRIVMSG #channel :test message')
    wrapper.kick('SpamUser', message='Test reason')

    assert mockbot.backend.message_sent == rawlist(
        'KICK #channel SpamUser :Test reason'
    )


def test_wrapper_kick_error_nick(mockbot, triggerfactory):
    wrapper = triggerfactory.wrapper(
        mockbot, ':Test!test@example.com PRIVMSG #channel :test message')
    with pytest.raises(RuntimeError):
        wrapper.kick(None)

    assert mockbot.backend.message_sent == []


def test_wrapper_kick_error_channel(mockbot, triggerfactory):
    wrapper = triggerfactory.wrapper(
        mockbot, ':Test!test@example.com PRIVMSG OtherUser :test message')
    with pytest.raises(RuntimeError):
        wrapper.kick('SpamUser')

    assert mockbot.backend.message_sent == []


def test_wrapper_kick_override_destination(mockbot, triggerfactory):
    wrapper = triggerfactory.wrapper(
        mockbot, ':Test!test@example.com PRIVMSG #channel :test message')
    wrapper.kick('SpamUser', channel='#another')

    assert mockbot.backend.message_sent == rawlist(
        'KICK #another SpamUser'
    )


def test_wrapper_kick_override_destination_message(mockbot, triggerfactory):
    wrapper = triggerfactory.wrapper(
        mockbot, ':Test!test@example.com PRIVMSG #channel :test message')
    wrapper.kick('SpamUser', channel='#another', message='Test reason')

    assert mockbot.backend.message_sent == rawlist(
        'KICK #another SpamUser :Test reason'
    )


# -----------------------------------------------------------------------------
# Register/Unregister plugins

def test_register_plugin(tmpconfig, mockplugin):
    sopel = bot.Sopel(tmpconfig)
    assert not sopel.has_plugin('mockplugin')

    mockplugin.load()
    mockplugin.setup(sopel)
    mockplugin.register(sopel)

    assert sopel.has_plugin('mockplugin')
    assert sopel.rules.has_command('do')
    assert sopel.rules.has_command('do', plugin='mockplugin')
    assert sopel.rules.has_nick_command('info')
    assert sopel.rules.has_nick_command('info', plugin='mockplugin')
    assert sopel.rules.has_action_command('tell')
    assert sopel.rules.has_action_command('tell', plugin='mockplugin')
    assert sopel.rules.has_url_callback('example_url')
    assert sopel.rules.has_url_callback('example_url', plugin='mockplugin')


def test_register_unregister_plugin(tmpconfig, mockplugin):
    sopel = bot.Sopel(tmpconfig, daemon=False)

    # register the plugin
    mockplugin.load()
    mockplugin.register(sopel)
    assert sopel.has_plugin('mockplugin'), 'The mockplugin must be registered!'

    # unregister it
    mockplugin.unregister(sopel)
    assert not sopel.has_plugin('mockplugin')
    assert not sopel.rules.has_command('do')
    assert not sopel.rules.has_nick_command('info')
    assert not sopel.rules.has_action_command('tell')


def test_remove_plugin_unknown_plugin(tmpconfig):
    sopel = bot.Sopel(tmpconfig, daemon=False)

    handler = plugins.handlers.PyModulePlugin('admin', 'sopel.builtins')
    with pytest.raises(plugins.exceptions.PluginNotRegistered):
        sopel.remove_plugin(handler, [], [], [], [])


def test_remove_plugin_unregistered_plugin(tmpconfig):
    sopel = bot.Sopel(tmpconfig, daemon=False)

    # register the plugin
    handler = plugins.handlers.PyModulePlugin('coretasks', 'sopel')
    handler.load()
    handler.register(sopel)

    # Unregister the plugin
    handler.unregister(sopel)

    # And now it must raise an exception
    with pytest.raises(plugins.exceptions.PluginNotRegistered):
        sopel.remove_plugin(handler, [], [], [], [])


def test_reload_plugin_unregistered_plugin(tmpconfig):
    sopel = bot.Sopel(tmpconfig, daemon=False)

    # register the plugin
    handler = plugins.handlers.PyModulePlugin('coretasks', 'sopel')
    handler.load()
    handler.register(sopel)

    # Unregister the plugin
    handler.unregister(sopel)

    # And now it must raise an exception
    with pytest.raises(plugins.exceptions.PluginNotRegistered):
        sopel.reload_plugin(handler.name)


# -----------------------------------------------------------------------------
# register callables, jobs, shutdown, urls

def test_register_callables(tmpconfig):
    sopel = bot.Sopel(tmpconfig)

    @plugin.rule(r'(hi|hello|hey|sup)')
    def rule_hello(bot, trigger):
        pass

    @plugin.rule_lazy(lambda *args: [re.compile(r'say what')])
    def rule_say_what(bot, trigger):
        pass

    @plugin.find(r'(hi|hello|hey|sup)')
    def rule_find_hello(bot, trigger):
        pass

    @plugin.find_lazy(lambda *args: [re.compile(r'what')])
    def rule_find_what(bot, trigger):
        pass

    @plugin.search(r'(hi|hello|hey|sup)')
    def rule_search_hello(bot, trigger):
        pass

    @plugin.search_lazy(lambda *args: [re.compile(r'what')])
    def rule_search_what(bot, trigger):
        pass

    @plugin.commands('do')
    @plugin.example('.do nothing')
    def command_do(bot, trigger):
        """The do command does nothing."""
        pass

    @plugin.commands('main sub')
    @plugin.example('.main sub')
    def command_main_sub(bot, trigger):
        """A command with subcommand sub."""
        pass

    @plugin.commands('main other')
    @plugin.example('.main other')
    def command_main_other(bot, trigger):
        """A command with subcommand other."""
        pass

    @plugin.nickname_commands('info')
    @plugin.example('$nickname: info about this')
    def nick_command_info(bot, trigger):
        """Ask Sopel to get some info about nothing."""
        pass

    @plugin.action_commands('tell')
    def action_command_tell(bot, trigger):
        pass

    @plugin.commands('mixed')
    @plugin.rule('mixing')
    def mixed_rule_command(bot, trigger):
        pass

    @plugin.event('JOIN')
    @plugin.label('handle_join_event')
    def on_join(bot, trigger):
        pass

    # prepare callables to be registered
    callables = [
        rule_hello,
        rule_say_what,
        rule_find_hello,
        rule_find_what,
        rule_search_hello,
        rule_search_what,
        command_do,
        command_main_sub,
        command_main_other,
        nick_command_info,
        action_command_tell,
        mixed_rule_command,
        on_join,
    ]

    # clean callables and set plugin name by hand
    # since the loader and plugin handlers are excluded here
    for handler in callables:
        loader.clean_callable(handler, tmpconfig)
        handler.plugin_name = 'testplugin'

    # register callables
    sopel.register_callables(callables)

    # trigger rule "hello"
    line = ':Foo!foo@example.com PRIVMSG #sopel :hello'
    pretrigger = trigger.PreTrigger(sopel.nick, line)

    matches = sopel.rules.get_triggered_rules(sopel, pretrigger)
    assert len(matches) == 3
    assert matches[0][0].get_rule_label() == 'rule_hello'
    assert matches[1][0].get_rule_label() == 'rule_find_hello'
    assert matches[2][0].get_rule_label() == 'rule_search_hello'

    # trigger lazy rule "say what"
    line = ':Foo!foo@example.com PRIVMSG #sopel :say what now?'
    pretrigger = trigger.PreTrigger(sopel.nick, line)

    matches = sopel.rules.get_triggered_rules(sopel, pretrigger)
    assert len(matches) == 3
    assert matches[0][0].get_rule_label() == 'rule_say_what'
    assert matches[1][0].get_rule_label() == 'rule_find_what'
    assert matches[2][0].get_rule_label() == 'rule_search_what'

    # trigger command "do"
    line = ':Foo!foo@example.com PRIVMSG #sopel :.do'
    pretrigger = trigger.PreTrigger(sopel.nick, line)

    matches = sopel.rules.get_triggered_rules(sopel, pretrigger)
    assert len(matches) == 1
    assert matches[0][0].get_rule_label() == 'do'

    # trigger command with subcommand "main-sub"
    line = ':Foo!foo@example.com PRIVMSG #sopel :.main sub'
    pretrigger = trigger.PreTrigger(sopel.nick, line)

    matches = sopel.rules.get_triggered_rules(sopel, pretrigger)
    assert len(matches) == 1
    assert matches[0][0].get_rule_label() == 'main-sub'

    # trigger command with the other subcommand "main-other"
    line = ':Foo!foo@example.com PRIVMSG #sopel :.main other'
    pretrigger = trigger.PreTrigger(sopel.nick, line)

    matches = sopel.rules.get_triggered_rules(sopel, pretrigger)
    assert len(matches) == 1
    assert matches[0][0].get_rule_label() == 'main-other'

    # trigger nick command "info"
    line = ':Foo!foo@example.com PRIVMSG #sopel :TestBot: info'
    pretrigger = trigger.PreTrigger(sopel.nick, line)

    matches = sopel.rules.get_triggered_rules(sopel, pretrigger)
    assert len(matches) == 1
    assert matches[0][0].get_rule_label() == 'info'

    # trigger action command "tell"
    line = ':Foo!foo@example.com PRIVMSG #sopel :\x01ACTION tell\x01'
    pretrigger = trigger.PreTrigger(sopel.nick, line)

    matches = sopel.rules.get_triggered_rules(sopel, pretrigger)
    assert len(matches) == 1
    assert matches[0][0].get_rule_label() == 'tell'

    # trigger rules with event
    line = ':Foo!foo@example.com JOIN #Sopel'
    pretrigger = trigger.PreTrigger(sopel.nick, line)

    matches = sopel.rules.get_triggered_rules(sopel, pretrigger)
    assert len(matches) == 1
    assert matches[0][0].get_rule_label() == 'handle_join_event'

    # trigger command "mixed"
    line = ':Foo!foo@example.com PRIVMSG #sopel :.mixed'
    pretrigger = trigger.PreTrigger(sopel.nick, line)

    matches = sopel.rules.get_triggered_rules(sopel, pretrigger)
    assert len(matches) == 1
    assert matches[0][0].get_rule_label() == 'mixed'

    # trigger rule "mixed_rule_command"
    line = ':Foo!foo@example.com PRIVMSG #sopel :mixing'
    pretrigger = trigger.PreTrigger(sopel.nick, line)

    matches = sopel.rules.get_triggered_rules(sopel, pretrigger)
    assert len(matches) == 1
    assert matches[0][0].get_rule_label() == 'mixed_rule_command'

    # check documentation
    assert sopel.command_groups == {
        'testplugin': ['do', 'info', 'main other', 'main sub', 'mixed'],
    }

    assert sopel.doc == {
        'do': (
            ['The do command does nothing.'],
            ['.do nothing'],
        ),
        'info': (
            ['Ask Sopel to get some info about nothing.'],
            ['TestBot: info about this'],
        ),
        'main sub': (
            ['A command with subcommand sub.'],
            ['.main sub'],
        ),
        'main other': (
            ['A command with subcommand other.'],
            ['.main other'],
        ),
        'mixed': (
            [],
            [],
        )
    }


def test_register_urls(tmpconfig):
    sopel = bot.Sopel(tmpconfig)

    @plugin.url(r'https://(\S+)/(.+)?')
    @plugin.label('handle_urls_https')
    def url_callback_https(bot, trigger, match):
        pass

    @plugin.url(r'http://(\S+)/(.+)?')
    @plugin.label('handle_urls_http')
    def url_callback_http(bot, trigger, match):
        pass

    # prepare callables to be registered
    callables = [
        url_callback_https,
        url_callback_http,
    ]

    # clean callables and set plugin name by hand
    # since the loader and plugin handlers are excluded here
    for handler in callables:
        loader.clean_callable(handler, tmpconfig)
        handler.plugin_name = 'testplugin'

    # register callables
    sopel.register_urls(callables)

    # trigger URL callback "handle_urls_https"
    line = ':Foo!foo@example.com PRIVMSG #sopel :https://example.com/test'
    pretrigger = trigger.PreTrigger(sopel.nick, line)

    matches = sopel.rules.get_triggered_rules(sopel, pretrigger)
    assert len(matches) == 1
    assert matches[0][0].get_rule_label() == 'handle_urls_https'

    # trigger URL callback "handle_urls_https"
    line = ':Foo!foo@example.com PRIVMSG #sopel :http://example.com/test'
    pretrigger = trigger.PreTrigger(sopel.nick, line)

    matches = sopel.rules.get_triggered_rules(sopel, pretrigger)
    assert len(matches) == 1
    assert matches[0][0].get_rule_label() == 'handle_urls_http'


# -----------------------------------------------------------------------------
# call_rule

@pytest.fixture
def match_hello_rule(mockbot: bot.Sopel, triggerfactory: TriggerFactory):
    """Helper for generating matches to each `Rule` in the following tests"""
    def _factory(rule_hello):
        # trigger
        line = ':Test!test@example.com PRIVMSG #channel :hello'

        trigger = triggerfactory(mockbot, line)
        pretrigger = trigger._pretrigger

        matches = list(rule_hello.match(mockbot, pretrigger))
        match = matches[0]

        wrapper = bot.SopelWrapper(mockbot, trigger)

        return match, trigger, wrapper
    return _factory


@pytest.fixture
def multimatch_hello_rule(mockbot: bot.Sopel, triggerfactory: TriggerFactory):
    def _factory(rule_hello):
        # trigger
        line = ':Test!test@example.com PRIVMSG #channel :hello hello hello'

        trigger = triggerfactory(mockbot, line)
        pretrigger = trigger._pretrigger

        for match in rule_hello.match(mockbot, pretrigger):
            wrapper = bot.SopelWrapper(mockbot, trigger)
            yield match, trigger, wrapper
    return _factory


def test_call_rule(
    mockbot: bot.Sopel,
    match_hello_rule: typing.Callable,
) -> None:
    # setup
    items = []

    def testrule(bot, trigger):
        bot.say('hi')
        items.append(1)
        return "Return Value"

    rule_hello = rules.Rule(
        [re.compile(r'(hi|hello|hey|sup)')],
        plugin='testplugin',
        label='testrule',
        handler=testrule)

    match, rule_trigger, wrapper = match_hello_rule(rule_hello)

    # call rule
    mockbot.call_rule(rule_hello, wrapper, rule_trigger)

    # assert the rule has been executed
    assert mockbot.backend.message_sent == rawlist(
        'PRIVMSG #channel :hi'
    )
    assert items == [1]

    # assert the rule is not rate limited
    at_time = datetime.now(timezone.utc)
    assert not rule_hello.is_user_rate_limited(Identifier('Test'), at_time)
    assert not rule_hello.is_channel_rate_limited('#channel', at_time)
    assert not rule_hello.is_global_rate_limited(at_time)

    match, rule_trigger, wrapper = match_hello_rule(rule_hello)

    # call rule again
    mockbot.call_rule(rule_hello, wrapper, rule_trigger)

    # assert the rule has been executed twice now
    assert mockbot.backend.message_sent == rawlist(
        'PRIVMSG #channel :hi',
        'PRIVMSG #channel :hi',
    )
    assert items == [1, 1]


def test_call_rule_multiple_matches(
    mockbot: bot.Sopel,
    multimatch_hello_rule: typing.Callable,
) -> None:
    # setup
    items = []

    def testrule(bot, trigger):
        bot.say('hi')
        items.append(1)
        return "Return Value"

    find_hello = rules.FindRule(
        [re.compile(r'(hi|hello|hey|sup)')],
        plugin='testplugin',
        label='testrule',
        handler=testrule)

    for match, rule_trigger, wrapper in multimatch_hello_rule(find_hello):
        mockbot.call_rule(find_hello, wrapper, rule_trigger)

    # assert the rule has been executed three times now
    assert mockbot.backend.message_sent == rawlist(
        'PRIVMSG #channel :hi',
        'PRIVMSG #channel :hi',
        'PRIVMSG #channel :hi',
    )
    assert items == [1, 1, 1]


def test_call_rule_rate_limited_user(mockbot, match_hello_rule):
    items = []

    # setup
    def testrule(bot, trigger):
        bot.say('hi')
        items.append(1)
        return "Return Value"

    rule_hello = rules.Rule(
        [re.compile(r'(hi|hello|hey|sup)')],
        plugin='testplugin',
        label='testrule',
        handler=testrule,
        user_rate_limit=100,
    )

    match, rule_trigger, wrapper = match_hello_rule(rule_hello)

    # call rule
    mockbot.call_rule(rule_hello, wrapper, rule_trigger)

    # assert the rule has been executed
    assert mockbot.backend.message_sent == rawlist(
        'PRIVMSG #channel :hi'
    )
    assert items == [1]

    # assert the rule is now rate limited
    at_time = datetime.now(timezone.utc)
    assert rule_hello.is_user_rate_limited(Identifier('Test'), at_time)
    assert not rule_hello.is_channel_rate_limited('#channel', at_time)
    assert not rule_hello.is_global_rate_limited(at_time)

    match, rule_trigger, wrapper = match_hello_rule(rule_hello)

    # call rule again
    mockbot.call_rule(rule_hello, wrapper, rule_trigger)

    # assert no new message
    assert mockbot.backend.message_sent == rawlist(
        'PRIVMSG #channel :hi'
    ), 'There must not be any new message sent'
    assert items == [1], 'There must not be any new item'


def test_call_rule_rate_limited_user_with_message(mockbot, match_hello_rule):
    items = []

    # setup
    def testrule(bot, trigger):
        bot.say('hi')
        items.append(1)
        return "Return Value"

    rule_hello = rules.Rule(
        [re.compile(r'(hi|hello|hey|sup)')],
        plugin='testplugin',
        label='testrule',
        handler=testrule,
        user_rate_limit=100,
        user_rate_message='You reached the rate limit.')

    match, rule_trigger, wrapper = match_hello_rule(rule_hello)

    # call rule
    mockbot.call_rule(rule_hello, wrapper, rule_trigger)

    # assert the rule has been executed
    assert mockbot.backend.message_sent == rawlist(
        'PRIVMSG #channel :hi'
    )
    assert items == [1]

    match, rule_trigger, wrapper = match_hello_rule(rule_hello)

    # call rule again
    mockbot.call_rule(rule_hello, wrapper, rule_trigger)

    # assert there is now a NOTICE
    assert mockbot.backend.message_sent == rawlist(
        'PRIVMSG #channel :hi',
        'NOTICE Test :You reached the rate limit.',
    ), 'A NOTICE should appear here.'
    assert items == [1], 'There must not be any new item'


def test_call_rule_rate_limited_channel(mockbot, match_hello_rule):
    items = []

    # setup
    def testrule(bot, trigger):
        bot.say('hi')
        items.append(1)
        return "Return Value"

    rule_hello = rules.Rule(
        [re.compile(r'(hi|hello|hey|sup)')],
        plugin='testplugin',
        label='testrule',
        handler=testrule,
        channel_rate_limit=100)

    match, rule_trigger, wrapper = match_hello_rule(rule_hello)

    # call rule
    mockbot.call_rule(rule_hello, wrapper, rule_trigger)

    # assert the rule has been executed
    assert mockbot.backend.message_sent == rawlist(
        'PRIVMSG #channel :hi'
    )
    assert items == [1]

    # assert the rule is now rate limited
    at_time = datetime.now(timezone.utc)
    assert not rule_hello.is_user_rate_limited(Identifier('Test'), at_time)
    assert rule_hello.is_channel_rate_limited('#channel', at_time)
    assert not rule_hello.is_global_rate_limited(at_time)

    match, rule_trigger, wrapper = match_hello_rule(rule_hello)

    # call rule again
    mockbot.call_rule(rule_hello, wrapper, rule_trigger)

    # assert no new message
    assert mockbot.backend.message_sent == rawlist(
        'PRIVMSG #channel :hi'
    ), 'There must not be any new message sent'
    assert items == [1], 'There must not be any new item'


def test_call_rule_rate_limited_channel_with_message(mockbot, match_hello_rule):
    items = []

    # setup
    def testrule(bot, trigger):
        bot.say('hi')
        items.append(1)
        return "Return Value"

    rule_hello = rules.Rule(
        [re.compile(r'(hi|hello|hey|sup)')],
        plugin='testplugin',
        label='testrule',
        handler=testrule,
        channel_rate_limit=100,
        channel_rate_message='You reached the channel rate limit.')

    match, rule_trigger, wrapper = match_hello_rule(rule_hello)

    # call rule
    mockbot.call_rule(rule_hello, wrapper, rule_trigger)

    # assert the rule has been executed
    assert mockbot.backend.message_sent == rawlist(
        'PRIVMSG #channel :hi'
    )
    assert items == [1]

    # assert the rule is now rate limited
    at_time = datetime.now(timezone.utc)
    assert not rule_hello.is_user_rate_limited(Identifier('Test'), at_time)
    assert rule_hello.is_channel_rate_limited('#channel', at_time)
    assert not rule_hello.is_global_rate_limited(at_time)

    match, rule_trigger, wrapper = match_hello_rule(rule_hello)

    # call rule again
    mockbot.call_rule(rule_hello, wrapper, rule_trigger)

    # assert there is now a NOTICE
    assert mockbot.backend.message_sent == rawlist(
        'PRIVMSG #channel :hi',
        'NOTICE Test :You reached the channel rate limit.',
    ), 'A NOTICE should appear here.'
    assert items == [1], 'There must not be any new item'


def test_call_rule_rate_limited_global(mockbot, match_hello_rule):
    items = []

    # setup
    def testrule(bot, trigger):
        bot.say('hi')
        items.append(1)
        return "Return Value"

    rule_hello = rules.Rule(
        [re.compile(r'(hi|hello|hey|sup)')],
        plugin='testplugin',
        label='testrule',
        handler=testrule,
        global_rate_limit=100)

    match, rule_trigger, wrapper = match_hello_rule(rule_hello)

    # call rule
    mockbot.call_rule(rule_hello, wrapper, rule_trigger)

    # assert the rule has been executed
    assert mockbot.backend.message_sent == rawlist(
        'PRIVMSG #channel :hi'
    )
    assert items == [1]

    # assert the rule is now rate limited
    at_time = datetime.now(timezone.utc)
    assert not rule_hello.is_user_rate_limited(Identifier('Test'), at_time)
    assert not rule_hello.is_channel_rate_limited('#channel', at_time)
    assert rule_hello.is_global_rate_limited(at_time)

    match, rule_trigger, wrapper = match_hello_rule(rule_hello)

    # call rule again
    mockbot.call_rule(rule_hello, wrapper, rule_trigger)

    # assert no new message
    assert mockbot.backend.message_sent == rawlist(
        'PRIVMSG #channel :hi'
    ), 'There must not be any new message sent'
    assert items == [1], 'There must not be any new item'


def test_call_rule_rate_limited_global_with_message(mockbot, match_hello_rule):
    items = []

    # setup
    def testrule(bot, trigger):
        bot.say('hi')
        items.append(1)
        return "Return Value"

    rule_hello = rules.Rule(
        [re.compile(r'(hi|hello|hey|sup)')],
        plugin='testplugin',
        label='testrule',
        handler=testrule,
        global_rate_limit=100,
        global_rate_message='You reached the server rate limit.')

    match, rule_trigger, wrapper = match_hello_rule(rule_hello)

    # call rule
    mockbot.call_rule(rule_hello, wrapper, rule_trigger)

    # assert the rule has been executed
    assert mockbot.backend.message_sent == rawlist(
        'PRIVMSG #channel :hi'
    )
    assert items == [1]

    # assert the rule is now rate limited
    at_time = datetime.now(timezone.utc)
    assert not rule_hello.is_user_rate_limited(Identifier('Test'), at_time)
    assert not rule_hello.is_channel_rate_limited('#channel', at_time)
    assert rule_hello.is_global_rate_limited(at_time)

    match, rule_trigger, wrapper = match_hello_rule(rule_hello)

    # call rule again
    mockbot.call_rule(rule_hello, wrapper, rule_trigger)

    # assert there is now a NOTICE
    assert mockbot.backend.message_sent == rawlist(
        'PRIVMSG #channel :hi',
        'NOTICE Test :You reached the server rate limit.',
    ), 'A NOTICE should appear here.'
    assert items == [1], 'There must not be any new item'


# -----------------------------------------------------------------------------
# rate limit response templating

@pytest.mark.parametrize("limit_type", ("user", "channel", "global"))
@pytest.mark.parametrize("msg_fmt, expected_notice", (
    ("{nick}", "NOTICE Test :Test"),
    ("{channel}", "NOTICE Test :#channel"),
    ("{sender}", "NOTICE Test :#channel"),
    ("{plugin}", "NOTICE Test :testplugin"),
    ("{label}", "NOTICE Test :testrule"),
    ("{rate_limit}", "NOTICE Test :0:01:40"),
    ("{rate_limit_sec}", "NOTICE Test :100.0"),
))
def test_rate_limit_fixed_fields(
    mockbot,
    match_hello_rule,
    limit_type,
    msg_fmt,
    expected_notice,
):
    def testrule(bot, trigger):
        return "Return Value"

    limit_type_params = {
        "{limit_type}_rate_limit".format(limit_type=limit_type): 100,
        "{limit_type}_rate_message".format(limit_type=limit_type): msg_fmt,
    }

    rule_hello = rules.Rule(
        [re.compile(r'(hi|hello|hey|sup)')],
        plugin='testplugin',
        label='testrule',
        handler=testrule,
        **limit_type_params,
    )

    # call rule
    match, rule_trigger, wrapper = match_hello_rule(rule_hello)
    mockbot.call_rule(rule_hello, wrapper, rule_trigger)

    # call rule again
    match, rule_trigger, wrapper = match_hello_rule(rule_hello)
    mockbot.call_rule(rule_hello, wrapper, rule_trigger)

    # assert there is now a NOTICE which contains templated rate-limit information
    assert mockbot.backend.message_sent == rawlist(
        expected_notice,
    )


@pytest.mark.parametrize("limit_type", ("user", "channel", "global"))
def test_rate_limit_type_field(mockbot, match_hello_rule, limit_type):
    def testrule(bot, trigger):
        return "Return Value"

    msg_fmt = "{rate_limit_type}"

    limit_type_params = {
        "{limit_type}_rate_limit".format(limit_type=limit_type): 100,
        "{limit_type}_rate_message".format(limit_type=limit_type): msg_fmt,
    }

    rule_hello = rules.Rule(
        [re.compile(r'(hi|hello|hey|sup)')],
        plugin='testplugin',
        label='testrule',
        handler=testrule,
        **limit_type_params,
    )

    # call rule
    match, rule_trigger, wrapper = match_hello_rule(rule_hello)
    mockbot.call_rule(rule_hello, wrapper, rule_trigger)

    # call rule again
    match, rule_trigger, wrapper = match_hello_rule(rule_hello)
    mockbot.call_rule(rule_hello, wrapper, rule_trigger)

    # assert there is now a NOTICE which contains templated rate-limit information
    assert mockbot.backend.message_sent == rawlist(
        "NOTICE Test :{limit_type}".format(limit_type=limit_type),
    )


@pytest.mark.parametrize("limit_type", ("user", "channel", "global"))
def test_rate_limit_time_left_field(mockbot, match_hello_rule, limit_type):
    def testrule(bot, trigger):
        return "Return Value"

    msg_fmt = "time_left={time_left} time_left_sec={time_left_sec}"
    limit_type_params = {
        "{limit_type}_rate_limit".format(limit_type=limit_type): 100,
        "{limit_type}_rate_message".format(limit_type=limit_type): msg_fmt,
    }

    rule_hello = rules.Rule(
        [re.compile(r'(hi|hello|hey|sup)')],
        plugin='testplugin',
        label='testrule',
        handler=testrule,
        **limit_type_params,
    )

    # call rule
    match, rule_trigger, wrapper = match_hello_rule(rule_hello)
    mockbot.call_rule(rule_hello, wrapper, rule_trigger)

    # call rule again
    match, rule_trigger, wrapper = match_hello_rule(rule_hello)
    mockbot.call_rule(rule_hello, wrapper, rule_trigger)

    # assert there is now a NOTICE which contains templated time left information
    assert mockbot.backend.message_sent
    patt = (br"NOTICE Test :"
            br"time_left=\d+:\d+:\d+ "
            br"time_left_sec=\d+")
    assert re.match(patt, mockbot.backend.message_sent[0])


# -----------------------------------------------------------------------------
# Channel privileges


def test_has_channel_privilege_no_privilege(ircfactory, botfactory, tmpconfig):
    sopel = botfactory.preloaded(tmpconfig)
    server = ircfactory(sopel)
    name = Identifier('#adminchannel')

    # unknown channel
    with pytest.raises(ValueError):
        sopel.has_channel_privilege('#adminchannel', plugin.VOICE)

    # join channel
    server.channel_joined('#adminchannel')

    # check privileges
    assert not sopel.has_channel_privilege(name, plugin.VOICE)
    assert not sopel.has_channel_privilege('#adminchannel', plugin.VOICE)
    assert not sopel.has_channel_privilege(name, plugin.HALFOP)
    assert not sopel.has_channel_privilege('#adminchannel', plugin.HALFOP)
    assert not sopel.has_channel_privilege(name, plugin.OP)
    assert not sopel.has_channel_privilege('#adminchannel', plugin.OP)
    assert not sopel.has_channel_privilege(name, plugin.ADMIN)
    assert not sopel.has_channel_privilege('#adminchannel', plugin.ADMIN)
    assert not sopel.has_channel_privilege(name, plugin.OWNER)
    assert not sopel.has_channel_privilege('#adminchannel', plugin.OWNER)
    assert not sopel.has_channel_privilege(name, plugin.OPER)
    assert not sopel.has_channel_privilege('#adminchannel', plugin.OPER)

    # unknown channel
    with pytest.raises(ValueError):
        sopel.has_channel_privilege('#anotherchannel', plugin.VOICE)


def test_has_channel_privilege_voice(ircfactory, botfactory, tmpconfig):
    sopel = botfactory.preloaded(tmpconfig)
    server = ircfactory(sopel)
    name = Identifier('#adminchannel')

    # join channel
    server.channel_joined('#adminchannel')
    server.mode_set('#adminchannel', '+v', [sopel.nick])

    assert sopel.has_channel_privilege(name, plugin.VOICE)
    assert sopel.has_channel_privilege('#adminchannel', plugin.VOICE)
    assert not sopel.has_channel_privilege(name, plugin.HALFOP)
    assert not sopel.has_channel_privilege('#adminchannel', plugin.HALFOP)
    assert not sopel.has_channel_privilege(name, plugin.OP)
    assert not sopel.has_channel_privilege('#adminchannel', plugin.OP)
    assert not sopel.has_channel_privilege(name, plugin.ADMIN)
    assert not sopel.has_channel_privilege('#adminchannel', plugin.ADMIN)
    assert not sopel.has_channel_privilege(name, plugin.OWNER)
    assert not sopel.has_channel_privilege('#adminchannel', plugin.OWNER)
    assert not sopel.has_channel_privilege(name, plugin.OPER)
    assert not sopel.has_channel_privilege('#adminchannel', plugin.OPER)


def test_has_channel_privilege_halfop(ircfactory, botfactory, tmpconfig):
    sopel = botfactory.preloaded(tmpconfig)
    server = ircfactory(sopel)
    name = Identifier('#adminchannel')

    # join channel
    server.channel_joined('#adminchannel')
    server.mode_set('#adminchannel', '+h', [sopel.nick])

    assert sopel.has_channel_privilege(name, plugin.VOICE)
    assert sopel.has_channel_privilege('#adminchannel', plugin.VOICE)
    assert sopel.has_channel_privilege(name, plugin.HALFOP)
    assert sopel.has_channel_privilege('#adminchannel', plugin.HALFOP)
    assert not sopel.has_channel_privilege(name, plugin.OP)
    assert not sopel.has_channel_privilege('#adminchannel', plugin.OP)
    assert not sopel.has_channel_privilege(name, plugin.ADMIN)
    assert not sopel.has_channel_privilege('#adminchannel', plugin.ADMIN)
    assert not sopel.has_channel_privilege(name, plugin.OWNER)
    assert not sopel.has_channel_privilege('#adminchannel', plugin.OWNER)
    assert not sopel.has_channel_privilege(name, plugin.OPER)
    assert not sopel.has_channel_privilege('#adminchannel', plugin.OPER)


def test_has_channel_privilege_op(ircfactory, botfactory, tmpconfig):
    sopel = botfactory.preloaded(tmpconfig)
    server = ircfactory(sopel)
    name = Identifier('#adminchannel')

    # join channel
    server.channel_joined('#adminchannel')
    server.mode_set('#adminchannel', '+o', [sopel.nick])

    assert sopel.has_channel_privilege(name, plugin.VOICE)
    assert sopel.has_channel_privilege('#adminchannel', plugin.VOICE)
    assert sopel.has_channel_privilege(name, plugin.HALFOP)
    assert sopel.has_channel_privilege('#adminchannel', plugin.HALFOP)
    assert sopel.has_channel_privilege(name, plugin.OP)
    assert sopel.has_channel_privilege('#adminchannel', plugin.OP)
    assert not sopel.has_channel_privilege(name, plugin.ADMIN)
    assert not sopel.has_channel_privilege('#adminchannel', plugin.ADMIN)
    assert not sopel.has_channel_privilege(name, plugin.OWNER)
    assert not sopel.has_channel_privilege('#adminchannel', plugin.OWNER)
    assert not sopel.has_channel_privilege(name, plugin.OPER)
    assert not sopel.has_channel_privilege('#adminchannel', plugin.OPER)


def test_has_channel_privilege_admin(ircfactory, botfactory, tmpconfig):
    sopel = botfactory.preloaded(tmpconfig)
    server = ircfactory(sopel)
    name = Identifier('#adminchannel')

    # join channel
    server.channel_joined('#adminchannel')
    server.mode_set('#adminchannel', '+a', [sopel.nick])

    assert sopel.has_channel_privilege(name, plugin.VOICE)
    assert sopel.has_channel_privilege('#adminchannel', plugin.VOICE)
    assert sopel.has_channel_privilege(name, plugin.HALFOP)
    assert sopel.has_channel_privilege('#adminchannel', plugin.HALFOP)
    assert sopel.has_channel_privilege(name, plugin.OP)
    assert sopel.has_channel_privilege('#adminchannel', plugin.OP)
    assert sopel.has_channel_privilege(name, plugin.ADMIN)
    assert sopel.has_channel_privilege('#adminchannel', plugin.ADMIN)
    assert not sopel.has_channel_privilege(name, plugin.OWNER)
    assert not sopel.has_channel_privilege('#adminchannel', plugin.OWNER)
    assert not sopel.has_channel_privilege(name, plugin.OPER)
    assert not sopel.has_channel_privilege('#adminchannel', plugin.OPER)


def test_has_channel_privilege_owner(ircfactory, botfactory, tmpconfig):
    sopel = botfactory.preloaded(tmpconfig)
    server = ircfactory(sopel)
    name = Identifier('#adminchannel')

    # join channel
    server.channel_joined('#adminchannel')
    server.mode_set('#adminchannel', '+q', [sopel.nick])

    assert sopel.has_channel_privilege(name, plugin.VOICE)
    assert sopel.has_channel_privilege('#adminchannel', plugin.VOICE)
    assert sopel.has_channel_privilege(name, plugin.HALFOP)
    assert sopel.has_channel_privilege('#adminchannel', plugin.HALFOP)
    assert sopel.has_channel_privilege(name, plugin.OP)
    assert sopel.has_channel_privilege('#adminchannel', plugin.OP)
    assert sopel.has_channel_privilege(name, plugin.ADMIN)
    assert sopel.has_channel_privilege('#adminchannel', plugin.ADMIN)
    assert sopel.has_channel_privilege(name, plugin.OWNER)
    assert sopel.has_channel_privilege('#adminchannel', plugin.OWNER)
    assert not sopel.has_channel_privilege(name, plugin.OPER)
    assert not sopel.has_channel_privilege('#adminchannel', plugin.OPER)


def test_has_channel_privilege_operator(ircfactory, botfactory, tmpconfig):
    sopel = botfactory.preloaded(tmpconfig)
    server = ircfactory(sopel)
    name = Identifier('#adminchannel')

    # join channel
    server.channel_joined('#adminchannel')
    server.mode_set('#adminchannel', '+y', [sopel.nick])

    assert sopel.has_channel_privilege(name, plugin.VOICE)
    assert sopel.has_channel_privilege('#adminchannel', plugin.VOICE)
    assert sopel.has_channel_privilege(name, plugin.HALFOP)
    assert sopel.has_channel_privilege('#adminchannel', plugin.HALFOP)
    assert sopel.has_channel_privilege(name, plugin.OP)
    assert sopel.has_channel_privilege('#adminchannel', plugin.OP)
    assert sopel.has_channel_privilege(name, plugin.ADMIN)
    assert sopel.has_channel_privilege('#adminchannel', plugin.ADMIN)
    assert sopel.has_channel_privilege(name, plugin.OWNER)
    assert sopel.has_channel_privilege('#adminchannel', plugin.OWNER)
    assert sopel.has_channel_privilege(name, plugin.OPER)
    assert sopel.has_channel_privilege('#adminchannel', plugin.OPER)


# -----------------------------------------------------------------------------
# URL Callbacks

def test_search_url_callbacks(tmpconfig):
    """Test search_url_callbacks for a registered URL."""
    sopel = bot.Sopel(tmpconfig, daemon=False)

    def url_handler(*args, **kwargs):
        return None

    sopel.register_url_callback(r'https://example\.com', url_handler)
    results = list(sopel._search_url_callbacks_impl('https://example.com'))
    assert len(results) == 1, 'Expected 1 handler; found %d' % len(results)
    assert url_handler in results[0], 'Once registered, handler must be found'


def test_search_url_callbacks_pattern(tmpconfig):
    """Test search_url_callbacks for a registered regex pattern."""
    sopel = bot.Sopel(tmpconfig, daemon=False)

    def url_handler(*args, **kwargs):
        return None

    sopel.register_url_callback(r'https://(www\.)?example\.com', url_handler)
    results = list(sopel._search_url_callbacks_impl('https://example.com'))
    assert len(results) == 1, 'Expected 1 handler; found %d' % len(results)
    assert url_handler in results[0], 'Once registered, handler must be found'

    results = list(sopel._search_url_callbacks_impl('https://www.example.com'))
    assert len(results) == 1, 'Regex pattern must match both URLs'
    assert url_handler in results[0]


def test_search_url_callbacks_compiled_pattern(tmpconfig):
    """Test search_url_callbacks for a registered compiled regex pattern."""
    sopel = bot.Sopel(tmpconfig, daemon=False)
    url_regex = re.compile(r'https://(www\.)?example\.com')

    def url_handler(*args, **kwargs):
        return None

    sopel.register_url_callback(url_regex, url_handler)
    results = list(sopel._search_url_callbacks_impl('https://example.com'))
    assert len(results) == 1, 'Expected 1 handler; found %d' % len(results)
    assert url_handler in results[0], 'Once registered, handler must be found'

    results = list(sopel._search_url_callbacks_impl('https://www.example.com'))
    assert len(results) == 1, 'Regex pattern must match both URLs'
    assert url_handler in results[0]


def test_search_url_callbacks_not_found(tmpconfig):
    """Test search_url_callbacks when pattern does not match."""
    sopel = bot.Sopel(tmpconfig, daemon=False)
    results = sopel._search_url_callbacks_impl('https://example.com')
    assert not list(results), 'No handler registered; must return an empty list'

    def url_handler(*args, **kwargs):
        return None

    sopel.register_url_callback(r'https://(www\.)?example\.com', url_handler)

    results = sopel._search_url_callbacks_impl('https://not-example.com')
    assert not list(results), 'URL must not match any pattern'


def test_register_url_callback_multiple(tmpconfig):
    """Test register_url_callback replace URL callbacks for a pattern."""
    test_pattern = r'https://(www\.)?example\.com'

    def url_handler(*args, **kwargs):
        return None

    def url_handler_replacement(*args, **kwargs):
        return None

    sopel = bot.Sopel(tmpconfig, daemon=False)
    sopel.register_url_callback(test_pattern, url_handler)

    results = list(sopel._search_url_callbacks_impl('https://www.example.com'))
    assert url_handler in results[0]

    sopel.register_url_callback(test_pattern, url_handler_replacement)

    results = list(sopel._search_url_callbacks_impl('https://www.example.com'))
    assert len(results) == 1, 'There must be one and only one callback'
    assert url_handler_replacement in results[0], (
        'Handler must have been replaced')


def test_unregister_url_callback(tmpconfig):
    """Test unregister_url_callback removes URL callback for a pattern."""
    test_pattern = r'https://(www\.)?example\.com'

    def url_handler(*args, **kwargs):
        return None

    sopel = bot.Sopel(tmpconfig, daemon=False)

    # now register a pattern, make sure it still work
    sopel.register_url_callback(test_pattern, url_handler)
    assert list(sopel._search_url_callbacks_impl('https://www.example.com'))

    # unregister this pattern
    sopel.unregister_url_callback(test_pattern, url_handler)

    # now it is not possible to find a callback for this pattern
    results = list(sopel._search_url_callbacks_impl('https://www.example.com'))
    assert not results, 'Unregistered URL callback must not work anymore'


def test_unregister_url_callback_no_memory(tmpconfig):
    """Test unregister_url_callback behavior when bot.memory empty"""
    test_pattern = r'https://(www\.)?example\.com'

    def url_handler(*args, **kwargs):
        return None

    sopel = bot.Sopel(tmpconfig, daemon=False)
    sopel.unregister_url_callback(test_pattern, url_handler)
    # no exception implies success


def test_unregister_url_callback_unknown_pattern(tmpconfig):
    """Test unregister_url_callback pass when pattern is unknown."""
    test_pattern = r'https://(www\.)?example\.com'

    def url_handler(*args, **kwargs):
        return None

    sopel = bot.Sopel(tmpconfig, daemon=False)

    # now register a pattern, make sure it still work
    sopel.register_url_callback(test_pattern, url_handler)
    assert list(sopel._search_url_callbacks_impl('https://www.example.com'))

    # unregister another pattern (that doesn't exist)
    sopel.unregister_url_callback(r'http://localhost', url_handler)

    # the existing pattern still work
    assert list(sopel._search_url_callbacks_impl('https://www.example.com'))


def test_unregister_url_callback_compiled_pattern(tmpconfig):
    """Test unregister_url_callback works with a compiled regex."""
    test_pattern = r'https://(www\.)?example\.com'
    url_regex = re.compile(test_pattern)

    def url_handler(*args, **kwargs):
        return None

    sopel = bot.Sopel(tmpconfig, daemon=False)

    # now register a pattern, make sure it still work
    sopel.register_url_callback(test_pattern, url_handler)
    assert list(sopel._search_url_callbacks_impl('https://www.example.com'))

    # unregister using the compiled version
    sopel.unregister_url_callback(url_regex, url_handler)

    assert not list(sopel._search_url_callbacks_impl('https://www.example.com'))


def test_multiple_url_callback(tmpconfig):
    """Test multiple URL callbacks for the same URL."""
    test_pattern_example = r'https://(www\.)?example\.com'
    test_pattern_global = r'https://.*\.com'

    def url_handler(*args, **kwargs):
        return None

    def url_handler_global(*args, **kwargs):
        return None

    sopel = bot.Sopel(tmpconfig, daemon=False)
    sopel.register_url_callback(test_pattern_example, url_handler)
    sopel.register_url_callback(test_pattern_global, url_handler_global)

    results = list(sopel._search_url_callbacks_impl('https://example.com'))
    assert len(results) == 2
    handlers = [result[0] for result in results]

    assert url_handler in handlers
    assert url_handler_global in handlers

    # now unregister one of them: the other must still work
    sopel.unregister_url_callback(test_pattern_example, url_handler)

    results = list(sopel._search_url_callbacks_impl('https://example.com'))
    assert len(results) == 1, 'Exactly one handler must remain'
    assert url_handler_global in results[0], 'Wrong remaining handler'


# Added for Sopel 8; can be removed in Sopel 9
def test_manual_url_callback_not_found(tmpconfig):
    """Test that the bot now ignores manually registered URL callbacks."""
    # Sopel 8.0 no longer supports `bot.memory['url_callbacks'], and this test
    # is to make sure that it *really* no longer works.
    test_pattern = r'https://(www\.)?example\.com'

    def url_handler(*args, **kwargs):
        return None

    sopel = bot.Sopel(tmpconfig, daemon=False)
    sopel.memory['url_callbacks'] = SopelMemory()

    # register a callback manually
    sopel.memory['url_callbacks'][re.compile(test_pattern)] = url_handler
    results = list(sopel._search_url_callbacks_impl("https://www.example.com"))
    assert not results, "Manually registered callback must not be found"


# -----------------------------------------------------------------------------
# Test various message handling

def test_ignore_replay_servertime(mockbot):
    """Test ignoring messages sent before bot joined a channel."""
    @plugin.rule("$nickname!")
    @plugin.thread(False)
    def ping(bot, trigger):
        bot.say(trigger.nick + "!")

    ping.plugin_name = "testplugin"
    mockbot.register_callables([ping])

    test_channel = Identifier("#test")
    mockbot.channels[test_channel] = target.Channel(test_channel)
    mockbot.channels[test_channel].join_time = datetime(
        2021, 6, 1, 12, 0, 0, 15000, tzinfo=timezone.utc
    )

    # replay
    mockbot.on_message(
        "@time=2021-06-01T12:00:00.010Z :user!user@user PRIVMSG #test :TestBot!"
    )
    assert mockbot.backend.message_sent == []

    # new message
    mockbot.on_message(
        "@time=2021-06-01T12:00:00.020Z :user2!user2@user PRIVMSG #test :TestBot!"
    )
    assert mockbot.backend.message_sent == rawlist("PRIVMSG #test :user2!")


def test_user_quit(
    tmpconfig: Config,
    botfactory: BotFactory,
    ircfactory: IRCFactory,
    userfactory: UserFactory,
):
    """Test the behavior of a QUIT message from another user."""
    mockbot: bot.Sopel = botfactory.preloaded(tmpconfig)
    server: MockIRCServer = ircfactory(mockbot, True)
    server.channel_joined('#test', ['MrPraline'])
    mockbot.backend.clear_message_sent()

    mockuser = userfactory('MrPraline', 'praline', 'example.com')

    assert 'MrPraline' in mockbot.channels['#test'].users

    servertime = datetime.now(timezone.utc) + timedelta(seconds=10)
    mockbot.on_message(
        "@time={servertime} :{user} QUIT :Ping timeout: 246 seconds".format(
            servertime=servertime.strftime('%Y-%m-%dT%H:%M:%SZ'),
            user=mockuser.prefix,
        )
    )

    assert 'MrPraline' not in mockbot.channels['#test'].users
