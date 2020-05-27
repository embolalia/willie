# coding=utf-8
"""Tests for the ``sopel.plugins.rules`` module."""
from __future__ import absolute_import, division, print_function, unicode_literals


import re


import pytest


from sopel import bot, loader, module, trigger
from sopel.plugins import rules
from sopel.tests import rawlist


TMP_CONFIG = """
[core]
owner = testnick
nick = TestBot
alias_nicks =
    AliasBot
    SupBot
enable = coretasks
"""


@pytest.fixture
def tmpconfig(configfactory):
    return configfactory('test.cfg', TMP_CONFIG)


@pytest.fixture
def mockbot(tmpconfig, botfactory):
    return botfactory(tmpconfig)


# -----------------------------------------------------------------------------
# test for :class:`Manager`

def test_manager_rule(mockbot):
    regex = re.compile('.*')
    rule = rules.Rule([regex], plugin='testplugin', label='testrule')
    manager = rules.Manager()
    manager.register(rule)

    assert manager.has_rule('testrule')
    assert manager.has_rule('testrule', plugin='testplugin')
    assert not manager.has_rule('testrule', plugin='not-plugin')

    line = ':Foo!foo@example.com PRIVMSG #sopel :Hello, world'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)

    items = manager.get_triggered_rules(mockbot, pretrigger)
    assert len(items) == 1, 'Exactly one rule must match'

    result = items[0]
    assert len(result) == 2, 'Result must contain two items: (rule, match)'

    result_rule, result_match = items[0]
    assert result_rule == rule
    assert result_match.group(0) == 'Hello, world'


def test_manager_command(mockbot):
    command = rules.Command('hello', prefix=r'\.', plugin='testplugin')
    manager = rules.Manager()
    manager.register_command(command)

    line = ':Foo!foo@example.com PRIVMSG #sopel :.hello'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)

    items = manager.get_triggered_rules(mockbot, pretrigger)
    assert len(items) == 1, 'Exactly one command must match'
    result = items[0]
    assert len(result) == 2, 'Result must contain two items: (command, match)'

    result_rule, result_match = items[0]
    assert result_rule == command
    assert result_match.group(0) == '.hello'
    assert result_match.group(1) == 'hello'

    assert list(manager.get_all_commands()) == [
        ('testplugin', {'hello': command}),
    ]
    assert list(manager.get_all_nick_commands()) == []


def test_manager_nick_command(mockbot):
    command = rules.NickCommand('Bot', 'hello', plugin='testplugin')
    manager = rules.Manager()
    manager.register_nick_command(command)

    line = ':Foo!foo@example.com PRIVMSG #sopel :Bot: hello'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)

    items = manager.get_triggered_rules(mockbot, pretrigger)
    assert len(items) == 1, 'Exactly one command must match'
    result = items[0]
    assert len(result) == 2, 'Result must contain two items: (command, match)'

    result_rule, result_match = items[0]
    assert result_rule == command
    assert result_match.group(0) == 'Bot: hello'
    assert result_match.group(1) == 'hello'

    assert list(manager.get_all_commands()) == []
    assert list(manager.get_all_nick_commands()) == [
        ('testplugin', {'hello': command}),
    ]


def test_manager_action_command(mockbot):
    command = rules.ActionCommand('hello', plugin='testplugin')
    manager = rules.Manager()
    manager.register_action_command(command)

    line = ':Foo!foo@example.com PRIVMSG #sopel :\x01ACTION hello\x01'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)

    items = manager.get_triggered_rules(mockbot, pretrigger)
    assert len(items) == 1, 'Exactly one command must match'
    result = items[0]
    assert len(result) == 2, 'Result must contain two items: (command, match)'

    result_rule, result_match = items[0]
    assert result_rule == command
    assert result_match.group(0) == 'hello'
    assert result_match.group(1) == 'hello'

    assert list(manager.get_all_commands()) == []
    assert list(manager.get_all_nick_commands()) == []


def test_manager_rule_and_command(mockbot):
    regex = re.compile('.*')
    rule = rules.Rule([regex], plugin='testplugin', label='testrule')
    command = rules.Command('hello', prefix=r'\.', plugin='testplugin')
    manager = rules.Manager()
    manager.register(rule)
    manager.register_command(command)

    line = ':Foo!foo@example.com PRIVMSG #sopel :.hello'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)

    items = manager.get_triggered_rules(mockbot, pretrigger)
    assert len(items) == 2, 'Both rules (anonymous rule & command) must match'
    rule_result, command_result = items

    assert rule_result[0] == rule, 'First match must be the anonymous rule'
    assert command_result[0] == command, 'Second match must be the command'

    assert list(manager.get_all_commands()) == [
        ('testplugin', {'hello': command}),
    ]
    assert list(manager.get_all_nick_commands()) == []


def test_manager_unregister_plugin(mockbot):
    regex = re.compile('.*')
    a_rule = rules.Rule([regex], plugin='plugin_a', label='the_rule')
    b_rule = rules.Rule([regex], plugin='plugin_b', label='the_rule')
    a_command = rules.Command('hello', prefix=r'\.', plugin='plugin_a')
    b_command = rules.Command('hello', prefix=r'\.', plugin='plugin_b')

    manager = rules.Manager()
    manager.register(a_rule)
    manager.register_command(a_command)
    manager.register(b_rule)
    manager.register_command(b_command)

    line = ':Foo!foo@example.com PRIVMSG #sopel :.hello'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)

    items = manager.get_triggered_rules(mockbot, pretrigger)
    assert len(items) == 4, 'All 4 rules must match'
    assert manager.has_command('hello')

    manager.unregister_plugin('plugin_a')
    assert manager.has_rule('the_rule')
    assert not manager.has_rule('the_rule', plugin='plugin_a')
    assert manager.has_command('hello')
    assert not manager.has_command('hello', plugin='plugin_a')

    items = manager.get_triggered_rules(mockbot, pretrigger)
    assert len(items) == 2, 'Only 2 must match by now'
    assert b_rule in items[0]
    assert b_command in items[1]


