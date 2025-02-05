"""coretasks.py tests"""
from __future__ import annotations

from datetime import datetime, timezone
import logging

import pytest

from sopel import coretasks
from sopel.irc import isupport
from sopel.module import ADMIN, HALFOP, OP, OWNER, VOICE
from sopel.tests import rawlist
from sopel.tools import Identifier


TMP_CONFIG = """
[core]
owner = Uowner
nick = TestBot
enable = coretasks
"""


@pytest.fixture
def tmpconfig(configfactory):
    return configfactory('conf.ini', TMP_CONFIG)


@pytest.fixture
def mockbot(tmpconfig, botfactory):
    return botfactory.preloaded(tmpconfig)


def test_bot_mixed_modes(mockbot, ircfactory):
    """Ensure mixed modes like ``+vha`` are tracked correctly.

    Sopel 6.6.6 and older would assign all modes to all users.

    .. seealso::

        GitHub issue #1575 (https://github.com/sopel-irc/sopel/pull/1575).
    """
    irc = ircfactory(mockbot)
    irc.channel_joined('#test', [
        'Uowner', 'Uvoice', 'Uhalfop', 'Uadmin', 'Uop', 'Unothing'])
    irc.mode_set('#test', '+qvhao', [
        'Uowner', 'Uvoice', 'Uhalfop', 'Uadmin', 'Uop'])

    assert mockbot.channels["#test"].privileges[Identifier("Uowner")] == OWNER
    assert mockbot.channels["#test"].privileges[Identifier("Uvoice")] == VOICE
    assert mockbot.channels["#test"].privileges[Identifier("Uhalfop")] == HALFOP
    assert mockbot.channels["#test"].privileges[Identifier("Uadmin")] == ADMIN
    assert mockbot.channels["#test"].privileges[Identifier("Uop")] == OP
    assert mockbot.channels["#test"].privileges[Identifier("Unothing")] == 0


def test_bot_mixed_mode_removal(mockbot, ircfactory):
    """Ensure mixed mode types like ``-h+a`` are handled.

    Sopel 6.6.6 and older did not handle this correctly.

    .. seealso::

        GitHub issue #1575 (https://github.com/sopel-irc/sopel/pull/1575).
    """
    irc = ircfactory(mockbot)
    irc.bot._isupport = isupport.ISupport(chanmodes=("b", "", "", "m", tuple()))
    irc.bot.modeparser.chanmodes = irc.bot.isupport.CHANMODES
    irc.channel_joined('#test', ['Uvoice', 'Uop'])

    irc.mode_set('#test', '+qao', ['Uvoice', 'Uvoice', 'Uvoice'])
    assert mockbot.channels["#test"].privileges[Identifier("Uop")] == 0
    assert mockbot.channels["#test"].privileges[Identifier("Uvoice")] == (
        ADMIN + OWNER + OP), 'Uvoice got +q, +a, and +o modes'

    irc.mode_set('#test', '-o+o-qa+v', [
        'Uvoice', 'Uop', 'Uvoice', 'Uvoice', 'Uvoice'])
    assert mockbot.channels["#test"].privileges[Identifier("Uop")] == OP, (
        'Uop got +o only')
    assert mockbot.channels["#test"].privileges[Identifier("Uvoice")] == VOICE, (
        'Uvoice got -o, -q, -a, then +v')


def test_bot_mixed_mode_types(mockbot, ircfactory):
    """Ensure mixed argument-required and -not-required modes are handled.

    Sopel 6.6.6 and older did not behave well.

    .. seealso::

        GitHub issue #1575 (https://github.com/sopel-irc/sopel/pull/1575).
    """
    irc = ircfactory(mockbot)
    irc.bot._isupport = isupport.ISupport(chanmodes=("be", "", "", "mn", tuple()))
    irc.bot.modeparser.chanmodes = irc.bot.isupport.CHANMODES
    irc.channel_joined('#test', [
        'Uvoice', 'Uop', 'Uadmin', 'Uvoice2', 'Uop2', 'Uadmin2'])
    irc.mode_set('#test', '+amovn', ['Uadmin', 'Uop', 'Uvoice'])

    assert mockbot.channels["#test"].privileges[Identifier("Uadmin")] == ADMIN
    assert mockbot.channels["#test"].modes["m"]
    assert mockbot.channels["#test"].privileges[Identifier("Uop")] == OP
    assert mockbot.channels["#test"].privileges[Identifier("Uvoice")] == VOICE
    assert mockbot.channels["#test"].modes["n"]

    irc.mode_set('#test', '+above', ['Uadmin2', 'x!y@z', 'Uop2', 'Uvoice2', 'a!b@c'])

    assert mockbot.channels["#test"].privileges[Identifier("Uadmin2")] == ADMIN
    assert "x!y@z" in mockbot.channels["#test"].modes["b"]
    assert mockbot.channels["#test"].privileges[Identifier("Uop2")] == OP
    assert mockbot.channels["#test"].privileges[Identifier("Uvoice2")] == VOICE
    assert "a!b@c" in mockbot.channels["#test"].modes["e"]


