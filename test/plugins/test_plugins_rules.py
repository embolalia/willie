"""Tests for the ``sopel.plugins.rules`` module."""
from __future__ import annotations

import datetime
import re

import pytest

from sopel import bot, loader, plugin, trigger
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
# tests for :class:`Manager`

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

    assert list(manager.get_all_commands()) == []
    assert list(manager.get_all_nick_commands()) == []
    assert list(manager.get_all_action_commands()) == []
    assert list(manager.get_all_generic_rules()) == [
        ('testplugin', [rule]),
    ]
    assert list(manager.get_all_url_callbacks()) == []


def test_manager_find(mockbot):
    regex = re.compile(r'\w+')
    rule = rules.FindRule([regex], plugin='testplugin', label='testrule')
    manager = rules.Manager()
    manager.register(rule)

    assert manager.has_rule('testrule')
    assert manager.has_rule('testrule', plugin='testplugin')
    assert not manager.has_rule('testrule', plugin='not-plugin')

    line = ':Foo!foo@example.com PRIVMSG #sopel :Hello, world'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)

    items = manager.get_triggered_rules(mockbot, pretrigger)
    assert len(items) == 2, 'Exactly two rules must match'
    assert len(items[0]) == 2, (
        'First result must contain two items: (rule, match)')
    assert len(items[1]) == 2, (
        'Second result must contain two items: (rule, match)')

    # first result
    result_rule, result_match = items[0]
    assert result_rule == rule
    assert result_match.group(0) == 'Hello', 'The first must match on "Hello"'

    # second result
    result_rule, result_match = items[1]
    assert result_rule == rule
    assert result_match.group(0) == 'world', 'The second must match on "world"'

    assert list(manager.get_all_commands()) == []
    assert list(manager.get_all_nick_commands()) == []
    assert list(manager.get_all_action_commands()) == []
    assert list(manager.get_all_generic_rules()) == [
        ('testplugin', [rule]),
    ]
    assert list(manager.get_all_url_callbacks()) == []


def test_manager_search(mockbot):
    regex = re.compile(r'\w+')
    rule = rules.SearchRule([regex], plugin='testplugin', label='testrule')
    manager = rules.Manager()
    manager.register(rule)

    assert manager.has_rule('testrule')
    assert manager.has_rule('testrule', plugin='testplugin')
    assert not manager.has_rule('testrule', plugin='not-plugin')

    line = ':Foo!foo@example.com PRIVMSG #sopel :Hello, world'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)

    items = manager.get_triggered_rules(mockbot, pretrigger)
    assert len(items) == 1, 'Exactly one rule must match'

    # first result
    result_rule, result_match = items[0]
    assert result_rule == rule
    assert result_match.group(0) == 'Hello'

    assert list(manager.get_all_commands()) == []
    assert list(manager.get_all_nick_commands()) == []
    assert list(manager.get_all_action_commands()) == []
    assert list(manager.get_all_generic_rules()) == [
        ('testplugin', [rule]),
    ]
    assert list(manager.get_all_url_callbacks()) == []


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
    assert list(manager.get_all_action_commands()) == []
    assert list(manager.get_all_generic_rules()) == []
    assert list(manager.get_all_url_callbacks()) == []


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
    assert list(manager.get_all_action_commands()) == []
    assert list(manager.get_all_generic_rules()) == []
    assert list(manager.get_all_url_callbacks()) == []


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
    assert list(manager.get_all_action_commands()) == [
        ('testplugin', {'hello': command}),
    ]
    assert list(manager.get_all_generic_rules()) == []
    assert list(manager.get_all_url_callbacks()) == []


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
    assert len(items) == 2, 'Both rules (generic rule & command) must match'
    rule_result, command_result = items

    assert rule_result[0] == rule, 'First match must be the generic rule'
    assert command_result[0] == command, 'Second match must be the command'

    assert list(manager.get_all_commands()) == [
        ('testplugin', {'hello': command}),
    ]
    assert list(manager.get_all_nick_commands()) == []
    assert list(manager.get_all_action_commands()) == []
    assert list(manager.get_all_generic_rules()) == [
        ('testplugin', [rule]),
    ]
    assert list(manager.get_all_url_callbacks()) == []


def test_manager_url_callback(mockbot):
    regex = re.compile(r'https://example\.com/.*')
    rule = rules.URLCallback([regex], plugin='testplugin', label='testrule')
    manager = rules.Manager()
    manager.register_url_callback(rule)

    assert manager.has_url_callback('testrule')
    assert manager.has_url_callback('testrule', plugin='testplugin')
    assert not manager.has_url_callback('testrule', plugin='not-plugin')

    line = ':Foo!foo@example.com PRIVMSG #sopel :https://example.com/'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)

    items = manager.get_triggered_rules(mockbot, pretrigger)
    assert len(items) == 1, 'Exactly one rule must match'

    result = items[0]
    assert len(result) == 2, 'Result must contain two items: (rule, match)'

    result_rule, result_match = items[0]
    assert result_rule == rule
    assert result_match.group(0) == 'https://example.com/'

    assert manager.check_url_callback(mockbot, 'https://example.com/')
    assert manager.check_url_callback(mockbot, 'https://example.com/test')
    assert not manager.check_url_callback(mockbot, 'https://not-example.com/')

    assert list(manager.get_all_commands()) == []
    assert list(manager.get_all_nick_commands()) == []
    assert list(manager.get_all_action_commands()) == []
    assert list(manager.get_all_generic_rules()) == []
    assert list(manager.get_all_url_callbacks()) == [
        ('testplugin', [rule]),
    ]


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

    result = manager.unregister_plugin('plugin_a')
    assert result == 2
    assert manager.has_rule('the_rule')
    assert not manager.has_rule('the_rule', plugin='plugin_a')
    assert manager.has_command('hello')
    assert not manager.has_command('hello', plugin='plugin_a')

    items = manager.get_triggered_rules(mockbot, pretrigger)
    assert len(items) == 2, 'Only 2 must match by now'
    assert b_rule in items[0]
    assert b_command in items[1]


def test_manager_unregister_plugin_url_callbacks(mockbot):
    regex = re.compile('.*')
    a_rule = rules.Rule([regex], plugin='plugin_a', label='the_rule')
    b_rule = rules.Rule([regex], plugin='plugin_b', label='the_rule')
    a_callback = rules.URLCallback([regex], plugin='plugin_a', label='the_url')
    b_callback = rules.URLCallback([regex], plugin='plugin_b', label='the_url')

    manager = rules.Manager()
    manager.register(a_rule)
    manager.register_url_callback(a_callback)
    manager.register(b_rule)
    manager.register_url_callback(b_callback)

    line = ':Foo!foo@example.com PRIVMSG #sopel :https://example.com/test'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)

    items = manager.get_triggered_rules(mockbot, pretrigger)
    assert len(items) == 4, 'All 4 rules must match'
    assert manager.has_rule('the_rule')
    assert manager.has_url_callback('the_url')

    result = manager.unregister_plugin('plugin_a')
    assert result == 2
    assert manager.has_rule('the_rule')
    assert not manager.has_rule('the_rule', plugin='plugin_a')
    assert manager.has_url_callback('the_url')
    assert not manager.has_url_callback('the_url', plugin='plugin_a')

    items = manager.get_triggered_rules(mockbot, pretrigger)
    assert len(items) == 2, 'Only 2 must match by now'
    assert b_rule in items[0]
    assert b_callback in items[1]


