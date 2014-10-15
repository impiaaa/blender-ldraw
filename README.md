This script imports LDraw model files into Blender (2.70 and above).

From the LDraw website:

> LDraw(tm) is an open standard for LEGO CAD programs that allow the user to create virtual LEGO models and scenes. You can use it to document models you have physically built, create building instructions just like LEGO, render 3D photo realistic images of your virtual models and even make animations. The possibilities are endless. Unlike real LEGO bricks where you are limited by the number of parts and colors, in LDraw nothing is impossible.

### Features

* Utilizes Blender's hierarchical object structure, for easy moving and management of parts
* Uses mesh-linking, so that every duplicate part has the same mesh, but can have different colors and transformations
* Imports colors from the LDraw header file as materials, complete with raytraced transparency for transparent colors, emissive materials for luminescent colors, and raytraced reflections for chrome, metal, and pearlescent colors
* Supports parts with multiple colors (stickers)
* Automatically set all round primitives (cylinders, spheres, cones, and tori) to use smoothed normals
* Force models to use hi-res primitives when available
* Replace light.dat references with lamps
* Scale individual parts to create a seam between pieces

### Usage

Execute this script from the "File->Import" menu and choose your model file. Make sure that the LDraw dir field is set to your LDraw install directory, chose the options you'd like on the left (more help in the tooltips), and click Import.

### Import options

* LDraw dir: THIS MUST BE SET CORRECTLY to your LDraw install path (the directory in which the P and PARTS directories reside).
* Transform: Rotate and scale the top-level model to match Blender's coordinate system.
* Smooth: Automatically smooth round primitives (cyl, sph, con, tor)
* Hi-Res Prims: Force use of high-resolution primitives (from p\48), if possible.
* Lights from model: Create lamps in place of light.dat references.
* Seam width: The amount of space in-between individual parts (scales each part to 1.0-seam width)

### Known issues

* Models should NOT be considered Game Engine-ready, as the script does not yet fully support the LDraw BFC syntax.
* Colors/materials can be drastically improved on.
* Some parts show incorrectly due to primitives with shearing transformation (e.g., 981, 982, 3823)
* Importing can be very slow for large models.
* Names mesh/objects to file names, rather than part names. Will probably stay this way.
