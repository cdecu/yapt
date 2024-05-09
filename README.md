# Photo Tools
Yet another photo tools

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
