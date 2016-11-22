#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Photo Tools
"""

import argparse
import shutil
import time
import threading
import os
import re
import sys
import pathlib
import datetime
import typing
import humanize
import piexif
from PIL import Image

__author__ = 'cdc'
__email__ = 'cdc@decumont.be'
__version__ = '0.0.1'

YAPT_Action_list = 'list'
YAPT_Action_rename = 'rename'
YAPT_Action_optimize = 'optimize'
YAPT_Action_thumbnails = 'thumbnails'

YAPT_Actions = (
    YAPT_Action_list,
    YAPT_Action_rename,
    YAPT_Action_optimize,
    YAPT_Action_thumbnails,
)

PIL_FORMATS = [
    'bmp', 'eps', 'gif', 'j2c', 'j2k', 'jp2', 'jpc', 'jpe', 'jpeg', 'jpf', 'jpg', 'jpx', 'mpo', 'pbm',
    'pcx', 'pgm', 'png', 'ppm', 'tga',
]

BORDER_Chars = '┌┐┘└─│┴├┬┤╷┼'

ILLEGAL_NTFS_CHARS = "[<>:/\\|?*\"]|[\0-\31]"


# ......................................................................................................................
class YaptError:
    """
    Class to store error
    """

    def __init__(self, file, error):
        """
        Yqpt Error Class
        """
        self.file = file
        self.type = error.__class__.__name__ if isinstance(error, Exception) else 'YaptError'
        self.message = str(error)

    def __str__(self):
        return '%s [%s: %s]' % (self.file, self.type, self.message)


def decode(path: str) -> str:
    """
    utility fct to encode/decode
    """
    return path.encode(sys.stdout.encoding, 'ignore').decode(sys.stdout.encoding)


def decodeExifDateTime(value: str) -> typing.Optional[datetime.datetime]:
    """
    utility fct to encode/decode
    """
    try:
        # return path.encode(sys.stdout.encoding, 'ignore').decode(sys.stdout.encoding)
        d = datetime.datetime.strptime(value, '%Y:%m:%d %H:%M:%S')
        return d
    except ValueError:
        return


# ......................................................................................................................
class YaptClass(object):
    """
    Class to Execute wanted actions. Yes a class just to learn python class
    """

    def __init__(self, source: str = '',
                 target: str = '',
                 onlytest: bool = True,
                 recursive: bool = True,
                 flat: int = 0,
                 threads: int = 5
                 ):
        self.source = os.path.realpath(source)
        self.target = os.path.realpath(target)
        self.onlytest = onlytest
        self.recursive = recursive
        self.flat = flat
        self.threads = threads if threads else 0

        # Prepare regex
        self.validNTFSCharsRegEx = re.compile(ILLEGAL_NTFS_CHARS)
        self.yyymmddhhmmRegEx = re.compile('(\d{4})\D*(\d{2})\D*(\d{2})\D*(\d{2})\D*(\d{2})[-_ ]*(.*)')
        self.yyymmddRegEx = re.compile('(\d{4})\D*(\d{2})\D*(\d{2})[-_ ]*(.*)')

        # default thumbnailSize (width, height)
        self.thumbnailSize = (800, 600,)

        # reset Counters
        self.files = []
        self.filesCount = 0
        self.filesSize = 0
        self.success = []
        self.errors = []
        self.fileToRename = 0
        self.fileRenamed = 0
        self.fileDeleted = 0
        self.newfilesCount = 0
        self.newfilesSize = 0

    # ..................................................................................................................
    def loadSource(self, source: str) -> bool:
        self.printTitle('loading %s ...' % source)
        self.source = os.path.realpath(source)
        elapsed_time = time.time()
        self.resetCounters()
        if source:
            if os.path.exists(source):
                if os.path.isfile(source):
                    self.files.append(source)
                elif os.path.isdir(source):
                    if self.recursive:
                        for r, d, f in os.walk(source):
                            for file in f:
                                name, ext = os.path.splitext(file)
                                if ext and ext.lower()[1:] in PIL_FORMATS:
                                    ff = os.path.join(r, file)
                                    self.filesSize += os.path.getsize(ff)
                                    self.files.append(ff)
                                    self.filesCount += 1
                    else:
                        for file in os.listdir(source):
                            name, ext = os.path.splitext(file)
                            if ext and ext.lower()[1:] in PIL_FORMATS:
                                ff = os.path.join(source, file)
                                self.filesSize += os.path.getsize(ff)
                                self.files.append(ff)
                                self.filesCount += 1
            else:
                print('Error: Path %s not exists!' % source, file=sys.stderr)
                exit(-1)

        if not self.files:
            print('Error: No images found', file=sys.stderr)
            exit(-1)

        print('%d files %s' % (self.filesCount, humanize.naturalsize(self.filesSize)))
        elapsed_time = time.time() - elapsed_time
        print('in %.3f sec\n' % elapsed_time)
        return True

    # ..................................................................................................................
    def processFiles(self, action: str) -> None:
        self.printActionStart(action)
        elapsed_time = time.time()
        before_action = {
            YAPT_Action_list: self.noCheck,
            YAPT_Action_rename: self.noCheck,
            YAPT_Action_optimize: self.checkTarget,
            YAPT_Action_thumbnails: self.checkTarget,
        }
        actions = {
            YAPT_Action_list: self.listFile,
            YAPT_Action_rename: self.rename,
            YAPT_Action_optimize: self.listFile,
            YAPT_Action_thumbnails: self.createThumbnail,
        }
        self.newfilesCount = self.filesCount
        self.newfilesSize = self.filesSize
        before_action[action](action)
        fct = actions[action]
        if self.threads:
            threads = []
            for i in range(self.threads):
                threads.append(threading.Thread(target=self.thread_processFiles, args=(fct,)))
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        else:
            self.thread_processFiles(fct)
        elapsed_time = time.time() - elapsed_time
        print('in %.3f sec\n' % elapsed_time)
        self.printActionEnd(action)
        pass

    def thread_processFiles(self, fct):
        while True:
            try:
                f = self.files.pop(0)
                fct(f)
            except IndexError:
                # Ok as expected . No items left
                break
        pass

    # ..................................................................................................................
    def resetCounters(self):
        self.files = []
        self.filesCount = 0
        self.filesSize = 0
        self.success = []
        self.errors = []
        self.fileToRename = 0
        self.fileRenamed = 0
        self.fileDeleted = 0
        self.newfilesCount = 0
        self.newfilesSize = 0

    @staticmethod
    def printTitle(title: str) -> None:
        print(title)
        print('-' * 1 * (len(title)))

    def printActionStart(self, action: str) -> None:
        title = 'Start ' + action
        if self.onlytest:
            title += ' OnlyTest'
        title += ' %d File(s)' % self.filesCount
        print(title)
        print('-' * 1 * (len(title)))

    def printActionEnd(self, action: str):
        if self.errors:
            print('%s Errors:' % action)
            for e in self.errors:
                print('\t' + decode(str(e)))
            print('\n')

        if self.success:
            print('%s Success:' % action)
            for s in self.success:
                print('\t' + decode(s))
            print('\n')

        print('Result\n------')
        print('..File(s)  : %d Size %s' % (self.newfilesCount, humanize.naturalsize(self.newfilesSize)))
        if self.fileToRename:
            print('..ToRename : %d' % self.fileToRename)
        if self.fileRenamed:
            print('..Renamed  : %d' % self.fileRenamed)
        if self.fileDeleted:
            print('..Deleted  : %d' % self.fileDeleted)
        print()

    # ..................................................................................................................
    def noCheck(self, action: str) -> None:
        pass

    def checkTarget(self, action: str) -> None:
        if not self.target:
            raise ValueError('Please select a valid target')

        if os.path.exists(self.target):
            if not os.path.isdir(self.target):
                raise ValueError('Please select a valid target dir for ' + action)
        else:
            os.mkdir(self.target)

        errs = os.path.join(self.target, 'errors')
        if not os.path.exists(errs):
            os.mkdir(errs)

        pass

    # ..................................................................................................................
    @staticmethod
    def getExifTimeStamp(file: str) -> typing.Optional[datetime.datetime]:
        try:
            exif_dict = piexif.load(file)
        except ValueError:
            return
        if piexif.ImageIFD.DateTime in exif_dict["0th"]:
            s = exif_dict["0th"].pop(piexif.ImageIFD.DateTime)
            return decodeExifDateTime(str(s, 'utf-8'))
        if piexif.ExifIFD.DateTimeOriginal in exif_dict["Exif"]:
            s = exif_dict["Exif"].pop(piexif.ExifIFD.DateTimeOriginal)
            return decodeExifDateTime(str(s, 'utf-8'))
        if piexif.ExifIFD.DateTimeDigitized in exif_dict["Exif"]:
            s = exif_dict["Exif"].pop(piexif.ExifIFD.DateTimeDigitized)
            return decodeExifDateTime(str(s, 'utf-8'))
        # for ifd in ("0th", "Exif", "GPS", "1st"):
        #     for tag in exif_dict[ifd]:
        #         print(ifd, piexif.TAGS[ifd][tag]["name"], exif_dict[ifd][tag])
        # print('****', file)
        # print('****', exif_dict)
        return

    def getCorrectFileName(self, file: str) -> typing.Optional[str]:
        # 20160712_1600_IMG_1692.jpg
        # 20100101_1930_2010_01_01_19h30_IMG_2647
        d = os.path.dirname(file)
        f = os.path.basename(file)
        x = f.replace('hpnx', 'HPNX')
        x = x.replace('IMG', 'Img').replace('img', 'Img')
        x = self.validNTFSCharsRegEx.sub('_', x)
        res = self.yyymmddhhmmRegEx.search(x)
        if res:
            p = res.group(1) + res.group(2) + res.group(3) + '_' + res.group(4) + res.group(5)
            s = res.group(6)
            s = re.sub(p, '', s)
            res = self.yyymmddhhmmRegEx.search(s)
            if res:
                s = res.group(6)
            x = p + '_' + s
            return os.path.join(d, x)
        res = self.yyymmddRegEx.search(x)
        if res:
            p = res.group(1) + res.group(2) + res.group(3)
            s = res.group(6)
            x = p + '_' + s
            return os.path.join(d, x)
        t = self.getExifTimeStamp(file)
        if t:
            x = t.strftime('%Y%m%d_%H%M') + '_' + x
            return os.path.join(d, x)
        return

    # ..................................................................................................................
    def getTargetFileName(self, file: str) -> str:
        f = os.path.basename(file)
        if self.flat == 0:
            n = os.path.join(self.target, f)
            return n
        p = os.path.dirname(file)
        p = p.replace(self.source, '')
        parts = pathlib.PurePath(p).parts
        lvls = self.flat + 1 if self.flat + 1 < len(parts) else len(parts)
        n = self.target
        for i in range(1, lvls):
            n = os.path.join(n, parts[i])
        if not os.path.exists(n):
            os.mkdir(n)
        n = os.path.join(n, f)
        return n

    def getTargetErrorFileName(self, file: str) -> str:
        f = os.path.basename(file)
        n = os.path.join(self.target, 'errors', f)
        return n

    # ...................................................................................................................
    def listFile(self, file: str):
        self.success.append(file)
        pass

    # ...................................................................................................................
    def rename(self, file: str):
        n = self.getCorrectFileName(file)
        if not n:
            self.errors.append(YaptError(file, 'Invalid FileName'))
            return

        if n == file:
            return

        self.fileToRename += 1
        # self.onlytest = True

        # Delete Existing !
        if os.path.exists(n):
            if not self.onlytest:
                try:
                    os.remove(file)
                    self.success.append('%s >> Deleted' % file)
                except IOError as Err:
                    self.errors.append(YaptError(file, 'Delete I/O error({0}): {1}'.format(Err.errno, Err.strerror)))
            else:
                self.success.append('%s >> replace existing %s' % (file, n))

        # Rename to yyyymm...
        if not self.onlytest:
            try:
                os.rename(file, n)
                self.success.append('%s >> Renamed' % file)
                self.fileToRename -= 1
                self.fileRenamed += 1
            except IOError as Err:
                self.errors.append(YaptError(file, 'Rename I/O error({0}): {1}'.format(Err.errno, Err.strerror)))
        else:
            self.success.append('%s >> to be renamed to %s' % (file, os.path.basename(n)))

    # ..................................................................................................................
    def createThumbnail(self, file: str) -> None:
        n = self.getTargetFileName(file)
        try:
            with Image.open(file) as img:
                if (img.width > self.thumbnailSize[0]) or (img.height > self.thumbnailSize[1]):
                    # Resize
                    img_format = img.format
                    newimg = img.copy()
                    newimg.thumbnail(self.thumbnailSize, Image.LANCZOS)
                    newimg.format = img_format
                    newimg.save(n, optimize=True)
                else:
                    # keep as is
                    img.save(n, optimize=True)
            self.newfilesSize -= os.path.getsize(file)
            self.newfilesSize += os.path.getsize(n)
        except Exception as ex:
            self.errors.append(YaptError(file, ex))
            n = self.getTargetErrorFileName(file)
            shutil.copy(file, n)
            self.newfilesCount -= 1


# ......................................................................................................................
def main():
    parser = argparse.ArgumentParser(
        prog="yapt.py",
        description=__doc__,
        epilog="\nbe carefull and good lock !\n",
        formatter_class=lambda prog: argparse.HelpFormatter(prog, max_help_position=80)
    )
    parser.add_argument('-y', '--onlytest', dest='onlytest', help='dry run', action='store_true')
    parser.add_argument('-r', '--recursive', dest='recursive', action='store_true', default=True,
                        help='recursive scan subfolders')
    parser.add_argument('-f', '--flat', dest='flat', type=int, default=1,
                        help='flat target tree level')
    parser.add_argument('-x', '--threads', dest='threads', type=int, default=5, help='set threads count')
    parser.add_argument('-s', '--source', type=str, default='/home/cdc/Photos/', help='Root Dir to process')
    parser.add_argument('-t', '--target', type=str, default='/home/cdc/yapt', help='Destination Folder')
    parser.add_argument('-a', '--action', dest='action', choices=YAPT_Actions, default=YAPT_Action_rename,
                        help='action to perform')
    args = parser.parse_args()

    yatp = YaptClass(source=args.source,
                     target=args.target,
                     onlytest=args.onlytest,
                     recursive=args.recursive,
                     flat=args.flat,
                     threads=args.threads
                     )
    if not yatp.loadSource(args.source):
        print('ByeBye')
        exit(-1)

    yatp.processFiles(args.action)


if __name__ == "__main__":
    main()