def test_manager_unregister_plugin_unknown():
    regex = re.compile('.*')
    a_rule = rules.Rule([regex], plugin='plugin_a', label='the_rule')
    a_command = rules.Command('hello', prefix=r'\.', plugin='plugin_a')

    manager = rules.Manager()
    manager.register(a_rule)
    manager.register_command(a_command)

    # remove an unknown plugin
    result = manager.unregister_plugin('unknown')

    # everything is fine
    assert result == 0
    assert manager.has_command('hello')
    assert manager.has_command('hello', plugin='plugin_a')


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

    # rules are matched in their registration order
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
    assert manager.has_command('hi')
    assert not manager.has_command('hi', follow_alias=False)
    assert not manager.has_command('unknown')


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
    assert manager.has_nick_command('hi')
    assert manager.has_nick_command('hello', follow_alias=False)
    assert not manager.has_nick_command('hi', follow_alias=False)
    assert not manager.has_nick_command('unknown')


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
    assert manager.has_action_command('hi')
    assert manager.has_action_command('hello', follow_alias=False)
    assert not manager.has_action_command('hi', follow_alias=False)
    assert not manager.has_action_command('unknown')


# -----------------------------------------------------------------------------
# tests for :class:`Manager`

def test_rulemetrics():
    now = datetime.datetime.now(datetime.timezone.utc)
    time_window = datetime.timedelta(seconds=3600)
    metrics = rules.RuleMetrics()

    # never executed, so not limited
    assert not metrics.is_limited(now)

    # test limit while running
    with metrics:
        assert metrics.is_limited(now - time_window)
        assert not metrics.is_limited(now + time_window)

    # test limit after
    assert metrics.is_limited(now - time_window)
    assert not metrics.is_limited(now + time_window)

    # test with NO LIMIT on the return value
    metrics.set_return_value(rules.IGNORE_RATE_LIMIT)
    assert not metrics.is_limited(now - time_window)
    assert not metrics.is_limited(now + time_window)

# -----------------------------------------------------------------------------
# tests for :class:`Rule`


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

    assert str(rule) == '<Rule testplugin.(generic) (1)>'


def test_rule_str_no_plugin_no_label():
    regex = re.compile(r'.*')
    rule = rules.Rule([regex])

    assert str(rule) == '<Rule (no-plugin).(generic) (1)>'


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

    rule = rules.Rule([regex], ctcp=[re.compile(r'ACTION')])
    matches = list(rule.match(mockbot, pretrigger))
    assert len(matches) == 1, 'Exactly one match must be found'

    match = matches[0]
    assert match.group(0) == 'Hello, world'

    rule = rules.Rule([regex], ctcp=[re.compile(r'VERSION')])
    assert not list(rule.match(mockbot, pretrigger))


def test_rule_match_privmsg_bot_tag(mockbot):
    regex = re.compile(r'.*')
    rule = rules.Rule([regex])

    line = '@bot :TestBot!sopel@example.com PRIVMSG #sopel :Hi!'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    assert not list(rule.match(mockbot, pretrigger)), (
        'Line with `bot` tag must be ignored'
    )


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


@pytest.mark.parametrize(
    'is_bot, allow_bots, is_echo, allow_echo, should_match',
    [
        (True, True, True, True, True),
        (True, True, True, False, False),
        (True, True, False, True, True),
        (True, True, False, False, True),
        (True, False, True, True, True),
        (True, False, True, False, False),
        (True, False, False, True, False),
        (True, False, False, False, False),
        (False, True, True, True, True),
        (False, True, True, False, False),
        (False, True, False, True, True),
        (False, True, False, False, True),
        (False, False, True, True, True),
        (False, False, True, False, False),
        (False, False, False, True, True),
        (False, False, False, False, True),
    ])
def test_rule_match_privmsg_echo_and_bot_tag(
    is_bot, allow_bots, is_echo, allow_echo, should_match, mockbot
):
    line = '{tags}:{nick}!user@example.com PRIVMSG #sopel :Hi!'.format(
        tags='@bot ' if is_bot else '',
        nick=mockbot.nick if is_echo else 'SomeUser',
    )
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    regex = re.compile(r'.*')

    rule = rules.Rule([regex], allow_bots=allow_bots, allow_echo=allow_echo)
    matches = list(rule.match(mockbot, pretrigger))

    if should_match:
        assert len(matches) == 1, 'This combination should match the Rule'
    else:
        assert not matches, 'This combination should not match the Rule'


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


def test_rule_match_ctcp():
    regex = re.compile('.*')

    rule = rules.Rule([regex])
    assert rule.match_ctcp(None)

    ctcp = [
        re.compile('VERSION'),
    ]
    rule = rules.Rule([regex], ctcp=ctcp)
    assert not rule.match_ctcp(None)
    assert rule.match_ctcp('VERSION')
    assert not rule.match_ctcp('PING')


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


def test_rule_rate_limit_admins():
    regex = re.compile('.*')

    rule = rules.Rule([regex])
    assert not rule.is_admin_rate_limited()

    rule = rules.Rule([regex], rate_limit_admins=True)
    assert rule.is_admin_rate_limited()


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
        return 'The return value'

    rule = rules.Rule([regex], handler=handler)
    matches = list(rule.match(mockbot, pretrigger))
    match = matches[0]
    match_trigger = trigger.Trigger(
        mockbot.settings, pretrigger, match, account=None)
    wrapped = bot.SopelWrapper(mockbot, match_trigger)
    result = rule.execute(wrapped, match_trigger)

    assert mockbot.backend.message_sent == rawlist('PRIVMSG #sopel :Hi!')
    assert result == 'The return value'


def test_rule_from_callable(mockbot):
    # prepare callable
    @plugin.rule(r'hello', r'hi', r'hey', r'hello|hi')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)
    handler.plugin_name = 'testplugin'

    # create rule from a cleaned callable
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

    # match on "hey" only once
    line = ':Foo!foo@example.com PRIVMSG #sopel :hey how are you doing?'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'Exactly 1 rule must match'
    assert results[0].group(0) == 'hey'


def test_rule_from_callable_nick_placeholder(mockbot):
    # prepare callable
    # note: yes, the $nick variable is super confusing
    # it should probably accept \s* instead of \s+
    # so a pattern like "$nick hello" would be way easier to read
    @plugin.rule(r'$nickhello')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)
    handler.plugin_name = 'testplugin'

    # create rule from a cleaned callable
    rule = rules.Rule.from_callable(mockbot.settings, handler)

    # match on "TestBot: hello" with a ":"
    line = ':Foo!foo@example.com PRIVMSG #sopel :TestBot: hello'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'Exactly 1 command must match'
    result = results[0]
    assert result.group(0) == 'TestBot: hello'

    with pytest.raises(IndexError):
        result.group(1)

    # match on "TestBot: hello" with a ","
    line = ':Foo!foo@example.com PRIVMSG #sopel :TestBot, hello'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'Exactly 1 command must match'
    result = results[0]
    assert result.group(0) == 'TestBot, hello'

    with pytest.raises(IndexError):
        result.group(1)


def test_rule_from_callable_nickname_placeholder(mockbot):
    # prepare callable
    @plugin.rule(r'$nickname hello')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)
    handler.plugin_name = 'testplugin'

    # create rule from a cleaned callable
    rule = rules.Rule.from_callable(mockbot.settings, handler)

    # match on "TestBot: hello" with a ":"
    line = ':Foo!foo@example.com PRIVMSG #sopel :TestBot hello'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'Exactly 1 command must match'
    result = results[0]
    assert result.group(0) == 'TestBot hello'

    with pytest.raises(IndexError):
        result.group(1)