def test_manager_rule_trigger_on_event(mockbot):
    regex = re.compile('.*')
    rule_default = rules.Rule([regex], plugin='testplugin', label='testrule')
    rule_events = rules.Rule(
        [regex],
        plugin='testplugin',
        label='testrule',
        events=['PRIVMSG', 'NOTICE'])
    manager = rules.Manager()
    manager.register(rule_default)
    manager.register(rule_events)

    line = ':Foo!foo@example.com PRIVMSG #sopel :Hello, world'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)

    items = manager.get_triggered_rules(mockbot, pretrigger)
    assert len(items) == 2, 'Exactly two rules must match'

    # rules are match in their registration order
    assert rule_default in items[0]
    assert rule_events in items[1]

    line = ':Foo!foo@example.com NOTICE #sopel :Hello, world'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)

    items = manager.get_triggered_rules(mockbot, pretrigger)
    assert len(items) == 1, 'Exactly one rule must match'

    assert rule_events in items[0]


def test_manager_has_command():
    command = rules.Command('hello', prefix=r'\.', plugin='testplugin')
    manager = rules.Manager()
    manager.register_command(command)

    assert manager.has_command('hello')
    assert not manager.has_command('hi')


def test_manager_has_command_aliases():
    command = rules.Command(
        'hello', prefix=r'\.', aliases=['hi'], plugin='testplugin')
    manager = rules.Manager()
    manager.register_command(command)

    assert manager.has_command('hello')
    assert not manager.has_command('hi')
    assert manager.has_command('hi', follow_alias=True)
    assert not manager.has_command('unknown', follow_alias=True)


def test_manager_has_nick_command():
    command = rules.NickCommand('Bot', 'hello', plugin='testplugin')
    manager = rules.Manager()
    manager.register_nick_command(command)

    assert manager.has_nick_command('hello')
    assert not manager.has_nick_command('hi')
    assert not manager.has_command('hello')


def test_manager_has_nick_command_aliases():
    command = rules.NickCommand(
        'Bot', 'hello', plugin='testplugin', aliases=['hi'])
    manager = rules.Manager()
    manager.register_nick_command(command)

    assert manager.has_nick_command('hello')
    assert not manager.has_nick_command('hi')
    assert manager.has_nick_command('hello', follow_alias=True)
    assert manager.has_nick_command('hi', follow_alias=True)
    assert not manager.has_nick_command('unknown', follow_alias=True)


def test_manager_has_action_command():
    command = rules.ActionCommand('hello', plugin='testplugin')
    manager = rules.Manager()
    manager.register_action_command(command)

    assert manager.has_action_command('hello')
    assert not manager.has_action_command('hi')
    assert not manager.has_command('hello')


def test_manager_has_action_command_aliases():
    command = rules.ActionCommand('hello', plugin='testplugin', aliases=['hi'])
    manager = rules.Manager()
    manager.register_action_command(command)

    assert manager.has_action_command('hello')
    assert not manager.has_action_command('hi')
    assert manager.has_action_command('hello', follow_alias=True)
    assert manager.has_action_command('hi', follow_alias=True)
    assert not manager.has_action_command('unknown', follow_alias=True)


# -----------------------------------------------------------------------------
# test for :class:`Rule`


def test_rule_str():
    regex = re.compile(r'.*')
    rule = rules.Rule([regex], plugin='testplugin', label='testrule')

    assert str(rule) == '<Rule testplugin.testrule (1)>'


def test_rule_str_no_plugin():
    regex = re.compile(r'.*')
    rule = rules.Rule([regex], label='testrule')

    assert str(rule) == '<Rule (no-plugin).testrule (1)>'


def test_rule_str_no_label():
    regex = re.compile(r'.*')
    rule = rules.Rule([regex], plugin='testplugin')

    assert str(rule) == '<Rule testplugin.(anonymous) (1)>'


def test_rule_str_no_plugin_label():
    regex = re.compile(r'.*')
    rule = rules.Rule([regex])

    assert str(rule) == '<Rule (no-plugin).(anonymous) (1)>'


def test_rule_get_rule_label(mockbot):
    regex = re.compile(r'.*')

    rule = rules.Rule([regex], label='testlabel')
    assert rule.get_rule_label() == 'testlabel'


def test_rule_get_rule_label_undefined(mockbot):
    regex = re.compile('.*')

    rule = rules.Rule([regex])
    with pytest.raises(RuntimeError):
        rule.get_rule_label()


def test_rule_get_rule_label_handler(mockbot):
    regex = re.compile('.*')

    def the_handler_rule(wrapped, trigger):
        pass

    rule = rules.Rule([regex], handler=the_handler_rule)
    assert rule.get_rule_label() == 'the_handler_rule'


def test_rule_get_plugin_name():
    regex = re.compile('.*')

    rule = rules.Rule([regex])
    assert rule.get_plugin_name() is None

    rule = rules.Rule([regex], plugin='testplugin')
    assert rule.get_plugin_name() == 'testplugin'


def test_rule_get_usages():
    usages = (
        {
            'example': 'hello',
            'result': ['Hi!'],
            'is_pattern': False,
            'is_help': True,
            'is_private_message': False,
            'is_admin': False,
            'is_owner': False,
        },
    )
    regex = re.compile('.*')
    rule = rules.Rule([regex], usages=usages)

    assert rule.get_usages() == (
        {
            'text': 'hello',
            'result': ['Hi!'],
            'is_pattern': False,
            'is_owner': False,
            'is_admin': False,
            'is_private_message': False,
        },
    )


def test_rule_get_test_parameters():
    test_parameters = (
        {
            'admin': False,
            'example': 'hello',
            'help': True,
            'privmsg': False,
            'result': 'hi!',
        },
    )
    regex = re.compile('.*')
    rule = rules.Rule([regex], tests=test_parameters)

    assert rule.get_test_parameters() == test_parameters


def test_rule_get_doc():
    doc = 'This is the doc you are looking for.'
    regex = re.compile('.*')
    rule = rules.Rule([regex], doc=doc)

    assert rule.get_doc() == doc


