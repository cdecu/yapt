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

import humanize
import piexif

__author__ = 'cdc'
__email__ = 'cdc@decumont.be'
__version__ = '0.1.0'

PIL_FORMATS = {
    'bmp', 'eps', 'gif', 'j2c', 'j2k', 'jp2', 'jpc', 'jpe', 'jpeg',
    'jpf', 'jpg', 'jpx', 'mpo', 'pbm', 'pcx', 'pgm', 'png', 'ppm',
    'tga', 'tif', 'tiff', 'webp', 'heic', 'heif', 'mp4', 'mov', 'avi',
    'mkv', '3gp', 'm4v',
}

# Noms de fichiers JSON d'album générés par Google Takeout selon la langue de l'interface
ALBUM_JSON_NAMES = {
    'métadonnées.json',   # français
    'metadonnees.json',   # français sans accent (variante)
    'metadata.json',      # anglais
    'metadaten.json',     # allemand
    'metadatos.json',     # espagnol
    'metadati.json',      # italien
    'метаданные.json',    # russe
}

# Patterns Google Takeout pour les noms de fichiers édités / suppléments
EDITED_SUFFIXES = re.compile(
    r'(-edited|-bewerkt|-modifié|-modifie|-modificato|-editado|'
    r'-redimensionné|-redimensionne|-redimensioniert|-ridimensionato|'
    r'-recortado|-cropped|-animado|-animé|-animiert|-animato)$',
    re.IGNORECASE
)

# Fichiers déjà nommés YYYYMMDD_HHMMSS[…] — ne jamais renommer
ALREADY_DATED_RE = re.compile(r'^\d{8}_\d{6}')

# Préfixe temporaire Google Takeout : ~tmpXXX_NOM → NOM~tmpXXX
TMP_PREFIX_RE = re.compile(r'^(~tmp[^_]*)_(.+)$', re.IGNORECASE)


# ──────────────────────────────────────────────────────────────────────────────
def decode_safe(text: str) -> str:
    return text.encode(sys.stdout.encoding, 'ignore').decode(sys.stdout.encoding)


def timestamp_to_datetime(ts: typing.Union[str, int, float]) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(int(ts))


def is_album_json(json_path: str, meta: dict) -> bool:
    """
    Retourne True si ce JSON est un fichier de métadonnées d'album Google Takeout,
    c'est-à-dire si :
      - son nom (insensible à la casse) est dans ALBUM_JSON_NAMES, OU
      - son `title` correspond exactement au nom du dossier qui le contient.
    """
    fname = os.path.basename(json_path).lower()
    if fname in ALBUM_JSON_NAMES:
        return True
    title = meta.get('title', '')
    dir_name = os.path.basename(os.path.dirname(json_path))
    return bool(title) and title == dir_name


def find_media_for_json(json_path: str, title: str) -> typing.Optional[str]:
    """
    Cherche le fichier média correspondant à un JSON sidecar Google Takeout.

    Stratégies (dans l'ordre) :
      1. Correspondance directe avec `title`.
      2. Déduction depuis le nom du JSON (photo.jpg.json → photo.jpg).
      3. Titre ~tmpXXX_NOM → fichier NOM~tmpXXX (renommé lors d'un run précédent).
      4. Correspondance par préfixe tronqué (Google tronque les noms longs).
      5. Fichiers édités : IMG_1234-edited.jpg → JSON titre IMG_1234.jpg.
    """
    directory = os.path.dirname(json_path)

    # 1 — correspondance directe via title
    if title:
        candidate = os.path.join(directory, title)
        if os.path.isfile(candidate):
            return candidate

    # 2 — déduction depuis le nom du JSON (photo.jpg.json → photo.jpg)
    json_name = os.path.basename(json_path)
    if json_name.lower().endswith('.json'):
        media_name = json_name[:-5]
        candidate = os.path.join(directory, media_name)
        if os.path.isfile(candidate):
            return candidate

    # 3 — titre ~tmpXXX_NOM.ext → fichier déjà renommé NOM~tmpXXX.ext
    if title:
        stem, ext = os.path.splitext(title)
        m = TMP_PREFIX_RE.match(stem)
        if m:
            transformed = f'{m.group(2)}{m.group(1)}{ext}'
            candidate = os.path.join(directory, transformed)
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
                    if stem.startswith(fstem) or fstem.startswith(stem):
                        fpath = os.path.join(directory, fname)
                        if os.path.isfile(fpath):
                            return fpath
        except OSError:
            pass

    # 5 — fichier édité : chercher title sans extension + suffixe -edited + ext
    if title:
        stem, ext = os.path.splitext(title)
        candidate = os.path.join(directory, f'{stem}-edited{ext}')
        if os.path.isfile(candidate):
            return candidate

    return None