def test_rule_from_callable_lazy(mockbot):
    def lazy_loader(settings):
        return [
            re.compile(r'hello', re.IGNORECASE),
            re.compile(r'hi', re.IGNORECASE),
            re.compile(r'hey', re.IGNORECASE),
            re.compile(r'hello|hi', re.IGNORECASE),
        ]

    # prepare callable
    @plugin.rule_lazy(lazy_loader)
    def handler(wrapped, trigger):
        wrapped.say('Hi!')
        return 'The return value: %s' % trigger.group(0)

    loader.clean_callable(handler, mockbot.settings)
    handler.plugin_name = 'testplugin'

    # create rule from a cleaned callable
    rule = rules.Rule.from_callable_lazy(mockbot.settings, handler)
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

    # match on "hey" only once
    line = ':Foo!foo@example.com PRIVMSG #sopel :hey how are you doing?'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'Exactly 1 rule must match'
    assert results[0].group(0) == 'hey'


def test_rule_from_callable_invalid(mockbot):
    def lazy_loader(settings):
        return [
            re.compile(re.escape('https://example.com/') + r'(\w+)'),
        ]

    # prepare callable
    @plugin.rule_lazy(lazy_loader)
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)
    handler.plugin_name = 'testplugin'

    # create rule from a cleaned callable
    with pytest.raises(RuntimeError):
        rules.Rule.from_callable(mockbot.settings, handler)


def test_rule_from_callable_lazy_invalid(mockbot):
    # prepare callable
    @plugin.rule(r'.*')
    def handler(wrapped, trigger, match=None):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)
    handler.plugin_name = 'testplugin'

    # create rule from a cleaned callable
    with pytest.raises(RuntimeError):
        rules.Rule.from_callable_lazy(mockbot.settings, handler)


def test_rule_from_callable_lazy_invalid_no_regex(mockbot):
    # prepare callable
    @plugin.rule_lazy(lambda *args: [])
    def handler(wrapped, trigger, match=None):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)
    handler.plugin_name = 'testplugin'

    # create rule from a cleaned callable
    with pytest.raises(RuntimeError):
        rules.Rule.from_callable_lazy(mockbot.settings, handler)


# -----------------------------------------------------------------------------
# test classmethod :meth:`Rule.kwargs_from_callable`

def test_kwargs_from_callable(mockbot):
    # prepare callable
    @plugin.rule(r'hello', r'hi', r'hey', r'hello|hi')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)
    handler.plugin_name = 'testplugin'  # normally added by the Plugin handler

    # get kwargs
    kwargs = rules.Rule.kwargs_from_callable(handler)

    assert 'plugin' in kwargs
    assert 'label' in kwargs
    assert 'priority' in kwargs
    assert 'events' in kwargs
    assert 'ctcp' in kwargs
    assert 'allow_echo' in kwargs
    assert 'threaded' in kwargs
    assert 'output_prefix' in kwargs
    assert 'unblockable' in kwargs
    assert 'rate_limit_admins' in kwargs
    assert 'user_rate_limit' in kwargs
    assert 'channel_rate_limit' in kwargs
    assert 'global_rate_limit' in kwargs
    assert 'user_rate_message' in kwargs
    assert 'channel_rate_message' in kwargs
    assert 'global_rate_message' in kwargs
    assert 'default_rate_message' in kwargs
    assert 'usages' in kwargs
    assert 'tests' in kwargs
    assert 'doc' in kwargs

    assert kwargs['plugin'] == 'testplugin'
    assert kwargs['label'] is None
    assert kwargs['priority'] == rules.PRIORITY_MEDIUM
    assert kwargs['events'] == ['PRIVMSG']
    assert kwargs['ctcp'] == []
    assert kwargs['allow_echo'] is False
    assert kwargs['threaded'] is True
    assert kwargs['output_prefix'] == ''
    assert kwargs['unblockable'] is False
    assert kwargs['rate_limit_admins'] is False
    assert kwargs['user_rate_limit'] == 0
    assert kwargs['channel_rate_limit'] == 0
    assert kwargs['global_rate_limit'] == 0
    assert kwargs['user_rate_message'] is None
    assert kwargs['channel_rate_message'] is None
    assert kwargs['global_rate_message'] is None
    assert kwargs['default_rate_message'] is None
    assert kwargs['usages'] == tuple()
    assert kwargs['tests'] == tuple()
    assert kwargs['doc'] is None


def test_kwargs_from_callable_label(mockbot):
    # prepare callable
    @plugin.rule(r'hello', r'hi', r'hey', r'hello|hi')
    @plugin.label('hello_rule')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # get kwargs
    kwargs = rules.Rule.kwargs_from_callable(handler)
    assert 'label' in kwargs
    assert kwargs['label'] == 'hello_rule'


def test_kwargs_from_callable_priority(mockbot):
    # prepare callable
    @plugin.rule(r'hello', r'hi', r'hey', r'hello|hi')
    @plugin.priority(rules.PRIORITY_LOW)
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # get kwargs
    kwargs = rules.Rule.kwargs_from_callable(handler)
    assert 'priority' in kwargs
    assert kwargs['priority'] == rules.PRIORITY_LOW


def test_kwargs_from_callable_event(mockbot):
    # prepare callable
    @plugin.rule(r'hello', r'hi', r'hey', r'hello|hi')
    @plugin.event('PRIVMSG', 'NOTICE')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # get kwargs
    kwargs = rules.Rule.kwargs_from_callable(handler)
    assert 'events' in kwargs
    assert kwargs['events'] == ['PRIVMSG', 'NOTICE']


def test_kwargs_from_callable_ctcp_intent(mockbot):
    # prepare callable
    @plugin.rule(r'hello', r'hi', r'hey', r'hello|hi')
    @plugin.ctcp('ACTION')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # get kwargs
    kwargs = rules.Rule.kwargs_from_callable(handler)
    assert 'ctcp' in kwargs
    assert kwargs['ctcp'] == [re.compile(r'ACTION', re.IGNORECASE)]


def test_kwargs_from_callable_allow_echo(mockbot):
    # prepare callable
    @plugin.rule(r'hello', r'hi', r'hey', r'hello|hi')
    @plugin.echo
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # get kwargs
    kwargs = rules.Rule.kwargs_from_callable(handler)
    assert 'allow_echo' in kwargs
    assert kwargs['allow_echo'] is True


def test_kwargs_from_callable_threaded(mockbot):
    # prepare callable
    @plugin.rule(r'hello', r'hi', r'hey', r'hello|hi')
    @plugin.thread(False)
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # get kwargs
    kwargs = rules.Rule.kwargs_from_callable(handler)
    assert 'threaded' in kwargs
    assert kwargs['threaded'] is False


def test_kwargs_from_callable_unblockable(mockbot):
    # prepare callable
    @plugin.rule(r'hello', r'hi', r'hey', r'hello|hi')
    @plugin.unblockable
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # get kwargs
    kwargs = rules.Rule.kwargs_from_callable(handler)
    assert 'unblockable' in kwargs
    assert kwargs['unblockable'] is True


def test_kwargs_from_callable_rate_limit(mockbot):
    # prepare callable
    @plugin.rule(r'hello', r'hi', r'hey', r'hello|hi')
    @plugin.rate(
        user=20, channel=30, server=40, message='Default message.',
        include_admins=True)
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # get kwargs
    kwargs = rules.Rule.kwargs_from_callable(handler)
    assert 'rate_limit_admins' in kwargs
    assert 'user_rate_limit' in kwargs
    assert 'channel_rate_limit' in kwargs
    assert 'global_rate_limit' in kwargs
    assert 'user_rate_message' in kwargs
    assert 'channel_rate_message' in kwargs
    assert 'global_rate_message' in kwargs
    assert 'default_rate_message' in kwargs
    assert kwargs['rate_limit_admins'] is True
    assert kwargs['user_rate_limit'] == 20
    assert kwargs['channel_rate_limit'] == 30
    assert kwargs['global_rate_limit'] == 40
    assert kwargs['user_rate_message'] is None
    assert kwargs['channel_rate_message'] is None
    assert kwargs['global_rate_message'] is None
    assert kwargs['default_rate_message'] == 'Default message.'


