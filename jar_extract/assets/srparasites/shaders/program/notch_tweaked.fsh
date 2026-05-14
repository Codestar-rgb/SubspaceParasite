#version 120

uniform sampler2D DiffuseSampler;
varying vec2 texCoord;

uniform vec2 InSize;
uniform float SRP_Time; // time

float saturate(float x) { return clamp(x, 0.0, 1.0); }

float hash1(float x) {
    return fract(sin(x * 127.1) * 43758.5453123);
}

float hash2(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

float smoothNoise1(float x) {
    float i = floor(x);
    float f = fract(x);
    f = f * f * (3.0 - 2.0 * f);
    return mix(hash1(i), hash1(i + 1.0), f);
}

void main() {
    vec2 baseUV = texCoord;
    float t = SRP_Time;

    // edge mask
    vec2 p = baseUV * 2.0 - 1.0;
    float r = length(p);

    // edge falloff
    float edge = smoothstep(0.35, 1.05, r);
    edge = edge * edge;

    // corner boost
    float cornerBoost = smoothstep(0.85, 1.25, r);
    edge = saturate(edge + cornerBoost * 0.25);

    // near bias
    float nearMask = smoothstep(0.05, 0.95, 1.0 - baseUV.y);
    nearMask = mix(0.55, 1.0, nearMask);

    // center lock
    float centerStable = 1.0 - edge;

    // final mask
    float mask = edge;

    // streak cols
    float colA = smoothNoise1(baseUV.x * 10.0);
    float colB = smoothNoise1(baseUV.x * 22.0 + 7.3);

    // streak shape
    float streak = saturate(colA * 0.70 + colB * 0.60);
    streak = streak * streak * streak;

    // waves
    float wave1 = sin(t * 1.37 + baseUV.x * 4.0);
    float wave2 = sin(t * 0.83 + baseUV.x * 9.0 + baseUV.y * 2.0);
    float wave3 = sin(t * 1.91 + baseUV.x * 2.0);

    // anim mix
    float anim = (wave1 * 0.45 + wave2 * 0.35 + wave3 * 0.20);
    anim = anim * 0.5 + 0.5;

    // flutter
    float flutter = (sin(t * 2.17 + hash2(baseUV * 50.0) * 6.2831853) * 0.5 + 0.5);

    // pull base
    float basePull = 0.06;
    float pull = (basePull + streak * 0.32) * mask;

    // breathe
    pull *= (0.75 + 0.25 * anim);
    pull *= (0.90 + 0.10 * flutter);

    // warp uv
    vec2 uvWarped = baseUV;

    // side tear
    float side = sin(t * 1.11 + baseUV.y * 8.0) * 0.010;
    uvWarped.x += side * mask * (0.30 + 0.70 * streak);

    // lens warp
    float lens = sin(t * 0.65 + r * 6.0) * 0.006;
    uvWarped += normalize(p + 1e-4) * lens * edge;

    // y pull
    uvWarped.y = clamp(baseUV.y - pull, 0.0, 1.0);
    uvWarped = clamp(uvWarped, 0.0, 1.0);

    // quantize
    vec2 q = InSize * 10.0;
    vec2 uvQuant = floor(uvWarped * q) / q;

    // stabilize
    float stabilize = (0.012 + streak * 0.020) * mask;
    stabilize *= (1.0 - centerStable * 0.85);

    // final uv
    vec2 uv = mix(uvWarped, uvQuant, saturate(stabilize));

    vec4 scene = texture2D(DiffuseSampler, uv);

    // crease
    float crease = streak * mask;
    vec3 outRgb = scene.rgb * (1.0 - crease * 0.09);

    gl_FragColor = vec4(outRgb, 1.0);
}
