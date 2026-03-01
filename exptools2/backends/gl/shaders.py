"""GLSL shader sources for core psychophysics primitives."""

GABOR_VERTEX_SHADER = """
#version 330 core
layout(location = 0) in vec2 in_pos;
layout(location = 1) in vec2 in_uv;
out vec2 v_uv;
uniform vec2 u_center;
uniform vec2 u_size;
void main() {
    vec2 pos = in_pos * u_size + u_center;
    gl_Position = vec4(pos, 0.0, 1.0);
    v_uv = in_uv;
}
"""

IMAGE_VERTEX_SHADER = """
#version 330 core
layout(location = 0) in vec2 in_pos;
layout(location = 1) in vec2 in_uv;
out vec2 v_uv;
uniform vec2 u_center;
uniform vec2 u_size;
uniform float u_rotation_deg;
void main() {
    float t = radians(u_rotation_deg);
    mat2 r = mat2(cos(t), -sin(t), sin(t), cos(t));
    vec2 pos = r * (in_pos * u_size) + u_center;
    gl_Position = vec4(pos, 0.0, 1.0);
    v_uv = in_uv;
}
"""

GABOR_FRAGMENT_SHADER = """
#version 330 core
in vec2 v_uv;
out vec4 fragColor;
uniform float u_phase;
uniform float u_spatial_freq;
uniform float u_sigma;
uniform float u_orientation_deg;
uniform float u_contrast;
uniform vec3 u_color;

void main() {
    vec2 centered = v_uv * 2.0 - 1.0;
    float theta = radians(u_orientation_deg);
    float x = centered.x * cos(theta) + centered.y * sin(theta);
    float grating = sin(2.0 * 3.14159265 * u_spatial_freq * x + u_phase);
    float gauss = exp(-dot(centered, centered) / max(1e-6, (2.0 * u_sigma * u_sigma)));
    float value = grating * gauss * u_contrast;
    vec3 rgb = 0.5 + 0.5 * value * u_color;
    fragColor = vec4(rgb, gauss);
}
"""

SDF_FRAGMENT_SHADER = """
#version 330 core
in vec2 v_uv;
out vec4 fragColor;
uniform vec4 u_color;
uniform float u_radius;
uniform float u_stroke;
uniform int u_shape_mode;
uniform int u_draw_mode;
uniform float u_line_width;

void main() {
    vec2 centered = v_uv * 2.0 - 1.0;
    float dist;
    if (u_shape_mode == 1) {
        vec2 d = abs(centered) - vec2(u_radius);
        dist = max(d.x, d.y);
    } else {
        dist = length(centered) - u_radius;
    }
    float alpha;
    if (u_draw_mode == 1) {
        float edge = abs(dist) - max(u_line_width * 0.5, 1e-6);
        alpha = 1.0 - smoothstep(-u_stroke, u_stroke, edge);
    } else {
        alpha = 1.0 - smoothstep(-u_stroke, u_stroke, dist);
    }
    fragColor = vec4(u_color.rgb, u_color.a * alpha);
}
"""

LINE_VERTEX_SHADER = """
#version 330 core
layout(location = 0) in vec2 in_pos;
void main() {
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
"""

LINE_FRAGMENT_SHADER = """
#version 330 core
out vec4 fragColor;
uniform vec4 u_color;
void main() {
    fragColor = u_color;
}
"""

IMAGE_FRAGMENT_SHADER = """
#version 330 core
in vec2 v_uv;
out vec4 fragColor;
uniform sampler2D u_tex;
uniform float u_opacity;
uniform vec4 u_tint;
uniform int u_flip_y;
void main() {
    vec2 uv = (u_flip_y == 1) ? vec2(v_uv.x, 1.0 - v_uv.y) : v_uv;
    vec4 tex = texture(u_tex, uv);
    fragColor = vec4(tex.rgb * u_tint.rgb, tex.a * u_tint.a * u_opacity);
}
"""

BAR_TEXTURE_FRAGMENT_SHADER = """
#version 330 core
in vec2 v_uv;
out vec4 fragColor;
uniform sampler2D u_tex;
uniform vec2 u_bar_center;
uniform vec2 u_bar_size;
uniform float u_bar_orientation_deg;
uniform float u_aperture_radius;
uniform float u_opacity;
uniform int u_flip_y;
uniform vec4 u_tint;
uniform float u_square_x_scale;

void main() {
    vec2 ndc = v_uv * 2.0 - 1.0;

    // Restrict drawing to a square stimulus area centered on screen.
    if (abs(ndc.x) > u_square_x_scale || abs(ndc.y) > 1.0) {
        fragColor = vec4(0.0);
        return;
    }

    vec2 p = vec2(ndc.x / u_square_x_scale, ndc.y); // square stimulus coordinates
    if (length(p) > u_aperture_radius) {
        fragColor = vec4(0.0);
        return;
    }

    float theta = radians(u_bar_orientation_deg);
    mat2 rot_neg = mat2(cos(theta), sin(theta), -sin(theta), cos(theta));
    vec2 q = rot_neg * (p - u_bar_center);

    if (abs(q.x) > (u_bar_size.x * 0.5) || abs(q.y) > (u_bar_size.y * 0.5)) {
        fragColor = vec4(0.0);
        return;
    }

    vec2 uv = (u_flip_y == 1) ? vec2((p.x + 1.0) * 0.5, 1.0 - ((p.y + 1.0) * 0.5))
                              : vec2((p.x + 1.0) * 0.5, (p.y + 1.0) * 0.5);
    vec4 tex = texture(u_tex, uv);
    fragColor = vec4(tex.rgb * u_tint.rgb, tex.a * u_tint.a * u_opacity);
}
"""

VIDEO_YUV_FRAGMENT_SHADER = """
#version 330 core
in vec2 v_uv;
out vec4 fragColor;
uniform sampler2D texY;
uniform sampler2D texU;
uniform sampler2D texV;

void main() {
    float y = texture(texY, v_uv).r;
    float u = texture(texU, v_uv).r - 0.5;
    float v = texture(texV, v_uv).r - 0.5;
    vec3 rgb;
    rgb.r = y + 1.402 * v;
    rgb.g = y - 0.344136 * u - 0.714136 * v;
    rgb.b = y + 1.772 * u;
    fragColor = vec4(rgb, 1.0);
}
"""
