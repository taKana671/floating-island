#version 430

uniform sampler2D tex_ground;
uniform sampler2D tex_rock1;
uniform sampler2D tex_rock2;
uniform sampler2D tex_rock3;
uniform sampler2D tex_heightfield;
uniform sampler2D tex_mask;

in vec2 terrain_uv;
in vec3 vtx_pos;

out vec4 p3d_FragColor;

// Three-Dimensional Mapping
vec4 getTriplanarBlend(sampler2D tex, vec3 pos, vec3 normal) {
    float repeat_count = 2.0; 
    vec3 uv_pos = pos * (repeat_count / 256.0); 

    // Sampling from three directions (XY plane, XZ plane, YZ plane)
    vec4 col_x = texture(tex, uv_pos.zy);
    vec4 col_y = texture(tex, uv_pos.zx);
    vec4 col_z = texture(tex, uv_pos.xy);

    // Calculate the weight that determines which texture to strongly use based on the slope's angle (normal).
    vec3 blend_weights = pow(abs(normal), vec3(4.0));
    blend_weights = max(blend_weights, 0.00001);
    blend_weights /= (blend_weights.x + blend_weights.y + blend_weights.z);

    return col_x * blend_weights.x + col_y * blend_weights.y + col_z * blend_weights.z;
}

void main() {
    float h = texture(tex_heightfield, terrain_uv).r;
    float mask = texture(tex_mask, terrain_uv).r;

    if (mask == 0.0) {
        discard;
        return;
    }

    // Calculate normal.
    vec3 calculated_normal = normalize(cross(dFdx(vtx_pos), dFdy(vtx_pos)));

    vec4 color_ground = getTriplanarBlend(tex_ground, vtx_pos, calculated_normal);
    vec4 color_rock1  = getTriplanarBlend(tex_rock1,  vtx_pos, calculated_normal);
    vec4 color_rock2  = getTriplanarBlend(tex_rock2,  vtx_pos, calculated_normal);
    vec4 color_rock3  = getTriplanarBlend(tex_rock3,  vtx_pos, calculated_normal);
    
    // If the height h of the heightmap exceeds 0.003, rock1 begins to appear;
    // when it reaches 0.06 or higher, the entire area consists solely of rock1.
    float blend_ground_rock1 = smoothstep(0.003, 0.06, h);
    float blend_rock1_rock2  = smoothstep(0.04,  0.16, h);
    float blend_rock2_rock3  = smoothstep(0.13,  0.27, h);

    vec4 final_color = color_ground;
    final_color = mix(final_color, color_rock1, blend_ground_rock1);
    final_color = mix(final_color, color_rock2, blend_rock1_rock2);
    final_color = mix(final_color, color_rock3, blend_rock2_rock3);

    p3d_FragColor = vec4(final_color.rgb, 1.0);
}