def test_bot_unknown_mode(mockbot, ircfactory):
    """Ensure modes not in PREFIX or CHANMODES trigger a WHO."""
    irc = ircfactory(mockbot)
    irc.bot._isupport = isupport.ISupport(chanmodes=("b", "", "", "mnt", tuple()))
    irc.bot.modeparser.chanmodes = irc.bot.isupport.CHANMODES
    irc.channel_joined("#test", ["Alex", "Bob", "Cheryl"])
    irc.mode_set("#test", "+te", ["Alex"])

    assert mockbot.channels["#test"].privileges[Identifier("Alex")] == 0
    assert mockbot.backend.message_sent == rawlist(
        "WHO #test"
    ), "Upon finding an unknown mode, the bot must send a WHO request."


def test_bot_unknown_priv_mode(mockbot, ircfactory):
    """Ensure modes in `mapping` but not PREFIX are treated as unknown."""
    irc = ircfactory(mockbot)
    irc.bot._isupport = isupport.ISupport(prefix={"o": "@", "v": "+"})
    irc.bot.modeparser.privileges = set(irc.bot.isupport.PREFIX.keys())
    irc.channel_joined("#test", ["Alex", "Bob", "Cheryl"])
    irc.mode_set("#test", "+oh", ["Alex", "Bob"])

    assert mockbot.channels["#test"].privileges[Identifier("Bob")] == 0
    assert mockbot.backend.message_sent == rawlist(
        "WHO #test"
    ), "The bot must treat mapped but non-PREFIX modes as unknown."


def test_bot_extra_mode_args(mockbot, ircfactory, caplog):
    """Test warning on extraneous MODE args."""
    irc = ircfactory(mockbot)
    irc.bot._isupport = isupport.ISupport(chanmodes=("b", "k", "l", "mnt", tuple()))
    irc.bot.modeparser.chanmodes = irc.bot.isupport.CHANMODES
    irc.channel_joined("#test", ["Alex", "Bob", "Cheryl"])

    mode_msg = ":Sopel!bot@bot MODE #test +m nonsense"
    mockbot.on_message(mode_msg)

    assert mockbot.channels["#test"].modes["m"]
    assert "Too many arguments received for MODE" in caplog.text


def test_handle_rpl_channelmodeis(mockbot, ircfactory):
    """Test handling RPL_CHANNELMODEIS events, response to MODE query."""
    rpl_channelmodeis = " ".join([
        ":niven.freenode.net",
        "324",
        "TestName",
        "#test",
        "+knlt",
        "hunter2",
        ":1",
    ])
    irc = ircfactory(mockbot)
    irc.bot._isupport = isupport.ISupport(chanmodes=("b", "k", "l", "mnt", tuple()))
    irc.bot.modeparser.chanmodes = irc.bot.isupport.CHANMODES
    irc.channel_joined("#test", ["Alex", "Bob", "Cheryl"])
    mockbot.on_message(rpl_channelmodeis)

    assert mockbot.channels["#test"].modes["k"] == "hunter2"
    assert mockbot.channels["#test"].modes["n"]
    assert mockbot.channels["#test"].modes["l"] == "1"
    assert mockbot.channels["#test"].modes["t"]


