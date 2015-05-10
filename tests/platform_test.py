# -*- coding: utf-8 -*-
u"""pytest for `pykern.platform`

:copyright: Copyright (c) 2015 Bivio Software, Inc.  All Rights Reserved.
:license: http://www.apache.org/licenses/LICENSE-2.0.html
"""
from __future__ import absolute_import, division, print_function, unicode_literals
from io import open

import platform
import pytest
import re
import sys

import pykern.platform as pbp


def test_conformance1():
    """Verify the platforms based on other calls"""
    if platform.system() == 'Linux':
        assert pbp.is_linux()
        assert pbp.is_unix()
        assert not pbp.is_darwin()
        assert not pbp.is_windows()
    elif platform.system().startswith('CYGWIN'):
        assert not pbp.is_linux()
        assert pbp.is_unix()
        assert not pbp.is_darwin()
        assert pbp.is_windows()
    elif platform.system() == 'Windows':
        assert not pbp.is_linux()
        assert not pbp.is_unix()
        assert not pbp.is_darwin()
        assert pbp.is_windows()
    elif platform.system() == 'Darwin':
        assert not pbp.is_linux()
        assert pbp.is_unix()
        assert pbp.is_darwin()
        assert not pbp.is_windows()
    else:
        assert not pbp.is_windows()
        assert not pbp.is_darwin()
        assert not pbp.is_linux()
        # Not sure if it would be unix