def load_takeout_json(json_path: str) -> dict:
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def apply_exif_timestamp(media_path: str, dt: datetime.datetime, onlytest: bool = False) -> bool:
    """
    Applique le timestamp dans les balises EXIF DateTimeOriginal / DateTimeDigitized.
    Ne traite que les JPEG/TIFF (formats supportés par piexif).
    Retourne True uniquement si les balises ont effectivement changé.
    """
    ext = os.path.splitext(media_path)[1].lower().lstrip('.')
    if ext not in ('jpg', 'jpeg', 'tif', 'tiff'):
        return False
    try:
        exif_dict = piexif.load(media_path)
        dt_str = dt.strftime('%Y:%m:%d %H:%M:%S').encode('ascii')
        # Vérifier si les valeurs sont déjà correctes
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
    """Décode lat/lon/alt depuis un dict GPS EXIF. Retourne None si incomplet."""
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
    """
    Insère les coordonnées GPS dans les balises EXIF.
    Retourne True uniquement si les valeurs ont effectivement changé (±0.0001°, ±1m).
    """
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
    """Décode un tag XP* (piexif le retourne en tuple d'ints ou bytes) en string."""
    try:
        if isinstance(raw, tuple):
            raw = bytes(raw)
        return raw.decode('utf-16-le').rstrip('\x00')
    except Exception:
        return ''


def apply_people_exif(media_path: str, names: list[str], onlytest: bool = False) -> bool:
    """
    Écrit les noms de personnes dans deux balises EXIF Windows (UTF-16LE) :
      - XPSubject  (0x9C9F) : sujet/personnes de la photo
      - XPKeywords (0x9C9E) : mots-clés (digiKam, Lightroom…)
    Les noms sont séparés par '; '.
    Retourne True uniquement si au moins une balise a effectivement changé.
    """
    if not names:
        return False
    ext = os.path.splitext(media_path)[1].lower().lstrip('.')
    if ext not in ('jpg', 'jpeg', 'tif', 'tiff'):
        return False
    try:
        exif_dict = piexif.load(media_path)
        kw_str = '; '.join(names)
        encoded = (kw_str + '\x00').encode('utf-16-le')
        # Comparer les strings décodées pour éviter les faux-positifs liés aux null-terminators
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
    """
    Écrit la description dans :
      - ImageDescription (0x010E) : ASCII standard
      - XPComment        (0x9C9C) : UTF-16LE (Windows/digiKam)
    Si `origin` est fourni (ex: 'ANDROID_PHONE'), il est ajouté entre crochets.
    Retourne True uniquement si la valeur a changé.
    """
    if not description and not origin:
        return False
    ext = os.path.splitext(media_path)[1].lower().lstrip('.')
    if ext not in ('jpg', 'jpeg', 'tif', 'tiff'):
        return False
    try:
        full = description
        if origin:
            full = f'{description} [{origin}]'.strip() if description else f'[{origin}]'
        exif_dict = piexif.load(media_path)
        # ImageDescription peut être bytes ou tuple selon piexif
        raw_desc = exif_dict['0th'].get(piexif.ImageIFD.ImageDescription, b'')
        if isinstance(raw_desc, tuple):
            raw_desc = bytes(raw_desc)
        existing_desc = raw_desc.decode('ascii', errors='replace').rstrip('\x00')
        existing_comment = _decode_xp_str(exif_dict['0th'].get(piexif.ImageIFD.XPComment, b''))
        if existing_desc == full and existing_comment == full:
            return False
        exif_dict['0th'][piexif.ImageIFD.ImageDescription] = (full + '\x00').encode('ascii', errors='replace')
        exif_dict['0th'][piexif.ImageIFD.XPComment] = (full + '\x00').encode('utf-16-le')
        if not onlytest:
            piexif.insert(piexif.dump(exif_dict), media_path)
        return True
    except Exception:
        return False