def test_handle_rpl_channelmodeis_clear(mockbot, ircfactory):
    """Test RPL_CHANNELMODEIS events clearing previous modes"""
    irc = ircfactory(mockbot)
    irc.bot._isupport = isupport.ISupport(chanmodes=("b", "k", "l", "mnt", tuple()))
    irc.bot.modeparser.chanmodes = irc.bot.isupport.CHANMODES
    irc.channel_joined("#test", ["Alex", "Bob", "Cheryl"])

    rpl_base = ":mercury.libera.chat 324 TestName #test {modes}"
    mockbot.on_message(rpl_base.format(modes="+knlt hunter2 :1"))
    mockbot.on_message(rpl_base.format(modes="+kl hunter2 :1"))

    assert mockbot.channels["#test"].modes["k"] == "hunter2"
    assert "n" not in mockbot.channels["#test"].modes
    assert mockbot.channels["#test"].modes["l"] == "1"
    assert "t" not in mockbot.channels["#test"].modes


def test_mode_colon(mockbot, ircfactory):
    """Ensure mode messages with colons are parsed properly."""
    irc = ircfactory(mockbot)
    irc.channel_joined('#test', ['Uadmin', 'Uvoice'])
    irc.mode_set('#test', '+av', ['Uadmin', ':Uvoice'])

    assert mockbot.channels["#test"].privileges[Identifier("Uvoice")] == VOICE
    assert mockbot.channels["#test"].privileges[Identifier("Uadmin")] == ADMIN


def test_execute_perform_raise_not_connected(mockbot):
    """Ensure bot will not execute ``commands_on_connect`` unless connected."""
    with pytest.raises(Exception):
        coretasks._execute_perform(mockbot)


def test_execute_perform_send_commands(mockbot):
    """Ensure bot sends ``commands_on_connect`` as specified in config."""
    commands = [
        # Example command for identifying to services on Undernet
        'PRIVMSG X@Channels.undernet.org :LOGIN my_username my_password',
        # Set modes on connect
        'MODE some_nick +Xx',
        # Oper on connect
        'OPER oper_username oper_password',
    ]

    mockbot.config.core.commands_on_connect = commands
    # For testing, pretend connection already happened
    mockbot.backend.connected = True
    mockbot._connection_registered.set()

    coretasks._execute_perform(mockbot)
    assert mockbot.backend.message_sent == rawlist(*commands)


def test_execute_perform_replaces_nickname(mockbot):
    """Confirm that bot replaces ``$nickname`` placeholder in commands."""
    command = 'MODE $nickname +Xxw'
    sent_command = 'MODE {} +Xxw'.format(mockbot.config.core.nick)

    mockbot.config.core.commands_on_connect = [command, ]
    # For testing, pretend connection already happened
    mockbot.backend.connected = True
    mockbot._connection_registered.set()

    coretasks._execute_perform(mockbot)
    assert mockbot.backend.message_sent == rawlist(sent_command)


def test_handle_isupport(mockbot):
    mockbot.on_message(
        ':irc.example.com 005 Sopel '
        'CHANTYPES=# EXCEPTS INVEX CHANMODES=eIbq,k,flj,CFLMPQScgimnprstz '
        'CHANLIMIT=#:120 PREFIX=(ov)@+ MAXLIST=bqeI:100 MODES=4 '
        'NETWORK=example STATUSMSG=@+ CALLERID=g CASEMAPPING=rfc1459 '
        ':are supported by this server')

    assert hasattr(mockbot, 'isupport')
    assert 'CHANTYPES' in mockbot.isupport
    assert 'EXCEPTS' in mockbot.isupport
    assert 'INVEX' in mockbot.isupport
    assert 'CHANMODES' in mockbot.isupport
    assert 'CHANLIMIT' in mockbot.isupport
    assert 'PREFIX' in mockbot.isupport
    assert 'NETWORK' in mockbot.isupport
    assert 'STATUSMSG' in mockbot.isupport
    assert 'CALLERID' in mockbot.isupport
    assert 'CASEMAPPING' in mockbot.isupport

    assert mockbot.isupport['CHANTYPES'] == ('#',)
    assert mockbot.isupport['EXCEPTS'] == 'e'
    assert mockbot.isupport['INVEX'] == 'I'
    assert mockbot.isupport['CHANMODES'] == (
        'eIbq', 'k', 'flj', 'CFLMPQScgimnprstz', tuple())
    assert hasattr(mockbot.isupport, 'CHANMODES')
    assert mockbot.isupport.CHANMODES == {
        'A': 'eIbq',
        'B': 'k',
        'C': 'flj',
        'D': 'CFLMPQScgimnprstz',
    }
    assert mockbot.isupport['CHANLIMIT'] == (('#', 120),)
    assert mockbot.isupport['PREFIX'] == (('o', '@'), ('v', '+'))
    assert mockbot.isupport['NETWORK'] == 'example'

    # not yet advertised
    assert 'CHARSET' not in mockbot.isupport
    assert 'NAMESX' not in mockbot.isupport

    # update
    mockbot.on_message(
        ':irc.example.com 005 Sopel '
        'CHARSET=ascii NICKLEN=16 CHANNELLEN=50 TOPICLEN=390 DEAF=D FNC '
        'TARGMAX=NAMES:1,LIST:1,KICK:1,WHOIS:1,PRIVMSG:4,NOTICE:4,ACCEPT:,'
        'MONITOR: EXTBAN=$,ajrxz CLIENTVER=3.0 ETRACE WHOX KNOCK '
        ':are supported by this server')

    # now they are advertised
    assert 'CHARSET' in mockbot.isupport
    assert 'NICKLEN' in mockbot.isupport
    assert 'CHANNELLEN' in mockbot.isupport
    assert 'TOPICLEN' in mockbot.isupport
    assert 'DEAF' in mockbot.isupport
    assert 'FNC' in mockbot.isupport
    assert 'TARGMAX' in mockbot.isupport
    assert 'EXTBAN' in mockbot.isupport
    assert 'CLIENTVER' in mockbot.isupport
    assert 'ETRACE' in mockbot.isupport
    assert 'WHOX' in mockbot.isupport
    assert 'KNOCK' in mockbot.isupport

    # but namesx still isn't!
    assert 'NAMESX' not in mockbot.isupport

    mockbot.on_message(
        ':irc.example.com 005 Sopel '
        'SAFELIST ELIST=CTU CPRIVMSG CNOTICE '
        ':are supported by this server')

    assert 'SAFELIST' in mockbot.isupport
    assert 'ELIST' in mockbot.isupport
    assert 'CPRIVMSG' in mockbot.isupport
    assert 'CNOTICE' in mockbot.isupport