def test_rule_get_priority():
    regex = re.compile('.*')

    rule = rules.Rule([regex])
    assert rule.get_priority() == rules.PRIORITY_MEDIUM

    rule = rules.Rule([regex], priority=rules.PRIORITY_LOW)
    assert rule.get_priority() == rules.PRIORITY_LOW


def test_rule_get_output_prefix():
    regex = re.compile('.*')

    rule = rules.Rule([regex])
    assert rule.get_output_prefix() == ''

    rule = rules.Rule([regex], output_prefix='[plugin] ')
    assert rule.get_output_prefix() == '[plugin] '


def test_rule_match(mockbot):
    line = ':Foo!foo@example.com PRIVMSG #sopel :Hello, world'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    regex = re.compile('.*')

    rule = rules.Rule([regex])
    matches = list(rule.match(mockbot, pretrigger))
    assert len(matches) == 1, 'Exactly one match must be found'

    match = matches[0]
    assert match.group(0) == 'Hello, world'

    rule = rules.Rule([regex], events=['JOIN'])
    assert not list(rule.match(mockbot, pretrigger))


def test_rule_match_privmsg_group_match(mockbot):
    line = ':Foo!foo@example.com PRIVMSG #sopel :Hello, world'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    regex = re.compile(r'hello,?\s(\w+)', re.IGNORECASE)

    rule = rules.Rule([regex])
    matches = list(rule.match(mockbot, pretrigger))
    assert len(matches) == 1, 'Exactly one match must be found'

    match = matches[0]
    assert match.group(0) == 'Hello, world'
    assert match.group(1) == 'world'


def test_rule_match_privmsg_action(mockbot):
    line = ':Foo!foo@example.com PRIVMSG #sopel :\x01ACTION Hello, world\x01'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    regex = re.compile('.*')

    rule = rules.Rule([regex])
    matches = list(rule.match(mockbot, pretrigger))
    assert len(matches) == 1, 'Exactly one match must be found'

    match = matches[0]
    assert match.group(0) == 'Hello, world'

    rule = rules.Rule([regex], intents=[re.compile(r'ACTION')])
    matches = list(rule.match(mockbot, pretrigger))
    assert len(matches) == 1, 'Exactly one match must be found'

    match = matches[0]
    assert match.group(0) == 'Hello, world'

    rule = rules.Rule([regex], intents=[re.compile(r'VERSION')])
    assert not list(rule.match(mockbot, pretrigger))


def test_rule_match_privmsg_echo(mockbot):
    line = ':TestBot!sopel@example.com PRIVMSG #sopel :Hi!'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    regex = re.compile(r'.*')

    rule = rules.Rule([regex])
    assert not list(rule.match(mockbot, pretrigger))

    rule = rules.Rule([regex], allow_echo=True)
    matches = list(rule.match(mockbot, pretrigger))
    assert len(matches) == 1, 'Exactly one match must be found'

    match = matches[0]
    assert match.group(0) == 'Hi!'


def test_rule_match_join(mockbot):
    line = ':Foo!foo@example.com JOIN #sopel'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    regex = re.compile(r'.*')

    rule = rules.Rule([regex])
    assert not list(rule.match(mockbot, pretrigger))

    rule = rules.Rule([regex], events=['JOIN'])
    matches = list(rule.match(mockbot, pretrigger))
    assert len(matches) == 1, 'Exactly one match must be found'

    match = matches[0]
    assert match.group(0) == '#sopel'


def test_rule_match_event():
    regex = re.compile('.*')
    rule = rules.Rule([regex])
    assert rule.match_event('PRIVMSG')
    assert not rule.match_event('JOIN')
    assert not rule.match_event(None)

    rule = rules.Rule([regex], events=['JOIN'])
    assert not rule.match_event('PRIVMSG')
    assert rule.match_event('JOIN')


def test_rule_match_intent():
    regex = re.compile('.*')

    rule = rules.Rule([regex])
    assert rule.match_intent(None)

    intents = [
        re.compile('VERSION'),
    ]
    rule = rules.Rule([regex], intents=intents)
    assert not rule.match_intent(None)
    assert rule.match_intent('VERSION')
    assert not rule.match_intent('PING')


def test_rule_echo_message():
    regex = re.compile('.*')

    rule = rules.Rule([regex])
    assert not rule.allow_echo()

    rule = rules.Rule([regex], allow_echo=True)
    assert rule.allow_echo()


def test_rule_is_threaded():
    regex = re.compile('.*')

    rule = rules.Rule([regex])
    assert rule.is_threaded()

    rule = rules.Rule([regex], threaded=False)
    assert not rule.is_threaded()


def test_rule_unblockable():
    regex = re.compile('.*')

    rule = rules.Rule([regex])
    assert not rule.is_unblockable()

    rule = rules.Rule([regex], unblockable=True)
    assert rule.is_unblockable()


def test_rule_parse_wildcard():
    # match everything
    regex = re.compile(r'.*')

    rule = rules.Rule([regex])
    assert list(rule.parse('')), 'Wildcard rule must parse empty text'
    assert list(rule.parse('Hello, world!'))


def test_rule_parse_starts_with():
    # match a text starting with a string
    regex = re.compile(r'Hello')

    rule = rules.Rule([regex])
    assert list(rule.parse('Hello, world!')), 'Partial match must work'
    assert not list(rule.parse('World, Hello!')), (
        'Partial match works only from the start of the text to match')


def test_rule_parse_pattern():
    # playing with regex
    regex = re.compile(r'(\w+),? world!$')

    rule = rules.Rule([regex])
    results = list(rule.parse('Hello, world!'))
    assert len(results) == 1, 'Exactly one parse result must be found.'

    result = results[0]
    assert result.group(0) == 'Hello, world!'
    assert result.group(1) == 'Hello'

    results = list(rule.parse('Hello world!'))
    assert len(results) == 1, 'Exactly one parse result must be found.'

    result = results[0]
    assert result.group(0) == 'Hello world!'
    assert result.group(1) == 'Hello'


