import random

import numpy as np
from panda3d.core import NodePath, PandaNode
from panda3d.core import Point3, Vec3
from panda3d.core import OmniBoundingVolume
from panda3d.core import Shader, ShaderBuffer, GeomEnums


class Vegetation:

    def __init__(self, model_path, model_scale, color_scale=None,
                 fade_out_range=20.0, base_density=0.04, z_min=0.01):
        self.fade_out_range = fade_out_range
        self.base_density = base_density
        self.z_min = z_min

        self.model_path = model_path
        self.model_scale = model_scale
        self.color_scale = color_scale

    def generate(self, parent, heightfield_img):
        positions = self.get_positions(parent, heightfield_img)
        dummy = NodePath(PandaNode("dummy_transform"))
        mat_plants = []

        for pos in positions:
            pos_w = Point3(*pos)
            mat_data = self.transform_plant(dummy, pos_w, Vec3.up())
            mat_plants.append(mat_data)

        self.vegetation(parent, mat_plants)

    def get_positions(self, parent, heightfield_img):
        height_arr = heightfield_img[:, :, 0].astype(np.float32)
        world_z_arr = (height_arr / 255.) * parent.island.top_height
        y_indices, x_indices = np.where(world_z_arr > self.z_min)
        z_coords = world_z_arr[y_indices, x_indices]

        vegetation_positions = np.column_stack((
            x_indices.astype(np.float32),
            y_indices.astype(np.float32),
            z_coords
        ))

        dx = vegetation_positions[:, 0] - parent.town.raw_center.x
        dy = vegetation_positions[:, 1] - parent.town.raw_center.y
        distances = np.sqrt(dx ** 2 + dy ** 2)

        spawn_probability = (distances - parent.town.radius * 1.2) / self.fade_out_range
        spawn_probability = np.clip(spawn_probability, 0.0, 1.0)
        final_probability = spawn_probability * self.base_density

        random_values = np.random.rand(len(vegetation_positions))
        keep_mask = random_values < final_probability

        offset_arr = np.array(list(parent.offset), dtype=np.float32)
        vegetation_positions = vegetation_positions[keep_mask] + offset_arr
        return vegetation_positions

    def vegetation(self, parent, matrices):
        arr_matrices = np.array(matrices, dtype=np.float32)
        raw_buffer_data = arr_matrices.tobytes()
        model = base.loader.load_model(f'models/{self.model_path}')

        if self.color_scale is not None:
            # Set the color to white first, since the color of plant1 didn't change with just set_color_scale.
            model.set_color(1, 1, 1, 1)
            model.set_color_scale(*self.color_scale, 1)

        model.flatten_light()
        # model.reparent_to(base.render)
        model.reparent_to(parent)
        model.set_pos(0, 0, 0)
        model.set_hpr(0, 0, 0)

        # Prevent curling.
        for geom_np in model.find_all_matches("**/+GeomNode"):
            geom_nd = geom_np.node()
            geom_nd.set_bounds(OmniBoundingVolume())
            geom_nd.set_final(True)

        # Set the number of instances.
        instance_cnt = len(matrices)
        model.set_instance_count(instance_cnt)
        # Set shader.
        model.set_shader(Shader.load(Shader.SL_GLSL, vertex='shaders/instancing_v.glsl', fragment='shaders/instancing_f.glsl'))
        model.set_shader_input("instanced_object", ShaderBuffer('DataBuffer', raw_buffer_data, GeomEnums.UH_static))

    def transform_plant(self, dummy_np, pos, normal):
        """Using a dummy NodePath, calculate the plant's translation, rotation,
            and scaling, and store the results in a temporary list.
        """
        dummy_np.set_pos(pos)
        dummy_np.set_scale(self.model_scale)

        if normal.length_squared() > 0.001:
            # If the plant is on a wall, rotate it so that it appears to be growing outward from the wall.
            dummy_np.look_at(pos + normal, Vec3(0, 0, 1))
            dummy_np.set_p(dummy_np, -90)
            dummy_np.set_h(dummy_np, random.uniform(0, 360))
        else:
            # If the plants are located on the rooftop, place it upright.
            dummy_np.set_h(random.uniform(0, 360))

        mat = dummy_np.get_mat()
        # Convert to a flat list.
        mat_data = [mat.get_cell(r, c) for r in range(4) for c in range(4)]
        return mat_data