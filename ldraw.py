bl_info = {
    'name': "Import LDraw model format",
    'author': "Spencer Alves (impiaaa)",
    'version': (1,0),
    'blender': (2, 6, 3),
    'api': 41226,
    'location': "File > Import > Import LDraw",
    'description': "This script imports LDraw model files.",
    'warning': "Some parts may be distorted", # used for warning icon and text in addons panel
    'category': "Import-Export"}

"""\
This script imports LDraw model files.

From the LDraw website:
"LDraw(tm) is an open standard for LEGO CAD programs that allow the user to 
create virtual LEGO models and scenes. You can use it to document models you 
have physically built, create building instructions just like LEGO, render 3D 
photo realistic images of your virtual models and even make animations. The 
possibilities are endless. Unlike real LEGO bricks where you are limited by the 
number of parts and colors, in LDraw nothing is impossible."

Usage:
    Execute this script from the "File->Import" menu and choose your model
    file. Make sure that the LDraw dir field is set to your LDraw install
    directory, chose the options you'd like on the left (more help in the
    tooltips), and click Import.

Changelog:
    1.0
        Initial re-release for Blender 2.60
"""

import bpy, bpy.props, bpy.utils, mathutils
import sys, os, math, time, warnings

DEFAULTMAT = mathutils.Matrix.Scale(0.025, 4)
DEFAULTMAT *= mathutils.Matrix.Rotation(math.pi/-2.0, 4, 'X') # -90 degree rotation
objectsInherit = [] # a list of part references (Blender objects) that inherit their color
THRESHOLD = 0.001
CW = 0
CCW = 1
MAXPATH = 1024
IMPORTDIR = "C:\\"

### UTILITY FUNCTIONS ###

def hex2rgb(hexColor):
    if hexColor[0] == '#': hexColor = hexColor[1:]
    elif hexColor[0:2].lower() == '0x': hexColor = hexColor[2:]
    if len(hexColor) < 6: hexColor = hexColor[0]+'0'+hexColor[1]+'0'+hexColor[2]+'0'
    return int(hexColor[0:2], 16)/255.0, int(hexColor[2:4], 16)/255.0, int(hexColor[4:6], 16)/255.0

def whatsAfter(lookThrough, lookFor):
    for idx, val in enumerate(lookThrough):
        if val == lookFor:
            return lookThrough[idx+1]

def deepcopy(o):
    # Copies and object AND all of its children. Links children to the current
    # scene, but not the parent.
    p = o.copy()
    if o in objectsInherit: objectsInherit.append(p)
    for c in o.children:
        d = deepcopy(c)
        bpy.context.scene.objects.link(d)
        d.parent = p
    return p

def applyMaterial(o, mat):
    # Recursively set mat to the 0 material slot.
    if len(o.material_slots) > 0:
        o.material_slots[0].material = mat
    for c in o.children:
        if c in objectsInherit:
            applyMaterial(c, mat)

def matrixEqual(a, b, threshold=THRESHOLD):
    if len(a.col) != len(b.col):
        return False
    for i in range(len(a)):
        for j in range(len(a[i])):
            if a[i][j] - b[i][j] > threshold: return False
    return True

class BFCContext(object):
    def __init__(self, other=None):
        self.localCull = True
        self.winding = CCW
        self.invertNext = False
        self.certified = None
        if other != None and other.certified == True:
            self.certified = True
            self.accumCull = other.accumCull and other.localCull
            self.accumInvert = other.accumInvert ^ other.invertNext
        else:
            self.accumCull = False
            self.accumInvert = False

### IMPORTER ###