def test_rule_execute(mockbot):
    regex = re.compile(r'.*')
    rule = rules.Rule([regex])

    line = ':Foo!foo@example.com PRIVMSG #sopel :Hello, world'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    matches = list(rule.match(mockbot, pretrigger))
    match = matches[0]
    match_trigger = trigger.Trigger(
        mockbot.settings, pretrigger, match, account=None)

    with pytest.raises(RuntimeError):
        rule.execute(mockbot, match_trigger)

    def handler(wrapped, trigger):
        wrapped.say('Hi!')

    rule = rules.Rule([regex], handler=handler)
    matches = list(rule.match(mockbot, pretrigger))
    match = matches[0]
    match_trigger = trigger.Trigger(
        mockbot.settings, pretrigger, match, account=None)
    wrapped = bot.SopelWrapper(mockbot, match_trigger)
    rule.execute(wrapped, match_trigger)

    assert mockbot.backend.message_sent == rawlist('PRIVMSG #sopel :Hi!')


def test_rule_from_callable(mockbot):
    # prepare callable
    @module.rule(r'hello', r'hi', r'hey', r'hello|hi')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)
    handler.plugin_name = 'testplugin'

    # create rule from a clean callable
    rule = rules.Rule.from_callable(mockbot.settings, handler)
    assert str(rule) == '<Rule testplugin.handler (4)>'

    # match on "Hello" twice
    line = ':Foo!foo@example.com PRIVMSG #sopel :Hello, world'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 2, 'Exactly 2 rules must match'
    assert all(result.group(0) == 'Hello' for result in results)

    # match on "hi" twice
    line = ':Foo!foo@example.com PRIVMSG #sopel :hi!'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 2, 'Exactly 2 rules must match'
    assert all(result.group(0) == 'hi' for result in results)

    # match on "hey" twice
    line = ':Foo!foo@example.com PRIVMSG #sopel :hey how are you doing?'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'Exactly 1 rule must match'
    assert results[0].group(0) == 'hey'


# -----------------------------------------------------------------------------
# test classmethod :meth:`Rule.kwargs_from_callable`

def test_kwargs_from_callable(mockbot):
    # prepare callable
    @module.rule(r'hello', r'hi', r'hey', r'hello|hi')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)
    handler.plugin_name = 'testplugin'  # added by the Plugin handler manually

    # get kwargs
    kwargs = rules.Rule.kwargs_from_callable(handler)

    assert 'plugin' in kwargs
    assert 'label' in kwargs
    assert 'priority' in kwargs
    assert 'events' in kwargs
    assert 'intents' in kwargs
    assert 'allow_echo' in kwargs
    assert 'threaded' in kwargs
    assert 'output_prefix' in kwargs
    assert 'unblockable' in kwargs
    assert 'usages' in kwargs
    assert 'tests' in kwargs
    assert 'doc' in kwargs

    assert kwargs['plugin'] == 'testplugin'
    assert kwargs['label'] is None
    assert kwargs['priority'] == rules.PRIORITY_MEDIUM
    assert kwargs['events'] == ['PRIVMSG']
    assert kwargs['intents'] == []
    assert kwargs['allow_echo'] is False
    assert kwargs['threaded'] is True
    assert kwargs['output_prefix'] == ''
    assert kwargs['unblockable'] is False
    assert kwargs['usages'] == tuple()
    assert kwargs['tests'] == tuple()
    assert kwargs['doc'] is None


def test_kwargs_from_callable_label(mockbot):
    # prepare callable
    @module.rule(r'hello', r'hi', r'hey', r'hello|hi')
    @module.label('hello_rule')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # get kwargs
    kwargs = rules.Rule.kwargs_from_callable(handler)
    assert 'label' in kwargs
    assert kwargs['label'] == 'hello_rule'


def test_kwargs_from_callable_priority(mockbot):
    # prepare callable
    @module.rule(r'hello', r'hi', r'hey', r'hello|hi')
    @module.priority(rules.PRIORITY_LOW)
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # get kwargs
    kwargs = rules.Rule.kwargs_from_callable(handler)
    assert 'priority' in kwargs
    assert kwargs['priority'] == rules.PRIORITY_LOW


def test_kwargs_from_callable_event(mockbot):
    # prepare callable
    @module.rule(r'hello', r'hi', r'hey', r'hello|hi')
    @module.event('PRIVMSG', 'NOTICE')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # get kwargs
    kwargs = rules.Rule.kwargs_from_callable(handler)
    assert 'events' in kwargs
    assert kwargs['events'] == ['PRIVMSG', 'NOTICE']


def test_kwargs_from_callable_intent(mockbot):
    # prepare callable
    @module.rule(r'hello', r'hi', r'hey', r'hello|hi')
    @module.intent('ACTION')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # get kwargs
    kwargs = rules.Rule.kwargs_from_callable(handler)
    assert 'intents' in kwargs
    assert kwargs['intents'] == [re.compile(r'ACTION', re.IGNORECASE)]


def test_kwargs_from_callable_allow_echo(mockbot):
    # prepare callable
    @module.rule(r'hello', r'hi', r'hey', r'hello|hi')
    @module.echo
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # get kwargs
    kwargs = rules.Rule.kwargs_from_callable(handler)
    assert 'allow_echo' in kwargs
    assert kwargs['allow_echo'] is True


def test_kwargs_from_callable_threaded(mockbot):
    # prepare callable
    @module.rule(r'hello', r'hi', r'hey', r'hello|hi')
    @module.thread(False)
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # get kwargs
    kwargs = rules.Rule.kwargs_from_callable(handler)
    assert 'threaded' in kwargs
    assert kwargs['threaded'] is False


def test_kwargs_from_callable_unblockable(mockbot):
    # prepare callable
    @module.rule(r'hello', r'hi', r'hey', r'hello|hi')
    @module.unblockable
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # get kwargs
    kwargs = rules.Rule.kwargs_from_callable(handler)
    assert 'unblockable' in kwargs
    assert kwargs['unblockable'] is True


