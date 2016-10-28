#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Photo Tools
"""

import argparse
import os
import humanize

__author__ = 'cdc'
__email__ = 'cdc@xpertbilling.com'
__version__ = '0.1.9'

__yapt_action_scan__ = 'scan'
__yapt_action_ren2date__ = 'ren2date'
__yapt_action_flatcp__ = 'flatcp'
__yapt_action_optimize__ = 'optimize'
__yapt_action_rename__ = 'rename'

__yapt_actions__ = (
    __yapt_action_scan__,
    __yapt_action_ren2date__,
    __yapt_action_flatcp__,
    __yapt_action_optimize__,
    __yapt_action_rename__
)

chars = {
    'a': '┌',
    'b': '┐',
    'c': '┘',
    'd': '└',
    'e': '─',
    'f': '│',
    'g': '┴',
    'h': '├',
    'i': '┬',
    'j': '┤',
    'k': '╷',
    'l': '┼',
}

"""
    Class to Execute wanted actions. Yes a class just to learn python class
"""


class YaptClass(object):
    def __init__(self,
                 params: object
                 ) -> None:
        self.imgsCount = 0
        self.imgsSize = 0
        self.source = params.source
        self.target = params.target
        self.onlytest = params.onlytest
        self.actions = params.actions

        self.functions = {
            __yapt_action_scan__: self.scan,
            __yapt_action_ren2date__: self.ren2date,
            __yapt_action_flatcp__: self.flatcp,
            __yapt_action_optimize__: self.optimize
        }

    def executes(self) -> None:
        for a in self.actions:
            self.scanSource(a, self.functions[a])

    def resetCounters(self):
        self.imgsCount = 0
        self.imgsSize = 0

    def scanSource(self, action, funct):
        print(action)
        print('-' * 1 * (len(action)))
        print('Source:', self.source)
        print('OnlyTest:', self.onlytest)
        self.resetCounters()
        for root, dirs, files in os.walk(self.source):
            level = root.replace(self.source, '').count(os.sep)
            indent = '>>' * 1 * (level + 1)
            subindent = '..' * 1 * (level + 2)
            print('{}{}/'.format(indent, os.path.basename(root)))
            for f in files:
                ff = f.lower()
                if ff.endswith('.jpg') or ff.endswith('.jpeg'):
                    ff = os.path.join(root, f)
                    self.imgsSize += os.path.getsize(ff)
                    if not funct:
                        print('{}{}'.format(subindent, ff))
                    else:
                        funct(ff)
                    self.imgsCount += 1
        print(self.imgsCount, humanize.naturalsize(self.imgsSize))

    def scan(self, file: str):
        f = os.path.basename(file)
        # ILLEGAL_NTFS_CHARS = "[<>:/\\|?*\"]|[\0-\31]"
        # def __removeIllegalChars(name):
        #     # removes characters that are invalid for NTFS
        #     return re.sub(ILLEGAL_NTFS_CHARS, "", name)
        # 2016-07-09 19h29   >>>  20160708_1730
        if '-' in f:
            print(f)
        pass

    def ren2date(self, file: str):
        print(file)

    def flatcp(self, file: str):
        print(file)

    def optimize(self, file: str):
        print(file)


""" ********************************************************************************************************************
Start yapt
"""
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="yapt-script.py",
        description=__doc__,
        epilog="\nbe carefull and good lock !\n",
        formatter_class=lambda prog: argparse.HelpFormatter(prog, max_help_position=80)
    )
    parser.add_argument('-s', '--source', help='Root Dir to process', type=str, default='~/Photos/', required=True)
    parser.add_argument('-t', '--target', help='Destination Folder', type=str, default='~/Tempo/yapt', required=False)
    parser.add_argument('-y', '--onlytest', help='dry run', type=bool, default=False)
    # parser.add_argument(dest='actions', help='action to perform', choices=__yapt_actions__, action='append')
    parser.add_argument(dest='actions', choices=__yapt_actions__, nargs='*', help='action to perform')
    args = parser.parse_args()

    if not args.actions:
        parser.print_help()
        exit(-1)

    # use YaptClass(**args)
    # kwargs['source'] = args.source
    # kwargs['target'] = args.target
    # kwargs['onlytest'] = args.onlytest
    # kwargs['actions'] = args.actions
    # kwargs = {'source': '', 'target': '', 'onlytest': False, 'actions': []}

    yapt = YaptClass(args)
    yapt.executes()

    exit(0)
