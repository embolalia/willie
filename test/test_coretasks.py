# coding=utf-8
"""coretasks.py tests"""
from __future__ import unicode_literals, absolute_import, print_function, division

import pytest

from sopel import coretasks
from sopel.bot import ServerISupport
from sopel.module import VOICE, HALFOP, OP, ADMIN, OWNER
from sopel.tools import Identifier
from sopel.test_tools import MockSopel, MockSopelWrapper
from sopel.trigger import PreTrigger, Trigger


@pytest.fixture
def sopel():
    bot = MockSopel("Sopel")
    bot.server_hostname = None
    bot.server_isupport = ServerISupport()
    return bot


def test_bot_mixed_modes(sopel):
    """
    Ensure mixed modes like +vha are tracked correctly.
    Sopel 6.6.6 and older would assign all modes to all users. #1575
    """

    # RPL_NAMREPLY to create Users and (zeroed) privs
    for user in set("Unothing Uvoice Uhalfop Uop Uadmin Uowner".split(" ")):
        pretrigger = PreTrigger(
            "Foo", ":test.example.com 353 Foo = #test :Foo %s" % user
        )
        trigger = Trigger(sopel.config, pretrigger, None)
        coretasks.handle_names(MockSopelWrapper(sopel, trigger), trigger)

    pretrigger = PreTrigger("Foo", "MODE #test +qvhao Uowner Uvoice Uhalfop Uadmin Uop")
    trigger = Trigger(sopel.config, pretrigger, None)
    coretasks.track_modes(MockSopelWrapper(sopel, trigger), trigger)

    assert sopel.channels["#test"].privileges[Identifier("Unothing")] == 0
    assert sopel.channels["#test"].privileges[Identifier("Uvoice")] == VOICE
    assert sopel.channels["#test"].privileges[Identifier("Uhalfop")] == HALFOP
    assert sopel.channels["#test"].privileges[Identifier("Uop")] == OP
    assert sopel.channels["#test"].privileges[Identifier("Uadmin")] == ADMIN
    assert sopel.channels["#test"].privileges[Identifier("Uowner")] == OWNER


def test_bot_mixed_mode_removal(sopel):
    """
    Ensure mixed mode types like -h+a are handled
    Sopel 6.6.6 and older did not handle this correctly. #1575
    """

    # RPL_NAMREPLY to create Users and (zeroed) privs
    for user in set("Uvoice Uop".split(" ")):
        pretrigger = PreTrigger(
            "Foo", ":test.example.com 353 Foo = #test :Foo %s" % user
        )
        trigger = Trigger(sopel.config, pretrigger, None)
        coretasks.handle_names(MockSopelWrapper(sopel, trigger), trigger)

    pretrigger = PreTrigger("Foo", "MODE #test +qao Uvoice Uvoice Uvoice")
    trigger = Trigger(sopel.config, pretrigger, None)
    coretasks.track_modes(MockSopelWrapper(sopel, trigger), trigger)

    pretrigger = PreTrigger(
        "Foo", "MODE #test -o+o-qa+v Uvoice Uop Uvoice Uvoice Uvoice"
    )
    trigger = Trigger(sopel.config, pretrigger, None)
    coretasks.track_modes(MockSopelWrapper(sopel, trigger), trigger)

    assert sopel.channels["#test"].privileges[Identifier("Uvoice")] == VOICE
    assert sopel.channels["#test"].privileges[Identifier("Uop")] == OP


def test_bot_mixed_mode_types(sopel):
    """
    Ensure mixed argument- and non-argument- modes are handled
    Sopel 6.6.6 and older did not behave well. #1575
    """

    # RPL_NAMREPLY to create Users and (zeroed) privs
    for user in set("Uvoice Uop Uadmin Uvoice2 Uop2 Uadmin2".split(" ")):
        pretrigger = PreTrigger(
            "Foo", ":test.example.com 353 Foo = #test :Foo %s" % user
        )
        trigger = Trigger(sopel.config, pretrigger, None)
        coretasks.handle_names(MockSopelWrapper(sopel, trigger), trigger)

    # Non-attribute-requiring non-permission mode
    pretrigger = PreTrigger("Foo", "MODE #test +amov Uadmin Uop Uvoice")
    trigger = Trigger(sopel.config, pretrigger, None)
    coretasks.track_modes(MockSopelWrapper(sopel, trigger), trigger)

    assert sopel.channels["#test"].privileges[Identifier("Uvoice")] == VOICE
    assert sopel.channels["#test"].privileges[Identifier("Uop")] == OP
    assert sopel.channels["#test"].privileges[Identifier("Uadmin")] == ADMIN

    # Attribute-requiring non-permission modes
    # This results in a _send_who, which isn't supported in MockSopel or this
    # test, so we just make sure it results in an exception instead of privesc.
    pretrigger = PreTrigger("Foo", "MODE #test +abov Uadmin2 x!y@z Uop2 Uvoice2")
    trigger = Trigger(sopel.config, pretrigger, None)
    try:
        coretasks.track_modes(MockSopelWrapper(sopel, trigger), trigger)
    except AttributeError as e:
        if e.args[0] == "'MockSopel' object has no attribute 'enabled_capabilities'":
            return

    assert sopel.channels["#test"].privileges[Identifier("Uvoice2")] == VOICE
    assert sopel.channels["#test"].privileges[Identifier("Uop2")] == OP
    assert sopel.channels["#test"].privileges[Identifier("Uadmin2")] == ADMIN