def test_kwargs_from_callable_rate_limit(mockbot):
    # prepare callable
    @module.rule(r'hello', r'hi', r'hey', r'hello|hi')
    @module.rate(user=20, channel=30, server=40)
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # get kwargs
    kwargs = rules.Rule.kwargs_from_callable(handler)
    assert 'rate_limit' in kwargs
    assert 'channel_rate_limit' in kwargs
    assert 'global_rate_limit' in kwargs
    assert kwargs['rate_limit'] == 20
    assert kwargs['channel_rate_limit'] == 30
    assert kwargs['global_rate_limit'] == 40


def test_kwargs_from_callable_examples(mockbot):
    # prepare callable
    @module.rule(r'hello', r'hi', r'hey', r'hello|hi')
    @module.example('hello')
    def handler(wrapped, trigger):
        """This is the doc you are looking for."""
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # get kwargs
    kwargs = rules.Rule.kwargs_from_callable(handler)

    # asserts
    expected = {
        'example': 'hello',
        'result': None,
        'is_pattern': False,
        'is_help': False,
        'is_owner': False,
        'is_admin': False,
        'is_private_message': False,
    }

    assert 'usages' in kwargs
    assert 'tests' in kwargs
    assert 'doc' in kwargs
    assert kwargs['usages'] == (expected,)
    assert kwargs['tests'] == tuple(), 'There must be no test'
    assert kwargs['doc'] == 'This is the doc you are looking for.'


def test_kwargs_from_callable_examples_test(mockbot):
    # prepare callable
    @module.rule(r'hello', r'hi', r'hey', r'hello|hi')
    @module.example('hi', 'Hi!')
    @module.example('hello', 'Hi!')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # get kwargs
    kwargs = rules.Rule.kwargs_from_callable(handler)

    # asserts
    expected = {
        'example': 'hello',
        'result': ['Hi!'],
        'is_pattern': False,
        'is_help': False,
        'is_owner': False,
        'is_admin': False,
        'is_private_message': False,
    }
    expected_tests = (
        {
            'example': 'hello',
            'result': ['Hi!'],
            'is_pattern': False,
            'is_help': False,
            'is_owner': False,
            'is_admin': False,
            'is_private_message': False,
        },
        {
            'example': 'hi',
            'result': ['Hi!'],
            'is_pattern': False,
            'is_help': False,
            'is_owner': False,
            'is_admin': False,
            'is_private_message': False,
        },
    )

    assert 'usages' in kwargs
    assert 'tests' in kwargs
    assert 'doc' in kwargs
    assert kwargs['usages'] == (expected,), 'The first example must be used'
    assert kwargs['tests'] == expected_tests
    assert kwargs['doc'] is None


def test_kwargs_from_callable_examples_help(mockbot):
    # prepare callable
    @module.rule(r'hello', r'hi', r'hey', r'hello|hi')
    @module.example('hi', user_help=True)
    @module.example('hey', 'Hi!')
    @module.example('hello', 'Hi!', user_help=True)
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # get kwargs
    kwargs = rules.Rule.kwargs_from_callable(handler)

    # asserts
    expected_usages = (
        {
            'example': 'hello',
            'result': ['Hi!'],
            'is_pattern': False,
            'is_help': True,
            'is_owner': False,
            'is_admin': False,
            'is_private_message': False,
        },
        {
            'example': 'hi',
            'result': None,
            'is_pattern': False,
            'is_help': True,
            'is_owner': False,
            'is_admin': False,
            'is_private_message': False,
        },
    )
    expected_tests = (
        {
            'example': 'hello',
            'result': ['Hi!'],
            'is_pattern': False,
            'is_help': True,
            'is_owner': False,
            'is_admin': False,
            'is_private_message': False,
        },
        {
            'example': 'hey',
            'result': ['Hi!'],
            'is_pattern': False,
            'is_help': False,
            'is_owner': False,
            'is_admin': False,
            'is_private_message': False,
        },
    )

    assert 'usages' in kwargs
    assert 'tests' in kwargs
    assert 'doc' in kwargs
    assert kwargs['usages'] == expected_usages
    assert kwargs['tests'] == expected_tests
    assert kwargs['doc'] is None


def test_kwargs_from_callable_examples_doc(mockbot):
    # prepare callable
    @module.rule(r'hello', r'hi', r'hey', r'hello|hi')
    @module.example('hello')
    def handler(wrapped, trigger):
        """This is the doc you are looking for.

        And now with extended text, for testing purpose only.
        """
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # get kwargs
    kwargs = rules.Rule.kwargs_from_callable(handler)

    # asserts
    expected_usages = (
        {
            'example': 'hello',
            'result': None,
            'is_pattern': False,
            'is_help': False,
            'is_owner': False,
            'is_admin': False,
            'is_private_message': False,
        },
    )

    assert 'usages' in kwargs
    assert 'tests' in kwargs
    assert 'doc' in kwargs
    assert kwargs['usages'] == expected_usages
    assert kwargs['tests'] == tuple(), 'There must be no test'
    assert kwargs['doc'] == (
        'This is the doc you are looking for.\n'
        '\n'
        'And now with extended text, for testing purpose only.'
    ), 'The docstring must have been cleaned.'


# -----------------------------------------------------------------------------
# test of rate-limit features

def test_rule_rate_limit(mockbot, triggerfactory):
    def handler(bot, trigger):
        return 'hello'

    wrapper = triggerfactory.wrapper(
        mockbot, ':Foo!foo@example.com PRIVMSG #channel :test message')
    mocktrigger = wrapper._trigger

    regex = re.compile(r'.*')
    rule = rules.Rule(
        [regex],
        handler=handler,
        rate_limit=20,
        global_rate_limit=20,
        channel_rate_limit=20,
    )
    assert rule.is_rate_limited(mocktrigger.nick) is False
    assert rule.is_channel_rate_limited(mocktrigger.sender) is False
    assert rule.is_global_rate_limited() is False

    rule.execute(mockbot, mocktrigger)
    assert rule.is_rate_limited(mocktrigger.nick) is True
    assert rule.is_channel_rate_limited(mocktrigger.sender) is True
    assert rule.is_global_rate_limited() is True