def lineType0(line, bfc, someObj=None):
    # Comment or meta-command
    if len(line) < 2:
        return
    if line[1] in ('WRITE', 'PRINT'):
        #Blender.Draw.PupMenu("Message in file:%t|"+(' '.join(line[2:])))
        pass
    elif line[1] == 'CLEAR':
        bpy.ops.wm.redraw_timer()
    elif line[1] == 'PAUSE':
        #Blender.Draw.PupMenu("Paused.%t")
        pass
    elif line[1] == 'SAVE':
        bpy.ops.render.render()
    elif line[1] == '!COLOUR':
        global MATERIALS
        name = line[2].strip()
        if name in bpy.data.materials:
            mat = bpy.data.materials[name]
        else:
            mat = bpy.data.materials.new(name)
        line = [s.upper() for s in line]
        MATERIALS[int(whatsAfter(line, 'CODE'))] = mat.name
        mat.game_settings.use_backface_culling = False # BFC not working ATM
        value = whatsAfter(line, 'VALUE')
        value = hex2rgb(value)
        mat.diffuse_color = value
        # We can ignore the edge color value
        alpha = whatsAfter(line, 'ALPHA')
        if not alpha:
            alpha = 255
        else:
            alpha = int(alpha)
        mat.alpha = alpha/255.0
        luminance = whatsAfter(line, 'LUMINANCE')
        if not luminance:
            luminance = 0
        else:
            luminance = int(luminance)
        mat.emit = luminance/127.0
        
        if "CHROME" in line:
            mat.ambient = 0.25
            mat.diffuse_intensity = 0.6
            mat.raytrace_mirror.use = True
            mat.specular_intensity = 1.4
            mat.roughness = 0.01
            mat.raytrace_mirror.reflect_factor = 0.3
        elif "PEARLESCENT" in line:
            mat.ambient = 0.22
            mat.diffuse_intensity = 0.6
            mat.raytrace_mirror.use = True
            mat.specular_intensity = 0.1
            mat.roughness = 0.32
            mat.raytrace_mirror.reflect_factor = 0.07
        elif "RUBBER" in line:
            mat.ambient = 0.5
            mat.specular_intensity = 0.19
            mat.specular_slope = 0.235
            mat.diffuse_intensity = 0.6
        elif "MATTE_METALLIC" in line:
            mat.raytrace_mirror.use = True
            mat.raytrace_mirror.reflect_factor = 0.84
            mat.diffuse_intensity = 0.844
            mat.specular_intensity = 0.5
            mat.specular_hardness = 40
            mat.gloss_factor = 0.725
        elif "METAL" in line:
            mat.raytrace_mirror.use = True
            mat.raytrace_mirror.reflect_factor = 0.9
            mat.diffuse_fresnel = 0.93
            mat.diffuse_intensity = 1.0
            mat.darkness = 0.771
            mat.specular_intensity = 1.473
            mat.specular_hardness = 292
        elif "MATERIAL" in line:
            materialLine = line[line.index("MATERIAL")+1:]
            # Only these two are official, and they are nearly the same.
            if "GLITTER" in materialLine or "SPECKLE" in materialLine:
                # I could use a particle system to make it more realistic,
                # but it would be VERY slow. Use procedural texture for now.
                # TODO There has to be a better way.
                if mat.name in bpy.data.textures:
                    tex = bpy.data.textures[mat.name]
                else:
                    tex = bpy.data.textures.new(mat.name, "STUCCI")
                value = whatsAfter(materialLine, "VALUE")
                value = hex2rgb(value)
                value = [v/255.0 for v in value]
                # Alpha value is the same for the whole material, so the
                # texture can "inherit" this value, but ignore luminance, since
                # Blender textures only have color and transparency.
                fraction = float(whatsAfter(materialLine, "FRACTION"))
                tex.use_color_ramp = True
                tex.color_ramp.interpolation = "CONSTANT"
                tex.color_ramp.elements[0].color = value+[alpha/255.0]
                tex.color_ramp.elements[1].color = [0, 0, 0, 0]
                tex.color_ramp.elements.new(fraction).color = value+[0]
                size = whatsAfter(materialLine, "SIZE")
                if not size:
                    # Hmm.... I don't know what to do here.
                    size = int(whatsAfter(materialLine, "MINSIZE"))+int(whatsAfter(materialLine, "MAXSIZE"))
                    size /= 2.0
                else:
                    size = float(size)
                size *= 0.025
                tex.noise_scale = size
                slot = mat.texture_slots.add()
                slot.texture = tex
                mat.use_textures[0] = True
                
            if alpha < 255:
                mat.raytrace_mirror.use = True
                mat.ambient = 0.3
                mat.diffuse_intensity = 0.8
                mat.raytrace_mirror.reflect_factor = 0.1
                mat.specular_intensity = 0.3
                mat.raytrace_transparency.ior = 1.40
            else:
                mat.ambient = 0.1
                mat.specular_intensity = 0.2
                
        elif alpha < 255:
            mat.raytrace_mirror.use = True
            mat.ambient = 0.3
            mat.diffuse_intensity = 0.8
            mat.raytrace_mirror.reflect_factor = 0.1
            mat.specular_intensity = 0.3
            mat.raytrace_transparency.ior = 1.40
        else:
            mat.ambient = 0.1
            mat.specular_intensity = 0.2
            mat.diffuse_intensity = 1.0

        if alpha < 255:
            mat.use_transparency = True
            mat.transparency_method = "RAYTRACE"
    
    elif line[1] == "BFC":
        # http://ldraw.org/Article415.html
        if bfc.certified and "NOCERTIFY" not in line:
            bfc.certified = True
        for option in line[2:]:
            if option == "CERTIFY":
                assert bfc.certified != False
                bfc.certified = True
            elif option == "NOCERTIFY":
                assert bfc.certified != True
                bfc.certified = False
            elif option == "CLIP": bfc.localCull = True
            elif option == "NOCLIP": bfc.localCull = False
            elif option == "CCW":
                if bfc.accumInvert:
                    bfc.winding = CW
                else:
                    bfc.winding = CCW
            elif option == "CW":
                if bfc.accumInvert:
                    bfc.winding = CCW
                else:
                    bfc.winding = CW
            elif option == "INVERTNEXT":
                 bfc.invertNext = True

