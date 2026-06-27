# Photo Tools
Yet another photo tools library 

# Scripts

## gtclean.py — Nettoyage d'un export Google Takeout

Traite des répertoires issu de **Google Takeout** :

| Action | Détail |
|--------|--------|
| **EXIF timestamp** | Lit `photoTakenTime` du JSON sidecar et l'écrit dans `DateTimeOriginal` / `DateTimeDigitized` |
| **GPS** | Copie `geoData` du JSON dans les balises EXIF GPS |
| **mtime** | Corrige la date de modification du fichier |
| **Renommage** | Préfixe les fichiers `YYYYMMDD_HHMMSS_<titre>` |
| **Suppression JSON** | Supprime les `.json` sidecar après traitement |
| **Dossiers vides** | Supprime les dossiers vides laissés après nettoyage |

### Usage

```bash
# Aperçu sans modifier (mode test par défaut)
python yapt/gtclean.py /chemin/Takeout

# Appliquer toutes les corrections
python yapt/gtclean.py /chemin/Takeout --apply

# Appliquer avec renommage des fichiers
python yapt/gtclean.py /chemin/Takeout --apply --rename

# Appliquer et supprimer les JSON sidecar
python yapt/gtclean.py /chemin/Takeout --apply --delete-json
```

### Options

```
  source                Chemin vers le dossier Google Takeout
  --apply               Applique réellement les modifications (défaut : mode test)
  --rename              Renommer les fichiers selon la date (YYYYMMDD_HHMMSS_<titre>)
  --no-exif             Ne pas modifier les balises EXIF
  --no-gps              Ne pas insérer les données GPS
  --no-mtime            Ne pas corriger la date de modification des fichiers
  --delete-json         Supprimer les fichiers JSON sidecar après traitement
  --keep-empty-dirs     Conserver les dossiers vides
```

# Read The Docs
- https://readthedocs.org/projects/piexif/downloads/pdf/latest/

# Replace old scripts

``` bash
for image in *.jpg; do
    if [ -n "$COMMENT" ]; 
	then
    	  	echo "Optimizing 80% $image Add Comment $COMMENT"
    		/usr/bin/convert -verbose -quality 80 -comment "$COMMENT" "$DIRPATH/$image" "$FINALPATH/$image"
   		    exiv2 -M"set Exif.Photo.UserComment charset=Ascii $COMMENT" "$FINALPATH/$image"
	        exiv2 -c"$COMMENT"  $FINALPATH/$image
	else
    	  	echo "Optimizing 80% $image"
    		/usr/bin/convert -verbose -quality 80 "$DIRPATH/$image" "$FINALPATH/$image"
	fi
#   jhead -autorot "$FINALPATH/$image"
   	exiv2 -t -r'%Y%m%d_%H%M_:basename:' $FINALPATH/$image
#   exiv2 -r':basename:' -t $FINALPATH/$image
#   exiv2 -r'%Y-%m-%d %H:%M :basename:' $FINALPATH/$image
done
```



# Sources
https://github.com/novoid/filetags/
https://github.com/Bobsans/image-optimizer

# Todos
- create an account on PyPi production and test sites
- create ~/.pypirc file 
- add to rootprj/setup.cfg [metadata]
- add to rootprj/setup.py classifiers=
- create a tag on github according __version__
- Publish to PyPi
``` bash
python setup.py register -r pypitest
python setup.py sdist upload -r pypitest
python setup.py register -r pypi
python setup.py sdist upload -r pypi
```
- Test our package 
``` bash
pip install pysimplib
```
