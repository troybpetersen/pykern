# -*- coding: utf-8 -*-
u"""PyTest for :mod:`pykern.pkunit`

:copyright: Copyright (c) 2015 Bivio Software, Inc.  All Rights Reserved.
:license: http://www.apache.org/licenses/LICENSE-2.0.html
"""
from __future__ import absolute_import, division, print_function, unicode_literals
from io import open

import os

import py
import pytest

from pykern.pkdebug import *
from pykern import pkunit

PY_PATH_LOCAL_TYPE = type(py.path.local())


def test_data_dir():
    expect = _expect('pkunit_data')
    d = pkunit.data_dir()
    assert isinstance(d, PY_PATH_LOCAL_TYPE), \
        'Verify type of data_dir is same as returned by py.path.local'
    assert d == expect, \
        'Verify data_dir has correct return value'


def test_data_dir():
    expect = _expect('pkunit_data')
    d = pkunit.data_dir()
    assert isinstance(d, PY_PATH_LOCAL_TYPE), \
        'Verify type of data_dir is same as returned by py.path.local'
    assert d == expect, \
        'Verify data_dir has correct return value'


def test_import_module_from_data_dir(monkeypatch):
    real_data_dir = pkunit.data_dir()
    fake_data_dir = None
    def mock_data_dir():
        return fake_data_dir
    monkeypatch.setattr(pkunit, 'data_dir', mock_data_dir)
    fake_data_dir = str(real_data_dir.join('import1'))
    assert 'imp1' == pkunit.import_module_from_data_dir('p1').v, \
        'import1/p1 should be from "imp1"'
    fake_data_dir = str(real_data_dir.join('import2'))
    assert 'imp2' == pkunit.import_module_from_data_dir('p1').v, \
        'import2/p1 should be from "imp2"'


def test_empty_work_dir():
    expect = _expect('pkunit_work')
    if os.path.exists(str(expect)):
        expect.remove(rec=1)
    assert not os.path.exists(str(expect)), \
        'Ensure directory was removed'
    d = pkunit.empty_work_dir()
    assert isinstance(d, PY_PATH_LOCAL_TYPE), \
        'Verify type of empty_work_dir is same as returned by py.path.local'
    assert expect == d, \
        'Verify empty_work_dir has correct return value'
    assert os.path.exists(str(d)), \
        'Ensure directory was created'


def _expect(base):
    d = py.path.local(__file__).dirname
    return py.path.local(d).join(base).realpath()
