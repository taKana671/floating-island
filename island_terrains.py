import cv2
from panda3d.bullet import BulletHeightfieldShape, ZUp
from panda3d.bullet import BulletRigidBodyNode
from panda3d.core import GeoMipTerrain
from panda3d.core import NodePath
from panda3d.core import PNMImage
from panda3d.core import Point3, Vec3, Texture
from panda3d.core import SamplerState
from panda3d.core import Shader
from panda3d.core import ShaderTerrainMesh

from texture_generator.heightmap_generator.heightmap_processing import ProcessHeightmapMixin


class IslandTerrainMixin(ProcessHeightmapMixin):

    def generate_texture_from_img(self, img, component_type=Texture.T_unsigned_byte,
                                  format=Texture.F_rgb):
        """Dynamically create a panda3d.core.Texture from a Numpy.ndarray.
            Args:
                img (Numpy.ndarray): Texture image.
                component_type (int): Component type like Texture.T_unsigned_byte
                format (int): Format like Texture.F_rgb

        """
        tex = Texture('image')
        size = img.shape[0]

        tex.setup_2d_texture(
            x_size=size,
            y_size=size,
            component_type=component_type,
            format=format
        )

        tex.set_ram_image(img)
        mem_view = memoryview(tex.modify_ram_image())
        tex.set_ram_image(mem_view)

        return tex


class TerrainGM(NodePath, IslandTerrainMixin):
    """A class that generates terrain using GeoMipTerrain.
        Args:
            name (str): The name of BulletRigidBodyNode
            height (float): Height scale
    """

    def __init__(self, name, height):
        super().__init__(BulletRigidBodyNode(name))
        self.height = height
        self.node().set_mass(0)
        # self.set_collide_mask(BitMask32.bit(1))

    def setup_gm_terrain(self, pnm_heightmap):
        shape = BulletHeightfieldShape(pnm_heightmap, self.height, ZUp)
        shape.set_use_diamond_subdivision(True)
        self.node().add_shape(shape)

        self.terrain = GeoMipTerrain('geomip_terrain')
        self.terrain.set_heightfield(pnm_heightmap)
        self.terrain.set_border_stitching(True)
        self.terrain.set_block_size(8)
        self.terrain.set_min_level(2)
        self.terrain.set_focal_point(base.camera)

        size_x, size_y = pnm_heightmap.get_size()
        x = (size_x - 1) / 2
        y = (size_y - 1) / 2
        pos = Point3(-x, -y, -(self.height / 2))
        scale = Vec3(1, 1, self.height)
        self.root = self.terrain.get_root()
        self.root.set_scale(scale)
        self.root.set_pos(pos)
        self.terrain.generate()

        self.root.reparent_to(self)

    def setup_shader(self, frag_file, tex_heightmap, texmap, textures):
        shader = Shader.load(Shader.SL_GLSL, 'shaders/gmterrain_v.glsl', f'shaders/{frag_file}')
        self.root.set_shader(shader)
        terrain_size = tex_heightmap.get_x_size()

        self.root.set_shader_input("height_scale", self.height)
        self.root.set_shader_input("terrain_size", terrain_size)
        self.root.set_shader_input('tex_heightfield', tex_heightmap)
        self.root.set_shader_input('tex_mask', texmap)

        for tex_name, tex_file in textures.items():
            tex = base.loader.load_texture(f"textures/{tex_file}")
            tex.setMinfilter(SamplerState.FT_linear_mipmap_linear)
            tex.set_anisotropic_degree(16)
            tex.wrap_u = SamplerState.WM_repeat
            tex.wrap_v = SamplerState.WM_repeat
            self.root.set_shader_input(tex_name, tex)


class GMBottomIsland(TerrainGM):
    """A class for generating the terrain of the island at the bottom using GeoMipTerrain.
        Args:
            heightmap_path (str):
                A heightfield image file path.
                The image size must be a power of two plus one.
            textures (dict):
                Use the variable name received by the shader as the key
                and the texture image filename as the value.
            height (float): Height scale; default is 256.
    """

    def __init__(self, heightmap_path, textures, height=256):
        super().__init__('bottom_island', height)
        self.create_terrain(heightmap_path, textures)

    def create_terrain(self, heightmap_path, textures):
        img = cv2.imread(heightmap_path)
        img = cv2.flip(img, 0)

        # Create a texture from a heightfield image.
        tex_heightfield = self.generate_texture_from_img(img)

        # Convert the texture to PNMImage to create GeoMipTerrain.
        pnm_image = PNMImage()
        tex_heightfield.store(pnm_image)
        self.setup_gm_terrain(pnm_image)

        # Create a texture map for the fragment shader and setup shader
        texmap_img = self.create_bw_texture_map(img)
        texmap = self.generate_texture_from_img(texmap_img)
        self.setup_shader('gmterrain_b_f.glsl', tex_heightfield, texmap, textures)


class GMTopIsland(TerrainGM):
    """A class for generating the terrain of the island at the top using GeoMipTerrain.
        Args:
            heightmap_path (str):
                A heightfield image file path.
                The image size must be a power of two plus one.
            textures (dict):
                Use the variable name received by the shader as the key
                and the texture image filename as the value.
            height (float): Height scale; default is 100.
    """

    def __init__(self, heightmap_path, textures, height=100):
        super().__init__('bottom_island', height)
        self.create_terrain(heightmap_path, textures)

    def create_terrain(self, heightmap_path, textures):
        # To create a gentle terrain, reduce only the brightness of the noise.
        img = cv2.imread(heightmap_path)
        heightmap = self.reshape_noise_peak(img, bit8=True)

        # Create a texture from a heightfield image.
        tex_heightfield = self.generate_texture_from_img(img=heightmap)

        # Convert the texture to PNMImage to create GeoMipTerrain.
        pnm_image = PNMImage()
        tex_heightfield.store(pnm_image)
        self.setup_gm_terrain(pnm_image)

        # Create a texture map for the fragment shader and setup shader
        texmap_img = self.create_bw_texture_map(img)
        texmap = self.generate_texture_from_img(texmap_img)
        self.setup_shader('gmterrain_b_f.glsl', tex_heightfield, texmap, textures)