def test_kwargs_from_callable_rate_limit_user(mockbot):
    # prepare callable
    @plugin.rule(r'hello', r'hi', r'hey', r'hello|hi')
    @plugin.rate_user(20, 'User message.', True)
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # get kwargs
    kwargs = rules.Rule.kwargs_from_callable(handler)
    assert 'rate_limit_admins' in kwargs
    assert 'user_rate_limit' in kwargs
    assert 'channel_rate_limit' in kwargs
    assert 'global_rate_limit' in kwargs
    assert 'user_rate_message' in kwargs
    assert 'channel_rate_message' in kwargs
    assert 'global_rate_message' in kwargs
    assert 'default_rate_message' in kwargs
    assert kwargs['rate_limit_admins'] is True
    assert kwargs['user_rate_limit'] == 20
    assert kwargs['channel_rate_limit'] == 0
    assert kwargs['global_rate_limit'] == 0
    assert kwargs['user_rate_message'] == 'User message.'
    assert kwargs['channel_rate_message'] is None
    assert kwargs['global_rate_message'] is None
    assert kwargs['default_rate_message'] is None


def test_kwargs_from_callable_rate_limit_channel(mockbot):
    # prepare callable
    @plugin.rule(r'hello', r'hi', r'hey', r'hello|hi')
    @plugin.rate_channel(20, 'Channel message.', True)
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # get kwargs
    kwargs = rules.Rule.kwargs_from_callable(handler)
    assert 'rate_limit_admins' in kwargs
    assert 'user_rate_limit' in kwargs
    assert 'channel_rate_limit' in kwargs
    assert 'global_rate_limit' in kwargs
    assert 'user_rate_message' in kwargs
    assert 'channel_rate_message' in kwargs
    assert 'global_rate_message' in kwargs
    assert 'default_rate_message' in kwargs
    assert kwargs['rate_limit_admins'] is True
    assert kwargs['user_rate_limit'] == 0
    assert kwargs['channel_rate_limit'] == 20
    assert kwargs['global_rate_limit'] == 0
    assert kwargs['user_rate_message'] is None
    assert kwargs['channel_rate_message'] == 'Channel message.'
    assert kwargs['global_rate_message'] is None
    assert kwargs['default_rate_message'] is None


def test_kwargs_from_callable_rate_limit_server(mockbot):
    # prepare callable
    @plugin.rule(r'hello', r'hi', r'hey', r'hello|hi')
    @plugin.rate_global(20, 'Server message.', True)
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # get kwargs
    kwargs = rules.Rule.kwargs_from_callable(handler)
    assert 'rate_limit_admins' in kwargs
    assert 'user_rate_limit' in kwargs
    assert 'channel_rate_limit' in kwargs
    assert 'global_rate_limit' in kwargs
    assert 'user_rate_message' in kwargs
    assert 'channel_rate_message' in kwargs
    assert 'global_rate_message' in kwargs
    assert 'default_rate_message' in kwargs
    assert kwargs['rate_limit_admins'] is True
    assert kwargs['user_rate_limit'] == 0
    assert kwargs['channel_rate_limit'] == 0
    assert kwargs['global_rate_limit'] == 20
    assert kwargs['user_rate_message'] is None
    assert kwargs['channel_rate_message'] is None
    assert kwargs['global_rate_message'] == 'Server message.'
    assert kwargs['default_rate_message'] is None


def test_kwargs_from_callable_examples(mockbot):
    # prepare callable
    @plugin.rule(r'hello', r'hi', r'hey', r'hello|hi')
    @plugin.example('hello')
    def handler(wrapped, trigger):
        """This is the doc you are looking for."""
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # get kwargs
    kwargs = rules.Rule.kwargs_from_callable(handler)

    # expectations
    expected = {
        'example': 'hello',
        'result': None,
        'is_pattern': False,
        'is_help': False,
        'is_owner': False,
        'is_admin': False,
        'is_private_message': False,
    }

    # reality
    assert 'usages' in kwargs
    assert 'tests' in kwargs
    assert 'doc' in kwargs
    assert kwargs['usages'] == (expected,)
    assert kwargs['tests'] == tuple(), 'There must be no test'
    assert kwargs['doc'] == 'This is the doc you are looking for.'


def test_kwargs_from_callable_examples_test(mockbot):
    # prepare callable
    @plugin.rule(r'hello', r'hi', r'hey', r'hello|hi')
    @plugin.example('hi', 'Hi!')
    @plugin.example('hello', 'Hi!')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # get kwargs
    kwargs = rules.Rule.kwargs_from_callable(handler)

    # expectations
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

    # reality
    assert 'usages' in kwargs
    assert 'tests' in kwargs
    assert 'doc' in kwargs
    assert kwargs['usages'] == (expected,), 'The first example must be used'
    assert kwargs['tests'] == expected_tests
    assert kwargs['doc'] is None


def test_kwargs_from_callable_examples_help(mockbot):
    # prepare callable
    @plugin.rule(r'hello', r'hi', r'hey', r'hello|hi')
    @plugin.example('hi', user_help=True)
    @plugin.example('hey', 'Hi!')
    @plugin.example('hello', 'Hi!', user_help=True)
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # get kwargs
    kwargs = rules.Rule.kwargs_from_callable(handler)

    # expectations
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

    # reality
    assert 'usages' in kwargs
    assert 'tests' in kwargs
    assert 'doc' in kwargs
    assert kwargs['usages'] == expected_usages
    assert kwargs['tests'] == expected_tests
    assert kwargs['doc'] is None


def test_kwargs_from_callable_examples_doc(mockbot):
    # prepare callable
    @plugin.rule(r'hello', r'hi', r'hey', r'hello|hi')
    @plugin.example('hello')
    def handler(wrapped, trigger):
        """This is the doc you are looking for.

        And now with extended text, for testing purpose only.
        """
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # get kwargs
    kwargs = rules.Rule.kwargs_from_callable(handler)

    # expectations
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

    # reality
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
# tests for rate-limiting features

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
        user_rate_limit=20,
        global_rate_limit=20,
        channel_rate_limit=20,
    )
    at_time = datetime.datetime.now(datetime.timezone.utc)
    assert rule.is_user_rate_limited(mocktrigger.nick, at_time) is False
    assert rule.is_channel_rate_limited(mocktrigger.sender, at_time) is False
    assert rule.is_global_rate_limited(at_time) is False

    rule.execute(mockbot, mocktrigger)
    at_time = datetime.datetime.now(datetime.timezone.utc)
    assert rule.is_user_rate_limited(mocktrigger.nick, at_time) is True
    assert rule.is_channel_rate_limited(mocktrigger.sender, at_time) is True
    assert rule.is_global_rate_limited(at_time) is True


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
        user_rate_limit=0,
        global_rate_limit=0,
        channel_rate_limit=0,
    )
    at_time = datetime.datetime.now(datetime.timezone.utc)
    assert rule.is_user_rate_limited(mocktrigger.nick, at_time) is False
    assert rule.is_channel_rate_limited(mocktrigger.sender, at_time) is False
    assert rule.is_global_rate_limited(at_time) is False

    rule.execute(mockbot, mocktrigger)
    at_time = datetime.datetime.now(datetime.timezone.utc)
    assert rule.is_user_rate_limited(mocktrigger.nick, at_time) is False
    assert rule.is_channel_rate_limited(mocktrigger.sender, at_time) is False
    assert rule.is_global_rate_limited(at_time) is False


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
        user_rate_limit=20,
        global_rate_limit=20,
        channel_rate_limit=20,
        threaded=False,  # make sure there is no race-condition here
    )
    at_time = datetime.datetime.now(datetime.timezone.utc)
    assert rule.is_user_rate_limited(mocktrigger.nick, at_time) is False
    assert rule.is_channel_rate_limited(mocktrigger.sender, at_time) is False
    assert rule.is_global_rate_limited(at_time) is False

    rule.execute(mockbot, mocktrigger)
    at_time = datetime.datetime.now(datetime.timezone.utc)
    assert rule.is_user_rate_limited(mocktrigger.nick, at_time) is False
    assert rule.is_channel_rate_limited(mocktrigger.sender, at_time) is False
    assert rule.is_global_rate_limited(at_time) is False


