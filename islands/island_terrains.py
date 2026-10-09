from enum import StrEnum

import cv2
from panda3d.bullet import BulletHeightfieldShape, ZUp
from panda3d.bullet import BulletRigidBodyNode
from panda3d.core import GeoMipTerrain
from panda3d.core import NodePath, PandaNode
from panda3d.core import PNMImage
from panda3d.core import Point3, Vec3, Texture
from panda3d.core import SamplerState, TransformState
from panda3d.core import Shader
from panda3d.core import ShaderTerrainMesh

from texture_generator.heightmap_generator.heightmap_processing import ProcessHeightmapMixin


class ImageAssets(StrEnum):

    # to_dictではなく、テクスチャをロードする関数を組む。
    # 小文字のname属性を持たせる？GeomipでもShaderTerrainでも使う。

    @classmethod
    def to_dict(cls):
        return {mem.name.lower(): f'textures/{mem.value}' for mem in cls}


class TopIslandTextures(ImageAssets):

    TEX_GROUND = 'grass_01.jpg'
    TEX_ROCK1 = 'ground_01.jpg'
    TEX_ROCK2 = 'tex_moss.png'
    TEX_ROCK3 = "P1050384a.jpg"


class BottomIslandTextures(ImageAssets):

    TEX_GROUND = 'grass_01.jpg'
    TEX_ROCK1 = 'tex_stone.png'
    TEX_ROCK2 = "tex_rock.png"
    TEX_ROCK3 = "tex_cracked.png"


class GeoMipIsland:
    """A class for creating floating island

        Args:
            parent (panda3d.core.NodePath): BulletRigidBodyNode
            heightfield_img (numpy.ndarray):
                A resolution of 2 to the power of 2 + 1 is desirable.
                On this floating island, the height and width of the image must be equal.
            top_height (float): Top island height.
            bottom_height (float): Bottom island height.
    """

    def __init__(self, parent, heightfield_img, top_height, bottom_height):
        self.size = heightfield_img.shape[0] - 1
        self.btm_island = self.generate_bottom_island(parent, heightfield_img, bottom_height)
        self.top_island = self.generate_top_island(parent, heightfield_img, top_height)

    @property
    def top_height(self):
        return self.top_island.height

    @property
    def bottom_height(self):
        return self.btm_island.height

    @property
    def img_size(self):
        return self.top_island.img_w

    def generate_bottom_island(self, parent, heightfield_img, bottom_height):
        textures = BottomIslandTextures.to_dict()
        btm_island = GMBottomIsland(parent, heightfield_img, textures, bottom_height)
        return btm_island

    def generate_top_island(self, parent, heightfield_img, top_height):
        textures = TopIslandTextures.to_dict()
        top_island = GMTopIsland(parent, heightfield_img, textures, top_height)
        return top_island


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
            z_scale (float): Height scale
            xy_scale (float): Scale of width and depth
    """

    def __init__(self, name, z_scale, xy_scale=1):
        super().__init__(PandaNode(name))
        self.height = z_scale
        self.xy_scale = xy_scale
        self.img_w = 0
        self.img_h = 0

    def setup_gm_terrain(self, pnm_heightmap):
        self.terrain = GeoMipTerrain('geomip_terrain')
        self.terrain.set_heightfield(pnm_heightmap)
        self.terrain.set_border_stitching(True)
        self.terrain.set_block_size(8)
        self.terrain.set_min_level(2)
        self.terrain.set_focal_point(base.camera)

        self.img_w, self.img_h = pnm_heightmap.get_size()

        x = (self.img_w - 1) / 2
        y = (self.img_h - 1) / 2
        pos = Point3(-x, -y, -(self.height / 2))
        scale = Vec3(self.xy_scale, self.xy_scale, self.height)
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
            tex = base.loader.load_texture(tex_file)
            tex.setMinfilter(SamplerState.FT_linear_mipmap_linear)
            tex.set_anisotropic_degree(16)
            tex.wrap_u = SamplerState.WM_repeat
            tex.wrap_v = SamplerState.WM_repeat
            self.root.set_shader_input(tex_name, tex)

    def add_to_bodynode(self, body_node, pnm_img, pos, hpr):
        shape = BulletHeightfieldShape(pnm_img, self.height, ZUp)
        shape.set_use_diamond_subdivision(True)
        body_node.node().add_shape(shape, TransformState.make_pos_hpr(pos, hpr))
        self.set_pos_hpr(pos, hpr)
        self.reparent_to(body_node)

    def get_terrain_z(self, world_x, world_y):
        """Convert world coordinates to pixel coordinates.
        """
        scale_x = (self.img_w - 1) * self.xy_scale
        scale_y = (self.img_h - 1) * self.xy_scale

        pixel_x = (world_x / scale_x) * (self.img_w - 1)
        pixel_y = (world_y / scale_y) * (self.img_h - 1)

        normalized_z = self.terrain.get_elevation(pixel_x, pixel_y)
        return normalized_z * self.height


class GMBottomIsland(TerrainGM):
    """A class for generating the terrain of the island at the bottom using GeoMipTerrain.
        Args:
            height (float): Height scale.
            xy_scale (float): Scale of width and depth
    """

    def __init__(self, parent, heighfield_img, textures, z_scale, xy_scale=1):
        super().__init__('bottom_island', z_scale, xy_scale)
        self.create_terrain(parent, heighfield_img, textures)

    def create_terrain(self, parent, heighfield_img, textures):
        flipped_img = cv2.flip(heighfield_img, 0)

        # Create a texture from a heightfield image.
        tex_heightfield = self.generate_texture_from_img(flipped_img)

        # Convert the texture to PNMImage
        pnm_img = PNMImage()
        tex_heightfield.store(pnm_img)
        self.setup_gm_terrain(pnm_img)

        # Create a texture map for the fragment shader and setup shader
        texmap_img = self.create_bw_texture_map(flipped_img)
        texmap = self.generate_texture_from_img(texmap_img)
        self.setup_shader('gmterrain_b_f.glsl', tex_heightfield, texmap, textures)

        pos = Point3(0, 0, -self.height / 2)
        hpr = Vec3(0, 180, 0)
        self.add_to_bodynode(parent, pnm_img, pos, hpr)


class GMTopIsland(TerrainGM):
    """A class for generating the terrain of the island at the top using GeoMipTerrain.
        Args:
            height (float): Height scale.
            xy_scale (float): Scale of width and depth
    """

    def __init__(self, parent, heighfield_img, textures, z_scale, xy_scale=1):
        super().__init__('top_island', z_scale, xy_scale)
        self.create_terrain(parent, heighfield_img, textures)

    def create_terrain(self, parent, heightfield_img, textures):
        # To create a gentle terrain, reduce only the brightness of the noise.
        reshaped_img = self.reshape_noise_peak(heightfield_img, bit8=True)

        # Create a texture from a heightfield image.
        tex_heightfield = self.generate_texture_from_img(reshaped_img)

        # Convert the texture to PNMImage.
        pnm_img = PNMImage()
        tex_heightfield.store(pnm_img)
        self.setup_gm_terrain(pnm_img)

        # Create a texture map for the fragment shader and setup shader
        texmap_img = self.create_bw_texture_map(heightfield_img)
        texmap = self.generate_texture_from_img(texmap_img)
        self.setup_shader('gmterrain_b_f.glsl', tex_heightfield, texmap, textures)

        pos = Point3(0, 0, self.height / 2)
        hpr = Vec3(0, 0, 0)
        self.add_to_bodynode(parent, pnm_img, pos, hpr)


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
        img = cv2.flip(img, 0)

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
        super().__init__('top_island', height)
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