def test_rule_rate_limit_no_limit(mockbot, triggerfactory):
    def handler(bot, trigger):
        return 'hello'

    wrapper = triggerfactory.wrapper(
        mockbot, ':Foo!foo@example.com PRIVMSG #channel :test message')
    mocktrigger = wrapper._trigger

    regex = re.compile(r'.*')
    rule = rules.Rule(
        [regex],
        handler=handler,
        rate_limit=0,
        global_rate_limit=0,
        channel_rate_limit=0,
    )
    assert rule.is_rate_limited(mocktrigger.nick) is False
    assert rule.is_channel_rate_limited(mocktrigger.sender) is False
    assert rule.is_global_rate_limited() is False

    rule.execute(mockbot, mocktrigger)
    assert rule.is_rate_limited(mocktrigger.nick) is False
    assert rule.is_channel_rate_limited(mocktrigger.sender) is False
    assert rule.is_global_rate_limited() is False


def test_rule_rate_limit_ignore_rate_limit(mockbot, triggerfactory):
    def handler(bot, trigger):
        return rules.IGNORE_RATE_LIMIT

    wrapper = triggerfactory.wrapper(
        mockbot, ':Foo!foo@example.com PRIVMSG #channel :test message')
    mocktrigger = wrapper._trigger

    regex = re.compile(r'.*')
    rule = rules.Rule(
        [regex],
        handler=handler,
        rate_limit=20,
        global_rate_limit=20,
        channel_rate_limit=20,
    )
    assert rule.is_rate_limited(mocktrigger.nick) is False
    assert rule.is_channel_rate_limited(mocktrigger.sender) is False
    assert rule.is_global_rate_limited() is False

    rule.execute(mockbot, mocktrigger)
    assert rule.is_rate_limited(mocktrigger.nick) is False
    assert rule.is_channel_rate_limited(mocktrigger.sender) is False
    assert rule.is_global_rate_limited() is False


# -----------------------------------------------------------------------------
# test for :class:`sopel.plugins.rules.Command`


def test_command_str():
    rule = rules.Command('hello', r'\.', plugin='testplugin')
    assert str(rule) == '<Command testplugin.hello []>'


def test_command_str_no_plugin():
    rule = rules.Command('hello', r'\.')
    assert str(rule) == '<Command (no-plugin).hello []>'


def test_command_str_alias():
    rule = rules.Command('hello', r'\.', plugin='testplugin', aliases=['hi'])
    assert str(rule) == '<Command testplugin.hello [hi]>'

    rule = rules.Command(
        'hello', r'\.', plugin='testplugin', aliases=['hi', 'hey'])
    assert str(rule) == '<Command testplugin.hello [hi|hey]>'


def test_command_get_rule_label(mockbot):
    rule = rules.Command('hello', r'\.')
    assert rule.get_rule_label() == 'hello'


def test_command_get_usages():
    usages = (
        {
            'example': '.hello',  # using default prefix
            'result': ['Hi!'],
            'is_pattern': False,
            'is_help': True,
            'is_owner': False,
            'is_admin': False,
            'is_private_message': False,
        },
        {
            'example': ';hi',  # using help-prefix
            'result': None,
            'is_pattern': False,
            'is_help': True,
            'is_owner': False,
            'is_admin': False,
            'is_private_message': False,
        },
        {
            'not_example': 'This will be ignored because no example key',
            'result': None,
            'is_pattern': False,
            'is_help': True,
            'is_owner': False,
            'is_admin': False,
            'is_private_message': False,
        },
    )

    rule = rules.Command(
        'hello', r';',
        help_prefix=';',
        aliases=['hi'],
        usages=usages,
    )

    assert rule.get_usages() == (
        {
            'text': ';hello',
            'result': ['Hi!'],
            'is_pattern': False,
            'is_owner': False,
            'is_admin': False,
            'is_private_message': False,
        },
        {
            'text': ';hi',
            'result': None,
            'is_pattern': False,
            'is_owner': False,
            'is_admin': False,
            'is_private_message': False,
        },
    )


def test_command_get_doc():
    doc = 'This is the doc you are looking for.'
    rule = rules.Command('hello', r'\.', doc=doc)

    assert rule.get_doc() == doc


def test_command_has_alias(mockbot):
    rule = rules.Command('hello', r'\.', aliases=['hi'])
    assert rule.has_alias('hi')
    assert not rule.has_alias('hello'), 'The name must not be an alias!'
    assert not rule.has_alias('unknown')


def test_command_match(mockbot):
    line = ':Foo!foo@example.com PRIVMSG #sopel :.hello'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)

    rule = rules.Command('hello', r'\.')
    matches = list(rule.match(mockbot, pretrigger))
    assert len(matches) == 1, 'Exactly one match must be found'

    match = matches[0]
    assert match.group(0) == '.hello'
    assert match.group(1) == 'hello'
    assert match.group(2) is None
    assert match.group(3) is None
    assert match.group(4) is None
    assert match.group(5) is None
    assert match.group(6) is None


def test_command_match_invalid_prefix(mockbot):
    line = ':Foo!foo@example.com PRIVMSG #sopel :.hello'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)

    rule = rules.Command('hello', r'\?')
    assert not list(rule.match(mockbot, pretrigger))


def test_command_match_aliases(mockbot):
    line = ':Foo!foo@example.com PRIVMSG #sopel :.hi'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)

    rule = rules.Command('hello', r'\.', aliases=['hi'])
    assert len(list(rule.match(mockbot, pretrigger))) == 1

    rule = rules.Command('hello', r'\?', aliases=['hi'])
    assert not list(rule.match(mockbot, pretrigger))