class TerrainSM(NodePath, IslandTerrainMixin):
    """A class that generates terrain using ShaderTerrainMesh
        Args:
            name (str): The name of BulletRigidBodyNode
            height (float): Height scale
    """

    def __init__(self, name, height):
        super().__init__(BulletRigidBodyNode(name))
        self.height = height
        self.node().set_mass(0)
        # self.set_collide_mask(BitMask32.bit(1))

    def setup_terrain_mesh(self, pnm_heightmap, tex_heightmap):
        """Create terrain by using ShaderTerrainMesh.
            Args:
                pnm_heightmap (panda3d.core.PNMImage)
                tex_heightmap (panda3d.core.Texture)
        """
        shape = BulletHeightfieldShape(pnm_heightmap, self.height, ZUp)
        self.node().add_shape(shape)

        terrain_node = ShaderTerrainMesh()
        terrain_node.heightfield = tex_heightmap
        terrain_node.target_triangle_width = 10.0
        terrain_node.generate()

        size_x, size_y = pnm_heightmap.get_size()
        self.terrain = self.attach_new_node(terrain_node)
        self.terrain.set_scale(size_x, size_y, 1)

        offset_x = size_x / 2.0 - 0.5
        offset_y = size_y / 2.0 - 0.5
        self.terrain.set_pos(-offset_x, -offset_y, -self.height / 2.0)

    def setup_shader(self, frag_file, texmap, textures):
        """Setup shader.
            Args:
                frag_file (str): Fragment shader file name.
                texmap (panda3d.core.Texture):
                    A texture map where the flat areas are black and everything else is white.
                textures (dict):
                    Use the variable name received by the shader as the key
                    and the texture image filename as the value.
        """
        terrain_shader = Shader.load(Shader.SL_GLSL, "shaders/smterrain_v.glsl", f"shaders/{frag_file}")
        self.terrain.set_shader(terrain_shader)

        self.terrain.set_shader_input("tex_mask", texmap)
        self.terrain.set_shader_input("terrain_scale", self.height)

        for tex_name, tex_file in textures.items():
            tex = base.loader.load_texture(f"textures/{tex_file}")
            tex.set_minfilter(SamplerState.FT_linear_mipmap_linear)
            tex.set_anisotropic_degree(16)
            tex.wrap_u = SamplerState.WM_repeat
            tex.wrap_v = SamplerState.WM_repeat
            self.terrain.set_shader_input(tex_name, tex)


class SMBottomIsland(TerrainSM):
    """A class for generating the terrain of the island at the top using ShaderTerrainMesh.
        Args:
            heightmap_path (str):
                A heightfield image file path.
                The images must have a depth of 16 bits.
            textures (dict):
                Use the variable name received by the shader as the key
                and the texture image filename as the value.
            height (float): Height scale; default is 256.
    """

    def __init__(self, heightmap_path, textures, height=256):
        super().__init__('bottom_island', height)
        self.create_terrain(heightmap_path, textures)

    def create_terrain(self, heightmap_path, textures):
        img = cv2.imread(heightmap_path, cv2.IMREAD_UNCHANGED)

        # Create a texture from a heightfield image.
        tex_heightfield = self.generate_texture_from_img(
            img=img,
            component_type=Texture.T_unsigned_short,
            format=Texture.F_red
        )
        # Convert the texture to PNMImage to create GeoMipTerrain.
        pnm_image = PNMImage()
        tex_heightfield.store(pnm_image)
        self.setup_terrain_mesh(pnm_image, tex_heightfield)

        # Create a texture map for the fragment shader and setup shader.
        texmap_img = self.create_bw_texture_map(img)
        texmap = self.generate_texture_from_img(texmap_img)
        self.setup_shader('smterrain_b_f.glsl', texmap, textures)


class SMTopIsland(TerrainSM):
    """A class for generating the terrain of the island at the top using ShaderTerrainMesh.
        Args:
            heightmap_path (str):
                A heightfield image file path.
                The image must have a depth of 16 bits.
            textures (dict):
                Use the variable name received by the shader as the key
                and the texture image filename as the value.
            height (float): Height scale; default is 100.
    """

    def __init__(self, heightmap_path, textures, height=100):
        super().__init__('bottom_island', height)
        self.create_terrain(heightmap_path, textures)

    def create_terrain(self, heightmap_path, textures):
        # To create a gentle terrain, reduce only the brightness of the noise.
        img = cv2.imread(heightmap_path, cv2.IMREAD_UNCHANGED)
        heightmap = self.reshape_noise_peak(img, bit8=False)

        # Create a texture from a heightfield image.
        tex_heightfield = self.generate_texture_from_img(
            img=heightmap,
            component_type=Texture.T_unsigned_short,
            format=Texture.F_red
        )
        # Convert the texture to PNMImage to create GeoMipTerrain.
        pnm_image = PNMImage()
        tex_heightfield.store(pnm_image)
        self.setup_terrain_mesh(pnm_image, tex_heightfield)

        # Create a texture map for the fragment shader and setup shader
        texmap_img = self.create_bw_texture_map(img)
        texmap = self.generate_texture_from_img(texmap_img)
        self.setup_shader('smterrain_b_f.glsl', texmap, textures)