def test_parse_reply_myinfo(sopel):
    pretrigger = PreTrigger('Foo', ':test.example.com 004 Sopel test.example.com SomeIRCd-v0 uSeRmOdEs cHaNnElMoDeS')
    trigger = Trigger(sopel.config, pretrigger, None)
    coretasks.parse_reply_myinfo(MockSopelWrapper(sopel, trigger), trigger)

    assert sopel.server_hostname == 'test.example.com'


def test_parse_reply_isupport(sopel):
    tokens = [
        # Parameter only (flag)
        'SAFELIST',
        # Non-flag parameter only
        'SILENCE',  # Indicates the server does not support the command
        # Parameter with optional value.(The value is OPTIONAL and when not
        # specified indicates that the letter "e" is used as the channel mode
        # for ban exceptions; see `tools.isupport.DEFAULT_VALUES`).
        'EXCEPTS',
        # Parameter with optional value (Provide "n" instead of default "I").
        'INVEX=n',
        # Parameter with required value. Value is cast to specific type (int).
        'AWAYLEN=200',
        # Parameter with no limit
        'MAXTARGETS=',
        # Parameters with list of values, containing limits (required/optional).
        'MAXLIST=b:60,e:60,I:60',
        'TARGMAX=PRIVMSG:3,WHOIS:1,JOIN:',
        # Special parameters.
        'CHANMODES=beI,k,l,BCMNORScimnpstz',
        'EXTBAN=~,cqnr',
        'PREFIX=(ov)@+'
    ]

    # Ensure `005 RPL_BOUNCE` is not parsed as `RPL_ISUPPORT`
    pretrigger = PreTrigger('Foo', ':test.example.com 005 Sopel go_here.example.com 1234 :Try this other server... or not.')
    trigger = Trigger(sopel.config, pretrigger, None)
    coretasks.parse_reply_isupport(MockSopelWrapper(sopel, trigger), trigger)

    assert len(sopel.server_isupport) == 0

    # Test normal parsing of various tokens
    pretrigger = PreTrigger('Foo', ':test.example.com 005 Sopel {} :are supported by this server'.format(' '.join(tokens)))
    trigger = Trigger(sopel.config, pretrigger, None)
    coretasks.parse_reply_isupport(MockSopelWrapper(sopel, trigger), trigger)

    # raise `KeyError` for unadvertised parameter
    with pytest.raises(KeyError):
        sopel.server_isupport['FAKE_PARAMETER']

    assert sopel.server_isupport['SAFELIST'] is True
    assert sopel.server_isupport['SILENCE'] is None
    assert sopel.server_isupport['EXCEPTS'] == 'e'
    assert sopel.server_isupport['INVEX'] == 'n'
    assert sopel.server_isupport['AWAYLEN'] == 200
    assert sopel.server_isupport['MAXTARGETS'] is None
    assert sopel.server_isupport['MAXLIST'] == {'b': 60, 'e': 60, 'I': 60}
    assert sopel.server_isupport['TARGMAX']['JOIN'] is None
    assert sopel.server_isupport['CHANMODES'] == {
        'A': 'beI', 'B': 'k', 'C': 'l', 'D': 'BCMNORScimnpstz'
    }
    assert sopel.server_isupport['EXTBAN'] == {'prefix': '~', 'types': 'cqnr'}
    assert sopel.server_isupport['PREFIX'] == {'modes': 'ov', 'prefixes': '@+'}

    # Negate a feature (TARGMAX)
    pretrigger = PreTrigger('Foo', ':test.example.com 005 Sopel -TARGMAX :are supported by this server')
    trigger = Trigger(sopel.config, pretrigger, None)
    coretasks.parse_reply_isupport(MockSopelWrapper(sopel, trigger), trigger)

    # raise `Exception` when negating an unadvertised parameter
    pretrigger = PreTrigger('Foo', ':test.example.com 005 Sopel -UNADVERTISED :are supported by this server')
    trigger = Trigger(sopel.config, pretrigger, None)
    with pytest.raises(Exception, match='Server is trying to negate unadvertised parameter: .*'):
        coretasks.parse_reply_isupport(MockSopelWrapper(sopel, trigger), trigger)

    with pytest.raises(KeyError):
        sopel.server_isupport['TARGMAX']