def test_handle_isupport_casemapping(mockbot):
    # Set bot's nick to something that needs casemapping
    mockbot.settings.core.nick = 'Test[a]'
    mockbot._nick = mockbot.make_identifier(mockbot.settings.core.nick)

    # check default behavior (`rfc1459` casemapping)
    assert mockbot.nick.lower() == 'test{a}'
    assert str(mockbot.nick) == 'Test[a]'

    # now the bot "connects" to a server using `CASEMAPPING=ascii`
    mockbot.on_message(
        ':irc.example.com 005 Sopel '
        'CHANTYPES=# EXCEPTS INVEX CHANMODES=eIbq,k,flj,CFLMPQScgimnprstz '
        'CHANLIMIT=#:120 PREFIX=(ov)@+ MAXLIST=bqeI:100 MODES=4 '
        'NETWORK=example STATUSMSG=@+ CALLERID=g CASEMAPPING=ascii '
        ':are supported by this server')

    assert mockbot.nick.lower() == 'test[a]'


def test_handle_isupport_casemapping_identifiermemory(mockbot):
    # create a nick that needs casemapping
    rfc1459 = 'Test[a]'

    # create `SopelIdentifierMemory` w/bot's helper method and add the nick
    memory = mockbot.make_identifier_memory()
    memory[rfc1459] = rfc1459

    # check default behavior (`rfc1459` casemapping)
    assert memory['test{a}'] == rfc1459
    assert memory['Test[a]'] == rfc1459

    # now the bot "connects" to a server using `CASEMAPPING=ascii`
    mockbot.on_message(
        ':irc.example.com 005 Sopel '
        'CHANTYPES=# EXCEPTS INVEX CHANMODES=eIbq,k,flj,CFLMPQScgimnprstz '
        'CHANLIMIT=#:120 PREFIX=(ov)@+ MAXLIST=bqeI:100 MODES=4 '
        'NETWORK=example STATUSMSG=@+ CALLERID=g CASEMAPPING=ascii '
        ':are supported by this server')

    # CASEMAPPING token change doesn't affect previously existing Identifiers...
    assert memory['Test{a}'] == rfc1459
    # ...so we have to create a new nick that will casemap differently now
    ascii = 'Test[b]'
    memory[ascii] = ascii
    assert len(memory) == 2
    assert memory['test[b]'] == ascii
    assert 'test{b}' not in memory


