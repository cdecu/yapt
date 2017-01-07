import datetime
import sys
import typing


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


