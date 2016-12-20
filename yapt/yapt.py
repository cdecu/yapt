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
YAPT_Action_touch = 'touch'
YAPT_Action_optimize = 'optimize'
YAPT_Action_thumbnails = 'thumbnails'

YAPT_Default_Action = YAPT_Action_thumbnails

YAPT_Actions = (
    YAPT_Action_list,
    YAPT_Action_rename,
    YAPT_Action_touch,
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
        self.filesResized = 0
        self.filesOptimized = 0
        self.filesToRename = 0
        self.filesRenamed = 0
        self.filesDeleted = 0
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
        self.newfilesCount = self.filesCount
        self.newfilesSize = self.filesSize
        return True

    # ..................................................................................................................
    def resetCounters(self):
        self.files = []
        self.filesCount = 0
        self.filesSize = 0
        self.success = []
        self.errors = []
        self.filesResized = 0
        self.filesOptimized = 0
        self.filesToRename = 0
        self.filesRenamed = 0
        self.filesDeleted = 0
        self.newfilesCount = 0
        self.newfilesSize = 0

    @staticmethod
    def printTitle(title: str) -> None:
        print(title)
        print('-' * 1 * (len(title)))

    def printActionStart(self, action: str) -> None:
        title = 'Start [%s]' % action
        title += ' %d File(s)' % self.filesCount
        title += ' * %d thread(s)' % self.threads
        if self.onlytest:
            title += ' * OnlyTest *'
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
        if self.filesToRename:
            print('..ToRename : %d' % self.filesToRename)
        if self.filesRenamed:
            print('..Renamed  : %d' % self.filesRenamed)
        if self.filesDeleted:
            print('..Deleted  : %d' % self.filesDeleted)
        if self.filesResized:
            print('..Resized  : %d' % self.filesResized)
        if self.filesOptimized:
            print('..Optimized: %d' % self.filesOptimized)
        print()

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
    @staticmethod
    def getExifOrientation(img) -> typing.Optional[int]:
        if "exif" in img.info:
            exif_dict = piexif.load(img.info["exif"])
            if piexif.ImageIFD.Orientation in exif_dict["0th"]:
                return exif_dict["0th"].pop(piexif.ImageIFD.Orientation)

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

    def getFileDateTime(self, file: str) -> typing.Optional[datetime.datetime]:
        t = self.getExifTimeStamp(file)
        if t:
            return t
        f = os.path.basename(file)
        res = self.yyymmddhhmmRegEx.search(f)
        if res:
            try:
                t = datetime.datetime(year=int(res.group(1)), month=int(res.group(2)), day=int(res.group(3)),
                                      hour=int(res.group(4)), minute=int(res.group(5)))
                return t
            except ValueError:
                pass
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

    def getOnlyTestTarget(self, file: str) -> str:
        f = os.path.basename(file)
        n = os.path.join(self.target,'test', f)
        return n

    def checkOnlyTestTarget(self) -> None:
        if not self.target:
            raise ValueError('Please select a valid target')

        if os.path.exists(self.target):
            if not os.path.isdir(self.target):
                raise ValueError('Please select a valid target dir')
        else:
            os.makedirs(self.target, exist_ok=True)

        errs = os.path.join(self.target, 'test')
        if not os.path.exists(errs):
            os.makedirs(errs, exist_ok=True)

    # ...................................................................................................................
    def listFile(self, file: str):
        self.success.append(file)
        pass

    def listFiles(self) -> None:
        self.printActionStart(YAPT_Action_list)
        self.thread_processFiles(self.listFile)
        self.printActionEnd(YAPT_Action_list)
        pass

    # ...................................................................................................................
    def renameFile(self, file: str):
        n = self.getCorrectFileName(file)
        if not n:
            self.errors.append(YaptError(file, 'Invalid FileName'))
            return

        if n == file:
            return

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
                self.filesRenamed += 1
            except IOError as Err:
                self.errors.append(YaptError(file, 'Rename I/O error({0}): {1}'.format(Err.errno, Err.strerror)))
                self.filesToRename += 1
        else:
            self.success.append('%s >> to be renamed to %s' % (file, os.path.basename(n)))
            self.filesToRename += 1
        pass

    def renameFiles(self) -> None:
        self.printActionStart(YAPT_Action_rename)
        if self.threads:
            threads = []
            for i in range(self.threads):
                threads.append(threading.Thread(target=self.thread_processFiles, args=(self.renameFile,)))
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        else:
            self.thread_processFiles(self.renameFile)
        self.printActionEnd(YAPT_Action_rename)
        pass

    # ...................................................................................................................
    def touchFile(self, file: str):
        t = self.getFileDateTime(file)
        if not t:
            self.errors.append(YaptError(file, 'Can find TimeStamp'))
            self.filesToRename += 1
            return
        res = os.stat(file)
        tt = time.mktime(t.timetuple())
        if res.st_mtime == tt:
            # ok time set
            return
        if self.onlytest:
            self.success.append('%s >> %s' % (file, time.strftime("%Y%m%d %H:%M", time.localtime(tt))))
            self.filesToRename += 1
            return
        try:
            os.utime(file, (tt, tt))
            self.filesRenamed += 1
        except IOError as Err:
            self.errors.append(YaptError(file, 'Touch I/O error({0}): {1}'.format(Err.errno, Err.strerror)))
            self.filesToRename += 1
        pass

    def touchFiles(self) -> None:
        self.printActionStart(YAPT_Action_touch)
        if self.threads:
            threads = []
            for i in range(self.threads):
                threads.append(threading.Thread(target=self.thread_processFiles, args=(self.touchFile,)))
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        else:
            self.thread_processFiles(self.touchFile)
        self.printActionEnd(YAPT_Action_touch)
        pass

    # ...................................................................................................................
    def optimizeFile(self, file: str):
        try:
            # target
            n = self.getCorrectFileName(file)
            if self.onlytest:
                n = self.getOnlyTestTarget(n)
            # Optimize File
            with Image.open(file) as img:
                img.save(n, optimize=True)
            # Touch File
            t = self.getFileDateTime(n)
            if t:
                tt = time.mktime(t.timetuple())
                os.utime(n, (tt, tt))
            # delete original
            if (not self.onlytest)and(n != file):
                os.remove(file)
        except Exception as ex:
            self.errors.append(YaptError(file, ex))
        pass

    def optimizeFiles(self) -> None:
        self.printActionStart(YAPT_Action_optimize)
        self.checkOnlyTestTarget()
        if self.threads:
            threads = []
            for i in range(self.threads):
                threads.append(threading.Thread(target=self.thread_processFiles, args=(self.optimizeFile,)))
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        else:
            self.thread_processFiles(self.optimizeFile)
        self.printActionEnd(YAPT_Action_optimize)
        pass

    # ..................................................................................................................
    def getThumbnailTarget(self, file: str) -> str:
        f = os.path.basename(file)
        if self.flat == 0:
            n = os.path.join(self.target, f)
            return n
        p = os.path.dirname(file)
        p = os.path.realpath(p)
        p = p.replace(self.source, '')
        parts = pathlib.PurePath(p).parts
        lvls = self.flat + 1 if self.flat + 1 < len(parts) else len(parts)
        n = self.target
        for i in range(1, lvls):
            n = os.path.join(n, parts[i])
        n = os.path.join(n, f)
        return n

    def getThumbnailErrorTarget(self, file: str) -> str:
        f = os.path.basename(file)
        n = os.path.join(self.target, 'errors', f)
        return n

    def checkThumbnailsTarget(self) -> None:
        if not self.target:
            raise ValueError('Please select a valid target')

        if os.path.exists(self.target):
            if not os.path.isdir(self.target):
                raise ValueError('Please select a valid thumbnails target dir')
        else:
            os.makedirs(self.target, exist_ok=True)

        errs = os.path.join(self.target, 'errors')
        if not os.path.exists(errs):
            os.makedirs(errs, exist_ok=True)

        for f in self.files:
            t = self.getThumbnailTarget(f)
            n = os.path.dirname(t)
            if not os.path.exists(n):
                os.makedirs(n, exist_ok=True)
        pass

    def createThumbnail(self, file: str) -> None:
        n = self.getThumbnailTarget(file)
        try:
            # Create thumbnail
            with Image.open(file) as img:
                if (img.width > self.thumbnailSize[0]) or (img.height > self.thumbnailSize[1]):
                    # Resize exif will be lost !
                    # exif_bytes = piexif.dump(exif_dict) and newimg.save(filename, exif=exif_bytes)
                    o = self.getExifOrientation(img)
                    img_format = img.format
                    newimg = img.copy()
                    newimg.thumbnail(self.thumbnailSize, Image.LANCZOS)
                    if o == 3:
                        newimg = newimg.transpose(Image.ROTATE_180)
                    elif o == 4:
                        newimg = newimg.transpose(Image.ROTATE_180)
                    elif o == 5:
                        newimg = newimg.transpose(Image.ROTATE_270)
                    elif o == 6:
                        newimg = newimg.transpose(Image.ROTATE_270)
                    elif o == 7:
                        newimg = newimg.transpose(Image.ROTATE_90)
                    elif o == 8:
                        newimg = newimg.transpose(Image.ROTATE_90)
                    newimg.format = img_format
                    newimg.save(n, optimize=True)
                    self.filesResized += 1
                else:
                    # keep as is
                    self.filesOptimized += 1
                    img.save(n, optimize=True)
            # Touch File
            t = self.getFileDateTime(file)
            if t:
                tt = time.mktime(t.timetuple())
                os.utime(n, (tt, tt))
            # Inc counters
            self.newfilesSize -= os.path.getsize(file)
            self.newfilesSize += os.path.getsize(n)
        except Exception as ex:
            self.errors.append(YaptError(file, ex))
            n = self.getThumbnailErrorTarget(file)
            shutil.copy(file, n)
            self.newfilesCount -= 1
        pass

    def createThumbnails(self) -> None:
        self.printActionStart(YAPT_Action_thumbnails)
        self.checkThumbnailsTarget()
        if self.threads:
            threads = []
            for i in range(self.threads):
                threads.append(threading.Thread(target=self.thread_processFiles, args=(self.createThumbnail,)))
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        else:
            self.thread_processFiles(self.createThumbnail)
        self.printActionEnd(YAPT_Action_thumbnails)
        pass

    # ..................................................................................................................
    def executeAction(self, action: str) -> None:
        actionsFct = {
            YAPT_Action_list: self.listFiles,
            YAPT_Action_rename: self.renameFiles,
            YAPT_Action_touch: self.touchFiles,
            YAPT_Action_optimize: self.optimizeFiles,
            YAPT_Action_thumbnails: self.createThumbnails,
            }
        elapsed_time = time.time()
        actionsFct[action]()
        elapsed_time = time.time() - elapsed_time
        print('in %.3f sec\n' % elapsed_time)
        pass

# ......................................................................................................................
def main():
    parser = argparse.ArgumentParser(
        prog="yapt.py",
        description=__doc__,
        epilog="\nbe carefull and good lock !\n",
        formatter_class=lambda prog: argparse.HelpFormatter(prog, max_help_position=35)
    )
    parser.add_argument('-y', '--run', dest='onlytest', help='real run(onlytest by default)', action='store_false')
    parser.add_argument('-r', '--recursive', dest='recursive', action='store_true', default=True,
                        help='recursive scan subfolders')
    parser.add_argument('-f', '--flat', dest='flat', type=int, default=1,
                        help='flat target tree level')
    parser.add_argument('-x', '--threads', dest='threads', type=int, default=5, help='set threads count')
    parser.add_argument('-s', '--source', type=str, default='/home/cdc/Images/', help='Root Dir to process')
    parser.add_argument('-t', '--target', type=str, default='/home/cdc/yapt', help='Destination Folder')
    parser.add_argument('-a', '--action', dest='action', choices=YAPT_Actions, default=YAPT_Default_Action,
                        help='Action to perform')
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

    yatp.executeAction(args.action)


if __name__ == "__main__":
    main()
