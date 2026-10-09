import random

import numpy as np
from panda3d.bullet import BulletConvexHullShape, BulletCylinderShape, ZUp
from panda3d.core import Point3, Vec3, TransformState
from panda3d.core import TextureStage

from shapes import RandomPolygonalPrism
from texture_generator.heightmap_generator.heightmap_processing import ProcessHeightmapMixin
from voronoi_generator.voronoi_2d import Polygon2DMixin
from voronoi_generator.voronoi_2d import VoronoiSitesGenerator, RoundedVoronoiGenerator


class Building(Polygon2DMixin):

    def __init__(self, building_id, foundation_h=18, wall_h=15, belt_h=2):
        self.building_id = building_id
        self.foundation_h = foundation_h
        self.wall_h = wall_h
        self.belt_h = belt_h

    def calc_tex_scale(self, total_length, distance):
        """Calculate texture scale.
            Args:
                total_length (float): Total distance
                distance (float):
                    Specify the distance in 3D space at which the texture repeats once (one cycle).
        """
        repeats = total_length / distance

        if (s := round(repeats)) < 1:
            s = 1

        return s

    def assemble(self, parent, model, pos, name):
        shape = BulletConvexHullShape()
        shape.add_geom(model.node().get_geom(0))

        parent.node().add_shape(shape, TransformState.make_pos(pos))
        model.set_pos(pos)
        model.set_name(f'{name}_{self.building_id}')
        model.reparent_to(parent)

    def generate(self, parent, vertices, textures):
        # Determine the value of segs_top_cap based on the vertex farthest from the center.
        _, max_distance = self.get_max_distance_from_center(vertices)
        segs_cap = 3 if max_distance <= 2 else int(max_distance / 2)

        wall_creator = RandomPolygonalPrism(list(vertices), segs_top_cap=0, segs_bottom_cap=0)
        belt_creator = RandomPolygonalPrism(list(vertices * 1.02), height=self.belt_h, segs_top_cap=0, segs_bottom_cap=segs_cap)

        foundation_pos = Point3(*wall_creator.center) + parent.offset
        self.create_foundation(parent, foundation_pos, wall_creator, textures)

        wall_pos = foundation_pos + Vec3(0, 0, self.foundation_h)
        self.create_wall(parent, wall_pos, wall_creator, belt_creator, textures)

    def create_foundation(self, parent, pos, wall_creator, textures):
        """Create building foundation.
        """
        # create_model.
        wall_creator.height = self.foundation_h
        model = wall_creator.create()

        # set texture.
        su = self.calc_tex_scale(wall_creator.edge_length, 25)
        sv = self.calc_tex_scale(self.foundation_h, 25)
        tex = textures['foundation']
        model.set_tex_scale(TextureStage.get_default(), (su, sv))
        model.set_texture(tex)

        self.assemble(parent, model, pos, name="foundtion")

    def create_wall(self, parent, pos, wall_creator, belt_creator, textures):
        """Create building wall.
        """
        tex_belt = textures['belt']
        tex_walls = textures['walls']

        wall_creator.height = self.wall_h
        wall_creator.segs_a = int(self.wall_h / 2)

        for i, tex_wall in enumerate(tex_walls):
            # create wall.
            wall = wall_creator.create()
            su = self.calc_tex_scale(wall_creator.edge_length, 20)
            wall.set_tex_scale(TextureStage.get_default(), (su, 1))
            wall.set_texture(tex_wall)
            self.assemble(parent, wall, pos, f'wall{i}')
            pos.z += wall_creator.height

            # Create belt between walls.
            belt = belt_creator.create()
            belt.set_texture(tex_belt)
            self.assemble(parent, belt, pos, f'belt{i}')
            pos.z += belt_creator.height


class Tree:

    def __init__(self, file_path, scale):
        self.file_path = file_path
        self.scale = scale  # Vec3(3)

    def generate(self, parent, vertices):
        model = base.loader.load_model(f'models/{self.file_path}')

        for vert in vertices:
            hpr = Vec3(random.uniform(0, 360), 0, 0)
            raw_pos = Point3(*vert, 0) * parent.island.size

            if (z := parent.island.top_island.get_terrain_z(raw_pos.x, raw_pos.y) - 3) >= 0:
                tree = model.copy_to(parent)
                tree_pos = Point3(raw_pos.xy, z) + parent.offset
                tree.set_pos_hpr_scale(tree_pos, hpr, self.scale)

                end, tip = tree.get_tight_bounds()
                size = tip - end
                shape_offset = Vec3(0, 0, size.z / 2.0 - 1)

                shape = BulletCylinderShape(2.0, size.z, ZUp)
                parent.node().add_shape(shape, TransformState.make_pos(
                    tree_pos + shape_offset))


class Town(Polygon2DMixin, ProcessHeightmapMixin):

    def __init__(self, tree, town_area_vertices=10, building_max_stories=4,
                 tree_num=20, tree_circle_rad=1.05):
        self.tree = tree
        self.town_verts = town_area_vertices
        self.max_stories = building_max_stories
        self.tree_num = tree_num
        self.tree_circle_rad = tree_circle_rad
        self.raw_center = None
        self.town_radius = None
        self.create_textures()

    def create_textures(self):
        self.tex_brick = self.load_tex('brick_04.jpg')
        self.tex_stone = self.load_tex('concrete_09.jpg')
        self.tex_walls = [
            self.load_tex('wall_window1.png'),  # most decorative
            self.load_tex('wall_window2.png'),  # a little decorative
            self.load_tex('wall_window3.png'),  # square
        ]

    def load_tex(self, file_name):
        return base.loader.load_texture(f'textures/{file_name}')

    def generate(self, parent, heightfield_img):
        center, radius, vertices = self.find_convex_polygon_in_irregular_region(
            heightfield_img, vertex_cnt=self.town_verts)

        self.raw_center = Point3(*center, 0)
        self.radius = radius

        region = np.array(vertices, dtype=np.float64) / parent.island.img_size
        sites = np.array([pt for pt in VoronoiSitesGenerator(region)])

        # Generate vertex coordinates of a rounded-corner Voronoi cell.
        for i, pts in enumerate(RoundedVoronoiGenerator(
                pts=sites, bnd=region, segment_length=0.0029)):

            if len(pts) == 0:
                continue

            polygon = np.insert(pts, pts.shape[1], 0, axis=1)
            sorted_pts = self.sort_counter_clockwise(polygon)
            self.create_building(parent, sorted_pts, i)

        self.plant_trees(parent, heightfield_img)

    def plant_trees(self, parent, heightfield_img):
        _, _, region = self.find_convex_polygon_in_irregular_region(
            heightfield_img, vertex_cnt=self.tree_num, within=self.tree_circle_rad)
        region = np.array(region, dtype=np.float64) / parent.island.img_size

        self.tree.generate(parent, region)

    def create_building(self, parent, sorted_pts, serial):
        stories = random.randint(1, self.max_stories)
        tex_wall = self.tex_walls[:1] * stories if stories <= 2 \
            else [self.tex_walls[1]] * (stories - 1) + [self.tex_walls[2]]

        textures = {
            'foundation': self.tex_brick,
            'belt': self.tex_stone,
            'walls': tex_wall
        }

        building = Building(serial)
        scaled_pts = sorted_pts * parent.island.size
        building.generate(parent, scaled_pts, textures)
