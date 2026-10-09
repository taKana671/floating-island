import cv2
from panda3d.bullet import BulletRigidBodyNode
from panda3d.core import NodePath, PandaNode
from panda3d.core import Vec3, LColor
from panda3d.core import BitMask32

from islands.island_terrains import GeoMipIsland
from islands.vegetation import Vegetation
from islands.town_builder import Town, Tree


class FloatingIsland(NodePath):

    def __init__(self, name, heightfield_path, scale=256, top_height=50, bottom_height=256):
        super().__init__(BulletRigidBodyNode(name))
        self.heightfield_path = heightfield_path
        self.top_height = top_height
        self.bottom_height = bottom_height
        self.scale = scale
        self.node().set_mass(0)
        self.set_collide_mask(BitMask32.bit(1))

    def create_floating_city(self):
        heightfield_img = cv2.imread(self.heightfield_path)
        self.island = GeoMipIsland(self, heightfield_img, self.top_height, self.bottom_height)
        self.offset = Vec3(-self.island.size / 2, -self.island.size / 2, 0)

        self.town = Town(
            tree=Tree(file_path='firtree/tree1.bam', scale=Vec3(3))
        )
        self.town.generate(self, heightfield_img)

        vegetation = Vegetation(
            model_path="plants1/plants1.egg",
            model_scale=Vec3(0.3),
            color_scale=LColor(1.2, 1.8, 1.4, 1.0),
        )
        vegetation.generate(self, heightfield_img)


class Scene(NodePath):

    def __init__(self):
        super().__init__(PandaNode('scene'))
        # heigtfield_path = 'images_8bit/island_heightmap_20260922121842.png'        
        heigtfield_path = 'images_8bit/island_heightmap_20260922121858.png'
        # self.build_town(heigtfield_path)
        # # self.buildings_root.set_pos(Point3(0, 0, 256 / 2 + 5))
        # self.buildings_root.set_pos(Point3(0, 0, 0))

        island = FloatingIsland('island', heigtfield_path)
        island.create_floating_city()
        island.reparent_to(base.render)
        base.world.attach(island.node())

        # island.set_pos(-50, -50, -50)