def apply_rating_exif(media_path: str, favorited: bool, onlytest: bool = False) -> bool:
    """
    Écrit le rating EXIF (0x4746) :
      - favorited=True  → Rating 5
      - favorited=False → Rating 0 (pas de dégradation si déjà renseigné)
    Retourne True uniquement si la valeur a changé.
    """
    if not favorited:
        return False
    ext = os.path.splitext(media_path)[1].lower().lstrip('.')
    if ext not in ('jpg', 'jpeg', 'tif', 'tiff'):
        return False
    try:
        exif_dict = piexif.load(media_path)
        rating = 5
        existing = exif_dict['0th'].get(piexif.ImageIFD.Rating)
        if existing == rating:
            return False
        exif_dict['0th'][piexif.ImageIFD.Rating] = rating
        if not onlytest:
            piexif.insert(piexif.dump(exif_dict), media_path)
        return True
    except Exception:
        return False


def _extract_origin(google_photos_origin: dict) -> str:
    """Extrait le type d'appareil depuis googlePhotosOrigin."""
    if not google_photos_origin:
        return ''
    try:
        mobile = google_photos_origin.get('mobileUpload', {})
        device = mobile.get('deviceType', '') or mobile.get('deviceFolder', {}).get('localFolderName', '')
        if device:
            return device
        # Autres sources connues
        if 'webUpload' in google_photos_origin:
            return 'WEB_UPLOAD'
        if 'backupPhotoUpload' in google_photos_origin:
            return 'BACKUP'
    except Exception:
        pass
    return ''


def set_file_mtime(path: str, dt: datetime.datetime, onlytest: bool = False) -> bool:
    """
    Corrige la date de modification du fichier.
    Retourne True uniquement si le mtime a effectivement changé (à la seconde près).
    """
    ts = dt.timestamp()
    if int(os.stat(path).st_mtime) == int(ts):
        return False
    if not onlytest:
        os.utime(path, (ts, ts))
    return True


def safe_rename(src: str, dst: str) -> None:
    """
    Renomme src → dst en évitant les collisions (ajoute un suffixe numérique).
    """
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