def lineType1(line, oldObj, oldMaterial, bfc, subfiles={}):
    # File reference
    fname = line[-1].strip()
    newMatrix = mathutils.Matrix()
    newMatrix[0][:] = [float(line[ 5]), float(line[ 6]), float(line[ 7]), float(line[2])]
    newMatrix[1][:] = [float(line[ 8]), float(line[ 9]), float(line[10]), float(line[3])]
    newMatrix[2][:] = [float(line[11]), float(line[12]), float(line[13]), float(line[4])]
    newMatrix[3][:] = [             0,              0,                 0,              1]
    materialId = int(line[1])
    if materialId in (16, 24):
        material = oldMaterial
    elif materialId in MATERIALS:
        material = bpy.data.materials[MATERIALS[materialId]]
    else:
        material = None
    if fname.lower() in subfiles:
        newObj = readFile(fname, BFCContext(bfc), subfiles=subfiles, material=material)
    elif fname.lower() == 'light.dat' and USELIGHTS:
        l = bpy.data.lamps.new(fname)
        newObj = bpy.data.objects.new(fname, l)

        l.color = material.diffuse_color
        l.energy = material.alpha
        l.shadow_method = "RAY_SHADOW"
        l.falloff_type = "CONSTANT"
    else:
        newObj = readFile(fname, BFCContext(bfc), material=material)
        if ((('con' in fname) and
             (not fname.startswith('con'))) or
            ('cyl' in fname) or\
            ('sph' in fname) or\
            fname.startswith('t0') or\
            fname.startswith('t1')) and\
           SMOOTH:
            newObj.select = True
            bpy.context.scene.objects.active = newObj
            bpy.ops.object.shade_smooth()
            newObj.select = False
    if newObj:
        if materialId in (16, 24):
            objectsInherit.append(newObj)
        newObj.parent = oldObj
        if os.path.exists(os.path.join(LDRAWDIR, "PARTS", fname)):
            if not ((fname[0] in ('s', 'S')) and (fname[1] in ('/', '\\'))):
                newMatrix *= GAPMAT
        newObj.matrix_local = newMatrix
        if bfc.invertNext:
            #newObj.matrix_local = -1*newObj.matrix_local
            pass
        bpy.context.scene.update()
        if not matrixEqual(newMatrix, newObj.matrix_local):
            warnings.warn("Object matrix has changed, model may have errors!")
    if bfc.invertNext:
        bfc.invertNext = False

def poly(line, m):
    # helper function for making polygons
    line = [float(i) for i in line]
    indices = []
    for i in range(2, len(line), 3):
        vert = (line[i], line[i+1], line[i+2])
        vidx = -1
        for j, v in enumerate(m.vertices):
            if (abs(v.co[0]-vert[0]) < THRESHOLD)\
               and (abs(v.co[1]-vert[1]) < THRESHOLD)\
               and (abs(v.co[2]-vert[2]) < THRESHOLD):
                vidx = j
                break
        if vidx == -1:
            m.vertices.add(1)
            m.vertices[len(m.vertices)-1].co = vert
            vidx = len(m.vertices)-1
        indices += [vidx]
    m.tessfaces.add(1)
    f = m.tessfaces[len(m.tessfaces)-1]
    for i, vidx in enumerate(indices):
        f.vertices_raw[i] = vidx
    if line[0] > 3 and f.vertices_raw[3] == 0:
        f.vertices_raw[3] = f.vertices_raw[1]
        f.vertices_raw[1] = 0

