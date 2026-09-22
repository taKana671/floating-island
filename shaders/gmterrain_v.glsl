#version 430

in vec4 p3d_Vertex;
in vec2 p3d_MultiTexCoord0;

uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelMatrix;

out vec2 terrain_uv;
out vec3 vtx_pos;

void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    
    // world coordinates
    vtx_pos = (p3d_ModelMatrix * p3d_Vertex).xyz;
    
    // uv coordinates
    terrain_uv = p3d_MultiTexCoord0;
}
