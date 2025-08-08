bl_info = {
    'name': 'Export: Flare3D Tools',
    'author': 'David E Jones, http://davidejones.com',
    'version': (1, 1, 0),
    'blender': (4, 4, 0),
    'location': 'File > Import/Export;',
    'description': 'Importer and exporter for Flare3D engine. Supports ZF3D files',
    'warning': '',
    'wiki_url': '',
    'tracker_url': 'http://davidejones.com',
    'category': 'Import-Export'
}

import bpy
import zlib
import time
import struct
import zipfile
import io
from struct import unpack, pack, calcsize
from bpy.props import StringProperty
from xml.etree import ElementTree as ET

#==================================
# Common Functions 
#==================================

def checkBMesh():
    a, b, c = bpy.app.version
    return (int(b) >= 63)

#==================================
# ZF3D IMPORTER
#==================================

class ZF3DImporterSettings:
    def __init__(self, FilePath=""):
        self.FilePath = str(FilePath)

class ZF3DImporter(bpy.types.Operator):
    bl_idname = "import_scene.zf3d"
    bl_label = "Import ZF3D (Flare3D)"
    bl_description = "Import ZF3D (Flare3D)"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: StringProperty(
        name="File Path",
        description="Filepath used for importing the ZF3D file",
        maxlen=1024,
        default=""
    )

    def execute(self, context):
        time1 = time.perf_counter()
        with open(self.filepath, 'rb') as file:
            Config = ZF3DImporterSettings(FilePath=self.filepath)
            ZF3DImport(file, Config)
        self.report({'INFO'}, ".zf3d import time: %.2f" % (time.perf_counter() - time1))
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

def ZF3DImport(file, Config):
    print("ZF3D Import started")
    surfaces, maps, materials, nodes = [], [], [], []
    data = file.read()
    if zipfile.is_zipfile(Config.FilePath):
        zf = zipfile.ZipFile(Config.FilePath, 'r')
        print(zf.namelist())
        mainxml = zf.read("main.xml")
        surfaces, maps, materials, nodes = parseMainXML(mainxml, Config)
        vertex0 = zf.read("0.vertex")
        b = io.BytesIO(vertex0)

        verts = []
        faces = []
        uvs = []
        norms = []

        inputs = {}
        inputs["POSITION"] = []
        inputs["NORMAL"] = []
        inputs["UV0"] = []
        inputs["UV1"] = []

        for xs in surfaces:
            numflts = 0
            for att in xs._inputs:
                if att == "POSITION":
                    numflts += 3
                if att == "NORMAL":
                    numflts += 3
                if att == "UV0":
                    numflts += 2
                if att == "UV1":
                    numflts += 2
            b.seek(0)
            bdata = b.read()
            flcount = int(len(bdata) / 4)
            points = int(flcount / numflts)

            b.seek(0)
            for p in range(points):
                for att in xs._inputs:
                    if att == "POSITION":
                        x = unpack(">f", b.read(4))[0]
                        y = unpack(">f", b.read(4))[0]
                        z = unpack(">f", b.read(4))[0]
                        verts.append((x, y, z))
                    if att == "NORMAL":
                        b.read(4)
                        b.read(4)
                        b.read(4)
                    if att == "UV0":
                        b.read(4)
                        b.read(4)
                    if att == "UV1":
                        b.read(4)
                        b.read(4)

        me = bpy.data.meshes.new("ZF3D_Mesh")
        ob = bpy.data.objects.new("ZF3D_Object", me)
        # Blender 2.8+ API: scene.collection.objects.link(ob)
        bpy.context.scene.collection.objects.link(ob)
        ob.location = bpy.context.scene.cursor.location
        me.from_pydata(verts, [], faces)
        me.update()
    else:
        print("Error: the file selected isn't recognized as zip compression")
    return {'FINISHED'}

def format2Byte(fmt, b):
    ret = None
    if fmt == "float3":
        ret = unpack(">fff", b.read(12))[0]
    elif fmt == "float2":
        ret = unpack(">ff", b.read(8))[0]
    else:
        print("Unrecognised format")
    return ret

