import datetime
import sys
import typing

from PIL import Image, ExifTags
import piexif
import piexif.helper

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


def exif_decode(o):
    if isinstance(o, bytes):
        return o.decode('ascii')
    return o


def exif_metadata2dict(metadata: list, m: dict):

    for d in metadata:
        for i in d:
            if i == 'XMP:CreatorTool':
                # print('Use 0th', i, d[i])
                m['0th'][ExifTags.TAGS[ExifTags.Base.Model]] = d[i].strip()
            elif i == 'XMP:Rating':
                # print('Use 0th', i, d[i])
                m['0th'][ExifTags.TAGS[ExifTags.Base.Rating]] = int(d[i])
            elif i == 'File:ImageWidth':
                # print('Use 0th', i, d[i])
                m['0th'][ExifTags.TAGS[ExifTags.Base.ImageWidth]] = int(d[i])
            elif i == 'File:ImageHeight':
                # print('Use 0th', i, d[i])
                m['0th'][ExifTags.TAGS[ExifTags.Base.ImageLength]] = int(d[i])

            elif i == 'XMP:CreateDate':
                # print('Use Exif', i, d[i])
                dd = datetime.datetime.strptime(d[i], '%Y:%m:%d %H:%M:%S.%f')
                oo = dd.utcoffset()
                m['Exif'][ExifTags.TAGS[ExifTags.Base.DateTimeOriginal]] = dd
                m['Exif'][ExifTags.TAGS[ExifTags.Base.DateTimeDigitized]] = dd
                if oo:
                    m['Exif'][ExifTags.TAGS[ExifTags.Base.OffsetTimeOriginal]] = oo
                    m['Exif'][ExifTags.TAGS[ExifTags.Base.OffsetTimeDigitized]] = oo
            else:
                # print('**Ignore', i, d[i])
                pass

    return


def exif_jsonbytes(m: dict) -> bytes:
    # print(m)
    exif_dict = {}
    for ifd in ("0th", "Exif", "GPS", "1st"):
        if ifd in m:
            data = {}
            for tk, tv in piexif.TAGS[ifd].items():
                if tv['name'] in m[ifd]:
                    td = m[ifd][tv['name']]
                    match tv['type']:
                        case 2:
                            if isinstance(td, bytes):
                                # print('Add bytes', tk, tv, td)
                                data[tk] = td
                            elif isinstance(td, datetime.datetime):
                                # print('Add date', tk, tv, td)
                                dd = td.strftime('%Y:%m:%d %H:%M:%S')
                                data[tk] = dd.encode('ascii')
                            else:
                                # print('Add ', type(td), tk, tv, td)
                                data[tk] = td.encode('ascii')
                        case 7:
                            match tk:
                                case ExifTags.Base.UserComment:
                                    # print('Add ', type(td), tk, tv, td)
                                    data[tk] = piexif.helper.UserComment.dump(td)
                                case _:
                                    # print('Add', tk, tv, td)
                                    data[tk] = td
                        case _:
                            # print('Add', tk, tv, td)
                            data[tk] = td
            exif_dict[ifd] = data

    exif_bytes = piexif.dump(exif_dict)
    # print(exif_dict)
    return exif_bytes

