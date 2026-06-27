#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google Takeout Cleaner
Traite un export Google Takeout :
  - applique les métadonnées des fichiers JSON sur les photos (timestamps, GPS)
  - renomme les fichiers selon la date prise (photoTakenTime)
  - supprime les fichiers JSON sidecar après traitement
  - nettoie les fichiers/dossiers inutiles produits par Takeout
"""

import argparse
import datetime
import json
import os
import re
import sys
import typing

import piexif

__author__ = 'cdc'
__email__ = 'cdc@decumont.be'
__version__ = '0.2.0'

PIL_FORMATS = {
    'bmp', 'eps', 'gif', 'j2c', 'j2k', 'jp2', 'jpc', 'jpe', 'jpeg',
    'jpf', 'jpg', 'jpx', 'mpo', 'pbm', 'pcx', 'pgm', 'png', 'ppm',
    'tga', 'tif', 'tiff', 'webp', 'heic', 'heif', 'mp4', 'mov', 'avi',
    'mkv', '3gp', 'm4v',
}

# Noms de fichiers JSON d'album générés par Google Takeout selon la langue
ALBUM_JSON_NAMES = {
    'métadonnées.json', 'metadonnees.json', 'metadata.json',
    'metadaten.json', 'metadatos.json', 'metadati.json', 'метаданные.json',
}

EDITED_SUFFIXES = re.compile(
    r'(-edited|-bewerkt|-modifié|-modifie|-modificato|-editado|'
    r'-redimensionné|-redimensionne|-redimensioniert|-ridimensionato|'
    r'-recortado|-cropped|-animado|-animé|-animiert|-animato)$',
    re.IGNORECASE
)

ALREADY_DATED_RE = re.compile(r'^\d{8}_\d{6}')
TMP_PREFIX_RE = re.compile(r'^(~tmp[^_]*)_(.+)$', re.IGNORECASE)
# Google Takeout suffixe le JSON avec .supplemental-xxx quand le nom est trop long
SUPPLEMENTAL_RE = re.compile(r'^(.+\.[a-zA-Z0-9]+)\.supplemental[-.].*$', re.IGNORECASE)


# ──────────────────────────────────────────────────────────────────────────────
def decode_safe(text: str) -> str:
    # TODO: sys.stdout.encoding peut être None si stdout est redirigé → crash
    return text.encode(sys.stdout.encoding, 'ignore').decode(sys.stdout.encoding)


def timestamp_to_datetime(ts: typing.Union[str, int, float]) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(int(ts))


def is_album_json(json_path: str, meta: dict) -> bool:
    fname = os.path.basename(json_path).lower()
    if fname in ALBUM_JSON_NAMES:
        return True
    # TODO: title peut être une liste → bool(title) est True mais title == dir_name est False
    title = meta.get('title', '')
    dir_name = os.path.basename(os.path.dirname(json_path))
    return bool(title) and title == dir_name


def find_media_for_json(json_path: str, title: str) -> typing.Optional[str]:
    """
    5 stratégies pour trouver le média correspondant à un JSON sidecar.
    """
    directory = os.path.dirname(json_path)

    # 1 — correspondance directe via title
    if title:
        candidate = os.path.join(directory, title)
        if os.path.isfile(candidate):
            return candidate

    # 1b — title avec caractères spéciaux sanitisés par Takeout (' → _)
    if title:
        sanitized = re.sub(r"['\"]", '_', title)
        if sanitized != title:
            candidate = os.path.join(directory, sanitized)
            if os.path.isfile(candidate):
                return candidate

    # 2 — déduction depuis le nom du JSON (photo.jpg.json → photo.jpg)
    json_name = os.path.basename(json_path)
    if json_name.lower().endswith('.json'):
        base = json_name[:-5]
        candidate = os.path.join(directory, base)
        if os.path.isfile(candidate):
            return candidate

    # 2b — JSON supplemental: nom.ext.supplemental-xxx.json → nom.ext
    #      Google Takeout utilise ce suffixe quand le nom de fichier est trop long
    if json_name.lower().endswith('.json'):
        m = SUPPLEMENTAL_RE.match(json_name[:-5])
        if m:
            candidate = os.path.join(directory, m.group(1))
            if os.path.isfile(candidate):
                return candidate

    # 3 — titre ~tmpXXX_NOM.ext → fichier déjà renommé NOM~tmpXXX.ext
    if title:
        stem, ext = os.path.splitext(title)
        m = TMP_PREFIX_RE.match(stem)
        if m:
            candidate = os.path.join(directory, f'{m.group(2)}{m.group(1)}{ext}')
            if os.path.isfile(candidate):
                return candidate

    # 4 — correspondance par préfixe tronqué
    if title:
        stem, ext = os.path.splitext(title)
        ext_lower = ext.lower()
        try:
            for fname in os.listdir(directory):
                if fname.lower().endswith(ext_lower):
                    fstem = os.path.splitext(fname)[0]
                    # TODO: fstem.startswith(stem) génère des faux positifs, ex: "photo" matche "photo2"
                    if stem.startswith(fstem) or fstem.startswith(stem):
                        fpath = os.path.join(directory, fname)
                        if os.path.isfile(fpath):
                            return fpath
        except OSError:
            pass

    # 5 — fichier édité
    if title:
        stem, ext = os.path.splitext(title)
        # TODO: seul '-edited' est testé ; les autres suffixes de EDITED_SUFFIXES sont ignorés
        candidate = os.path.join(directory, f'{stem}-edited{ext}')
        if os.path.isfile(candidate):
            return candidate

    return None


def load_takeout_json(json_path: str) -> dict:
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def apply_exif_timestamp(media_path: str, dt: datetime.datetime, onlytest: bool = False) -> bool:
    ext = os.path.splitext(media_path)[1].lower().lstrip('.')
    if ext not in ('jpg', 'jpeg', 'tif', 'tiff'):
        return False
    try:
        exif_dict = piexif.load(media_path)
        dt_str = dt.strftime('%Y:%m:%d %H:%M:%S').encode('ascii')
        already = (
            exif_dict['Exif'].get(piexif.ExifIFD.DateTimeOriginal) == dt_str
            and exif_dict['Exif'].get(piexif.ExifIFD.DateTimeDigitized) == dt_str
            and exif_dict['0th'].get(piexif.ImageIFD.DateTime) == dt_str
        )
        if already:
            return False
        exif_dict['Exif'][piexif.ExifIFD.DateTimeOriginal] = dt_str
        exif_dict['Exif'][piexif.ExifIFD.DateTimeDigitized] = dt_str
        exif_dict['0th'][piexif.ImageIFD.DateTime] = dt_str
        if not onlytest:
            piexif.insert(piexif.dump(exif_dict), media_path)
        return True
    except Exception:
        return False


def _gps_exif_to_float(gps_dict: dict) -> typing.Optional[tuple[float, float, float]]:
    try:
        def dms(v):
            return v[0][0]/v[0][1] + v[1][0]/(v[1][1]*60) + v[2][0]/(v[2][1]*3600)
        lat = dms(gps_dict[piexif.GPSIFD.GPSLatitude])
        if gps_dict.get(piexif.GPSIFD.GPSLatitudeRef) in (b'S', 'S'):
            lat = -lat
        lon = dms(gps_dict[piexif.GPSIFD.GPSLongitude])
        if gps_dict.get(piexif.GPSIFD.GPSLongitudeRef) in (b'W', 'W'):
            lon = -lon
        alt = 0.0
        if piexif.GPSIFD.GPSAltitude in gps_dict:
            a = gps_dict[piexif.GPSIFD.GPSAltitude]
            alt = a[0] / a[1]
            if gps_dict.get(piexif.GPSIFD.GPSAltitudeRef) in (1, b'\x01'):
                alt = -alt
        return lat, lon, alt
    except Exception:
        return None


def apply_gps_exif(media_path: str, lat: float, lon: float, alt: float = 0.0,
                   onlytest: bool = False) -> bool:
    ext = os.path.splitext(media_path)[1].lower().lstrip('.')
    if ext not in ('jpg', 'jpeg', 'tif', 'tiff'):
        return False
    try:
        exif_dict = piexif.load(media_path)
        existing = _gps_exif_to_float(exif_dict.get('GPS') or {})
        if existing is not None:
            ex_lat, ex_lon, ex_alt = existing
            if abs(ex_lat - lat) < 0.0001 and abs(ex_lon - lon) < 0.0001 and abs(ex_alt - alt) < 50.0:
                return False

        def deg_to_dms_rational(deg: float):
            d = int(abs(deg))
            m = int((abs(deg) - d) * 60)
            s = round(((abs(deg) - d) * 60 - m) * 60 * 100)
            return ((d, 1), (m, 1), (s, 100))

        exif_dict['GPS'] = {
            piexif.GPSIFD.GPSLatitudeRef: b'N' if lat >= 0 else b'S',
            piexif.GPSIFD.GPSLatitude: deg_to_dms_rational(lat),
            piexif.GPSIFD.GPSLongitudeRef: b'E' if lon >= 0 else b'W',
            piexif.GPSIFD.GPSLongitude: deg_to_dms_rational(lon),
            piexif.GPSIFD.GPSAltitudeRef: b'\x00' if alt >= 0 else b'\x01',
            piexif.GPSIFD.GPSAltitude: (int(abs(alt) * 100), 100),
        }
        if not onlytest:
            piexif.insert(piexif.dump(exif_dict), media_path)
        return True
    except Exception:
        return False


def _decode_xp_str(raw) -> str:
    try:
        if isinstance(raw, tuple):
            raw = bytes(raw)
        return raw.decode('utf-16-le').rstrip('\x00')
    except Exception:
        return ''


def apply_people_exif(media_path: str, names: list[str], onlytest: bool = False) -> bool:
    if not names:
        return False
    ext = os.path.splitext(media_path)[1].lower().lstrip('.')
    if ext not in ('jpg', 'jpeg', 'tif', 'tiff'):
        return False
    try:
        exif_dict = piexif.load(media_path)
        kw_str = '; '.join(names)
        encoded = (kw_str + '\x00').encode('utf-16-le')
        existing_subject = _decode_xp_str(exif_dict['0th'].get(piexif.ImageIFD.XPSubject, b''))
        existing_keywords = _decode_xp_str(exif_dict['0th'].get(piexif.ImageIFD.XPKeywords, b''))
        if existing_subject == kw_str and existing_keywords == kw_str:
            return False
        exif_dict['0th'][piexif.ImageIFD.XPSubject] = encoded
        exif_dict['0th'][piexif.ImageIFD.XPKeywords] = encoded
        if not onlytest:
            piexif.insert(piexif.dump(exif_dict), media_path)
        return True
    except Exception:
        return False


def apply_description_exif(media_path: str, description: str, origin: str,
                            onlytest: bool = False) -> bool:
    if not description and not origin:
        return False
    ext = os.path.splitext(media_path)[1].lower().lstrip('.')
    if ext not in ('jpg', 'jpeg', 'tif', 'tiff'):
        return False
    try:
        full = f'{description} [{origin}]'.strip() if (description and origin) else (description or f'[{origin}]')
        exif_dict = piexif.load(media_path)
        raw_desc = exif_dict['0th'].get(piexif.ImageIFD.ImageDescription, b'')
        if isinstance(raw_desc, tuple):
            raw_desc = bytes(raw_desc)
        existing_desc = raw_desc.decode('ascii', errors='replace').rstrip('\x00')
        existing_comment = _decode_xp_str(exif_dict['0th'].get(piexif.ImageIFD.XPComment, b''))
        if existing_desc == full and existing_comment == full:
            return False
        exif_dict['0th'][piexif.ImageIFD.ImageDescription] = (full + '\x00').encode('ascii', errors='replace')
        # TODO: encode ASCII avec errors='replace' → accents perdus ; à chaque run la valeur
        #       diffère de l'originale et le tag est réécrit inutilement
        exif_dict['0th'][piexif.ImageIFD.XPComment] = (full + '\x00').encode('utf-16-le')
        if not onlytest:
            piexif.insert(piexif.dump(exif_dict), media_path)
        return True
    except Exception:
        return False


def apply_rating_exif(media_path: str, favorited: bool, onlytest: bool = False) -> bool:
    if not favorited:
        return False
    ext = os.path.splitext(media_path)[1].lower().lstrip('.')
    if ext not in ('jpg', 'jpeg', 'tif', 'tiff'):
        return False
    try:
        exif_dict = piexif.load(media_path)
        if exif_dict['0th'].get(piexif.ImageIFD.Rating) == 5:
            return False
        exif_dict['0th'][piexif.ImageIFD.Rating] = 5
        if not onlytest:
            piexif.insert(piexif.dump(exif_dict), media_path)
        return True
    except Exception:
        return False


def _extract_origin(google_photos_origin: dict) -> str:
    if not google_photos_origin:
        return ''
    try:
        mobile = google_photos_origin.get('mobileUpload', {})
        device = mobile.get('deviceType', '') or mobile.get('deviceFolder', {}).get('localFolderName', '')
        if device:
            return device
        if 'webUpload' in google_photos_origin:
            return 'WEB_UPLOAD'
        if 'backupPhotoUpload' in google_photos_origin:
            return 'BACKUP'
    except Exception:
        pass
    return ''


def set_file_mtime(path: str, dt: datetime.datetime, onlytest: bool = False) -> bool:
    ts = dt.timestamp()
    if int(os.stat(path).st_mtime) == int(ts):
        return False
    if not onlytest:
        os.utime(path, (ts, ts))
    return True


def safe_rename(src: str, dst: str) -> None:
    if src == dst:
        return
    if not os.path.exists(dst):
        os.rename(src, dst)
        return
    base, ext = os.path.splitext(dst)
    counter = 1
    while True:
        candidate = f'{base}_{counter:03d}{ext}'
        if not os.path.exists(candidate):
            os.rename(src, candidate)
            return
        counter += 1


# ── Compteurs (par dossier et globaux) ────────────────────────────────────────
class Counters:
    __slots__ = (
        'processed', 'no_media', 'album_loaded',
        'exif_fixed', 'gps_fixed', 'people_fixed',
        'description_fixed', 'rating_fixed', 'mtime_fixed',
        'renamed', 'already_dated', 'json_deleted', 'empty_dirs',
        'json_sidecar',
    )

    def __init__(self):
        for s in self.__slots__:
            setattr(self, s, 0)

    def __iadd__(self, other: 'Counters') -> 'Counters':
        for s in self.__slots__:
            setattr(self, s, getattr(self, s) + getattr(other, s))
        return self


# ──────────────────────────────────────────────────────────────────────────────
class TakeoutCleaner:
    """
    Nettoie un export Google Takeout dossier par dossier pour éviter les
    collisions de noms entre répertoires différents.
    """

    def __init__(
        self,
        source: str,
        onlytest: bool = True,
        recursive: bool = True,
        rename: bool = False,
        fix_exif: bool = True,
        fix_gps: bool = True,
        fix_people: bool = True,
        fix_description: bool = True,
        fix_rating: bool = True,
        fix_mtime: bool = True,
        delete_json: bool = False,
        delete_empty_dirs: bool = True,
        verbose: bool = False,
    ):
        self.source = os.path.realpath(source)
        self.onlytest = onlytest
        self.recursive = recursive
        self.rename = rename
        self.fix_exif = fix_exif
        self.fix_gps = fix_gps
        self.fix_people = fix_people
        self.fix_description = fix_description
        self.fix_rating = fix_rating
        self.fix_mtime = fix_mtime
        self.delete_json = delete_json
        self.delete_empty_dirs = delete_empty_dirs
        self.verbose = verbose
        self.curr_dir: str = ""
        self.curr_counters: Counters = Counters()
        self.curr_files: list[str] = []

        self.totals = Counters()
        self.errors: list[str] = []

    # ── 1.1 : charger le JSON d'album d'un dossier ───────────────────────────
    def _load_album_json_for_dir(self) -> dict:
        """Charge et retourne le meta d'album du dossier, ou {} si absent."""
        for fname in self.curr_files:
            if os.path.splitext(fname)[1].lower() != '.json':
                continue
            fpath = os.path.join(self.curr_dir, fname)
            try:
                meta = load_takeout_json(fpath)
            except Exception:
                meta = {}
            if is_album_json(fpath, meta):
                self.curr_counters.album_loaded += 1
                dir_name = os.path.basename(self.curr_dir)
                desc = meta.get('description', '')
                geo = meta.get('geoData') or {}
                lat, lon = geo.get('latitude', 0.0), geo.get('longitude', 0.0)
                geo_str = f'  GPS({lat:.4f},{lon:.4f})' if lat or lon else ''
                # print(f'  album  [{decode_safe(dir_name)}]{geo_str}  {decode_safe(desc)}')
                if self.delete_json:
                    if not self.onlytest:
                        try:
                            os.remove(fpath)
                        except OSError as e:
                            self.errors.append(f'Cannot delete {fpath}: {e}')
                    self.curr_counters.json_deleted += 1
                return meta
        return {}

    # ── 1.2 : charger et grouper les JSON sidecar d'un dossier ───────────────
    def _group_sidecar_for_dir(self, album: dict) -> dict[str, tuple[list[dict], list[str]]]:
        """
        Pour chaque JSON sidecar du dossier, trouve le média et groupe les metas.
        Retourne { media_path: ([meta,…], [json_path,…]) }
        """
        c = self.curr_counters
        groups: dict[str, tuple[list[dict], list[str]]] = {}
        for fname in self.curr_files:
            if os.path.splitext(fname)[1].lower() != '.json':
                continue
            fpath = os.path.join(self.curr_dir, fname)
            # Ignorer les JSON d'album (déjà traités)
            try:
                meta = load_takeout_json(fpath)
            except Exception as e:
                self.errors.append(f'JSON parse error {fpath}: {e}')
                continue
            if is_album_json(fpath, meta):
                continue
            c.json_sidecar += 1
            raw_title = meta.get('title', '')
            title: str = raw_title if isinstance(raw_title, str) else (raw_title[0] if isinstance(raw_title, list) and raw_title else str(raw_title))
            media_path = find_media_for_json(fpath, title)
            if not media_path:
                c.no_media += 1
                hint = (
                    ' — le média est peut-être dans un autre dossier (photo partagée entre plusieurs albums)'
                    if self.recursive else
                    ' — le média est peut-être dans un autre dossier (photo partagée entre plusieurs albums) ; essayez sans --no-recursive'
                )
                self.errors.append(f'Média introuvable pour {fname} (title={title!r}){hint}')
                continue
            ext = os.path.splitext(media_path)[1].lower().lstrip('.')
            if ext not in PIL_FORMATS:
                # TODO: no_media est trompeur ici : le média est trouvé mais son format
                #       n'est pas supporté ; utiliser un compteur dédié
                c.no_media += 1
                continue
            if media_path not in groups:
                groups[media_path] = ([], [])
            groups[media_path][0].append(meta)
            groups[media_path][1].append(fpath)
        return groups

    # ── merge ────────────────────────────────────────────────────────────────
    @staticmethod
    def _merge_meta(metas: list[dict], album: dict) -> dict:
        merged: dict = {}
        for m in metas:
            if m.get('title'):
                # TODO: m['title'] peut être une liste → crash dans _process_media_group
                #       (os.path.splitext sur une liste)
                merged['title'] = m['title']
                break
        for key in ('photoTakenTime', 'creationTime'):
            for src in (*metas, album):
                if src.get(key):
                    merged.setdefault(key, src[key])
                    break
        for key in ('geoDataExif', 'geoData'):
            for src in (*metas, album):
                v = src.get(key)
                if v and (v.get('latitude', 0.0) != 0.0 or v.get('longitude', 0.0) != 0.0):
                    merged.setdefault('geoData', v)
                    break
        seen: set[str] = set()
        people = []
        for src in (*metas, album):
            for p in src.get('people', []):
                name = p.get('name', '')
                if name and name not in seen:
                    seen.add(name)
                    people.append(p)
        if people:
            merged['people'] = people
        for src in (*metas, album):
            if src.get('description'):
                merged.setdefault('description', src['description'])
                break
        merged['favorited'] = any(src.get('favorited') for src in (*metas, album))
        for src in (*metas, album):
            if src.get('googlePhotosOrigin'):
                merged.setdefault('googlePhotosOrigin', src['googlePhotosOrigin'])
                break
        return merged

    # ── 1.3 : traiter un groupe média ────────────────────────────────────────
    def _process_media_group(self, media_path: str, metas: list[dict],
                              json_paths: list[str], album: dict) -> None:
        c = self.curr_counters
        c.processed += 1
        meta = self._merge_meta(metas, album)
        title: str = meta.get('title', '')
        if len(metas) > 1 and self.verbose:
            print(f'  merge {len(metas)} JSON → {decode_safe(os.path.basename(media_path))}')

        # Timestamp
        dt: typing.Optional[datetime.datetime] = None
        photo_taken = meta.get('photoTakenTime') or meta.get('creationTime')
        if photo_taken:
            try:
                dt = timestamp_to_datetime(photo_taken['timestamp'])
            except Exception:
                pass

        if dt and self.fix_exif:
            if apply_exif_timestamp(media_path, dt, self.onlytest):
                c.exif_fixed += 1

        # GPS
        geo = meta.get('geoData')
        if geo and self.fix_gps:
            lat = geo.get('latitude', 0.0)
            lon = geo.get('longitude', 0.0)
            alt = geo.get('altitude', 0.0)
            if lat != 0.0 or lon != 0.0:
                if apply_gps_exif(media_path, lat, lon, alt, self.onlytest):
                    c.gps_fixed += 1

        # People
        raw_people = meta.get('people') or []
        if raw_people and self.fix_people:
            names = [p['name'] for p in raw_people if p.get('name')]
            if apply_people_exif(media_path, names, self.onlytest):
                c.people_fixed += 1

        # Description + Origin
        if self.fix_description:
            desc = meta.get('description', '')
            origin = _extract_origin(meta.get('googlePhotosOrigin', {}))
            if apply_description_exif(media_path, desc, origin, self.onlytest):
                c.description_fixed += 1

        # Rating
        if self.fix_rating:
            if apply_rating_exif(media_path, bool(meta.get('favorited')), self.onlytest):
                c.rating_fixed += 1

        # Renommage
        new_path = media_path
        fname_stem = os.path.splitext(os.path.basename(media_path))[0]
        if ALREADY_DATED_RE.match(fname_stem):
            c.already_dated += 1
            if self.verbose:
                print(f'  dated {decode_safe(os.path.basename(media_path))}')
        elif dt:
            directory = os.path.dirname(media_path)
            _, media_ext = os.path.splitext(media_path)
            base_title = title or os.path.basename(media_path)
            title_stem = os.path.splitext(base_title)[0]
            m = TMP_PREFIX_RE.match(title_stem)
            if m:
                title_stem = f'{m.group(2)}{m.group(1)}'
            clean_title = EDITED_SUFFIXES.sub('', title_stem)
            prefix = dt.strftime('%Y%m%d_%H%M%S')
            new_name = (f'{clean_title}{media_ext}' if clean_title.startswith(prefix)
                        else f'{prefix}_{clean_title}{media_ext}')
            candidate = os.path.join(directory, new_name)
            if os.path.basename(candidate) != os.path.basename(media_path):
                c.renamed += 1
                new_path = candidate
                if self.verbose:
                    print(f'  ren  {decode_safe(os.path.basename(media_path))} → {decode_safe(new_name)}')
                if self.rename and not self.onlytest:
                    safe_rename(media_path, candidate)

        # JSON : suppression ou mise à jour
        for jp in json_paths:
            if self.delete_json:
                if not self.onlytest:
                    try:
                        os.remove(jp)
                    except OSError as e:
                        self.errors.append(f'Cannot delete {jp}: {e}')
                c.json_deleted += 1
            elif self.rename and new_path != media_path:
                # TODO: si len(json_paths) > 1, tous les JSONs sont renommés vers
                #       new_path + '.json' → safe_rename crée _001.json, _002.json…
                #       Il faudrait n'en garder qu'un seul (le merged) et supprimer les autres
                new_json = new_path + '.json'
                if not self.onlytest:
                    try:
                        meta['title'] = os.path.basename(new_path)
                        with open(jp, 'w', encoding='utf-8') as f:
                            json.dump(meta, f, ensure_ascii=False, indent=2)
                        safe_rename(jp, new_json)
                    except OSError as e:
                        self.errors.append(f'Cannot update JSON {jp}: {e}')
                if self.verbose:
                    print(f'  json {decode_safe(os.path.basename(jp))} → {decode_safe(os.path.basename(new_json))}')

        # mtime : toujours en dernier
        if dt and self.fix_mtime:
            actual = new_path if (self.rename and not self.onlytest and new_path != media_path) else media_path
            if set_file_mtime(actual, dt, self.onlytest):
                c.mtime_fixed += 1

    # ── 1.4 : résumé dossier ─────────────────────────────────────────────────
    def _print_dir_summary(self) -> None:
        c = self.curr_counters
        name = os.path.relpath(self.curr_dir, self.source) or '.'
        print(f'  [{decode_safe(name)}]  '
              f'médias={c.processed}  '
              f'exif={c.exif_fixed}  '
              f'gps={c.gps_fixed}  '
              f'mtime={c.mtime_fixed}  '
              f'ren={c.renamed}  '
              f'dated={c.already_dated}')

    # ── Suppression des dossiers vides ────────────────────────────────────────
    def _remove_empty_dirs(self) -> None:
        if not self.recursive:
            return
        # TODO: double parcours os.walk ; pourrait être fusionné avec le parcours principal
        for root, dirs, files in os.walk(self.source, topdown=False):
            if root == self.source:
                continue
            if not os.listdir(root):
                self.totals.empty_dirs += 1
                if not self.onlytest:
                    try:
                        os.rmdir(root)
                        if self.verbose:
                            print(f'  rmdir {decode_safe(root)}')
                    except OSError as e:
                        self.errors.append(f'Cannot rmdir {root}: {e}')

    # ── Point d'entrée ────────────────────────────────────────────────────────
    def run(self) -> None:
        if not os.path.isdir(self.source):
            print(f"Erreur : {self.source} n'est pas un répertoire valide.", file=sys.stderr)
            sys.exit(1)

        print('Paramètres')
        print('----------')
        print(f'  Source          : {self.source}')
        print(f'  Mode            : {"TEST (aucune modification)" if self.onlytest else "RÉEL"}')
        print(f'  Récursif        : {"oui" if self.recursive else "non"}')
        print(f'  Renommage       : {"oui" if self.rename else "non"}')
        print(f'  EXIF timestamp  : {"oui" if self.fix_exif else "non"}')
        print(f'  GPS             : {"oui" if self.fix_gps else "non"}')
        print(f'  People          : {"oui" if self.fix_people else "non"}')
        print(f'  Description     : {"oui" if self.fix_description else "non"}')
        print(f'  Rating          : {"oui" if self.fix_rating else "non"}')
        print(f'  mtime           : {"oui" if self.fix_mtime else "non"}')
        print(f'  Suppr. JSON     : {"oui" if self.delete_json else "non"}')
        print(f'  Suppr. vides    : {"oui" if self.delete_empty_dirs else "non"}')
        print(f'  Verbose         : {"oui" if self.verbose else "non"}')
        print()

        mode = '*** MODE TEST — aucune modification ***' if self.onlytest else 'MODE RÉEL'

        # Collecter les dossiers à traiter
        if self.recursive:
            dirs_to_process = sorted({root for root, _, _ in os.walk(self.source)})
        else:
            dirs_to_process = [self.source]

        print(f'Traitement [{mode}]  —  {len(dirs_to_process)} dossier(s)')
        print('-' * 80)

        for directory in dirs_to_process:
            self.curr_dir = directory
            self.curr_counters = Counters()
            print(f'  [{decode_safe(os.path.basename(self.curr_dir))}]')
            try:
                self.curr_files = os.listdir(self.curr_dir)
            except OSError:
                continue

            # 1.1 charger JSON d'album
            album = self._load_album_json_for_dir()

            # 1.2 grouper les JSON sidecar
            groups = self._group_sidecar_for_dir(album)

            # 1.3 traiter chaque groupe
            for media_path, (metas, json_paths) in groups.items():
                self._process_media_group(media_path, metas, json_paths, album)

            # 1.4 résumé dossier
            self._print_dir_summary()
            # if not self.verbose:
            #     return

            # Accumuler dans les totaux globaux
            self.totals += self.curr_counters

        if self.delete_empty_dirs:
            self._remove_empty_dirs()

        self._print_summary()

    # ── 2 : résumé global ────────────────────────────────────────────────────
    def _print_summary(self) -> None:
        W = 26
        c = self.totals
        print('\nRésumé global\n-------------')
        if c.album_loaded:
            print(f'  {"Albums chargés":<{W}}: {c.album_loaded}')
        print(f'  {"JSON sidecar":<{W}}: {c.json_sidecar}')
        print(f'  {"Médias trouvés":<{W}}: {c.processed}')
        if c.no_media:
            print(f'  {"Médias introuvables":<{W}}: {c.no_media}')
        if self.fix_exif:
            print(f'  {"EXIF timestamp":<{W}}: {c.exif_fixed}')
        if self.fix_gps:
            print(f'  {"GPS insérés":<{W}}: {c.gps_fixed}')
        if self.fix_people:
            print(f'  {"People (Subject+Keywords)":<{W}}: {c.people_fixed}')
        if self.fix_description:
            print(f'  {"Description+Origin":<{W}}: {c.description_fixed}')
        if self.fix_rating:
            print(f'  {"Favoris (Rating=5)":<{W}}: {c.rating_fixed}')
        if self.fix_mtime:
            print(f'  {"mtime corrigés":<{W}}: {c.mtime_fixed}')
        if c.renamed:
            label = 'Renommés' if self.rename else 'À renommer (--rename off)'
            print(f'  {label:<{W}}: {c.renamed}')
        if c.already_dated:
            print(f'  {"Déjà datés (ignorés)":<{W}}: {c.already_dated}')
        if self.delete_json:
            print(f'  {"JSON supprimés":<{W}}: {c.json_deleted}')
        if self.delete_empty_dirs:
            print(f'  {"Dossiers vides":<{W}}: {c.empty_dirs}')
        if self.errors:
            print(f'\n  Erreurs ({len(self.errors)}) :')
            for e in self.errors:
                print(f'    {e}')
        if self.onlytest:
            print('\n  ⚠  Mode test : relancez avec --apply pour appliquer les modifications.')
        print()