def test_rule_rate_limit_messages(mockbot, triggerfactory):
    def handler(bot, trigger):
        return 'hello'

    regex = re.compile(r'.*')
    rule = rules.Rule(
        [regex],
        handler=handler,
        user_rate_limit=20,
        global_rate_limit=20,
        channel_rate_limit=20,
        user_rate_message='User message: {nick}',
        channel_rate_message='Channel message: {nick}/{channel}',
        global_rate_message='Server message: {nick}',
        default_rate_message='Default message: {nick}',
    )
    assert rule.user_rate_template == 'User message: {nick}'
    assert rule.channel_rate_template == 'Channel message: {nick}/{channel}'
    assert rule.global_rate_template == 'Server message: {nick}'


def test_rule_rate_limit_messages_default(mockbot, triggerfactory):
    def handler(bot, trigger):
        return 'hello'

    regex = re.compile(r'.*')
    rule = rules.Rule(
        [regex],
        handler=handler,
        user_rate_limit=20,
        global_rate_limit=20,
        channel_rate_limit=20,
        default_rate_message='Default message',
    )
    assert rule.user_rate_template == 'Default message'
    assert rule.channel_rate_template == 'Default message'
    assert rule.global_rate_template == 'Default message'


def test_rule_rate_limit_messages_default_mixed(mockbot, triggerfactory):
    def handler(bot, trigger):
        return 'hello'

    regex = re.compile(r'.*')
    rule = rules.Rule(
        [regex],
        handler=handler,
        user_rate_limit=20,
        global_rate_limit=20,
        channel_rate_limit=20,
        user_rate_message='User message.',
        default_rate_message='The default.',
    )
    assert rule.user_rate_template == 'User message.'
    assert rule.channel_rate_template == 'The default.'
    assert rule.global_rate_template == 'The default.'

    rule = rules.Rule(
        [regex],
        handler=handler,
        user_rate_limit=20,
        global_rate_limit=20,
        channel_rate_limit=20,
        channel_rate_message='Channel message.',
        default_rate_message='The default.',
    )
    assert rule.user_rate_template == 'The default.'
    assert rule.channel_rate_template == 'Channel message.'
    assert rule.global_rate_template == 'The default.'

    rule = rules.Rule(
        [regex],
        handler=handler,
        user_rate_limit=20,
        global_rate_limit=20,
        channel_rate_limit=20,
        global_rate_message='Server message.',
        default_rate_message='The default.',
    )
    assert rule.user_rate_template == 'The default.'
    assert rule.channel_rate_template == 'The default.'
    assert rule.global_rate_template == 'Server message.'


# -----------------------------------------------------------------------------
# tests for :class:`sopel.plugins.rules.Command`


def test_command_str():
    rule = rules.Command('hello', r'\.', plugin='testplugin')
    assert str(rule) == '<Command testplugin.hello []>'


def test_command_str_subcommand():
    rule = rules.Command('main sub', r'\.', plugin='testplugin')
    assert str(rule) == '<Command testplugin.main-sub []>'


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


def test_command_get_rule_label_subcommand(mockbot):
    rule = rules.Command('main sub', r'\.')
    assert rule.get_rule_label() == 'main-sub'


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


def test_command_match_subcommand(mockbot):
    line = ':Foo!foo@example.com PRIVMSG #sopel :.main sub'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)

    rule = rules.Command('main sub', r'\.')
    matches = list(rule.match(mockbot, pretrigger))
    assert len(matches) == 1, 'Exactly one match must be found'

    match = matches[0]
    assert match.group(0) == '.main sub'
    assert match.group(1) == 'main sub'
    assert match.group(2) is None
    assert match.group(3) is None
    assert match.group(4) is None
    assert match.group(5) is None
    assert match.group(6) is None


def test_command_match_subcommand_args(mockbot):
    line = (
        ':Foo!foo@example.com PRIVMSG #sopel :'
        '.main sub arg1 arg2 arg3 arg4 arg5'
    )
    pretrigger = trigger.PreTrigger(mockbot.nick, line)

    rule = rules.Command('main sub', r'\.')
    matches = list(rule.match(mockbot, pretrigger))
    assert len(matches) == 1, 'Exactly one match must be found'

    match = matches[0]
    assert match.group(0) == '.main sub arg1 arg2 arg3 arg4 arg5'
    assert match.group(1) == 'main sub', (
        'The command match must include the subcommand')
    assert match.group(2) == 'arg1 arg2 arg3 arg4 arg5', (
        'The global arg list must include everything else')
    # group 3-6 must match the 4 first arguments
    assert match.group(3) == 'arg1'
    assert match.group(4) == 'arg2'
    assert match.group(5) == 'arg3'
    assert match.group(6) == 'arg4'

    # command regex doesn't match more than 4 extra args
    with pytest.raises(IndexError):
        match.group(7)


def test_command_match_subcommand_aliases(mockbot):
    line = ':Foo!foo@example.com PRIVMSG #sopel :.main sub arg1'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)

    rule = rules.Command('main', r'\.', aliases=['main sub', 'main other'])
    matches = list(rule.match(mockbot, pretrigger))
    assert len(matches) == 1, 'Exactly one match must be found'

    match = matches[0]
    assert match.group(0) == '.main sub arg1'
    assert match.group(1) == 'main', (
        'Because the name is `main`, it has priority')
    assert match.group(2) == 'sub arg1'
    assert match.group(3) == 'sub'
    assert match.group(4) == 'arg1'
    assert match.group(5) is None
    assert match.group(6) is None

    # still, no more than 4 extra args
    with pytest.raises(IndexError):
        match.group(7)

    # reverse order
    rule = rules.Command('main sub', r'\.', aliases=['main', 'main other'])
    matches = list(rule.match(mockbot, pretrigger))
    assert len(matches) == 1, 'Exactly one match must be found'

    match = matches[0]
    assert match.group(0) == '.main sub arg1'
    assert match.group(1) == 'main sub', (
        'Because the name is now `main sub`, it has priority')
    assert match.group(2) == 'arg1'
    assert match.group(3) == 'arg1'
    assert match.group(4) is None
    assert match.group(5) is None
    assert match.group(6) is None

    # still, no more than 4 extra args
    with pytest.raises(IndexError):
        match.group(7)

    # check the "main other", defined as the *last* alias
    line = ':Foo!foo@example.com PRIVMSG #sopel :.main other arg1'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    matches = list(rule.match(mockbot, pretrigger))
    assert len(matches) == 1, 'Exactly one match must be found'

    match = matches[0]
    assert match.group(0) == '.main other arg1'
    assert match.group(1) == 'main', (
        'Because the alias `other` is last, alias `main` has priority')
    assert match.group(2) == 'other arg1'
    assert match.group(3) == 'other'
    assert match.group(4) == 'arg1'
    assert match.group(5) is None
    assert match.group(6) is None

    # still, no more than 4 extra args
    with pytest.raises(IndexError):
        match.group(7)


def test_command_from_callable(mockbot):
    # prepare callable
    @plugin.commands('hello', 'hi', 'hey')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # create rule from a cleaned callable
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