# ──────────────────────────────────────────────────────────────────────────────
class TakeoutCleaner:
    """
    Nettoie un export Google Takeout :
      - applique les métadonnées JSON sur les médias
      - renomme selon la date
      - supprime les JSON sidecar
      - supprime les dossiers vides et les fichiers non-média
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

        self.album_json_files: list[str] = []   # JSON d'album (title == dirname)
        self.json_files: list[str] = []          # JSON sidecar individuels
        self.album_meta: dict[str, dict] = {}    # dir → métadonnées d'album (défauts)

        self.count_processed = 0
        self.count_no_media = 0
        self.count_album_loaded = 0
        self.count_exif_fixed = 0
        self.count_gps_fixed = 0
        self.count_people_fixed = 0
        self.count_description_fixed = 0
        self.count_rating_fixed = 0
        self.count_mtime_fixed = 0
        self.count_renamed = 0
        self.count_already_dated = 0
        self.count_json_deleted = 0
        self.count_empty_dirs = 0
        self.errors: list[str] = []

    # ── Scan ──────────────────────────────────────────────────────────────────
    def scan(self) -> None:
        print(f'Scanning {self.source} …')
        if self.recursive:
            roots = os.walk(self.source)
        else:
            roots = [(self.source, [], os.listdir(self.source))]

        for root, dirs, files in roots:
            for fname in files:
                if os.path.splitext(fname)[1].lower() != '.json':
                    continue
                fpath = os.path.join(root, fname)
                try:
                    meta = load_takeout_json(fpath)
                except Exception:
                    meta = {}
                if is_album_json(fpath, meta):
                    self.album_json_files.append(fpath)
                else:
                    self.json_files.append(fpath)

        print(f'  {len(self.album_json_files)} JSON d\'album  (métadonnées de dossier)')
        print(f'  {len(self.json_files)} JSON sidecar (métadonnées individuelles)')

    # ── Passe 1 : chargement des JSON d'album ────────────────────────────────
    def _load_album_json(self, json_path: str) -> None:
        """
        Charge les métadonnées d'un JSON d'album dans self.album_meta[directory].
        Ces valeurs servent de DÉFAUTS pour tous les médias du dossier ;
        elles seront surchargées par les JSON individuels en passe 2.
        """
        try:
            meta = load_takeout_json(json_path)
        except Exception as e:
            self.errors.append(f'Album JSON parse error {json_path}: {e}')
            return

        directory = os.path.dirname(json_path)
        self.album_meta[directory] = meta
        self.count_album_loaded += 1

        dir_name = os.path.basename(directory)
        desc = meta.get('description', '')
        geo = meta.get('geoData') or {}
        lat, lon = geo.get('latitude', 0.0), geo.get('longitude', 0.0)
        geo_str = f'  GPS({lat:.4f},{lon:.4f})' if lat or lon else ''
        # Always Print album !
        print(f'  album  [{decode_safe(dir_name)}]{geo_str}  {decode_safe(desc)}')

        # Supprimer le JSON d'album
        if self.delete_json:
            if not self.onlytest:
                try:
                    os.remove(json_path)
                except OSError as e:
                    self.errors.append(f'Cannot delete {json_path}: {e}')
            self.count_json_deleted += 1

    # ── Passe 2a : groupement des JSON sidecar par média ─────────────────────
    def _group_sidecar_json(self) -> dict[str, tuple[list[dict], list[str]]]:
        """
        Charge tous les JSON sidecar, résout leur média et les groupe :
          { media_path: ([meta, …], [json_path, …]) }
        Plusieurs JSON peuvent pointer vers le même média.
        """
        groups: dict[str, tuple[list[dict], list[str]]] = {}
        for json_path in self.json_files:
            try:
                meta = load_takeout_json(json_path)
            except Exception as e:
                self.errors.append(f'JSON parse error {json_path}: {e}')
                continue
            title: str = meta.get('title', '')
            media_path = find_media_for_json(json_path, title)
            if not media_path:
                self.count_no_media += 1
                self.errors.append(f'Média introuvable pour {os.path.basename(json_path)} (title={title!r})')
                continue
            ext = os.path.splitext(media_path)[1].lower().lstrip('.')
            if ext not in PIL_FORMATS:
                self.count_no_media += 1
                continue
            if media_path not in groups:
                groups[media_path] = ([], [])
            groups[media_path][0].append(meta)
            groups[media_path][1].append(json_path)
        return groups

    @staticmethod
    def _merge_meta(metas: list[dict], album: dict) -> dict:
        """
        Fusionne plusieurs metas JSON + défauts d'album en une seule dict.
        Règles :
          - photoTakenTime : première valeur non-nulle parmi les metas, puis album
          - geoDataExif    : préféré à geoData (GPS enregistré vs interpolé)
          - geoData        : fallback, premier avec lat/lon non-nuls
          - people         : union des noms dédoublonnée
          - title          : premier meta individuel
        """
        merged: dict = {}
        for m in metas:
            if m.get('title'):
                merged['title'] = m['title']
                break
        for key in ('photoTakenTime', 'creationTime'):
            for src in (*metas, album):
                if src.get(key):
                    merged.setdefault(key, src[key])
                    break
        # geoDataExif prioritaire sur geoData
        for key in ('geoDataExif', 'geoData'):
            for src in (*metas, album):
                v = src.get(key)
                if v and (v.get('latitude', 0.0) != 0.0 or v.get('longitude', 0.0) != 0.0):
                    merged.setdefault('geoData', v)
                    break
        seen_names: set[str] = set()
        all_people = []
        for src in (*metas, album):
            for p in src.get('people', []):
                name = p.get('name', '')
                if name and name not in seen_names:
                    seen_names.add(name)
                    all_people.append(p)
        if all_people:
            merged['people'] = all_people
        # description : première non-vide
        for src in (*metas, album):
            if src.get('description'):
                merged.setdefault('description', src['description'])
                break
        # favorited : True si l'un des metas le dit
        merged['favorited'] = any(src.get('favorited') for src in (*metas, album))
        # googlePhotosOrigin : premier non-nul
        for src in (*metas, album):
            if src.get('googlePhotosOrigin'):
                merged.setdefault('googlePhotosOrigin', src['googlePhotosOrigin'])
                break
        return merged

    # ── Passe 2b : application sur un média (metas fusionnées) ───────────────
    def process_media_group(self, media_path: str, metas: list[dict], json_paths: list[str]) -> None:
        self.count_processed += 1
        album = self.album_meta.get(os.path.dirname(json_paths[0]), {})
        meta = self._merge_meta(metas, album)
        title: str = meta.get('title', '')
        if len(metas) > 1 and self.verbose:
            print(f'  merge {len(metas)} JSON → {decode_safe(os.path.basename(media_path))}')

        # ── Timestamp ─────────────────────────────────────────────────────────
        dt: typing.Optional[datetime.datetime] = None
        photo_taken = meta.get('photoTakenTime') or meta.get('creationTime')
        if photo_taken:
            try:
                dt = timestamp_to_datetime(photo_taken['timestamp'])
            except Exception:
                pass

        if dt and self.fix_exif:
            if apply_exif_timestamp(media_path, dt, self.onlytest):
                self.count_exif_fixed += 1

        # ── GPS (déjà fusionné dans meta) ──────────────────────────────────────
        geo = meta.get('geoData')
        if geo and self.fix_gps:
            lat = geo.get('latitude', 0.0)
            lon = geo.get('longitude', 0.0)
            alt = geo.get('altitude', 0.0)
            if lat != 0.0 or lon != 0.0:
                if apply_gps_exif(media_path, lat, lon, alt, self.onlytest):
                    self.count_gps_fixed += 1

        # ── People ────────────────────────────────────────────────────────────
        raw_people = meta.get('people') or []
        if raw_people and self.fix_people:
            names = [p['name'] for p in raw_people if p.get('name')]
            if apply_people_exif(media_path, names, self.onlytest):
                self.count_people_fixed += 1

        # ── Description + Origin ──────────────────────────────────────────────
        if self.fix_description:
            desc = meta.get('description', '')
            origin = _extract_origin(meta.get('googlePhotosOrigin', {}))
            if apply_description_exif(media_path, desc, origin, self.onlytest):
                self.count_description_fixed += 1

        # ── Rating (favorited) ────────────────────────────────────────────────
        if self.fix_rating:
            if apply_rating_exif(media_path, bool(meta.get('favorited')), self.onlytest):
                self.count_rating_fixed += 1

        # ── Renommage ─────────────────────────────────────────────────────────
        new_path = media_path
        fname_stem = os.path.splitext(os.path.basename(media_path))[0]
        if ALREADY_DATED_RE.match(fname_stem):
            self.count_already_dated += 1
            if self.verbose:
                print(f'  dated {decode_safe(os.path.basename(media_path))}')
        elif dt:
            directory = os.path.dirname(media_path)
            _, media_ext = os.path.splitext(media_path)
            base_title = title or os.path.basename(media_path)
            # ~tmpXXX_NOM.jpg → NOM~tmpXXX.jpg
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
                self.count_renamed += 1
                new_path = candidate
                if self.verbose:
                    print(f'  ren  {decode_safe(os.path.basename(media_path))} → {decode_safe(new_name)}')
                if self.rename and not self.onlytest:
                    safe_rename(media_path, candidate)

        # ── Suppression / mise à jour JSON (tous les JSON du groupe) ──────────
        for jp in json_paths:
            if self.delete_json:
                if not self.onlytest:
                    try:
                        os.remove(jp)
                    except OSError as e:
                        self.errors.append(f'Cannot delete {jp}: {e}')
                self.count_json_deleted += 1
            elif self.rename and new_path != media_path:
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

        # ── mtime : toujours en dernier pour écraser les touches précédentes ──
        if dt and self.fix_mtime:
            # Après un rename effectif, le fichier est à new_path
            actual_path = new_path if (self.rename and not self.onlytest and new_path != media_path) else media_path
            if set_file_mtime(actual_path, dt, self.onlytest):
                self.count_mtime_fixed += 1

    # ── Suppression des dossiers vides ────────────────────────────────────────
    def remove_empty_dirs(self) -> None:
        if not self.recursive:
            return
        for root, dirs, files in os.walk(self.source, topdown=False):
            if root == self.source:
                continue
            if not os.listdir(root):
                self.count_empty_dirs += 1
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

        print(f'Paramètres')
        print(f'----------')
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

        self.scan()
        print()

        mode = '*** MODE TEST — aucune modification ***' if self.onlytest else 'MODE RÉEL'

        # ── Passe 1 : chargement des JSON d'album (défauts) ──────────────────
        if self.album_json_files:
            header = f'Passe 1 [{mode}]  —  {len(self.album_json_files)} JSON d\'album'
            print(header)
            print('-' * len(header))
            for json_path in self.album_json_files:
                self._load_album_json(json_path)
            print()

        # ── Passe 2 : groupement + merge + application ────────────────────────
        groups = self._group_sidecar_json()
        merged_count = sum(1 for metas, _ in groups.values() if len(metas) > 1)
        header = f'Passe 2 [{mode}]  —  {len(groups)} médias ({len(self.json_files)} JSON'
        header += f', {merged_count} fusionnés)' if merged_count else ')'
        print(header)
        print('-' * len(header))
        for media_path, (metas, json_paths) in groups.items():
            self.process_media_group(media_path, metas, json_paths)

        if self.delete_empty_dirs:
            self.remove_empty_dirs()

        self._print_summary()

    # ── Résumé ────────────────────────────────────────────────────────────────
    def _print_summary(self) -> None:
        W = 26
        print('\nRésumé\n------')
        if self.album_json_files:
            print(f'  {"Albums chargés":<{W}}: {self.count_album_loaded}')
        print(f'  {"JSON sidecar":<{W}}: {len(self.json_files)}')
        print(f'  {"Médias trouvés":<{W}}: {self.count_processed}')
        if self.count_no_media:
            print(f'  {"Médias introuvables":<{W}}: {self.count_no_media}')
        if self.fix_exif:
            print(f'  {"EXIF timestamp":<{W}}: {self.count_exif_fixed}')
        if self.fix_gps:
            print(f'  {"GPS insérés":<{W}}: {self.count_gps_fixed}')
        if self.fix_people:
            print(f'  {"People (Subject+Keywords)":<{W}}: {self.count_people_fixed}')
        if self.fix_description:
            print(f'  {"Description+Origin":<{W}}: {self.count_description_fixed}')
        if self.fix_rating:
            print(f'  {"Favoris (Rating=5)":<{W}}: {self.count_rating_fixed}')
        if self.fix_mtime:
            print(f'  {"mtime corrigés":<{W}}: {self.count_mtime_fixed}')
        if self.count_renamed:
            label = 'Renommés' if self.rename else 'À renommer (--rename off)'
            print(f'  {label:<{W}}: {self.count_renamed}')
        if self.count_already_dated:
            print(f'  {"Déjà datés (ignorés)":<{W}}: {self.count_already_dated}')
        if self.delete_json:
            print(f'  {"JSON supprimés":<{W}}: {self.count_json_deleted}')
        if self.delete_empty_dirs:
            print(f'  {"Dossiers vides":<{W}}: {self.count_empty_dirs}')
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
    p.add_argument(
        '--apply', dest='onlytest', action='store_false', default=True,
        help='Applique réellement les modifications (par défaut : mode test)',
    )
    p.add_argument('--no-recursive', dest='recursive', action='store_false', default=True,
                   help='Ne pas parcourir les sous-dossiers (dossier source uniquement)')
    p.add_argument('--rename', dest='rename', action='store_true', default=False,
                   help='Renommer les fichiers selon la date (YYYYMMDD_HHMMSS_<titre>)')
    p.add_argument('--no-exif', dest='fix_exif', action='store_false', default=True,
                   help='Ne pas modifier les balises EXIF')
    p.add_argument('--no-gps', dest='fix_gps', action='store_false', default=True,
                   help='Ne pas insérer les données GPS')
    p.add_argument('--no-people', dest='fix_people', action='store_false', default=True,
                   help='Ne pas écrire les tags people dans XPKeywords')
    p.add_argument('--no-description', dest='fix_description', action='store_false', default=True,
                   help='Ne pas écrire la description et l\'origine')
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