# ──────────────────────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog='gtclean',
        description='Nettoie un export Google Takeout.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  # Aperçu sans modifier (mode test par défaut)
  python gtclean.py /chemin/Takeout

  # Appliquer toutes les corrections
  python gtclean.py /chemin/Takeout --apply

  # Appliquer avec renommage des fichiers
  python gtclean.py /chemin/Takeout --apply --rename

  # Appliquer et supprimer les JSON sidecar
  python gtclean.py /chemin/Takeout --apply --delete-json
""",
    )
    p.add_argument('source', help='Chemin vers le dossier Google Takeout')
    p.add_argument('--apply', dest='onlytest', action='store_false', default=True,
                   help='Applique réellement les modifications (par défaut : mode test)')
    p.add_argument('--no-recursive', dest='recursive', action='store_false', default=True,
                   help='Ne pas parcourir les sous-dossiers')
    p.add_argument('--rename', dest='rename', action='store_true', default=False,
                   help='Renommer les fichiers selon la date (YYYYMMDD_HHMMSS_<titre>)')
    p.add_argument('--no-exif', dest='fix_exif', action='store_false', default=True,
                   help='Ne pas modifier les balises EXIF')
    p.add_argument('--no-gps', dest='fix_gps', action='store_false', default=True,
                   help='Ne pas insérer les données GPS')
    p.add_argument('--no-people', dest='fix_people', action='store_false', default=True,
                   help='Ne pas écrire les tags people dans XPKeywords')
    p.add_argument('--no-description', dest='fix_description', action='store_false', default=True,
                   help="Ne pas écrire la description et l'origine")
    p.add_argument('--no-rating', dest='fix_rating', action='store_false', default=True,
                   help='Ne pas écrire le rating (favorited → 5 étoiles)')
    p.add_argument('--no-mtime', dest='fix_mtime', action='store_false', default=True,
                   help='Ne pas corriger la date de modification des fichiers')
    p.add_argument('--delete-json', dest='delete_json', action='store_true', default=False,
                   help='Supprimer les fichiers JSON sidecar après traitement')
    p.add_argument('--keep-empty-dirs', dest='delete_empty_dirs', action='store_false', default=True,
                   help='Conserver les dossiers vides')
    p.add_argument('--verbose', dest='verbose', action='store_true', default=False,
                   help='Afficher le détail de chaque fichier traité')
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    cleaner = TakeoutCleaner(
        source=args.source,
        onlytest=args.onlytest,
        recursive=args.recursive,
        rename=args.rename,
        fix_exif=args.fix_exif,
        fix_gps=args.fix_gps,
        fix_people=args.fix_people,
        fix_description=args.fix_description,
        fix_rating=args.fix_rating,
        fix_mtime=args.fix_mtime,
        delete_json=args.delete_json,
        delete_empty_dirs=args.delete_empty_dirs,
        verbose=args.verbose,
    )
    cleaner.run()


if __name__ == '__main__':
    main()