def test_command_from_callable_subcommand(mockbot):
    # prepare callable
    @plugin.commands('main sub')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # create rule from a cleaned callable
    rule = rules.Command.from_callable(mockbot.settings, handler)

    # match on ".main sub"
    line = ':Foo!foo@example.com PRIVMSG #sopel :.main sub'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'Exactly 1 command must match'
    result = results[0]
    assert result.group(0) == '.main sub'
    assert result.group(1) == 'main sub'

    # does not match on ".main"
    line = ':Foo!foo@example.com PRIVMSG #sopel :.main'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))
    assert not results


def test_command_from_callable_subcommand_aliases(mockbot):
    # prepare callable
    @plugin.commands('main', 'main sub')
    @plugin.commands('reverse sub', 'reverse')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # create rule from a cleaned callable
    rule = rules.Command.from_callable(mockbot.settings, handler)

    # match on ".main sub": .main matches first
    line = ':Foo!foo@example.com PRIVMSG #sopel :.main sub'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'Exactly 1 command must match'
    result = results[0]
    assert result.group(0) == '.main sub'
    assert result.group(1) == 'main', (
        'Because "main" is declared first, it must match first')

    # match on ".main"
    line = ':Foo!foo@example.com PRIVMSG #sopel :.main'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'Exactly 1 command must match'
    result = results[0]
    assert result.group(0) == '.main'
    assert result.group(1) == 'main'

    # match on ".reverse sub": as it's declared first, it'll take priority
    line = ':Foo!foo@example.com PRIVMSG #sopel :.reverse sub'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'Exactly 1 command must match'
    result = results[0]
    assert result.group(0) == '.reverse sub'
    assert result.group(1) == 'reverse sub', (
        'Because "reverse sub" is declared first, it must match first')

    # match on ".main"
    line = ':Foo!foo@example.com PRIVMSG #sopel :.reverse'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'Exactly 1 command must match'
    result = results[0]
    assert result.group(0) == '.reverse'
    assert result.group(1) == 'reverse'


def test_command_from_callable_escaped_regex_pattern(mockbot):
    # prepare callable
    @plugin.commands('main .*')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # create rule from a cleaned callable
    rule = rules.Command.from_callable(mockbot.settings, handler)

    # does not match on ".main anything"
    line = ':Foo!foo@example.com PRIVMSG #sopel :.main anything'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert not results, 'Regex commands are not allowed since Sopel 8.0'

    # match on ".main .*"
    line = ':Foo!foo@example.com PRIVMSG #sopel :.main .*'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, (
        'Command name must be escaped to get an exact match')
    result = results[0]
    assert result.group(0) == '.main .*'
    assert result.group(1) == 'main .*'


def test_command_from_callable_invalid(mockbot):
    # prepare callable
    @plugin.rule(r'.*')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # create rule from a cleaned callable
    with pytest.raises(RuntimeError):
        rules.Command.from_callable(mockbot.settings, handler)


# -----------------------------------------------------------------------------
# tests for :class:`sopel.plugins.rules.NickCommand`


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


def test_nick_command_match_args(mockbot):
    line = (
        ':Foo!foo@example.com PRIVMSG #sopel :'
        'TestBot: hello arg1 arg2 arg3 arg4 arg5'
    )
    pretrigger = trigger.PreTrigger(mockbot.nick, line)

    rule = rules.NickCommand('TestBot', 'hello')
    matches = list(rule.match(mockbot, pretrigger))
    assert len(matches) == 1, 'Exactly one match must be found'

    match = matches[0]
    assert match.group(0) == 'TestBot: hello arg1 arg2 arg3 arg4 arg5'
    assert match.group(1) == 'hello'
    assert match.group(2) == 'arg1 arg2 arg3 arg4 arg5', (
        'The global arg list must include everything else')
    # group 3-6 must match the 4 first arguments
    assert match.group(3) == 'arg1'
    assert match.group(4) == 'arg2'
    assert match.group(5) == 'arg3'
    assert match.group(6) == 'arg4'

    # command regex doesn't match more than 4 extra args
    with pytest.raises(IndexError):
        match.group(7)


def test_nick_command_has_alias(mockbot):
    rule = rules.NickCommand('TestBot', 'hello', aliases=['hi'])
    assert rule.has_alias('hi')
    assert not rule.has_alias('hello'), 'The name must not be an alias!'
    assert not rule.has_alias('unknown')


def test_nick_command_from_callable_invalid(mockbot):
    # prepare callable
    @plugin.rule(r'.*')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # create rule from a cleaned callable
    with pytest.raises(RuntimeError):
        rules.NickCommand.from_callable(mockbot.settings, handler)


def test_nick_command_from_callable(mockbot):
    # prepare callable
    @plugin.nickname_commands('hello', 'hi', 'hey')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # create rule from a cleaned callable
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


def test_nick_command_from_callable_regex_pattern(mockbot):
    @plugin.nickname_commands('do .*')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # create rule from a cleaned callable
    rule = rules.NickCommand.from_callable(mockbot.settings, handler)

    # does not match on ".do anything"
    line = ':Foo!foo@example.com PRIVMSG #sopel :TestBot: do anything'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert not results, 'Regex commands are not allowed since Sopel 8.0'

    # match on ".do .*"
    line = ':Foo!foo@example.com PRIVMSG #sopel :TestBot: do .*'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))
    assert len(results) == 1, 'Exactly 1 command must match'
    result = results[0]
    assert result.group(0) == 'TestBot: do .*'
    assert result.group(1) == 'do .*'
    assert result.group(2) is None
    assert result.group(3) is None
    assert result.group(4) is None
    assert result.group(5) is None
    assert result.group(6) is None


# -----------------------------------------------------------------------------
# tests for :class:`sopel.plugins.rules.ActionCommand`

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


def test_action_command_match_args(mockbot):
    line = (
        ':Foo!foo@example.com PRIVMSG #sopel :'
        '\x01ACTION hello arg1 arg2 arg3 arg4 arg5\x01'
    )
    pretrigger = trigger.PreTrigger(mockbot.nick, line)

    rule = rules.ActionCommand('hello')
    matches = list(rule.match(mockbot, pretrigger))
    assert len(matches) == 1, 'Exactly one match must be found'

    match = matches[0]
    assert match.group(0) == 'hello arg1 arg2 arg3 arg4 arg5'
    assert match.group(1) == 'hello'
    assert match.group(2) == 'arg1 arg2 arg3 arg4 arg5', (
        'The global arg list must include everything else')
    # group 3-6 must match the 4 first arguments
    assert match.group(3) == 'arg1'
    assert match.group(4) == 'arg2'
    assert match.group(5) == 'arg3'
    assert match.group(6) == 'arg4'

    # command regex doesn't match more than 4 extra args
    with pytest.raises(IndexError):
        match.group(7)


def test_action_command_has_alias(mockbot):
    rule = rules.ActionCommand('hello', aliases=['hi'])
    assert rule.has_alias('hi')
    assert not rule.has_alias('hello'), 'The name must not be an alias!'
    assert not rule.has_alias('unknown')


def test_action_command_match_ctcp(mockbot):
    rule = rules.ActionCommand('hello')
    assert rule.match_ctcp('ACTION')
    assert not rule.match_ctcp('VERSION')
    assert not rule.match_ctcp('PING')

    ctcp = (re.compile(r'VERSION'), re.compile(r'SOURCE'))
    rule = rules.ActionCommand('hello', ctcp=ctcp)
    assert rule.match_ctcp('ACTION'), 'ActionCommand always match ACTION'
    assert not rule.match_ctcp('VERSION'), (
        'ActionCommand never match other CTCP commands')
    assert not rule.match_ctcp('PING'), (
        'ActionCommand never match other CTCP commands')


