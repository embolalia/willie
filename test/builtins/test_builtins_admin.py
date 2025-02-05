"""Tests for Sopel's ``admin`` plugin"""
from __future__ import annotations

import pytest

from sopel.tests import rawlist


BOT_NICK = 'TestBot'
TEST_CHAN = '#test'
TMP_CONFIG = f"""
[core]
owner = Uowner
nick = {BOT_NICK}

[admin]
auto_accept_invite = True
"""


@pytest.fixture
def tmpconfig(configfactory):
    return configfactory('conf.ini', TMP_CONFIG)


@pytest.fixture
def mockbot(tmpconfig, botfactory):
    return botfactory.preloaded(tmpconfig, ['admin'])


def test_invite_accept_admin(mockbot):
    """Verify that bot admins' invites are accepted."""
    mockbot.on_message(f":Uowner!owner@sopel.chat INVITE {BOT_NICK} {TEST_CHAN}")
    assert len(mockbot.backend.message_sent) == 1
    assert mockbot.backend.message_sent == rawlist('JOIN #test')


def test_invite_accept_non_admin_auto(mockbot):
    """Verify that non-admin invites are accepted if enabled."""
    mockbot.settings.admin.auto_accept_invite = True
    mockbot.on_message(f":Henry!king@monar.ch INVITE {BOT_NICK} {TEST_CHAN}")
    assert len(mockbot.backend.message_sent) == 1
    assert mockbot.backend.message_sent == rawlist('JOIN #test')


def test_invite_accept_non_admin_no_auto(mockbot):
    """Verify that non-admin invites are ignored if disabled."""
    mockbot.settings.admin.auto_accept_invite = False
    mockbot.on_message(f":Henry!king@monar.ch INVITE {BOT_NICK} {TEST_CHAN}")
    assert len(mockbot.backend.message_sent) == 0


def test_invite_accept_not_us(mockbot):
    """Verify that the plugin ignores invites not meant for it."""
    mockbot.on_message(":Henry!king@monar.ch INVITE Anne #boudoir")
    assert len(mockbot.backend.message_sent) == 0