def parseMainXML(xml, Config):
    root = ET.XML(xml)
    surfaces = []
    maps = []
    materials = []
    nodes = []

    elem_surfaces, elem_maps, elem_materials, elem_nodes = list(root)

    for x in range(len(elem_surfaces)):
        xs = XMLSurface(Config)
        surfaces.append(xs.read(elem_surfaces[x]))

    # Uncomment and implement when needed
    # for x in range(len(elem_maps)):
    #     xmp = XMLMap(Config)
    #     maps.append(xmp.read(elem_maps[x]))

    # for x in range(len(elem_materials)):
    #     xmt = XMLMaterial(Config)
    #     materials.append(xmt.read(elem_materials[x]))

    # for x in range(len(elem_nodes)):
    #     xno = XMLNode(Config)
    #     nodes.append(xno.read(elem_nodes[x]))

    return surfaces, maps, materials, nodes

class XMLSurface:
    def __init__(self, Config):
        self._id = 0
        self._source = None
        self._sizePerVertex = 0
        self._inputs = []
        self._formats = []
        self.Config = Config

    def read(self, elem):
        self._id = elem.get("id")
        self._sizePerVertex = elem.get("sizePerVertex")
        self._inputs = elem.get("inputs").split(",")
        self._formats = elem.get("formats").split(",")
        return self

class XMLMap:
    def __init__(self, Config):
        self._id = 0
        self._type = None
        self._channel = 0
        self._source = []
        self._uvOffset = []
        self._uvRepeat = []
        self.Config = Config

    def read(self, elem):
        self._id = elem.get("id")
        self._type = elem.get("type")
        self._channel = elem.get("channel")
        self._source = elem.get("source")
        return self

class XMLMaterial:
    def __init__(self, Config):
        self._id = 0
        self._name = ""
        self._twoSided = True
        self._opacity = 100
        self._diffuse = []
        self._specular = []
        self.Config = Config

    def read(self, elem):
        self._id = elem.get("id")
        self._name = elem.get("name")
        self._twoSided = elem.get("twoSided") == "true"
        self._opacity = elem.get("opacity")
        return self

class XMLMeshNode:
    def __init__(self, Config):
        self._id = 0
        self._name = ""
        self._type = True
        self._surfaces = 100
        self._materials = []
        self._min = []
        self._max = []
        self._center = []
        self._radius = []
        self._transform = []
        self.Config = Config

    def read(self, elem):
        self._id = elem.get("id")
        self._name = elem.get("name")
        self._twoSided = elem.get("twoSided")
        self._opacity = elem.get("opacity")
        return self

class XMLCameraNode:
    def __init__(self, Config):
        self._id = 0
        self._name = ""
        self._type = True
        self._class = 100
        self._fov = []
        self._nearclip = []
        self._farclip = []
        self._active = []
        self._transform = []
        self.Config = Config

    def read(self, elem):
        self._id = elem.get("id")
        self._name = elem.get("name")
        self._twoSided = elem.get("twoSided")
        self._opacity = elem.get("opacity")
        return self

class ZF3DExporterSettings:
    def __init__(self, filePath=""):
        self.filePath = filePath

class ZF3DExporter(bpy.types.Operator):
    bl_idname = "export_scene.zf3d"
    bl_label = "Export ZF3D (Flare3D)"
    bl_description = "Export ZF3D (Flare3D)"
    bl_options = {'REGISTER'}

    filepath: StringProperty(
        name="File Path",
        description="Filepath used for exporting the ZF3D file",
        maxlen=1024,
        default=""
    )

    def execute(self, context):
        filePath = self.filepath
        if not filePath.lower().endswith('.zf3d'):
            filePath += '.zf3d'
        try:
            time1 = time.perf_counter()
            print('Output file : %s' % filePath)
            with open(filePath, 'wb') as file:
                pass
            Config = ZF3DExporterSettings(filePath)
            with open(filePath, 'ab') as file:
                ZF3DExport(file, Config)
            self.report({'INFO'}, ".zf3d export time: %.2f" % (time.perf_counter() - time1))
        except Exception as e:
            print(e)
            self.report({'ERROR'}, str(e))
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

def ZF3DExport(file, Config):
    # Actual export logic would go here
    pass

def menu_func_import(self, context):
    self.layout.operator(ZF3DImporter.bl_idname, text='Flare3D (.zf3d)')

def menu_func_export(self, context):
    zf3d_path = bpy.data.filepath.replace('.blend', '.zf3d')
    op = self.layout.operator(ZF3DExporter.bl_idname, text='Flare3D (.zf3d)')
    op.filepath = zf3d_path

classes = (
    ZF3DImporter,
    ZF3DExporter,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

if __name__ == '__main__':
    register()