def test_handle_isupport_chantypes(mockbot):
    # check default behavior (chantypes allows #, &, +, and !)
    assert not mockbot.make_identifier('#channel').is_nick()
    assert not mockbot.make_identifier('&channel').is_nick()
    assert not mockbot.make_identifier('+channel').is_nick()
    assert not mockbot.make_identifier('!channel').is_nick()

    # now the bot "connects" to a server using `CHANTYPES=#`
    mockbot.on_message(
        ':irc.example.com 005 Sopel '
        'CHANTYPES=# EXCEPTS INVEX CHANMODES=eIbq,k,flj,CFLMPQScgimnprstz '
        'CHANLIMIT=#:120 PREFIX=(ov)@+ MAXLIST=bqeI:100 MODES=4 '
        'NETWORK=example STATUSMSG=@+ CALLERID=g CASEMAPPING=ascii '
        ':are supported by this server')

    assert not mockbot.make_identifier('#channel').is_nick()
    assert mockbot.make_identifier('&channel').is_nick()
    assert mockbot.make_identifier('+channel').is_nick()
    assert mockbot.make_identifier('!channel').is_nick()


@pytest.mark.parametrize('modes', [None, '', 'Rw'])
def test_handle_isupport_bot_mode(mockbot, modes):
    mockbot.config.core.modes = modes

    mockbot.on_message(
        ':irc.example.com 005 Sopel '
        'SAFELIST ELIST=CTU CPRIVMSG CNOTICE '
        ':are supported by this server')

    assert 'BOT' not in mockbot.isupport
    assert mockbot.backend.message_sent == []

    mockbot.on_message(
        ':irc.example.com 005 Sopel '
        'BOT=B '
        ':are supported by this server')

    assert 'BOT' in mockbot.isupport
    assert mockbot.isupport['BOT'] == 'B'
    assert mockbot.backend.message_sent == rawlist('MODE TestBot +B')

    mockbot.on_message(
        ':irc.example.com 005 Sopel '
        'BOT=B '
        ':are supported by this server')

    assert len(mockbot.backend.message_sent) == 1, 'No need to resend!'


@pytest.mark.parametrize('modes', ['B', 'RBw'])
def test_handle_isupport_bot_mode_override(mockbot, modes):
    mockbot.config.core.modes = modes

    mockbot.on_message(
        ':irc.example.com 005 Sopel '
        'BOT=B '
        ':are supported by this server')

    assert 'BOT' in mockbot.isupport
    assert mockbot.isupport['BOT'] == 'B'
    assert mockbot.backend.message_sent == [], (
        'Bot should not set mode overridden by config setting'
    )


def test_handle_isupport_namesx(mockbot):
    mockbot.on_message(
        ':irc.example.com 005 Sopel '
        'SAFELIST ELIST=CTU CPRIVMSG CNOTICE '
        ':are supported by this server')

    assert 'NAMESX' not in mockbot.isupport
    assert mockbot.backend.message_sent == []
    assert 'multi-prefix' not in mockbot.server_capabilities

    mockbot.on_message(
        ':irc.example.com 005 Sopel '
        'NAMESX '
        ':are supported by this server')

    assert 'NAMESX' in mockbot.isupport
    assert mockbot.backend.message_sent == rawlist('PROTOCTL NAMESX')

    mockbot.on_message(
        ':irc.example.com 005 Sopel '
        'NAMESX '
        ':are supported by this server')

    assert len(mockbot.backend.message_sent) == 1, 'No need to resend!'


def test_handle_isupport_uhnames(mockbot):
    mockbot.on_message(
        ':irc.example.com 005 Sopel '
        'SAFELIST ELIST=CTU CPRIVMSG CNOTICE '
        ':are supported by this server')

    assert 'UHNAMES' not in mockbot.isupport
    assert mockbot.backend.message_sent == []
    assert 'userhost-in-names' not in mockbot.server_capabilities

    mockbot.on_message(
        ':irc.example.com 005 Sopel '
        'UHNAMES '
        ':are supported by this server')

    assert 'UHNAMES' in mockbot.isupport
    assert mockbot.backend.message_sent == rawlist('PROTOCTL UHNAMES')

    mockbot.on_message(
        ':irc.example.com 005 Sopel '
        'UHNAMES '
        ':are supported by this server')

    assert len(mockbot.backend.message_sent) == 1, 'No need to resend!'