def test_action_command_from_callable_invalid(mockbot):
    # prepare callable
    @plugin.rule(r'.*')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # create rule from a cleaned callable
    with pytest.raises(RuntimeError):
        rules.ActionCommand.from_callable(mockbot.settings, handler)


def test_action_command_from_callable(mockbot):
    # prepare callable
    @plugin.action_commands('hello', 'hi', 'hey')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # create rule from a cleaned callable
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


def test_action_command_from_callable_regex_pattern(mockbot):
    # prepare callable
    @plugin.action_commands('do .*')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # create rule from a cleaned callable
    rule = rules.ActionCommand.from_callable(mockbot.settings, handler)

    # does not match on ".do anything"
    line = ':Foo!foo@example.com PRIVMSG #sopel :\x01ACTION do anything\x01'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert not results, 'Regex commands are not allowed since Sopel 8.0'

    # match on ".do .*"
    line = ':Foo!foo@example.com PRIVMSG #sopel :\x01ACTION do .*\x01'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'Exactly 1 command must match'
    result = results[0]
    assert result.group(0) == 'do .*'
    assert result.group(1) == 'do .*'
    assert result.group(2) is None
    assert result.group(3) is None
    assert result.group(4) is None
    assert result.group(5) is None
    assert result.group(6) is None


# -----------------------------------------------------------------------------
# tests for :class:`sopel.plugins.rules.FindRule`

def test_find_rule_str():
    regex = re.compile(r'.*')
    rule = rules.FindRule([regex], plugin='testplugin', label='testrule')

    assert str(rule) == '<FindRule testplugin.testrule (1)>'


def test_find_rule_str_no_plugin():
    regex = re.compile(r'.*')
    rule = rules.FindRule([regex], label='testrule')

    assert str(rule) == '<FindRule (no-plugin).testrule (1)>'


def test_find_str_no_label():
    regex = re.compile(r'.*')
    rule = rules.FindRule([regex], plugin='testplugin')

    assert str(rule) == '<FindRule testplugin.(generic) (1)>'


def test_find_str_no_plugin_label():
    regex = re.compile(r'.*')
    rule = rules.FindRule([regex])

    assert str(rule) == '<FindRule (no-plugin).(generic) (1)>'


def test_find_rule_parse_pattern():
    # playing with regex
    regex = re.compile(r'\w+')

    rule = rules.FindRule([regex])
    results = list(rule.parse('Hello, world!'))
    assert len(results) == 2, 'Find rule on word must match twice'
    assert results[0].group(0) == 'Hello'
    assert results[1].group(0) == 'world'


def test_find_rule_from_callable(mockbot):
    # prepare callable
    @plugin.find(r'hello', r'hi', r'hey', r'hello|hi')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)
    handler.plugin_name = 'testplugin'

    # create rule from a cleaned callable
    rule = rules.FindRule.from_callable(mockbot.settings, handler)
    assert str(rule) == '<FindRule testplugin.handler (4)>'

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

    # match on "hey" twice because it's twice in the line
    line = ':Foo!foo@example.com PRIVMSG #sopel :I say hey, can you say hey?'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 2, 'Exactly 2 rules must match'
    assert all(result.group(0) == 'hey' for result in results)


# -----------------------------------------------------------------------------
# tests for :class:`sopel.plugins.rules.SearchRule`

def test_search_rule_str():
    regex = re.compile(r'.*')
    rule = rules.SearchRule([regex], plugin='testplugin', label='testrule')

    assert str(rule) == '<SearchRule testplugin.testrule (1)>'


def test_search_rule_str_no_plugin():
    regex = re.compile(r'.*')
    rule = rules.SearchRule([regex], label='testrule')

    assert str(rule) == '<SearchRule (no-plugin).testrule (1)>'


def test_search_str_no_label():
    regex = re.compile(r'.*')
    rule = rules.SearchRule([regex], plugin='testplugin')

    assert str(rule) == '<SearchRule testplugin.(generic) (1)>'


def test_search_str_no_plugin_label():
    regex = re.compile(r'.*')
    rule = rules.SearchRule([regex])

    assert str(rule) == '<SearchRule (no-plugin).(generic) (1)>'


def test_search_rule_parse_pattern():
    # playing with regex
    regex = re.compile(r'\w+')

    rule = rules.SearchRule([regex])
    results = list(rule.parse('Hello, world!'))
    assert len(results) == 1, 'Search rule on word must match only once'
    assert results[0].group(0) == 'Hello'


def test_search_rule_from_callable(mockbot):
    # prepare callable
    @plugin.search(r'hello', r'hi', r'hey', r'hello|hi')
    def handler(wrapped, trigger):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)
    handler.plugin_name = 'testplugin'

    # create rule from a cleaned callable
    rule = rules.SearchRule.from_callable(mockbot.settings, handler)
    assert str(rule) == '<SearchRule testplugin.handler (4)>'

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

    # match on "hey" once
    line = ':Foo!foo@example.com PRIVMSG #sopel :hey how are you doing?'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'Exactly 1 rule must match'
    assert results[0].group(0) == 'hey'

    # match on "hey" once even if not at the beginning of the line
    line = ':Foo!foo@example.com PRIVMSG #sopel :I say hey, can you say hey?'
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'The rule must match once from anywhere'
    assert results[0].group(0) == 'hey'


# -----------------------------------------------------------------------------
# tests for :class:`sopel.plugins.rules.URLCallback`


def test_url_callback_str():
    regex = re.compile(r'.*')
    rule = rules.URLCallback([regex], plugin='testplugin', label='testrule')

    assert str(rule) == '<URLCallback testplugin.testrule (1)>'


def test_url_callback_str_no_plugin():
    regex = re.compile(r'.*')
    rule = rules.URLCallback([regex], label='testrule')

    assert str(rule) == '<URLCallback (no-plugin).testrule (1)>'


def test_url_callback_str_no_label():
    regex = re.compile(r'.*')
    rule = rules.URLCallback([regex], plugin='testplugin')

    assert str(rule) == '<URLCallback testplugin.(generic) (1)>'


def test_url_callback_str_no_plugin_label():
    regex = re.compile(r'.*')
    rule = rules.URLCallback([regex])

    assert str(rule) == '<URLCallback (no-plugin).(generic) (1)>'


def test_url_callback_parse():
    # playing with regex
    regex = re.compile(
        re.escape('https://wikipedia.com/') + r'(\w+)'
    )

    rule = rules.URLCallback([regex])
    results = list(rule.parse('https://wikipedia.com/something'))
    assert len(results) == 1, 'URLCallback on word must match only once'
    assert results[0].group(0) == 'https://wikipedia.com/something'
    assert results[0].group(1) == 'something'


def test_url_callback_match(mockbot):
    regex = re.compile(r'.*')
    rule = rules.URLCallback([regex])

    line = (
        ':Foo!foo@example.com PRIVMSG #sopel :'
        'two links http://example.com one invalid https://[dfdsdfsdf'
    )
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    matches = list(rule.match(mockbot, pretrigger))
    assert len(matches) == 1, 'URLCallback must ignore invalid URLs'
    assert matches[0].group(0) == 'http://example.com'