def test_command_from_callable(mockbot):
    # prepare callable
    @module.commands('hello', 'hi', 'hey')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # create rule from a clean callable
    rule = rules.Command.from_callable(mockbot.settings, handler)

    # match on ".hello"
    line = ':Foo!foo@example.com PRIVMSG #sopel :.hello'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'Exactly 1 command must match'
    result = results[0]
    assert result.group(0) == '.hello'
    assert result.group(1) == 'hello'

    # match on ".hi"
    line = ':Foo!foo@example.com PRIVMSG #sopel :.hi'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'Exactly 1 command must match'
    result = results[0]
    assert result.group(0) == '.hi'
    assert result.group(1) == 'hi'

    # match on ".hey"
    line = ':Foo!foo@example.com PRIVMSG #sopel :.hey'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'Exactly 1 command must match'
    result = results[0]
    assert result.group(0) == '.hey'
    assert result.group(1) == 'hey'

    # does not match on "hello"
    line = ':Foo!foo@example.com PRIVMSG #sopel :hello'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))
    assert not results

    # does not match on ".bye"
    line = ':Foo!foo@example.com PRIVMSG #sopel :.bye'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))
    assert not results


def test_command_from_callable_invalid(mockbot):
    # prepare callable
    @module.rule(r'.*')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # create rule from a clean callable
    with pytest.raises(RuntimeError):
        rules.Command.from_callable(mockbot.settings, handler)


# -----------------------------------------------------------------------------
# test for :class:`sopel.plugins.rules.NickCommand`


def test_nick_command_str():
    rule = rules.NickCommand('TestBot', 'hello', plugin='testplugin')
    assert str(rule) == '<NickCommand testplugin.hello [] (TestBot [])>'


def test_nick_command_str_no_plugin():
    rule = rules.NickCommand('TestBot', 'hello')
    assert str(rule) == '<NickCommand (no-plugin).hello [] (TestBot [])>'


def test_nick_command_str_alias():
    rule = rules.NickCommand(
        'TestBot', 'hello', plugin='testplugin', aliases=['hi'])
    assert str(rule) == '<NickCommand testplugin.hello [hi] (TestBot [])>'

    rule = rules.NickCommand(
        'TestBot', 'hello', plugin='testplugin', aliases=['hi', 'hey'])
    assert str(rule) == '<NickCommand testplugin.hello [hi|hey] (TestBot [])>'


def test_nick_command_str_nick_alias():
    rule = rules.NickCommand(
        'TestBot', 'hello', nick_aliases=['Alfred'], plugin='testplugin')
    assert str(rule) == '<NickCommand testplugin.hello [] (TestBot [Alfred])>'

    rule = rules.NickCommand(
        'TestBot', 'hello', nick_aliases=['Alfred', 'Joe'], plugin='testplugin')
    assert str(rule) == (
        '<NickCommand testplugin.hello [] (TestBot [Alfred|Joe])>'
    )


def test_nick_command_str_alias_and_nick_alias():
    rule = rules.NickCommand(
        'TestBot', 'hello',
        nick_aliases=['Alfred'],
        aliases=['hi'],
        plugin='testplugin')
    assert str(rule) == (
        '<NickCommand testplugin.hello [hi] (TestBot [Alfred])>'
    )

    rule = rules.NickCommand(
        'TestBot', 'hello',
        nick_aliases=['Alfred', 'Joe'],
        aliases=['hi', 'hey'],
        plugin='testplugin')
    assert str(rule) == (
        '<NickCommand testplugin.hello [hi|hey] (TestBot [Alfred|Joe])>'
    )


def test_nick_command_get_rule_label(mockbot):
    rule = rules.NickCommand('TestBot', 'hello')
    assert rule.get_rule_label() == 'hello'


def test_nick_command_get_usages():
    usages = (
        {
            'example': '$nickname: hello',
            'result': ['Hi!'],
            'is_pattern': False,
            'is_help': True,
            'is_owner': False,
            'is_admin': False,
            'is_private_message': False,
        },
        {
            'not_example': 'This will be ignored because no example key',
            'result': None,
            'is_pattern': False,
            'is_help': True,
            'is_owner': False,
            'is_admin': False,
            'is_private_message': False,
        },
    )

    rule = rules.NickCommand('TestBot', 'hello', usages=usages)

    assert rule.get_usages() == (
        {
            'text': 'TestBot: hello',
            'result': ['Hi!'],
            'is_pattern': False,
            'is_owner': False,
            'is_admin': False,
            'is_private_message': False,
        },
    )


def test_nick_command_get_doc():
    doc = 'This is the doc you are looking for.'
    rule = rules.NickCommand('TestBot', 'hello', doc=doc)

    assert rule.get_doc() == doc


def test_nick_command_match(mockbot):
    line = ':Foo!foo@example.com PRIVMSG #sopel :TestBot: hello'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)

    rule = rules.NickCommand('TestBot', 'hello')
    matches = list(rule.match(mockbot, pretrigger))
    assert len(matches) == 1, 'Exactly one match must be found'

    match = matches[0]
    assert match.group(0) == 'TestBot: hello'
    assert match.group(1) == 'hello'
    assert match.group(2) is None
    assert match.group(3) is None
    assert match.group(4) is None
    assert match.group(5) is None
    assert match.group(6) is None


def test_nick_command_has_alias(mockbot):
    rule = rules.NickCommand('TestBot', 'hello', aliases=['hi'])
    assert rule.has_alias('hi')
    assert not rule.has_alias('hello'), 'The name must not be an alias!'
    assert not rule.has_alias('unknown')


def test_nick_command_from_callable_invalid(mockbot):
    # prepare callable
    @module.rule(r'.*')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # create rule from a clean callable
    with pytest.raises(RuntimeError):
        rules.NickCommand.from_callable(mockbot.settings, handler)