def test_handle_isupport_namesx_with_multi_prefix(mockbot):
    # set multi-prefix
    mockbot.on_message(':irc.example.com CAP Sopel ACK :multi-prefix')

    # send NAMESX in ISUPPORT
    mockbot.on_message(
        ':irc.example.com 005 Sopel '
        'NAMESX '
        ':are supported by this server')

    assert 'NAMESX' in mockbot.isupport
    assert mockbot.backend.message_sent == [], (
        'Sopel must not send PROTOCTL NAMESX '
        'when multi-prefix capability is available'
    )


def test_handle_rpl_myinfo(mockbot):
    """Test handling RPL_MYINFO events."""
    assert not hasattr(mockbot, 'myinfo'), (
        'Attribute myinfo is not available until the server sends RPL_MYINFO')

    rpl_myinfo = ' '.join([
        ':niven.freenode.net',
        '004',
        'TestName',
        'irc.example.net',
        'example-1.2.3',
        # modes for channels and users are ignored by Sopel
        # we prefer to use RPL_ISUPPORT for that
        'DOQRSZaghilopsuwz',
        'CFILMPQSbcefgijklmnopqrstuvz',
        'bkloveqjfI',
        # text is ignored for RPL_MYINFO
        ':Some random text',
    ])
    mockbot.on_message(rpl_myinfo)

    assert hasattr(mockbot, 'myinfo')
    assert mockbot.myinfo.client == 'TestName'
    assert mockbot.myinfo.servername == 'irc.example.net'
    assert mockbot.myinfo.version == 'example-1.2.3'


def test_recv_chghost(mockbot, ircfactory):
    """Ensure that CHGHOST messages are correctly handled."""
    irc = ircfactory(mockbot)
    irc.channel_joined("#test", ["Alex", "Bob", "Cheryl"])

    mockbot.on_message(":Alex!~alex@test.local CHGHOST alex identd.confirmed")

    assert mockbot.users[Identifier('Alex')].user == 'alex'
    assert mockbot.users[Identifier('Alex')].host == 'identd.confirmed'


def test_recv_chghost_invalid(mockbot, ircfactory, caplog):
    """Ensure that malformed CHGHOST messages are ignored and logged."""
    irc = ircfactory(mockbot)
    irc.channel_joined("#test", ["Alex", "Bob", "Cheryl"])
    alex = Identifier('Alex')
    bob = Identifier('Bob')
    cheryl = Identifier('Cheryl')

    # Mock bot + mock IRC server doesn't populate these on its own
    assert mockbot.users[alex].user is None
    assert mockbot.users[alex].host is None
    assert mockbot.users[bob].user is None
    assert mockbot.users[bob].host is None
    assert mockbot.users[cheryl].user is None
    assert mockbot.users[cheryl].host is None

    mockbot.on_message(":Alex!~alex@test.local CHGHOST alex is a boss")
    mockbot.on_message(":Bob!bob@grills.burgers CHGHOST rarely")
    mockbot.on_message(":Cheryl!~carol@danger.zone CHGHOST")

    # These should be unchanged
    assert mockbot.users[alex].user is None
    assert mockbot.users[alex].host is None
    assert mockbot.users[bob].user is None
    assert mockbot.users[bob].host is None
    assert mockbot.users[cheryl].user is None
    assert mockbot.users[cheryl].host is None

    # Meanwhile, the malformed input should have generated log lines
    assert len(caplog.messages) == 3
    assert 'extra arguments' in caplog.messages[0]
    assert 'insufficient arguments' in caplog.messages[1]
    assert 'insufficient arguments' in caplog.messages[2]


def test_join_time(mockbot):
    """Make sure channel.join_time is set from JOIN echo time tag"""
    mockbot.on_message(
        "@time=2021-01-01T12:00:00.015Z :TestBot!bot@bot JOIN #test * :bot"
    )
    assert mockbot.channels["#test"].join_time == datetime(
        2021, 1, 1, 12, 0, 0, 15000, tzinfo=timezone.utc
    )


def test_handle_rpl_namreply_with_malformed_uhnames(mockbot, caplog):
    """Make sure Sopel can cope with expected but missing hostmask in 353"""
    caplog.set_level(logging.DEBUG)
    mockbot.on_message(
        ':somenet.behind.znc 005 Sopel '
        'UHNAMES '
        ':are supported by this server')
    mockbot.on_message(
        ':somenet.behind.znc 353 Sopel = #sopel '
        ':correct!~right@alwa.ys incorrect')

    assert len(caplog.messages) == 1
    assert 'RPL_NAMREPLY item without a hostmask' in caplog.messages[0]