def test_url_callback_execute(mockbot):
    regex = re.compile(r'.*')
    rule = rules.URLCallback([regex])

    line = (
        ':Foo!foo@example.com PRIVMSG #sopel :'
        'some link https://example.com/test in your line'
    )
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    matches = list(rule.match(mockbot, pretrigger))
    match = matches[0]
    match_trigger = trigger.Trigger(
        mockbot.settings, pretrigger, match, account=None)

    with pytest.raises(RuntimeError):
        rule.execute(mockbot, match_trigger)

    def handler(wrapped, trigger):
        wrapped.say('Hi!')
        return 'The return value: %s' % trigger.group(0)

    rule = rules.URLCallback([regex], handler=handler)
    matches = list(rule.match(mockbot, pretrigger))
    match = matches[0]
    match_trigger = trigger.Trigger(
        mockbot.settings, pretrigger, match, account=None)
    wrapped = bot.SopelWrapper(mockbot, match_trigger)
    result = rule.execute(wrapped, match_trigger)

    assert mockbot.backend.message_sent == rawlist('PRIVMSG #sopel :Hi!')
    assert result == 'The return value: https://example.com/test'


def test_url_callback_match_filter_intent(mockbot):
    test_url = 'https://example.com/test'
    line = (
        ':Foo!foo@example.com PRIVMSG #sopel :'
        '\x01ACTION reads %s\x01' % test_url
    )
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    regex = re.compile(re.escape('https://example.com/') + r'(.*)')

    rule = rules.URLCallback([regex])
    matches = list(rule.match(mockbot, pretrigger))
    assert len(matches) == 1, 'Exactly one match must be found'

    match = matches[0]
    assert match.group(0) == 'https://example.com/test'
    assert match.group(1) == 'test'

    rule = rules.URLCallback([regex], ctcp=[re.compile(r'ACTION')])
    matches = list(rule.match(mockbot, pretrigger))
    assert len(matches) == 1, 'Exactly one match must be found'

    match = matches[0]
    assert match.group(0) == 'https://example.com/test'
    assert match.group(1) == 'test'

    rule = rules.URLCallback([regex], ctcp=[re.compile(r'VERSION')])
    assert not list(rule.match(mockbot, pretrigger))


def test_url_callback_from_callable(mockbot):
    base = ':Foo!foo@example.com PRIVMSG #sopel'
    link_1 = 'https://example.com/test'
    link_2 = 'https://example.com/other'
    link_3 = 'https://not-example.com/test'

    # prepare callable
    @plugin.url(re.escape('https://example.com/') + r'(\w+)')
    def handler(wrapped, trigger, match):
        wrapped.say('Hi!')
        return 'The return value: %s' % match.group(0)

    loader.clean_callable(handler, mockbot.settings)
    handler.plugin_name = 'testplugin'

    # create rule from a cleaned callable
    rule = rules.URLCallback.from_callable(mockbot.settings, handler)
    assert str(rule) == '<URLCallback testplugin.handler (1)>'

    # match on a single link
    line = '%s :%s' % (base, link_1)
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'Exactly 1 rule must match'
    assert all(result.group(0) == link_1 for result in results)

    # match on a two link
    line = '%s :%s %s' % (base, link_1, link_2)
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 2, 'Exactly 2 rules must match'
    assert results[0].group(0) == link_1
    assert results[1].group(0) == link_2

    # match only once per unique link
    line = '%s :%s %s' % (base, link_1, link_1)
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'Exactly 1 rule must match'
    assert all(result.group(0) == link_1 for result in results)

    # match on a single link with pre-text
    line = '%s :there is some pre-text: %s' % (base, link_1)
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'Exactly 1 rule must match'
    assert all(result.group(0) == link_1 for result in results)

    # match on a single link with post-text
    line = '%s :%s and with post-text this time' % (base, link_1)
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'Exactly 1 rule must match'
    assert all(result.group(0) == link_1 for result in results)

    # match on a single link with surrounding text
    line = '%s :before text %s and after text' % (base, link_1)
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'Exactly 1 rule must match'
    assert all(result.group(0) == link_1 for result in results)

    # execute based on the match
    match_trigger = trigger.Trigger(
        mockbot.settings, pretrigger, results[0], account=None)
    wrapped = bot.SopelWrapper(mockbot, match_trigger)
    result = rule.execute(wrapped, match_trigger)

    assert mockbot.backend.message_sent == rawlist('PRIVMSG #sopel :Hi!')
    assert result == 'The return value: https://example.com/test'

    # does not match an invalid link
    line = '%s :%s' % (base, link_3)
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    assert not any(rule.match(mockbot, pretrigger))


def test_url_callback_from_callable_no_match_parameter(mockbot):
    base = ':Foo!foo@example.com PRIVMSG #sopel'
    link = 'https://example.com/test'

    # prepare callable
    @plugin.url(re.escape('https://example.com/') + r'(\w+)')
    def handler(wrapped, trigger):
        wrapped.say('Hi!')
        return 'The return value: %s' % trigger.group(0)

    loader.clean_callable(handler, mockbot.settings)
    handler.plugin_name = 'testplugin'

    # create rule from a cleaned callable
    rule = rules.URLCallback.from_callable(mockbot.settings, handler)
    assert str(rule) == '<URLCallback testplugin.handler (1)>'

    # execute based on the match
    line = '%s :before text %s and after text' % (base, link)
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    match_trigger = trigger.Trigger(
        mockbot.settings, pretrigger, results[0], account=None)
    wrapped = bot.SopelWrapper(mockbot, match_trigger)
    result = rule.execute(wrapped, match_trigger)

    assert mockbot.backend.message_sent == rawlist('PRIVMSG #sopel :Hi!')
    assert result == 'The return value: https://example.com/test'


def test_url_callback_from_callable_lazy(mockbot):
    base = ':Foo!foo@example.com PRIVMSG #sopel'
    link_1 = 'https://example.com/test'
    link_2 = 'https://help.example.com/other'
    link_3 = 'https://not-example.com/test'

    def lazy_loader(settings):
        return [
            re.compile(re.escape('https://example.com/') + r'(\w+)'),
            re.compile(re.escape('https://help.example.com/') + r'(\w+)'),
        ]

    # prepare callable
    @plugin.url_lazy(lazy_loader)
    def handler(wrapped, trigger):
        wrapped.say('Hi!')
        return 'The return value: %s' % trigger.group(0)

    loader.clean_callable(handler, mockbot.settings)
    handler.plugin_name = 'testplugin'

    # create rule from a cleaned callable
    rule = rules.URLCallback.from_callable_lazy(mockbot.settings, handler)
    assert str(rule) == '<URLCallback testplugin.handler (2)>'

    # match on the example.com link
    line = '%s :%s' % (base, link_1)
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'Exactly 1 rule must match'
    print(list(result.group(0) for result in results))
    assert all(result.group(0) == link_1 for result in results)

    # match on the help.example.com link
    line = '%s :%s' % (base, link_2)
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    results = list(rule.match(mockbot, pretrigger))

    assert len(results) == 1, 'Exactly 1 rule must match'
    assert all(result.group(0) == link_2 for result in results)

    # does not match an invalid link
    line = '%s :%s' % (base, link_3)
    pretrigger = trigger.PreTrigger(mockbot.nick, line)
    assert not any(rule.match(mockbot, pretrigger))


def test_url_callback_from_callable_invalid(mockbot):
    def url_loader(settings):
        return [
            re.compile(re.escape('https://example.com/') + r'(\w+)'),
        ]

    # prepare callable
    @plugin.url_lazy(url_loader)
    def handler(wrapped, trigger, match=None):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # create rule from a cleaned callable
    with pytest.raises(RuntimeError):
        rules.URLCallback.from_callable(mockbot.settings, handler)


def test_url_callback_from_callable_lazy_invalid(mockbot):
    # prepare callable
    @plugin.url(r'.*')
    def handler(wrapped, trigger, match=None):
        wrapped.reply('Hi!')

    loader.clean_callable(handler, mockbot.settings)

    # create rule from a cleaned callable
    with pytest.raises(RuntimeError):
        rules.URLCallback.from_callable_lazy(mockbot.settings, handler)
