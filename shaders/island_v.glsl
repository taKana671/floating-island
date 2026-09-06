#version 430

in vec4 p3d_Vertex;
in vec3 p3d_Normal;

uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelMatrix;
uniform mat3 p3d_NormalMatrix;

// A structure automatically allocated internally by the ShaderTerrainMesh system
uniform struct {
    sampler2D data_texture;
    sampler2D heightfield;
    int view_index;
    int terrain_size;
    int chunk_size;
} ShaderTerrainMesh;

uniform sampler2D alphamap;
uniform float terrain_scale;

out vec2 terrain_uv;
out vec3 vtx_pos;
out vec3 vtx_normal;

void main() {
    // Terrain data has the layout:
    // x: x-pos, y: y-pos, z: size, w: clod
    vec4 terrain_data = texelFetch(ShaderTerrainMesh.data_texture,
    ivec2(gl_InstanceID, ShaderTerrainMesh.view_index), 0);

    // Get initial chunk position in the (0, 0, 0), (1, 1, 0) range
    vec3 chunk_position = p3d_Vertex.xyz;

    // CLOD implementation
    float clod_factor = smoothstep(0.0, 1.0, terrain_data.w);
    chunk_position.xy -= clod_factor * fract(chunk_position.xy * float(ShaderTerrainMesh.chunk_size) / 2.0)
                            * 2.0 / float(ShaderTerrainMesh.chunk_size);

    // Scale the chunk
    chunk_position *= terrain_data.z * float(ShaderTerrainMesh.chunk_size)
                    / float(ShaderTerrainMesh.terrain_size);
    chunk_position.z *= float(ShaderTerrainMesh.chunk_size);

    // Offset the chunk, it is important that this happens after the scale
    chunk_position.xy += terrain_data.xy / float(ShaderTerrainMesh.terrain_size);

    // Compute the terrain UV coordinates
    terrain_uv = chunk_position.xy;

    // ##########################################
  
    // Sample heights from the height map and add them to the Z-axis
    float raw_height = texture(ShaderTerrainMesh.heightfield, terrain_uv).x;
    float mask_alpha = texture(alphamap, terrain_uv).a;
    float is_land = step(0.01, mask_alpha);

    float finalheight = raw_height * terrain_scale * is_land;
    chunk_position.z += finalheight;

    // Calculating Slope Normals from a Height Map.
    float texel_size = 1.0 / float(ShaderTerrainMesh.terrain_size);

    // Check the heights to the right (X+) and above (Y+) of the current location.
    float h_right = texture(ShaderTerrainMesh.heightfield, terrain_uv + vec2(texel_size, 0.0)).x * terrain_scale * is_land;
    float h_up = texture(ShaderTerrainMesh.heightfield, terrain_uv + vec2(0.0, texel_size)).x * terrain_scale * is_land;

    // Calculate the tilt vector.
    vec3 tangent_x = vec3(1.0, 0.0, h_right - finalheight);
    vec3 tangent_y = vec3(0.0, 1.0, h_up - finalheight);
    
    // Use the cross product to determine the vector perpendicular to the slope (the normal vector).
    vec3 calculated_normal = normalize(cross(tangent_x, tangent_y));

    // ##########################################

    // Convert to screen coordinates.
    gl_Position = p3d_ModelViewProjectionMatrix * vec4(chunk_position, 1.0);

    // // Output the vertex world space position - in this case we use this to render the fog.
    vtx_pos = (p3d_ModelMatrix * vec4(chunk_position, 1.0)).xyz;
    
    // Convert normals to world space.
    vtx_normal = normalize(mat3(p3d_ModelMatrix) * calculated_normal);

}