def test_handle_who_reply(mockbot):
    """Make sure Sopel correctly updates user info from WHO replies"""
    # verify we start with no users/channels
    assert len(mockbot.users) == 0
    assert 'Internets' not in mockbot.users
    assert len(mockbot.channels) == 0
    assert '#channel' not in mockbot.channels

    # add one user, who is Here
    mockbot.on_message(
        ':some.irc.network 352 Sopel #channel '
        'internets services.irc.network * Internets Hr* '
        ':0 Network Services Bot')
    mockbot.on_message(
        ':some.irc.network 315 Sopel #channel '
        ':End of /WHO list.')

    assert len(mockbot.users) == 1
    assert 'Internets' in mockbot.users
    assert mockbot.users['Internets'].nick == 'Internets'
    assert mockbot.users['Internets'].user == 'internets'
    assert mockbot.users['Internets'].host == 'services.irc.network'
    assert mockbot.users['Internets'].realname == 'Network Services Bot'
    assert mockbot.users['Internets'].away is False
    assert mockbot.users['Internets'].is_bot is None

    assert '#channel' in mockbot.channels
    assert mockbot.channels['#channel']
    assert len(mockbot.channels['#channel'].users) == 1
    assert 'Internets' in mockbot.channels['#channel'].users
    assert (
        mockbot.users['Internets'] is mockbot.channels['#channel'].users['Internets']
    )

    # on next WHO, user has been marked as Gone
    mockbot.on_message(
        ':some.irc.network 352 Sopel #channel '
        'internets services.irc.network * Internets Gr* '
        ':0 Network Services Bot')
    mockbot.on_message(
        ':some.irc.network 315 Sopel #channel '
        ':End of /WHO list.')

    assert mockbot.users['Internets'].away is True
    assert mockbot.users['Internets'].is_bot is None


def test_handle_who_reply_botmode(mockbot):
    """Make sure Sopel correctly tracks users' bot status from WHO replies"""
    mockbot.on_message(
        ':irc.example.com 005 Sopel '
        'BOT=B '
        ':are supported by this server')

    # non-bot user
    mockbot.on_message(
        ':some.irc.network 352 Sopel #channel '
        'human somewhere.in.the.world * E_R_Bradshaw H* '
        ':0 E. R. Bradshaw')

    assert mockbot.users['E_R_Bradshaw'].is_bot is False

    # bot user
    mockbot.on_message(
        ':some.irc.network 352 Sopel #channel '
        'internets services.irc.network * Internets HBr* '
        ':0 Network Services Bot')
    mockbot.on_message(
        ':some.irc.network 315 Sopel #channel '
        ':End of /WHO list.')

    assert mockbot.users['Internets'].is_bot is True


def test_handle_setname(mockbot):
    """Make sure Sopel updates user's realname from SETNAME message"""
    # add one user
    mockbot.on_message(
        ':some.irc.network 352 Sopel #channel '
        'internets services.irc.network * Internets Hr* '
        ':0 Network Services Bot')
    mockbot.on_message(
        ':some.irc.network 315 Sopel #channel '
        ':End of /WHO list.')

    assert 'Internets' in mockbot.users
    assert mockbot.users['Internets'].realname == 'Network Services Bot'

    # have the user change their realname
    mockbot.on_message(
        ':Internets!internets@services.irc.network '
        'SETNAME :Bot du service réseau'
    )

    assert mockbot.users['Internets'].realname == 'Bot du service réseau'

    # change user's realname again to something not requiring a colon
    # (this corresponds to an example specifically shown in the `setname` spec)
    mockbot.on_message(
        ':Internets!internets@services.irc.network '
        'SETNAME ServiceBot'
    )

    assert mockbot.users['Internets'].realname == 'ServiceBot'


def test_handle_setname_no_user(mockbot, caplog):
    """Make sure Sopel ignores SETNAME message for unknown user"""
    caplog.set_level(logging.DEBUG)
    mockbot.on_message(':Akarin!yuruyuri@hajimaru.yo SETNAME :Bun Bazooka')

    assert len(caplog.messages) == 1
    assert caplog.messages[0] == (
        "Discarding SETNAME ('Bun Bazooka') received for unknown user Akarin.")
    assert caplog.record_tuples[0][1] == logging.DEBUG
