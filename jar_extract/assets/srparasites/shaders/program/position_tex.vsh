#version 120
attribute vec3 Position;
attribute vec2 UV;
varying   vec2 texCoord;
uniform   mat4 ProjMat;
void main() {
    gl_Position = ProjMat * vec4(Position, 1.0);
    texCoord = UV;
}