def test_nick_command_from_callable(mockbot):
    # prepare callable
    @module.nickname_commands('hello', 'hi', 'hey')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # create rule from a clean callable
    rule = rules.NickCommand.from_callable(mockbot.settings, handler)

    # match on "$nick: hello"
    line = ':Foo!foo@example.com PRIVMSG #sopel :TestBot: hello'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'Exactly 1 command must match'
    result = results[0]
    assert result.group(0) == 'TestBot: hello'
    assert result.group(1) == 'hello'

    # match on "$nick_alias: hello"
    line = ':Foo!foo@example.com PRIVMSG #sopel :AliasBot: hello'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'Exactly 1 command must match'
    result = results[0]
    assert result.group(0) == 'AliasBot: hello'
    assert result.group(1) == 'hello'

    # match on "$nick_alias: hello"
    line = ':Foo!foo@example.com PRIVMSG #sopel :SupBot: hello'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'Exactly 1 command must match'
    result = results[0]
    assert result.group(0) == 'SupBot: hello'
    assert result.group(1) == 'hello'

    # match on "$nick: hi"
    line = ':Foo!foo@example.com PRIVMSG #sopel :TestBot: hi'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'Exactly 1 command must match'
    result = results[0]
    assert result.group(0) == 'TestBot: hi'
    assert result.group(1) == 'hi'

    # match on "$nick_alias: hi"
    line = ':Foo!foo@example.com PRIVMSG #sopel :AliasBot: hi'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'Exactly 1 command must match'
    result = results[0]
    assert result.group(0) == 'AliasBot: hi'
    assert result.group(1) == 'hi'

    # match on "$nick: hey"
    line = ':Foo!foo@example.com PRIVMSG #sopel :TestBot: hey'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'Exactly 1 command must match'
    result = results[0]
    assert result.group(0) == 'TestBot: hey'
    assert result.group(1) == 'hey'

    # does not match on ".hello"
    line = ':Foo!foo@example.com PRIVMSG #sopel :.hello'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))
    assert not results

    # does not match on "$nick: .hello"
    line = ':Foo!foo@example.com PRIVMSG #sopel :TestBot: .hello'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))
    assert not results

    # does not match on "$nick: bye"
    line = ':Foo!foo@example.com PRIVMSG #sopel :TestBot: bye'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))
    assert not results


# -----------------------------------------------------------------------------
# test for :class:`sopel.plugins.rules.ActionCommand`

def test_action_command_str():
    rule = rules.ActionCommand('hello', plugin='testplugin')
    assert str(rule) == '<ActionCommand testplugin.hello []>'


def test_action_command_str_no_plugin():
    rule = rules.ActionCommand('hello')
    assert str(rule) == '<ActionCommand (no-plugin).hello []>'


def test_action_command_str_alias():
    rule = rules.ActionCommand(
        'hello', plugin='testplugin', aliases=['hi'])
    assert str(rule) == '<ActionCommand testplugin.hello [hi]>'

    rule = rules.ActionCommand(
        'hello', plugin='testplugin', aliases=['hi', 'hey'])
    assert str(rule) == '<ActionCommand testplugin.hello [hi|hey]>'


def test_action_command_get_rule_label(mockbot):
    rule = rules.ActionCommand('hello')
    assert rule.get_rule_label() == 'hello'


def test_action_command_match(mockbot):
    line = ':Foo!foo@example.com PRIVMSG #sopel :\x01ACTION hello\x01'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)

    rule = rules.ActionCommand('hello')
    matches = list(rule.match(mockbot, pretrigger))
    assert len(matches) == 1, 'Exactly one match must be found'

    match = matches[0]
    assert match.group(0) == 'hello'
    assert match.group(1) == 'hello'
    assert match.group(2) is None
    assert match.group(3) is None
    assert match.group(4) is None
    assert match.group(5) is None
    assert match.group(6) is None


def test_action_command_has_alias(mockbot):
    rule = rules.ActionCommand('hello', aliases=['hi'])
    assert rule.has_alias('hi')
    assert not rule.has_alias('hello'), 'The name must not be an alias!'
    assert not rule.has_alias('unknown')


def test_action_command_match_intent(mockbot):
    rule = rules.ActionCommand('hello')
    assert rule.match_intent('ACTION')
    assert not rule.match_intent('VERSION')
    assert not rule.match_intent('PING')

    intents = (re.compile(r'VERSION'), re.compile(r'SOURCE'))
    rule = rules.ActionCommand('hello', intents=intents)
    assert rule.match_intent('ACTION'), 'ActionCommand always match ACTION'
    assert not rule.match_intent('VERSION'), (
        'ActionCommand never match other intents')
    assert not rule.match_intent('PING'), (
        'ActionCommand never match other intents')


def test_action_command_from_callable_invalid(mockbot):
    # prepare callable
    @module.rule(r'.*')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # create rule from a clean callable
    with pytest.raises(RuntimeError):
        rules.ActionCommand.from_callable(mockbot.settings, handler)


def test_action_command_from_callable(mockbot):
    # prepare callable
    @module.action_commands('hello', 'hi', 'hey')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # create rule from a clean callable
    rule = rules.ActionCommand.from_callable(mockbot.settings, handler)

    # match on "ACTION hello"
    line = ':Foo!foo@example.com PRIVMSG #sopel :\x01ACTION hello\x01'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'Exactly 1 command must match'
    result = results[0]
    assert result.group(0) == 'hello'
    assert result.group(1) == 'hello'

    # match on "ACTION hi"
    line = ':Foo!foo@example.com PRIVMSG #sopel :\x01ACTION hi\x01'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'Exactly 1 command must match'
    result = results[0]
    assert result.group(0) == 'hi'
    assert result.group(1) == 'hi'

    # match on "ACTION hey"
    line = ':Foo!foo@example.com PRIVMSG #sopel :\x01ACTION hey\x01'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'Exactly 1 command must match'
    result = results[0]
    assert result.group(0) == 'hey'
    assert result.group(1) == 'hey'

    # does not match on "hello"
    line = ':Foo!foo@example.com PRIVMSG #sopel :hello'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))
    assert not results

    # does not match on "VERSION hello"
    line = ':Foo!foo@example.com PRIVMSG #sopel :\x01VERSION hello\x01'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))
    assert not results

    # does not match on "ACTION .hello"
    line = ':Foo!foo@example.com PRIVMSG #sopel :\x01ACTION .hello\x01'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))
    assert not results

    # does not match on "ACTION bye"
    line = ':Foo!foo@example.com PRIVMSG #sopel :\x01ACTION bye\x01'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))
    assert not results
