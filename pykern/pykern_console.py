# -*- coding: utf-8 -*-
u"""Front-end command line for :mod:`pykern.cli`.

Example:

:copyright: Copyright (c) 2015 Bivio Software, Inc.  All Rights Reserved.
:license: http://www.apache.org/licenses/LICENSE-2.0.html
"""
from __future__ import absolute_import, division, print_function, unicode_literals
from io import open

import sys

import pykern.cli


def main():
    return pykern.cli.main('pykern')


if __name__ == '__main__':
    sys.exit(main())