def readLine(line, o, material, bfc, subfiles={}):
    # Returns True if the file references any files or contains any polys;
    # otherwise, it is likely a header file and can be ignored.
    if len(line.strip()) == 0: return False
    line = line.split()
    m = o.data
    if line[0] == '0':
        # Comment or meta-command
        lineType0(line, bfc)
        return False
    elif line[0] == '1':
        # File reference
        lineType1(line, o, material, bfc, subfiles=subfiles)
        return True
    elif line[0] in ('3', '4'):
        # Tri or quad (poly)
        poly(line, m)
        line[0] = int(line[0])
        line[1] = int(line[1])
        if line[1] not in (16, 24):
            if line[1] in MATERIALS:
                material = bpy.data.materials[MATERIALS[line[1]]]
            else:
                material = None
            slotIdx = -1
            for i, matSlot in enumerate(o.material_slots):
                if matSlot.material == material and matSlot.link == "DATA":
                    slotIdx = i
                    break
            if slotIdx == -1:
                m.materials.append(material)
                m.tessfaces[-1].material_index = len(o.material_slots)-1
            else:
                m.tessfaces[-1].material_index = slotIdx
        else:
            m.tessfaces[-1].material_index = 0
        return True
    elif line[0] in ('2', '5'):
        # Line and conditional line
        # Not supported
        return False
    else:
        warnings.warn("Unknown linetype %s\n" % line[0])
        return False

def readFile(fname, bfc, first=False, smooth=False, material=None, transform=False, subfiles={}):
    if fname.lower() in subfiles:
        # part of a multi-part
        import io
        f = io.StringIO(subfiles[fname.lower()])
    else:
        fname = fname.replace('\\', os.path.sep)
    
        ldrawPath = os.path.join(LDRAWDIR, fname)
        partsPath = os.path.join(LDRAWDIR, "PARTS", fname)
        primitivesPath = os.path.join(LDRAWDIR, "P", fname)
        hiResPath = os.path.join(LDRAWDIR, "P", "48", fname)
        if os.path.exists(fname):
            pass
        elif os.path.exists(ldrawPath):
            fname = ldrawPath
        elif os.path.exists(hiResPath) and HIRES:
            fname = hiResPath
        elif os.path.exists(primitivesPath):
            fname = primitivesPath
        elif os.path.exists(partsPath):
            fname = partsPath
        else:
            warnings.warn("Could not find file %s" % fname)
            return
        f = open(fname, "rU")
    
        if os.path.splitext(fname)[1].lower() in ('.mpd', '.ldr'):
            # multi-part!
            subfiles = {}
            name = None
            firstName = None
            for line in f:
                if line[0] == '0':
                    sline = line.split()
                    if len(sline) < 2: continue
                    if sline[1].lower() == 'file':
                        i = line.lower().find('file')
                        i += 4
                        name = line[i:].strip().lower()
                        subfiles[name] = ''
                        if firstName == None:
                            firstName = name
                    elif sline[1].lower() == 'nofile':
                        name = None
                    elif name != None:
                        subfiles[name] += line
                elif name != None:
                    subfiles[name] += line
            if firstName == None:
                # This is if it wasn't actually multi-part (as is the case with most LDRs)
                firstName = fname.lower()
                f.seek(0)
                subfiles[firstName] = f.read()
            f.close()
            return readFile(firstName, bfc, first=first, smooth=smooth, material=material, transform=transform, subfiles=subfiles)
        
    mname = os.path.split(fname)[1]
    if mname in bpy.data.objects:
        # We don't need to re-import a part if it's already in the file
        obj = deepcopy(bpy.data.objects[mname])
        bpy.context.scene.objects.link(obj)
        applyMaterial(obj, material)
        return obj

    mesh = bpy.data.meshes.new(mname)
    obj = bpy.data.objects.new(mname, mesh)
    bpy.context.scene.objects.link(obj)
    
    bpy.context.scene.objects.active = obj
    obj.select = True
    bpy.ops.object.material_slot_add()
    obj.select = False
    obj.active_material_index = 0
    obj.material_slots[0].material = material
    obj.material_slots[0].link = 'OBJECT'
    obj.active_material = material

    containsData = False
    if first:
        lines = f.readlines()
        f.close()
        total = float(len(lines))
        for idx, line in enumerate(lines):
            containsData = readLine(line, obj, material, bfc, subfiles=subfiles) or containsData
        if transform:
            obj.matrix_local = DEFAULTMAT
    else:
        for line in f:
            containsData = readLine(line, obj, material, bfc, subfiles=subfiles) or containsData
    f.close()
    mesh.update()
    if not containsData:
        # This is to check for header files (like ldconfig.ldr)
        bpy.context.scene.objects.unlink(obj)
        bpy.data.objects.remove(obj)
        return None
    return obj

def main(fname, context=None, transform=False):
    global MATERIALS, LDRAWDIR, GAPMAT, SMOOTH, HIRES, USELIGHTS
    #Blender.Window.WaitCursor(1)
    start = time.time()
    IMPORTDIR = os.path.split(fname)[0]
    MATERIALS = {}
    readFile(os.path.join(LDRAWDIR, "LDConfig.ldr"), BFCContext(), first=False)
    readFile(fname, BFCContext(), first=True, transform=transform)
    context.scene.update()
    print('LDraw "{0}" imported in {1:.4} seconds.'.format(fname, time.time()-start))

class IMPORT_OT_ldraw(bpy.types.Operator):
    '''Import LDraw model Operator.'''
    bl_idname= "import_scene.ldraw_dat"
    bl_label= "Import LDR/DAT/MPD"
    bl_description= "Import an LDraw model file (.dat, .ldr, .mpd)"
    bl_options= {'REGISTER', 'UNDO'}

    filepath= bpy.props.StringProperty(name="File Path", description="Filepath used for importing the LDR/DAT/MPD file", maxlen=MAXPATH, default="")

    ldrawPathProp = bpy.props.StringProperty(name="LDraw directory", description="The directory in which the P and PARTS directories reside", maxlen=MAXPATH, default={"win32": "C:\\Program Files\\LDraw", "darwin": "/Library/LDraw"}.get(sys.platform, "/opt/ldraw"))
    transformProp = bpy.props.BoolProperty(name="Transform", description="Transform objects to match Blender's coordinate system", default=True)
    smoothProp = bpy.props.BoolProperty(name="Smooth", description="Automatically shade round primitives (cyl, sph, con, tor) smooth", default=True)
    hiResProp = bpy.props.BoolProperty(name="Hi-Res prims", description="Force use of high-resolution primitives, if possible", default=False)
    lightProp = bpy.props.BoolProperty(name="Lights from model", description="Create lamps in place of light.dat references", default=True)
    scaleProp = bpy.props.FloatProperty(name="Seam width", description="The amout of space in-between individual parts", default=0.001, min=0.0, max=1.0, precision=3)

    def execute(self, context):
        global LDRAWDIR, SMOOTH, HIRES, USELIGHTS, GAPMAT
        LDRAWDIR = str(self.ldrawPathProp)
        transform = bool(self.transformProp)
        SMOOTH = bool(self.smoothProp)
        HIRES = bool(self.hiResProp)
        USELIGHTS = bool(self.lightProp)
        gap = float(self.scaleProp)
        GAPMAT = mathutils.Matrix.Scale(1.0-gap, 4)
        main(self.filepath, context, transform)
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


def menu_import(self, context):
    self.layout.operator(IMPORT_OT_ldraw.bl_idname, text="LDraw Model (.dat)")

def register(): 
    bpy.utils.register_module(__name__) 
    bpy.types.INFO_MT_file_import.append(menu_import)
     
def unregister():
    bpy.utils.unregister_module(__name__) 
    bpy.types.INFO_MT_file_import.remove(menu_import)
     
if __name__ == "__main__":
    register()
    #LDRAWDIR = "/Library/LDraw"
    #import cProfile
    #LDRAWDIR = "C:\\Program Files\\LDraw"
    #SMOOTH = True
    #HIRES = False
    #USELIGHTS = True
    #gap = 0.01
    #GAPMAT = mathutils.Matrix.Scale(1.0-gap, 4)
    #try:
    #    main(os.path.join(LDRAWDIR, "Models", "pyramid.dat"), bpy.context, True)
    #finally:
    #    sys.stderr.flush()
    #    sys.stdout.flush()